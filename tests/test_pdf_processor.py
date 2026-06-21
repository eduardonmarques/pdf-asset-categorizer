import pytest
from unittest.mock import patch, MagicMock
from src.pdf_processor import extract_text, _build_table_filter


# ---------------------------------------------------------------------------
# _build_table_filter unit tests
# ---------------------------------------------------------------------------

def _char(x0, x1, top, bottom):
    return {"x0": x0, "x1": x1, "top": top, "bottom": bottom}


def test_filter_excludes_char_inside_table():
    # table bbox: x0=50, top=100, x1=400, bottom=200
    fn = _build_table_filter([(50, 100, 400, 200)])
    # char centre at (225, 150) — inside table
    assert fn(_char(200, 250, 140, 160)) is False


def test_filter_keeps_char_outside_table():
    fn = _build_table_filter([(50, 100, 400, 200)])
    # char centre at (225, 50) — above table
    assert fn(_char(200, 250, 40, 60)) is True


def test_filter_keeps_char_beside_table():
    fn = _build_table_filter([(50, 100, 400, 200)])
    # char centre at (10, 150) — left of table
    assert fn(_char(5, 15, 140, 160)) is True


def test_filter_multiple_tables():
    bboxes = [(0, 0, 100, 50), (200, 200, 400, 300)]
    fn = _build_table_filter(bboxes)
    assert fn(_char(10, 90, 10, 40)) is False   # inside first table
    assert fn(_char(210, 390, 210, 290)) is False  # inside second table
    assert fn(_char(110, 190, 100, 150)) is True   # between tables


def test_filter_no_tables_always_true():
    fn = _build_table_filter([])
    assert fn(_char(0, 100, 0, 100)) is True


# ---------------------------------------------------------------------------
# extract_text integration tests (pdfplumber mocked)
# ---------------------------------------------------------------------------

@patch("src.pdf_processor.pdfplumber")
def test_extract_digital_text_no_tables(mock_pdfplumber, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mock_page = MagicMock()
    mock_page.find_tables.return_value = []
    mock_page.extract_text.return_value = "PETR4 subiu hoje no mercado financeiro com grande volume"

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]
    mock_pdfplumber.open.return_value = mock_pdf

    text = extract_text(str(pdf), min_text_length=10)
    assert "PETR4" in text
    # No tables → filter should NOT be called
    mock_page.filter.assert_not_called()


@patch("src.pdf_processor.pdfplumber")
def test_extract_digital_text_with_tables_uses_filter(mock_pdfplumber, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mock_table = MagicMock()
    mock_table.bbox = (50, 100, 400, 200)

    filtered_page = MagicMock()
    filtered_page.extract_text.return_value = "VALE3 em destaque no corpo do texto"

    mock_page = MagicMock()
    mock_page.find_tables.return_value = [mock_table]
    mock_page.filter.return_value = filtered_page

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]
    mock_pdfplumber.open.return_value = mock_pdf

    text = extract_text(str(pdf), min_text_length=10)
    assert "VALE3" in text
    # Tables present → filter must be applied
    mock_page.filter.assert_called_once()


@patch("src.pdf_processor.convert_from_path")
@patch("src.pdf_processor.pytesseract")
@patch("src.pdf_processor.pdfplumber")
def test_falls_back_to_ocr_when_text_too_short(mock_pdfplumber, mock_tess, mock_c2p, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mock_page = MagicMock()
    mock_page.find_tables.return_value = []
    mock_page.extract_text.return_value = ""

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]
    mock_pdfplumber.open.return_value = mock_pdf

    mock_img = MagicMock()
    mock_c2p.return_value = [mock_img]
    mock_tess.image_to_string.return_value = "MXRF11 distribuiu proventos"

    text = extract_text(str(pdf), min_text_length=50, max_pages=1)
    assert "MXRF11" in text
    mock_tess.image_to_string.assert_called_once()
