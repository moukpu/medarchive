"""Определение формата файла и выбор extractor-плагина."""
from __future__ import annotations

from pathlib import Path

from app.extractors.base import BaseExtractor
from app.models import FileFormat


def detect_format(path: str) -> FileFormat:
    """Определить тип файла по расширению и содержимому.

    Для PDF различаем текстовый и скан: пробуем извлечь текст; если его почти
    нет — считаем сканом (требует OCR).
    """
    ext = Path(path).suffix.lower()
    if ext in (".xlsx", ".xls"):
        return FileFormat.xlsx
    if ext == ".docx":
        return FileFormat.docx
    if ext == ".pdf":
        return FileFormat.scan_pdf if _is_scanned_pdf(path) else FileFormat.pdf
    # по умолчанию пробуем как pdf
    return FileFormat.pdf


def _is_scanned_pdf(path: str) -> bool:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return False
    try:
        doc = fitz.open(path)
        text_len = 0
        for page in doc:
            text_len += len(page.get_text("text").strip())
            if text_len > 100:
                return False  # достаточно текста — это текстовый PDF
        return True
    except Exception:
        return False


def get_extractor(fmt: FileFormat) -> BaseExtractor:
    # ленивый импорт: тяжёлые зависимости подгружаются только при необходимости
    if fmt == FileFormat.xlsx:
        from app.extractors.xlsx import XlsxExtractor
        return XlsxExtractor()
    if fmt == FileFormat.docx:
        from app.extractors.docx import DocxExtractor
        return DocxExtractor()
    if fmt == FileFormat.scan_pdf:
        from app.extractors.pdf_scan import PdfScanExtractor
        return PdfScanExtractor()
    from app.extractors.pdf_text import PdfTextExtractor
    return PdfTextExtractor()
