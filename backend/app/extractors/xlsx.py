"""XLSX/XLS extractor: обход всех листов, авто-детект строки заголовков.

Новый формат .xlsx читается openpyxl, устаревший .xls — через xlrd
(openpyxl его не поддерживает). Оба пути сводятся к матрице ячеек и общему
парсеру rows_from_matrix, так что ядро от формата не зависит.
"""
from __future__ import annotations

from pathlib import Path

from app.extractors.base import ExtractResult, rows_from_matrix


def _sheets_xlsx(path: str):
    """[(title, matrix)] для .xlsx через openpyxl."""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        for ws in wb.worksheets:
            matrix = [["" if c is None else str(c) for c in row] for row in ws.iter_rows(values_only=True)]
            yield ws.title, matrix
    finally:
        wb.close()


def _sheets_xls(path: str):
    """[(title, matrix)] для устаревшего .xls через xlrd."""
    import xlrd

    book = xlrd.open_workbook(path)
    for sheet in book.sheets():
        matrix = [
            ["" if sheet.cell_value(r, c) is None else str(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)
        ]
        yield sheet.name, matrix


class XlsxExtractor:
    def extract(self, path: str) -> ExtractResult:
        result = ExtractResult()
        is_legacy = Path(path).suffix.lower() == ".xls"
        try:
            sheets = list(_sheets_xls(path) if is_legacy else _sheets_xlsx(path))
        except Exception:
            # Автофоллбэк: если openpyxl не смог — пробуем xlrd, и наоборот
            try:
                sheets = list(_sheets_xls(path) if not is_legacy else _sheets_xlsx(path))
            except Exception:
                raise

        raw_chunks: list[str] = []
        for title, matrix in sheets:
            if not matrix:
                continue
            for cells in matrix:
                raw_chunks.append("\t".join(cells))
            rows, warnings = rows_from_matrix(matrix)
            result.rows.extend(rows)
            result.warnings.extend(f"[{title}] {w}" for w in warnings)

        result.raw_text = "\n".join(raw_chunks)
        if not result.rows:
            result.warnings.append("Не извлечено ни одной позиции из XLSX/XLS")
        return result
