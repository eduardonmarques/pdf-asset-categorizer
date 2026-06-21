import logging
from pathlib import Path
from typing import Optional

import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

logger = logging.getLogger(__name__)


def _build_table_filter(table_bboxes: list[tuple]):
    """
    Returns a pdfplumber character-filter function that excludes characters
    whose centre falls inside any of the given table bounding boxes.
    bbox format: (x0, top, x1, bottom) — pdfplumber convention.
    """
    def outside_tables(char: dict) -> bool:
        mid_x = (char["x0"] + char["x1"]) / 2
        mid_y = (char["top"] + char["bottom"]) / 2
        for x0, top, x1, bottom in table_bboxes:
            if x0 <= mid_x <= x1 and top <= mid_y <= bottom:
                return False
        return True

    return outside_tables


def _extract_text_digital(pdf_path: str) -> str:
    """
    Extract selectable text from a digital PDF using pdfplumber.
    Text inside table cells is excluded — only body text is returned.
    """
    text_parts: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.find_tables()
                if tables:
                    table_bboxes = [t.bbox for t in tables]
                    filtered = page.filter(_build_table_filter(table_bboxes))
                    page_text = filtered.extract_text() or ""
                    logger.debug(
                        "Página com %d tabela(s) detectada(s) — texto de tabelas ignorado",
                        len(tables),
                    )
                else:
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
    max_pages: int = 10,
) -> str:
    """
    Convert PDF pages to images one at a time and run Tesseract OCR.
    Processes at most max_pages pages to avoid memory exhaustion.
    Note: table exclusion is NOT applied for OCR — no structural information
    is available in scanned images without dedicated table-detection models.
    """
    text_parts: list[str] = []
    convert_kwargs: dict = {"dpi": dpi}
    if poppler_path:
        convert_kwargs["poppler_path"] = poppler_path

    page_num = 1
    while page_num <= max_pages:
        try:
            images = convert_from_path(
                pdf_path,
                first_page=page_num,
                last_page=page_num,
                **convert_kwargs,
            )
        except Exception as exc:
            # convert_from_path raises when first_page exceeds total pages
            logger.debug("Fim do PDF na página %d de '%s': %s", page_num, pdf_path, exc)
            break

        if not images:
            break

        img = images[0]
        try:
            page_text = pytesseract.image_to_string(img, lang=language)
            text_parts.append(page_text)
        except Exception as exc:
            logger.warning("OCR falhou na página %d de '%s': %s", page_num, pdf_path, exc)
        finally:
            img.close()
            del img, images

        page_num += 1

    if page_num > max_pages:
        logger.debug("OCR limitado a %d página(s) em '%s'", max_pages, pdf_path)

    return "\n".join(text_parts)


def extract_text(
    pdf_path: str,
    min_text_length: int = 50,
    ocr_language: str = "por+eng",
    ocr_dpi: int = 300,
    poppler_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
    max_pages: int = 10,
) -> str:
    """
    Extract body text from a PDF (tables excluded for digital PDFs).
    First tries digital extraction; falls back to OCR if text is too short.
    """
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    logger.info("Extraindo texto de '%s'", Path(pdf_path).name)

    text = _extract_text_digital(pdf_path)
    avg_chars = len(text) / max(1, text.count("\n") + 1)

    if len(text.strip()) < min_text_length or avg_chars < 10:
        logger.info("Texto digital insuficiente — usando OCR em '%s'", Path(pdf_path).name)
        text = _extract_text_ocr(pdf_path, ocr_dpi, ocr_language, poppler_path, max_pages)

    return text
