"""Docling-фоллбэк для PDF: ML-модель структуры таблиц там, где детерминированный
pdfplumber дал мусор/0 строк. Две ветки:

* **local**  — docling в процессе (тяжёлый: torch + ~1ГБ моделей, CPU-медленный).
  Жёсткий лимит страниц, чтобы не словить bad_alloc и 7+ минут на файл.
* **remote** — POST на docling-serve (GPU, напр. RunPod). Контракт REST подтверждён
  по docs/usage.md: `POST {url}/v1/convert/file` (multipart), ответ
  `{"document": {"md_content": ...}, "status": "success|partial_success|..."}`.

Обе ветки сводят таблицы к матрице и переиспользуют `rows_from_matrix` из base.py —
никакого нового парсинга цен/колонок. Опциональная зависимость: если пакет docling
не установлен и serve_url не задан — `docling_available()` возвращает False и пайплайн
спокойно идёт по старой LLM-цепочке."""
from __future__ import annotations

import importlib.util
import os
import tempfile

from app.config import settings
from app.extractors.base import RawPriceRow, rows_from_matrix

# Статусы docling-serve, при которых доверяем результату.
_OK_STATUSES = {"success", "partial_success"}


def _local_package_available() -> bool:
    return importlib.util.find_spec("docling") is not None


def docling_available() -> bool:
    """Включён ли docling-путь: настройка + (удалённый URL ИЛИ локальный пакет)."""
    if not settings.use_docling:
        return False
    return bool(settings.docling_serve_url) or _local_package_available()


# --- markdown pipe-таблицы → матрицы ----------------------------------------

def _is_separator_row(cells: list[str]) -> bool:
    """Строка-разделитель GFM-таблицы: только -, :, пробелы в каждой ячейке."""
    return bool(cells) and all(set(c.strip()) <= set("-: ") and c.strip() for c in cells)


def _split_md_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _matrices_from_markdown(md: str) -> list[list[list[str]]]:
    """Выделить все pipe-таблицы из markdown как список матриц (с заголовками)."""
    matrices: list[list[list[str]]] = []
    current: list[list[str]] = []
    for raw_line in (md or "").splitlines():
        line = raw_line.strip()
        if line.startswith("|") and line.count("|") >= 2:
            cells = _split_md_row(line)
            if _is_separator_row(cells):
                continue  # строку-разделитель в матрицу не кладём
            current.append(cells)
        else:
            if len(current) >= 2:
                matrices.append(current)
            current = []
    if len(current) >= 2:
        matrices.append(current)
    return matrices


def _rows_from_markdown(md: str) -> list[RawPriceRow]:
    rows: list[RawPriceRow] = []
    for matrix in _matrices_from_markdown(md):
        r, _w = rows_from_matrix(matrix)
        rows.extend(r)
    return rows


# --- remote (docling-serve / GPU) -------------------------------------------

def rows_from_pdf_docling_remote(path: str, serve_url: str) -> tuple[list[RawPriceRow], list[str]]:
    """POST файла на docling-serve, разбор markdown-таблиц ответа.
    Если страниц больше 10, разбиваем на части по 10 страниц, чтобы обойти 504 таймаут прокси RunPod.
    """
    import httpx
    import fitz  # PyMuPDF
    import tempfile

    warnings: list[str] = []

    # 1. Открываем PDF и смотрим число страниц
    try:
        doc = fitz.open(path)
        total_pages = len(doc)
    except Exception as exc:
        warnings.append(f"Ошибка при открытии PDF для подсчета страниц: {exc}")
        return [], warnings

    # 2. Если файл маленький, отправляем целиком
    if total_pages <= 10:
        res_rows, res_warns = _send_single_pdf_remote(path, serve_url)
        doc.close()
        return res_rows, res_warns

    # 3. Если файл большой, делим на чанки по 10 страниц
    all_rows: list[RawPriceRow] = []
    chunk_size = 10

    for start_idx in range(0, total_pages, chunk_size):
        end_idx = min(start_idx + chunk_size, total_pages)
        # Вырезаем страницы в новый временный PDF
        try:
            chunk_doc = fitz.open()
            chunk_doc.insert_pdf(doc, from_page=start_idx, to_page=end_idx - 1)
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            chunk_doc.save(tmp_path)
            chunk_doc.close()
        except Exception as exc:
            warnings.append(f"Ошибка при нарезке страниц {start_idx}-{end_idx}: {exc}")
            continue

        # Отправляем чанк на docling-serve
        try:
            chunk_rows, chunk_warnings = _send_single_pdf_remote(tmp_path, serve_url)
            all_rows.extend(chunk_rows)
            warnings.extend(chunk_warnings)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    doc.close()
    warnings.append(f"Сплит-обработка завершена: обработано {total_pages} страниц, найдено {len(all_rows)} позиций")
    return all_rows, warnings


def _send_single_pdf_remote(path: str, serve_url: str) -> tuple[list[RawPriceRow], list[str]]:
    """Вспомогательный метод отправки одного PDF чанка на docling-serve."""
    import httpx
    warnings: list[str] = []
    url = serve_url.rstrip("/") + "/v1/convert/file"
    data = {
        "to_formats": "md",
        "do_ocr": "false",
        "do_table_structure": "true",
        "table_mode": "accurate",
    }
    headers = {}
    if settings.docling_api_key:
        headers["Authorization"] = f"Bearer {settings.docling_api_key}"
        
    try:
        with open(path, "rb") as fh:
            files = {"files": (os.path.basename(path), fh, "application/pdf")}
            resp = httpx.post(url, data=data, files=files, headers=headers, timeout=settings.docling_timeout_seconds)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        warnings.append(f"docling-serve недоступен: {exc}")
        return [], warnings

    status = str(payload.get("status", "")).lower()
    md = (payload.get("document") or {}).get("md_content") or ""
    if status not in _OK_STATUSES or not md:
        warnings.append(f"docling-serve вернул status={status or 'нет'} без таблиц")
        return [], warnings
    rows = _rows_from_markdown(md)
    return rows, warnings


# --- local (docling в процессе) ---------------------------------------------

def _slice_pdf_first_pages(path: str, max_pages: int) -> str | None:
    """Вырезать первые max_pages страниц во временный PDF (PyMuPDF) — страховка от
    bad_alloc/7-минутных прогонов на длинных документах. None → срез не понадобился."""
    try:
        import fitz  # PyMuPDF

        src = fitz.open(path)
        if src.page_count <= max_pages:
            src.close()
            return None
        dst = fitz.open()
        dst.insert_pdf(src, from_page=0, to_page=max_pages - 1)
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        dst.save(tmp)
        dst.close()
        src.close()
        return tmp
    except Exception:  # noqa: BLE001 — не вышло урезать → отдаём исходный путь
        return None


def rows_from_pdf_docling_local(path: str) -> tuple[list[RawPriceRow], list[str]]:
    """In-process docling: do_ocr=False, do_table_structure=True, лимит страниц."""
    warnings: list[str] = []
    sliced = _slice_pdf_first_pages(path, settings.docling_max_pages)
    work_path = sliced or path
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = False               # обязательно: дефолтный RapidOCR падает на version-mismatch
        opts.do_table_structure = True
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
        result = converter.convert(work_path)
        doc = result.document

        rows: list[RawPriceRow] = []
        tables = getattr(doc, "tables", []) or []
        for table in tables:
            try:
                df = table.export_to_dataframe(doc)
            except TypeError:
                df = table.export_to_dataframe()      # старые версии — без аргумента
            matrix = [[str(c) for c in df.columns]] + [[str(c) for c in row] for row in df.values.tolist()]
            r, _w = rows_from_matrix(matrix)
            rows.extend(r)
        if sliced:
            warnings.append(f"docling-local: обработаны первые {settings.docling_max_pages} стр. (лимит)")
        warnings.append(f"docling-local: таблиц {len(tables)}, позиций {len(rows)}")
        return rows, warnings
    except Exception as exc:  # noqa: BLE001 — любой сбой модели → деградируем к LLM
        warnings.append(f"docling-local не сработал: {exc}")
        return [], warnings
    finally:
        if sliced and os.path.exists(sliced):
            try:
                os.remove(sliced)
            except OSError:
                pass


def rows_from_pdf_docling(path: str) -> tuple[list[RawPriceRow], list[str]]:
    """Диспетчер: если задан serve_url — пробует удалённый GPU-путь,
    в случае недоступности сервера (ошибки подключения/таймаут) переключается на локальный."""
    if settings.docling_serve_url:
        rows, warnings = rows_from_pdf_docling_remote(path, settings.docling_serve_url)
        # Если RunPod недоступен/выключен, переключаемся на локальное железо
        if not rows and any("docling-serve недоступен" in w for w in warnings):
            warnings.append("Удалённый сервер недоступен, автоматический переход на локальный Docling (CPU)...")
            local_rows, local_warnings = rows_from_pdf_docling_local(path)
            rows.extend(local_rows)
            warnings.extend(local_warnings)
        return rows, warnings
    return rows_from_pdf_docling_local(path)
