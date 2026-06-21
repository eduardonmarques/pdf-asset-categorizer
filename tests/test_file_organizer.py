import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.file_organizer import (
    is_already_categorized,
    rename_as_categorized,
    ensure_asset_folder,
    CATEGORIZED_SUFFIX,
)


def test_is_already_categorized_true(tmp_path):
    f = tmp_path / "relatorio_categorizado.pdf"
    f.touch()
    assert is_already_categorized(f) is True


def test_is_already_categorized_false(tmp_path):
    f = tmp_path / "relatorio.pdf"
    f.touch()
    assert is_already_categorized(f) is False


def test_rename_as_categorized(tmp_path):
    original = tmp_path / "relatorio.pdf"
    original.write_bytes(b"%PDF-1.4")
    new_path = rename_as_categorized(original)
    assert new_path.name == "relatorio_categorizado.pdf"
    assert new_path.exists()
    assert not original.exists()


def test_rename_already_categorized_is_noop(tmp_path):
    f = tmp_path / "relatorio_categorizado.pdf"
    f.write_bytes(b"%PDF-1.4")
    result = rename_as_categorized(f)
    assert result == f
    assert f.exists()


def test_ensure_asset_folder_creates(tmp_path):
    folder = ensure_asset_folder(tmp_path, "PETR4")
    assert folder.is_dir()
    assert folder.name == "PETR4"


def test_ensure_asset_folder_idempotent(tmp_path):
    ensure_asset_folder(tmp_path, "VALE3")
    ensure_asset_folder(tmp_path, "VALE3")  # second call must not raise
    assert (tmp_path / "VALE3").is_dir()


@patch("src.file_organizer.win32com.client")
def test_organize_pdf_dry_run(mock_com, tmp_path):
    pdf = tmp_path / "relatorio.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    from src.file_organizer import organize_pdf
    result = organize_pdf(pdf, tmp_path, {"PETR4"}, dry_run=True)
    assert result == pdf  # not renamed in dry-run
    assert not (tmp_path / "PETR4").exists()
