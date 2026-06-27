"""Текстовый PDF extractor: таблицы через pdfplumber + fallback по тексту."""
from __future__ import annotations

from app.extractors.base import ExtractResult, rows_from_matrix, rows_from_text


class PdfTextExtractor:
    def extract(self, path: str) -> ExtractResult:
        import pdfplumber

        result = ExtractResult()
        raw_chunks: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                raw_chunks.append(page.extract_text() or "")
                for table in page.extract_tables() or []:
                    matrix = [["" if c is None else str(c) for c in row] for row in table]
                    rows, warnings = rows_from_matrix(matrix)
                    result.rows.extend(rows)
                    result.warnings.extend(warnings)
        result.raw_text = "\n".join(raw_chunks)

        # fallback: если таблицы не распознались, парсим плоский текст
        if not result.rows and result.raw_text:
            rows, _ = rows_from_text(result.raw_text)
            result.rows.extend(rows)
        if not result.rows:
            result.warnings.append("Не извлечено ни одной позиции из PDF (текст)")
        return result
