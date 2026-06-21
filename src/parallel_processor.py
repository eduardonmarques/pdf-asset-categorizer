"""
Pipeline de dois estágios com ProcessPoolExecutor:

Fase 1 — Digital (workers rápidos):
  Tenta extração de texto via pdfplumber em paralelo.
  PDFs com texto suficiente → asset detection imediata.
  PDFs escaneados → fila para Fase 2.

Fase 2 — OCR (workers lentos, limitados por memória):
  Roda Tesseract em paralelo apenas nos PDFs que precisam.

As funções de worker devem ficar no nível de módulo (requisito do
multiprocessing "spawn" do Windows com ProcessPoolExecutor).
"""

import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

# Raiz do projeto — adicionada ao sys.path dos subprocessos (spawn no Windows)
_PROJECT_ROOT = str(Path(__file__).parent.parent)


def _worker_init(project_root: str) -> None:
    """Inicializador dos subprocessos: garante que o pacote src seja importável."""
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


# ---------------------------------------------------------------------------
# Funções de worker (executadas em subprocessos)
# ---------------------------------------------------------------------------

def _digital_worker(args: tuple) -> tuple[str, list[str], bool]:
    """
    Extrai texto digital de um PDF e detecta ativos.
    Retorna (path_str, sorted_assets, needs_ocr).
    """
    pdf_path_str, asset_pattern, min_text_length = args
    from src.pdf_processor import _extract_text_digital
    from src.asset_detector import find_assets

    text = _extract_text_digital(pdf_path_str)
    needs_ocr = len(text.strip()) < min_text_length
    assets = [] if needs_ocr else sorted(find_assets(text, asset_pattern))
    return pdf_path_str, assets, needs_ocr


def _ocr_worker(args: tuple) -> tuple[str, list[str]]:
    """
    Extrai texto via OCR e detecta ativos.
    Retorna (path_str, sorted_assets).
    """
    (
        pdf_path_str,
        asset_pattern,
        dpi,
        language,
        poppler_path,
        tesseract_cmd,
        max_pages,
    ) = args

    import pytesseract
    from src.pdf_processor import _extract_text_ocr
    from src.asset_detector import find_assets

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    text = _extract_text_ocr(pdf_path_str, dpi, language, poppler_path, max_pages)
    return pdf_path_str, sorted(find_assets(text, asset_pattern))


# ---------------------------------------------------------------------------
# Orquestrador principal
# ---------------------------------------------------------------------------

def process_folder_parallel(
    working_folder: Path,
    config,
    dry_run: bool,
    digital_workers: int = 4,
    ocr_workers: int = 2,
) -> dict[str, list[str]]:
    from src.file_organizer import is_already_categorized, organize_pdf

    summary: dict[str, list[str]] = {
        "categorized": [],
        "no_assets": [],
        "skipped": [],
        "errors": [],
    }

    all_pdfs = list(working_folder.glob("*.pdf"))

    to_process: list[Path] = []
    for p in all_pdfs:
        if is_already_categorized(p) and config.reprocess_mode == "skip":
            summary["skipped"].append(p.name)
        else:
            to_process.append(p)

    total = len(to_process)
    logger.info(
        "Total: %d PDF(s) | ignorados: %d | a processar: %d",
        len(all_pdfs),
        len(summary["skipped"]),
        total,
    )

    if not to_process:
        return summary

    # ------------------------------------------------------------------
    # Fase 1 — Extração digital em paralelo
    # ------------------------------------------------------------------
    logger.info("Fase 1 — Extração digital (%d workers)...", digital_workers)

    ocr_queue: list[Path] = []
    done = 0

    digital_args = [
        (str(p), config.asset_pattern, config.ocr.min_text_length)
        for p in to_process
    ]
    path_lookup = {str(p): p for p in to_process}

    with ProcessPoolExecutor(
        max_workers=digital_workers,
        initializer=_worker_init,
        initargs=(_PROJECT_ROOT,),
    ) as pool:
        futures = {pool.submit(_digital_worker, arg): arg[0] for arg in digital_args}
        for future in as_completed(futures):
            done += 1
            path_str = futures[future]
            try:
                _, assets, needs_ocr = future.result()
                pdf_path = path_lookup[path_str]

                if needs_ocr:
                    ocr_queue.append(pdf_path)
                elif assets:
                    _finalize(pdf_path, assets, working_folder, dry_run, summary)
                else:
                    logger.info("[digital] Sem ativos: '%s'", pdf_path.name)
                    summary["no_assets"].append(pdf_path.name)

            except Exception as exc:
                logger.error("[digital] Erro em '%s': %s", Path(path_str).name, exc)
                summary["errors"].append(Path(path_str).name)

            _log_progress("Fase 1", done, total)

    logger.info(
        "Fase 1 concluída — %d digital(is), %d para OCR.",
        total - len(ocr_queue),
        len(ocr_queue),
    )

    # ------------------------------------------------------------------
    # Fase 2 — OCR em paralelo (apenas PDFs escaneados)
    # ------------------------------------------------------------------
    if not ocr_queue:
        return summary

    logger.info("Fase 2 — OCR (%d workers, %d arquivo(s))...", ocr_workers, len(ocr_queue))

    ocr_total = len(ocr_queue)
    ocr_done = 0

    ocr_args = [
        (
            str(p),
            config.asset_pattern,
            config.ocr.dpi,
            config.ocr.language,
            config.poppler_path,
            config.tesseract_cmd,
            config.ocr.max_pages,
        )
        for p in ocr_queue
    ]
    ocr_lookup = {str(p): p for p in ocr_queue}

    with ProcessPoolExecutor(
        max_workers=ocr_workers,
        initializer=_worker_init,
        initargs=(_PROJECT_ROOT,),
    ) as pool:
        futures = {pool.submit(_ocr_worker, arg): arg[0] for arg in ocr_args}
        for future in as_completed(futures):
            ocr_done += 1
            path_str = futures[future]
            try:
                _, assets = future.result()
                pdf_path = ocr_lookup[path_str]

                if assets:
                    _finalize(pdf_path, assets, working_folder, dry_run, summary)
                else:
                    logger.info("[OCR] Sem ativos: '%s'", pdf_path.name)
                    summary["no_assets"].append(pdf_path.name)

            except Exception as exc:
                logger.error("[OCR] Erro em '%s': %s", Path(path_str).name, exc)
                summary["errors"].append(Path(path_str).name)

            _log_progress("Fase 2 (OCR)", ocr_done, ocr_total)

    logger.info("Fase 2 concluída.")
    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finalize(
    pdf_path: Path,
    assets: list[str],
    working_folder: Path,
    dry_run: bool,
    summary: dict,
) -> None:
    from src.file_organizer import organize_pdf

    logger.info("Ativos em '%s': %s", pdf_path.name, ", ".join(assets))
    try:
        organize_pdf(pdf_path, working_folder, set(assets), dry_run=dry_run)
        summary["categorized"].append(f"{pdf_path.name} → {assets}")
    except Exception as exc:
        logger.error("Erro ao organizar '%s': %s", pdf_path.name, exc)
        summary["errors"].append(pdf_path.name)


def _log_progress(phase: str, done: int, total: int) -> None:
    if total and done % 100 == 0:
        pct = done / total * 100
        logger.info("%s: %d/%d (%.0f%%)", phase, done, total, pct)
