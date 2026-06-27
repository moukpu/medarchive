"""Нечёткое сопоставление через RapidFuzz."""
from __future__ import annotations

from rapidfuzz import fuzz, process


def best_fuzzy(name: str, choices: dict[str, str]) -> tuple[str | None, float]:
    """choices: {service_id: text}. Возвращает (service_id, score 0..1)."""
    if not choices:
        return None, 0.0
    result = process.extractOne(name, choices, scorer=fuzz.token_set_ratio)
    if result is None:
        return None, 0.0
    _matched_text, score, key = result
    return key, score / 100.0
