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

# Маркер обрезки документа по лимитам. runner ищет эту подстроку в warnings,
# чтобы пометить документ needs_review (явная, а не тихая потеря строк).
TRUNCATED_MARK = "ВНИМАНИЕ: ОБРЕЗАНО"

_SYSTEM_PROMPT = (
    "Ты — парсер прайс-листов медицинских клиник (язык: русский/казахский). "
    "Тебе дают текст или изображение страницы прайса (часто это плохой/кривой скан). "
    "Нужны ТОЛЬКО три поля на строку: название услуги, цена резидента, цена нерезидента. "
    "Извлеки КАЖДУЮ строку-услугу с ценой. Различай колонки 'резидент' и 'нерезидент' "
    "(иностранцы), если они есть. "
    "Если цена одна (без деления на резидент/нерезидент) — клади её в price_single. "
    "Сохраняй исходное название услуги как в документе, без перевода и сокращений. "
    "3. Игнорируй промежуточные итоги и примечания. Но ОБРАЩАЙ ВНИМАНИЕ на заголовки секций! "
    "Если название услуги слишком короткое или непонятное (например 'Лук', 'Свинина', 'IgG'), "
    "ОБЯЗАТЕЛЬНО добавь к нему заголовок секции, чтобы получилось осмысленное название (например 'Аллергопанель пищевая: Лук').\n"
    "4. В поля 'price_resident' и 'price_nonresident' пиши ТОЛЬКО цену. "
    "ВАЖНО: Если в строке есть код (например 1.2.3 или длинное число 330.037.007), он ДОЛЖЕН БЫТЬ в названии услуги или игнорироваться, но НЕ в цене! "
    "Цена за медуслугу редко превышает 2 000 000. Если ты видишь число в миллиардах (например 2782020865), это ОШИБКА — ты случайно захватил код услуги! "
    "Валюта по умолчанию KZT (тенге, ₸, тг); распознавай USD ($) и RUB (₽, руб). "
    "КРИТИЧНО ПРИ ПЛОХОМ СКАНЕ: НЕ ВЫДУМЫВАЙ. Если строка/цифры нечитаемы или ты не "
    "уверен в значении — пропусти эту строку целиком, не угадывай цену. Лучше вернуть "
    "меньше строк, но точных, чем много с ошибочными цифрами. Не приписывай услуге "
    "цену из соседней строки. Если на странице вообще нет таблицы услуг — верни пустой rows. "
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
    return settings.hf_api_key or settings.openai_api_key or os.environ.get("HF_TOKEN")


def llm_available() -> bool:
    """Включён ли LLM-фоллбэк: `use_llm_extraction=True` + есть ключ."""
    if not settings.use_llm_extraction:
        return False
    return bool(settings.openai_api_key) or bool(settings.hf_api_key)


def _client():
    from openai import OpenAI
    # Если есть OpenAI-ключ — используем его (или кастомный URL, если это OpenAI-совместимый эндпоинт типа RunPod/vLLM)
    if settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key, base_url=settings.llm_base_url)
    
    # Иначе — Hugging Face Serverless Inference API (Router)
    url = settings.llm_base_url or "https://router.huggingface.co/v1"
    return OpenAI(api_key=settings.hf_api_key, base_url=url)


# Модель по умолчанию, если не задана. 
# Используем мощную бесплатную модель на HF, так как Vision модели часто недоступны на Free Tier.
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"


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
    key = _api_key()
    model = "gpt-4o-mini" if key and key.startswith("sk-") else settings.llm_model
    kwargs: dict = {
        "model": model,
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
    # Символьный кап щедрый (1 млн ≈ 500 стр) — режем по чанкам, а не по символам.
    all_chunks = _chunk_text(text[:1_000_000])
    cap = max(1, settings.llm_max_chunks)
    chunks = all_chunks[:cap]
    all_rows: list[RawPriceRow] = []
    warnings: list[str] = [f"LLM-чанков: {len(chunks)}" + (
        f" из {len(all_chunks)}" if len(all_chunks) > len(chunks) else "")]
    if len(all_chunks) > cap:
        lost = 100 - cap * 100 // len(all_chunks)
        warnings.append(
            f"{TRUNCATED_MARK} текст: обработано {cap}/{len(all_chunks)} фрагментов "
            f"(~{lost}% позиций пропущено). Подними MEDARCHIVE_LLM_MAX_CHUNKS."
        )
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

    total_pages = len(doc)
    pages = min(total_pages, settings.llm_max_pages)
    dpi = settings.vision_ocr_dpi
    all_rows: list[RawPriceRow] = []
    warnings: list[str] = [f"vision-OCR страниц: {pages} (DPI {dpi}, постранично)"]
    if total_pages > pages:
        lost = 100 - pages * 100 // total_pages
        warnings.append(
            f"{TRUNCATED_MARK} скан: распознано {pages}/{total_pages} страниц "
            f"(~{lost}% потеряно). Подними MEDARCHIVE_LLM_MAX_PAGES."
        )
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
