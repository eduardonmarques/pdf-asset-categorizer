import yaml
import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OcrConfig:
    language: str = "por+eng"
    dpi: int = 300
    min_text_length: int = 50
    max_pages: int = 10


@dataclass
class AppConfig:
    working_folder: str = ""
    reprocess_mode: str = "skip"
    asset_pattern: str = r"\b[A-Z]{4}(?:11|3|4)\b"
    ocr: OcrConfig = field(default_factory=OcrConfig)
    tesseract_cmd: str = "tesseract"
    poppler_path: Optional[str] = None
    log_level: str = "INFO"
    log_file: Optional[str] = "categorizer.log"


def load_config(config_path: Optional[str] = None) -> AppConfig:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    ocr_data = data.get("ocr", {})
    ocr = OcrConfig(
        language=ocr_data.get("language", "por+eng"),
        dpi=ocr_data.get("dpi", 300),
        min_text_length=ocr_data.get("min_text_length", 50),
        max_pages=ocr_data.get("max_pages", 10),
    )

    return AppConfig(
        working_folder=data.get("working_folder", ""),
        reprocess_mode=data.get("reprocess_mode", "skip"),
        asset_pattern=data.get("asset_pattern", r"\b[A-Z]{4}(?:11|3|4)\b"),
        ocr=ocr,
        tesseract_cmd=data.get("tesseract_cmd", "tesseract"),
        poppler_path=data.get("poppler_path"),
        log_level=data.get("log_level", "INFO"),
        log_file=data.get("log_file", "categorizer.log"),
    )


def setup_logging(config: AppConfig) -> None:
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if config.log_file:
        log_path = Path(__file__).parent.parent / config.log_file
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
