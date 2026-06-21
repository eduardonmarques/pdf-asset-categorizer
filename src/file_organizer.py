import logging
import os
from pathlib import Path

import win32com.client

logger = logging.getLogger(__name__)

CATEGORIZED_SUFFIX = "_categorizado"


def is_already_categorized(pdf_path: Path) -> bool:
    return CATEGORIZED_SUFFIX in pdf_path.stem


def rename_as_categorized(pdf_path: Path) -> Path:
    """Rename file appending '_categorizado' before the extension. Returns new path."""
    if is_already_categorized(pdf_path):
        return pdf_path
    new_path = pdf_path.with_name(pdf_path.stem + CATEGORIZED_SUFFIX + pdf_path.suffix)
    pdf_path.rename(new_path)
    logger.info("Renomeado: '%s' → '%s'", pdf_path.name, new_path.name)
    return new_path


def ensure_asset_folder(working_folder: Path, asset: str) -> Path:
    """Create and return the asset subfolder inside working_folder."""
    folder = working_folder / asset
    folder.mkdir(exist_ok=True)
    return folder


def create_shortcut(target_path: Path, shortcut_dir: Path, original_stem: str, asset: str) -> None:
    """Create a Windows .lnk shortcut inside shortcut_dir pointing to target_path."""
    shortcut_name = f"{original_stem} - {asset}.lnk"
    shortcut_path = shortcut_dir / shortcut_name

    if shortcut_path.exists():
        logger.debug("Atalho já existe: '%s'", shortcut_name)
        return

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.Targetpath = str(target_path.resolve())
        shortcut.WorkingDirectory = str(target_path.parent.resolve())
        shortcut.save()
        logger.info("Atalho criado: '%s' → '%s'", shortcut_name, target_path.name)
    except Exception as exc:
        logger.error("Falha ao criar atalho '%s': %s", shortcut_name, exc)


def organize_pdf(
    pdf_path: Path,
    working_folder: Path,
    assets: set[str],
    dry_run: bool = False,
) -> Path:
    """
    For each asset found in the PDF:
      1. Create asset folder (if needed)
      2. Rename PDF to original_categorizado.pdf
      3. Create shortcut in asset folder pointing to renamed file

    Returns the final (possibly renamed) path of the PDF.
    """
    original_stem = pdf_path.stem

    if dry_run:
        logger.info("[DRY-RUN] Processaria '%s' com ativos: %s", pdf_path.name, assets)
        return pdf_path

    # Rename first so shortcuts always point to the final filename
    new_pdf_path = rename_as_categorized(pdf_path)

    for asset in sorted(assets):
        asset_folder = ensure_asset_folder(working_folder, asset)
        create_shortcut(new_pdf_path, asset_folder, original_stem, asset)

    return new_pdf_path
