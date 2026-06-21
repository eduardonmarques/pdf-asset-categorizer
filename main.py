"""
Categorizador de PDFs por Ativo Financeiro
===========================================
Lê os PDFs da pasta configurada, identifica ativos (ações e FIIs),
cria subpastas por ativo e atalhos .lnk apontando para cada PDF.
PDFs processados são renomeados com o sufixo _categorizado.

Uso:
    python main.py [--config CONFIG] [--dry-run] [--sequential]
"""

import argparse
import logging
import sys
from pathlib import Path

from src.config_loader import load_config, setup_logging
from src.pdf_processor import extract_text
from src.asset_detector import find_assets
from src.file_organizer import is_already_categorized, organize_pdf

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Categoriza PDFs por ativo financeiro")
    parser.add_argument("--config", default=None, help="Caminho para config.yaml")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula sem renomear arquivos nem criar atalhos",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Processa arquivos um a um (sem paralelismo — útil para depuração)",
    )
    return parser.parse_args()


def process_folder_sequential(working_folder: Path, config, dry_run: bool) -> dict[str, list[str]]:
    """Processamento sequencial — mantido para depuração."""
    summary: dict[str, list[str]] = {
        "categorized": [], "no_assets": [], "skipped": [], "errors": [],
    }

    pdf_files = list(working_folder.glob("*.pdf"))
    logger.info("Encontrados %d arquivo(s) PDF em '%s'", len(pdf_files), working_folder)

    for pdf_path in pdf_files:
        if is_already_categorized(pdf_path) and config.reprocess_mode == "skip":
            logger.debug("Ignorando (já categorizado): '%s'", pdf_path.name)
            summary["skipped"].append(pdf_path.name)
            continue

        logger.info("Processando: '%s'", pdf_path.name)

        try:
            text = extract_text(
                str(pdf_path),
                min_text_length=config.ocr.min_text_length,
                ocr_language=config.ocr.language,
                ocr_dpi=config.ocr.dpi,
                poppler_path=config.poppler_path,
                max_pages=config.ocr.max_pages,
                tesseract_cmd=config.tesseract_cmd,
            )
        except Exception as exc:
            logger.error("Erro ao extrair texto de '%s': %s", pdf_path.name, exc)
            summary["errors"].append(pdf_path.name)
            continue

        assets = find_assets(text, config.asset_pattern)
        if not assets:
            logger.info("Nenhum ativo encontrado em '%s'", pdf_path.name)
            summary["no_assets"].append(pdf_path.name)
            continue

        logger.info("Ativos em '%s': %s", pdf_path.name, ", ".join(sorted(assets)))
        try:
            organize_pdf(pdf_path, working_folder, assets, dry_run=dry_run)
            summary["categorized"].append(f"{pdf_path.name} → {sorted(assets)}")
        except Exception as exc:
            logger.error("Erro ao organizar '%s': %s", pdf_path.name, exc)
            summary["errors"].append(pdf_path.name)

    return summary


def print_summary(summary: dict[str, list[str]]) -> None:
    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"  Categorizados : {len(summary['categorized'])}")
    print(f"  Sem ativos    : {len(summary['no_assets'])}")
    print(f"  Ignorados     : {len(summary['skipped'])}")
    print(f"  Erros         : {len(summary['errors'])}")

    if summary["categorized"]:
        print("\nCategorizados:")
        for entry in summary["categorized"]:
            print(f"  + {entry}")

    if summary["errors"]:
        print("\nErros:")
        for name in summary["errors"]:
            print(f"  x {name}")

    print("=" * 60)


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Erro ao carregar configuração: {exc}", file=sys.stderr)
        return 1

    setup_logging(config)

    working_folder = Path(config.working_folder)
    if not working_folder.is_dir():
        logger.error("Pasta de trabalho não encontrada: '%s'", working_folder)
        return 1

    if args.dry_run:
        logger.info("MODO DRY-RUN — nenhum arquivo será modificado")

    if args.sequential:
        logger.info("Modo sequencial ativado.")
        summary = process_folder_sequential(working_folder, config, dry_run=args.dry_run)
    else:
        from src.parallel_processor import process_folder_parallel
        logger.info(
            "Modo paralelo: %d worker(s) digital, %d worker(s) OCR.",
            config.workers.digital,
            config.workers.ocr,
        )
        summary = process_folder_parallel(
            working_folder,
            config,
            dry_run=args.dry_run,
            digital_workers=config.workers.digital,
            ocr_workers=config.workers.ocr,
        )

    print_summary(summary)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
