import pytest
from unittest.mock import patch, MagicMock
from src.pdf_processor import extract_text


@patch("src.pdf_processor.pdfplumber")
def test_extract_digital_text(mock_pdfplumber, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "PETR4 subiu hoje no mercado financeiro com grande volume"
    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]
    mock_pdfplumber.open.return_value = mock_pdf

    text = extract_text(str(pdf), min_text_length=10)
    assert "PETR4" in text


@patch("src.pdf_processor.convert_from_path")
@patch("src.pdf_processor.pytesseract")
@patch("src.pdf_processor.pdfplumber")
def test_falls_back_to_ocr_when_text_too_short(mock_pdfplumber, mock_tess, mock_c2p, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""  # no digital text
    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]
    mock_pdfplumber.open.return_value = mock_pdf

    mock_img = MagicMock()
    mock_c2p.return_value = [mock_img]
    mock_tess.image_to_string.return_value = "MXRF11 distribuiu proventos"

    text = extract_text(str(pdf), min_text_length=50)
    assert "MXRF11" in text
    mock_tess.image_to_string.assert_called_once()
