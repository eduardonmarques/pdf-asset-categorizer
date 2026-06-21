import logging
import os
from pathlib import Path
from typing import Optional

import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

logger = logging.getLogger(__name__)


def _extract_text_digital(pdf_path: str) -> str:
    """Extract selectable text from a digital PDF using pdfplumber."""
    text_parts: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
    except Exception as exc:
        logger.warning("pdfplumber falhou em '%s': %s", pdf_path, exc)
    return "\n".join(text_parts)


def _extract_text_ocr(
    pdf_path: str,
    dpi: int,
    language: str,
    poppler_path: Optional[str],
) -> str:
    """Convert PDF pages to images and run Tesseract OCR."""
    text_parts: list[str] = []
    convert_kwargs: dict = {"dpi": dpi}
    if poppler_path:
        convert_kwargs["poppler_path"] = poppler_path

    try:
        images: list[Image.Image] = convert_from_path(pdf_path, **convert_kwargs)
    except Exception as exc:
        logger.error("pdf2image falhou em '%s': %s", pdf_path, exc)
        return ""

    for i, img in enumerate(images):
        try:
            page_text = pytesseract.image_to_string(img, lang=language)
            text_parts.append(page_text)
        except Exception as exc:
            logger.warning("OCR falhou na página %d de '%s': %s", i + 1, pdf_path, exc)

    return "\n".join(text_parts)


def extract_text(
    pdf_path: str,
    min_text_length: int = 50,
    ocr_language: str = "por+eng",
    ocr_dpi: int = 300,
    poppler_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
) -> str:
    """
    Extract text from a PDF.
    First tries digital extraction; falls back to OCR if text is too short.
    """
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    logger.info("Extraindo texto de '%s'", Path(pdf_path).name)

    text = _extract_text_digital(pdf_path)
    avg_chars = len(text) / max(1, text.count("\n") + 1)

    if len(text.strip()) < min_text_length or avg_chars < 10:
        logger.info("Texto digital insuficiente — usando OCR em '%s'", Path(pdf_path).name)
        text = _extract_text_ocr(pdf_path, ocr_dpi, ocr_language, poppler_path)

    return text
