"""
Pipeline verdadeiro de dois estágios com dois ProcessPoolExecutor simultâneos.

Ambos os pools ficam abertos ao mesmo tempo:
  - digital_pool (Fase 1): extração pdfplumber em paralelo
  - ocr_pool     (Fase 2): Tesseract em paralelo

À medida que futuros da Fase 1 completam e identificam PDFs escaneados,
eles são submetidos IMEDIATAMENTE ao ocr_pool — sem esperar o fim da Fase 1.
Resultado: OCR começa no primeiro arquivo escaneado encontrado, enquanto
a extração digital ainda está processando os demais.
"""

import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = str(Path(__file__).parent.parent)


def _worker_init(project_root: str) -> None:
    """Garante que src.* seja importável nos subprocessos (spawn no Windows)."""
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


# ---------------------------------------------------------------------------
# Workers (executados em subprocessos)
# ---------------------------------------------------------------------------

def _digital_worker(args: tuple) -> tuple[str, list[str], bool]:
    """
    Extrai texto digital e detecta ativos.
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
# Orquestrador
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
        "categorized": [], "no_assets": [], "skipped": [], "errors": [],
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
        len(all_pdfs), len(summary["skipped"]), total,
    )
    if not to_process:
        return summary

    _pool_kwargs = dict(initializer=_worker_init, initargs=(_PROJECT_ROOT,))

    digital_args = [
        (str(p), config.asset_pattern, config.ocr.min_text_length)
        for p in to_process
    ]
    path_lookup = {str(p): p for p in to_process}

    ocr_arg_template = (
        None,  # placeholder para path_str
        config.asset_pattern,
        config.ocr.dpi,
        config.ocr.language,
        config.poppler_path,
        config.tesseract_cmd,
        config.ocr.max_pages,
    )

    # -----------------------------------------------------------------------
    # Ambos os pools abertos simultaneamente — pipeline verdadeiro
    # -----------------------------------------------------------------------
    logger.info(
        "Iniciando pipeline: %d worker(s) digital + %d worker(s) OCR (simultâneos)",
        digital_workers, ocr_workers,
    )

    with ProcessPoolExecutor(max_workers=digital_workers, **_pool_kwargs) as digital_pool, \
         ProcessPoolExecutor(max_workers=ocr_workers, **_pool_kwargs) as ocr_pool:
        # Submete toda a Fase 1 de uma vez
        digital_futures = {
            digital_pool.submit(_digital_worker, arg): path_lookup[arg[0]]
            for arg in digital_args
        }

        ocr_futures: dict = {}
        phase1_done = 0

        # Coleta resultados da Fase 1; submete ao ocr_pool imediatamente
        for future in as_completed(digital_futures):
            phase1_done += 1
            pdf_path = digital_futures[future]
            try:
                _, assets, needs_ocr = future.result()
                if needs_ocr:
                    ocr_args = (str(pdf_path),) + ocr_arg_template[1:]
                    ocr_future = ocr_pool.submit(_ocr_worker, ocr_args)
                    ocr_futures[ocr_future] = pdf_path
                elif assets:
                    _finalize(pdf_path, assets, working_folder, dry_run, summary)
                else:
                    logger.debug("[digital] Sem ativos: '%s'", pdf_path.name)
                    summary["no_assets"].append(pdf_path.name)
            except Exception as exc:
                logger.error("[digital] Erro em '%s': %s", pdf_path.name, exc)
                summary["errors"].append(pdf_path.name)

            _log_progress("Fase 1 (digital)", phase1_done, total, step=200)

        ocr_total = len(ocr_futures)
        logger.info(
            "Fase 1 concluída. %d digital(is) resolvidos, %d em OCR (já em execução).",
            total - ocr_total, ocr_total,
        )

        # Coleta resultados da Fase 2 (workers já rodando desde o início)
        phase2_done = 0
        for future in as_completed(ocr_futures):
            phase2_done += 1
            pdf_path = ocr_futures[future]
            try:
                _, assets = future.result()
                if assets:
                    _finalize(pdf_path, assets, working_folder, dry_run, summary)
                else:
                    logger.debug("[OCR] Sem ativos: '%s'", pdf_path.name)
                    summary["no_assets"].append(pdf_path.name)
            except Exception as exc:
                logger.error("[OCR] Erro em '%s': %s", pdf_path.name, exc)
                summary["errors"].append(pdf_path.name)

            _log_progress("Fase 2 (OCR)", phase2_done, ocr_total, step=50)

    logger.info("Pipeline concluído.")
    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finalize(pdf_path, assets, working_folder, dry_run, summary):
    from src.file_organizer import organize_pdf
    logger.info("Ativos em '%s': %s", pdf_path.name, ", ".join(assets))
    try:
        organize_pdf(pdf_path, working_folder, set(assets), dry_run=dry_run)
        summary["categorized"].append(f"{pdf_path.name} → {assets}")
    except Exception as exc:
        logger.error("Erro ao organizar '%s': %s", pdf_path.name, exc)
        summary["errors"].append(pdf_path.name)


def _log_progress(phase: str, done: int, total: int, step: int = 100) -> None:
    if total and done % step == 0:
        pct = done / total * 100
        logger.info("%s: %d/%d (%.0f%%)", phase, done, total, pct)
