"""Конвертация валют в KZT по курсу на дату прайса.

Для MVP — статическая таблица курсов. В проде заменяется на источник курсов
(НБ РК API) с привязкой к дате; интерфейс convert_to_kzt при этом не меняется.
"""
from __future__ import annotations

from datetime import date

# Базовые курсы к KZT (упрощённо; для демо). Ключ — валюта.
_RATES_KZT = {
    "KZT": 1.0,
    "USD": 470.0,
    "RUB": 5.2,
}


def convert_to_kzt(amount: float | None, currency: str, on_date: date | None = None) -> float | None:
    """Сконвертировать сумму в KZT. on_date зарезервирован под исторические курсы."""
    if amount is None:
        return None
    rate = _RATES_KZT.get((currency or "KZT").upper(), 1.0)
    return round(amount * rate, 2)
