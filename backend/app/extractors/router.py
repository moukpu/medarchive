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
    """Определить, является ли PDF сканом (требует OCR).

    Эвристики (по первым 5 страницам):
    1. Если на странице есть изображение, покрывающее >50% площади — скан.
    2. Если текста совсем мало (<50 символов на страницу) — скан.
    3. Если текст есть, но >40% символов — не буква/цифра/пробел (OCR-мусор) — скан.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return False
    try:
        doc = fitz.open(path)
        pages_to_check = min(len(doc), 5)
        if pages_to_check == 0:
            return False

        scan_pages = 0
        for i in range(pages_to_check):
            page = doc[i]
            page_area = page.rect.width * page.rect.height
            if page_area <= 0:
                continue

            # ПРИОРИТЕТ — текстовый слой. Цифровой PDF с фирменным бланком/печатью
            # (крупная картинка) всё равно имеет извлекаемый текст — это НЕ скан.
            # Проверяем текст ПЕРВЫМ, иначе картинка-фон ложно метит документ сканом.
            text = page.get_text("text").strip()
            words = len(page.get_text("words"))
            alpha_digit = sum(1 for c in text if c.isalpha() or c.isdigit() or c.isspace())
            quality = alpha_digit / len(text) if text else 0.0
            if words >= 20 and quality >= 0.6:
                continue  # полноценный текст-слой → страница не скан

            # Текста мало/он мусорный → это либо скан, либо страница-картинка.
            if len(text) < 50:
                scan_pages += 1
                continue
            if quality < 0.6:
                scan_pages += 1
                continue

            # Текст пограничный + крупное изображение (>50% площади) → скан.
            try:
                for img in page.get_images(full=True):
                    try:
                        bbox = page.get_image_bbox(img)
                        if (bbox.width * bbox.height) / page_area > 0.5:
                            scan_pages += 1
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        doc.close()
        # Если >50% проверенных страниц — сканы, весь документ — скан
        return scan_pages > pages_to_check / 2
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
