"""Скан-PDF extractor: OCR через Tesseract + постобработка артефактов."""
from __future__ import annotations

import re

from app.config import settings
from app.extractors.base import ExtractResult, rows_from_text


def _otsu_threshold(gray) -> int:
    """Порог Отсу по гистограмме яркости (numpy, без OpenCV)."""
    import numpy as np

    arr = np.asarray(gray).ravel()
    hist = np.bincount(arr, minlength=256).astype(float)
    total = arr.size
    if total == 0:
        return 128
    sum_all = np.dot(np.arange(256), hist)
    w_b = 0.0
    sum_b = 0.0
    max_var = -1.0
    threshold = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return threshold


def _preprocess(image):
    """Грейскейл + автоконтраст + бинаризация Отсу для повышения качества OCR.

    Бинаризация (чёрный текст на белом) заметно помогает Tesseract на шумных
    сканах: убирает серый фон, тени и неравномерную засветку. При сбое порога
    тихо откатываемся к grayscale+autocontrast.
    """
    from PIL import ImageOps

    img = ImageOps.autocontrast(image.convert("L"))
    try:
        t = _otsu_threshold(img)
        img = img.point(lambda p: 255 if p > t else 0, mode="L")
    except Exception:  # noqa: BLE001
        pass
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

        # 1. Vision-OCR (HF Inference) как основной путь для сканов — распознаёт таблицу
        #    напрямую с изображения, надёжнее чем Tesseract+regex на плохих сканах.
        from app.extractors.llm import (
            llm_available,
            rows_from_pdf_images_llm,
            rows_from_text_llm,
        )

        if llm_available():
            rows, warnings = rows_from_pdf_images_llm(path)
            result.warnings.extend(warnings)
            if rows:
                result.rows.extend(rows)
                result.raw_text = "[vision-OCR] распознано позиций: %d" % len(rows)
                return result

        # 2. Tesseract OCR (грейскейл+автоконтраст+Отсу, 300 DPI, --psm 6).
        import pytesseract
        from pdf2image import convert_from_path

        pages = convert_from_path(path, dpi=300)
        raw_chunks: list[str] = []
        for image in pages:
            img = _preprocess(image)
            text = pytesseract.image_to_string(img, lang=settings.tesseract_lang, config="--psm 6")
            raw_chunks.append(_clean_ocr(text))
        result.raw_text = "\n".join(raw_chunks)

        # 2a. Двухэтапный конвейер OCR→LLM: если ключ есть, но vision-OCR не дал
        #     строк, прогоняем сырой текст Tesseract через LLM-постпроцессор —
        #     он чистит артефакты распознавания и собирает таблицу лучше regex.
        if llm_available():
            rows, warnings = rows_from_text_llm(result.raw_text)
            result.warnings.extend(warnings)
            if rows:
                result.rows.extend(rows)
                return result

        # 3. Fallback: построчный regex-парсер по OCR-тексту.
        rows, warnings = rows_from_text(result.raw_text)
        result.rows.extend(rows)
        result.warnings.extend(warnings)
        if not result.rows:
            result.warnings.append("OCR не дал распознаваемых позиций — требуется ручная проверка")
        return result
