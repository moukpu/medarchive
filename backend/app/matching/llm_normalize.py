"""LLM как «скальпель» для нормализации грязных названий услуг (Fallback Loop).

Назначение — точечно (по одной строке) привести непонятное название к
общепринятому медицинскому термину, чтобы повторный векторный поиск нашёл
совпадение. Пример: «ОАК с лейк. фор.» → «Общий анализ крови развернутый».

ВАЖНО: это НЕ массовая отправка документа в LLM (это долго/дорого и режет
контекст — ошибки 429, потеря строк). Сюда попадают ТОЛЬКО строки, которые
embedding-тир не смог сматчить выше порога `embedding_match_threshold`.

Если LLM решает, что строка вообще не медицинская услуга («Договор оказания
услуг», «Итого», шапки) — возвращаем None: вызывающий помечает строку мусором
и откидывает.

Клиент и доступность переиспользуются из `app.extractors.llm` (тот же HF
Inference Router, OpenAI-совместимый). Без ключа модуль тихо деградирует:
`llm_normalize_name` возвращает исходную строку (не мусор), пайплайн жив.
"""
from __future__ import annotations

import json

from app.config import settings

_SYSTEM_PROMPT = (
    "Ты — нормализатор названий медицинских услуг (русский/казахский). "
    "Тебе дают ОДНУ сырую строку из прайс-листа клиники (возможно с сокращениями, "
    "опечатками, шумом OCR). Задачи: "
    "1) Определи, является ли это названием медицинской услуги/анализа/процедуры. "
    "2) Если да — приведи к общепринятому полному медицинскому термину "
    "(раскрой сокращения), сохраняя смысл. Пример: 'ОАК с лейк. фор.' → "
    "'Общий анализ крови развернутый'. Не добавляй цены, коды, примечания. "
    "Если это НЕ медицинская услуга (договор, итог, шапка, скидка, реквизиты) — "
    "пометь is_medical=false. "
    "Ответ СТРОГО JSON без обёрток: "
    '{"is_medical": true|false, "normalized": "..."}.'
)


def llm_normalize_name(raw: str) -> str | None:
    """Нормализовать одну строку через LLM.

    Возвращает:
      * нормализованный медицинский термин (str) — для повторного векторного поиска;
      * None — если LLM считает строку НЕ медицинской услугой (мусор → откинуть);
      * исходную строку — если LLM недоступен/ошибка (деградация без потери строк).
    """
    raw = (raw or "").strip()
    if not raw:
        return raw

    from app.extractors.llm import _client, llm_available

    if not llm_available():
        return raw

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Сырая строка: {raw}"},
    ]
    try:
        resp = _client().chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=256,
        )
        content = (resp.choices[0].message.content or "{}").strip()
        if content.startswith("```"):
            content = "\n".join(
                l for l in content.split("\n") if not l.strip().startswith("```")
            )
        payload = json.loads(content)
    except Exception:  # noqa: BLE001 — недоступность/невалидный JSON не валит пайплайн
        return raw

    if not payload.get("is_medical", True):
        return None
    normalized = (payload.get("normalized") or "").strip()
    return normalized or raw
