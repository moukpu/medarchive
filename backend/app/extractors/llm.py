"""LLM-извлечение через Hugging Face Inference Providers (OpenAI-совместимый API + vision).

Назначение — вытащить структурированные позиции прайса там, где детерминированный
парсер (regex/ключевые слова) бессилен: шумный OCR, нестандартные шапки, слитые
колонки, билингва рус/каз. Используется как:
  • fallback для текста (runner): если обычный extractor дал мало строк, отдаём
    сырой текст модели и получаем чистые строки;
  • vision-OCR для скан-PDF (pdf_scan): рендерим страницы в PNG и просим модель
    распознать таблицу напрямую — качественнее Tesseract на плохих сканах.

Использует openai SDK с кастомным base_url, направленным на HF Inference
Router (https://router.huggingface.co/v1). Бесплатный тир доступен.

Без ключа (`MEDARCHIVE_HF_API_KEY` / `HF_TOKEN`) модуль тихо
деградирует: `llm_available()` → False, функции возвращают пустой результат,
а пайплайн продолжает работать на Tesseract/regex.
"""
from __future__ import annotations

import base64
import json
import os
from functools import lru_cache

from app.config import settings
from app.extractors.base import RawPriceRow

# Валюты, поддерживаемые моделью данных (Currency enum). Прочее → KZT.
_ALLOWED_CURRENCY = {"KZT", "USD", "RUB"}

_SYSTEM_PROMPT = (
    "Ты — парсер прайс-листов медицинских клиник (язык: русский/казахский). "
    "Тебе дают текст или изображение страницы прайса. Извлеки КАЖДУЮ строку-услугу "
    "с ценой. Различай колонки 'резидент' и 'нерезидент', если они есть. "
    "Если цена одна (без деления на резидент/нерезидент) — клади её в price_single. "
    "Сохраняй исходное название услуги как в документе, без перевода и сокращений. "
    "Игнорируй заголовки секций, итоги, примечания и пустые строки без цены. "
    "Валюта по умолчанию KZT (тенге, ₸, тг); распознавай USD ($) и RUB (₽, руб). "
    "Числа — без пробелов-разделителей и валютных символов. "
    "ВАЖНО: ответ СТРОГО в формате JSON (без маркдаун-обёртки, без пояснений), "
    "структура: {\"rows\": [{\"service_name\": \"...\", \"price_resident\": число|null, "
    "\"price_nonresident\": число|null, \"price_single\": число|null, "
    "\"currency\": \"KZT\"|\"USD\"|\"RUB\", \"code\": \"...\"|null}, ...]}."
)

# JSON-схема для structured outputs (strict): модель обязана вернуть ровно это.
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "service_name": {"type": "string"},
                    "price_resident": {"type": ["number", "null"]},
                    "price_nonresident": {"type": ["number", "null"]},
                    "price_single": {"type": ["number", "null"]},
                    "currency": {"type": "string", "enum": ["KZT", "USD", "RUB"]},
                    "code": {"type": ["string", "null"]},
                },
                "required": [
                    "service_name",
                    "price_resident",
                    "price_nonresident",
                    "price_single",
                    "currency",
                    "code",
                ],
            },
        }
    },
    "required": ["rows"],
}


def _api_key() -> str | None:
    return settings.hf_api_key or os.environ.get("HF_TOKEN")


def llm_available() -> bool:
    """LLM-извлечение включено и есть HF-токен + установлен пакет openai."""
    if not settings.use_llm_extraction or not _api_key():
        return False
    try:
        import openai  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI(
        api_key=_api_key(),
        base_url=settings.llm_base_url,
    )


def _rows_from_payload(payload: dict) -> list[RawPriceRow]:
    """Преобразовать ответ модели в RawPriceRow с нормализацией валюты/цены."""
    rows: list[RawPriceRow] = []
    for r in payload.get("rows", []):
        name = (r.get("service_name") or "").strip()
        if not name:
            continue
        resident = r.get("price_resident")
        nonresident = r.get("price_nonresident")
        single = r.get("price_single")
        # если деления нет — единая цена идёт в резидента
        if resident is None and single is not None:
            resident = single
        if resident is None and nonresident is None:
            continue  # строка без цены — пропускаем
        currency = (r.get("currency") or "KZT").upper()
        if currency not in _ALLOWED_CURRENCY:
            currency = "KZT"
        base_price = resident if resident is not None else nonresident
        rows.append(
            RawPriceRow(
                service_name_raw=name,
                price_resident=resident,
                price_nonresident=nonresident,
                price_original=base_price,
                currency=currency,
                service_code_source=(r.get("code") or None),
            )
        )
    return rows


def _create(messages: list[dict], response_format: dict | None = None):
    """Вызов chat.completions через HF Inference Providers.

    HF router поддерживает response_format={"type": "json_object"} для
    большинства моделей. strict json_schema может не поддерживаться,
    поэтому используем json_object + схема в промпте.
    """
    kwargs: dict = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": 8192,
        "temperature": 0.1,
    }
    if response_format:
        kwargs["response_format"] = response_format
    return _client().chat.completions.create(**kwargs)


def _call(messages: list[dict]) -> tuple[list[RawPriceRow], list[str]]:
    """Один вызов модели. Сначала json_object, при ошибке — без формата
    (модель получает JSON-схему в промпте). Ошибки не валят пайплайн.
    """
    for response_format in ({"type": "json_object"}, None):
        try:
            resp = _create(messages, response_format)
            content = resp.choices[0].message.content or "{}"
            # Извлечь JSON из ответа (модель может обернуть в ```json ... ```)
            content = content.strip()
            if content.startswith("```"):
                # Убираем маркдаун-обёртку
                lines = content.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                content = "\n".join(lines)
            payload = json.loads(content)
            rows = _rows_from_payload(payload)
            return rows, [f"LLM ({settings.llm_model}) извлёк позиций: {len(rows)}"]
        except Exception as exc:  # noqa: BLE001
            last = exc
    return [], [f"LLM-извлечение не удалось: {last}"]


def _chunk_text(text: str, size: int = 8000, overlap: int = 500) -> list[str]:
    """Разбить большой текст на чанки с ПЕРЕКРЫТИЕМ по границам строк.

    Перекрытие нужно, чтобы многострочная услуга (название в конце чанка, цена
    в начале следующего) не разрывалась на обрывки: следующий чанк включает
    «хвост» предыдущего, а дубли потом убирает _dedup.
    """
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + size, n)
        # не резать посередине строки — дотянуть до ближайшего перевода строки
        nl = text.find("\n", end)
        if nl != -1 and nl - end < 300:
            end = nl
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def _dedup(rows: list[RawPriceRow]) -> list[RawPriceRow]:
    seen: set = set()
    out: list[RawPriceRow] = []
    for r in rows:
        key = (r.service_name_raw, r.price_resident, r.price_nonresident)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def rows_from_text_llm(text: str) -> tuple[list[RawPriceRow], list[str]]:
    """Структурировать сырой текст прайса через LLM с разбивкой на чанки.

    Большие документы (десятки страниц) не влезают в один ответ модели —
    разбиваем на чанки, обрабатываем каждый и склеиваем с дедупом.
    """
    text = (text or "").strip()
    if not text or not llm_available():
        return [], []
    chunks = _chunk_text(text[:200_000])[: settings.llm_max_chunks]
    all_rows: list[RawPriceRow] = []
    warnings: list[str] = [f"LLM-чанков: {len(chunks)}"]
    for ch in chunks:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT + " Верни JSON вида {\"rows\":[...]}."},
            {"role": "user", "content": f"Текст прайс-листа (фрагмент):\n\n{ch}"},
        ]
        rows, w = _call(messages)
        all_rows.extend(rows)
        warnings.extend(w)
    return _dedup(all_rows), warnings


def rows_from_pdf_images_llm(path: str) -> tuple[list[RawPriceRow], list[str]]:
    """Vision-OCR скан-PDF: рендерим страницы в PNG и распознаём таблицу моделью.

    Обработка ПОСТРАНИЧНАЯ (по одному изображению на вызов), а не пачкой: при
    длинном контексте VLM начинают пропускать позиции и обрывать таблицы, поэтому
    каждую страницу распознаём отдельным запросом, а результаты склеиваем с
    дедупом. Это надёжнее на многостраничных сканах ценой бóльшего числа вызовов.
    """
    if not llm_available():
        return [], []
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return [], ["PyMuPDF недоступен — vision-OCR пропущен"]

    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        return [], [f"Не удалось открыть PDF для vision-OCR: {exc}"]

    pages = min(len(doc), settings.llm_max_pages)
    dpi = settings.vision_ocr_dpi
    all_rows: list[RawPriceRow] = []
    warnings: list[str] = [f"vision-OCR страниц: {pages} (DPI {dpi}, постранично)"]
    for i in range(pages):
        pix = doc[i].get_pixmap(dpi=dpi)
        b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"Страница {i + 1} из {pages}. Распознай ВСЕ строки-услуги с "
                    "ценами из таблицы прайса на изображении и верни их."
                ),
            },
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
        rows, w = _call(messages)
        all_rows.extend(rows)
        warnings.append(f"стр. {i + 1}: {len(rows)}")
    doc.close()

    if pages == 0:
        return [], ["В PDF нет страниц для vision-OCR"]
    return _dedup(all_rows), warnings
