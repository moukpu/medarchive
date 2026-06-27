"""Скан-PDF extractor: OCR через Tesseract + постобработка артефактов."""
from __future__ import annotations

import re

from app.config import settings
from app.extractors.base import ExtractResult, rows_from_text


def _preprocess(image):
    """Грейскейл + автоконтраст для повышения качества OCR."""
    from PIL import ImageOps

    img = image.convert("L")  # grayscale
    img = ImageOps.autocontrast(img)
    return img


def _clean_ocr(text: str) -> str:
    """Постобработка артефактов OCR."""
    text = text.replace("|", " ")
    text = re.sub(r"[ \t]{2,}", "  ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


class PdfScanExtractor:
    def extract(self, path: str) -> ExtractResult:
        result = ExtractResult()

        # 1. Vision-OCR (OpenAI) как основной путь для сканов — распознаёт таблицу
        #    напрямую с изображения, надёжнее чем Tesseract+regex на плохих сканах.
        from app.extractors.llm import llm_available, rows_from_pdf_images_llm

        if llm_available():
            rows, warnings = rows_from_pdf_images_llm(path)
            result.warnings.extend(warnings)
            if rows:
                result.rows.extend(rows)
                result.raw_text = "[vision-OCR] распознано позиций: %d" % len(rows)
                return result

        # 2. Fallback: Tesseract + построчный regex-парсер.
        import pytesseract
        from pdf2image import convert_from_path

        pages = convert_from_path(path, dpi=300)
        raw_chunks: list[str] = []
        for image in pages:
            img = _preprocess(image)
            text = pytesseract.image_to_string(img, lang=settings.tesseract_lang, config="--psm 6")
            raw_chunks.append(_clean_ocr(text))
        result.raw_text = "\n".join(raw_chunks)

        rows, warnings = rows_from_text(result.raw_text)
        result.rows.extend(rows)
        result.warnings.extend(warnings)
        if not result.rows:
            result.warnings.append("OCR не дал распознаваемых позиций — требуется ручная проверка")
        return result
