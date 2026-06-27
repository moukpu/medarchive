"""Валидация позиций прайса по правилам ТЗ §4.4."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.config import settings
from app.extractors.base import RawPriceRow
from app.pipeline.fx import convert_to_kzt


@dataclass
class ValidationOutcome:
    skip: bool = False                 # пропустить строку (пустое название и т.п.)
    needs_review: bool = False         # требуется ручная проверка
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    price_original: float | None = None
    currency_original: str = "KZT"
    warnings: list[str] = field(default_factory=list)


def validate_row(
    row: RawPriceRow,
    effective: date | None,
    prev_resident_kzt: float | None = None,
) -> ValidationOutcome:
    """Применить проверки §4.4 к одной строке. prev_* — для детекта аномалии цены."""
    out = ValidationOutcome(currency_original=row.currency or "KZT")

    # Название услуги не пустое → иначе пропуск строки
    if not row.service_name_raw or not row.service_name_raw.strip():
        out.skip = True
        out.warnings.append("Пустое название услуги — строка пропущена")
        return out

    # Валюта не KZT → конвертировать, сохранить оригинал
    out.price_original = row.price_original if row.price_original is not None else row.price_resident
    res = row.price_resident
    nonres = row.price_nonresident
    if (row.currency or "KZT").upper() != "KZT":
        res = convert_to_kzt(res, row.currency, effective)
        nonres = convert_to_kzt(nonres, row.currency, effective)
        out.warnings.append(f"Валюта {row.currency} сконвертирована в KZT")
    out.price_resident_kzt = res
    out.price_nonresident_kzt = nonres

    # Цена > 0 и число
    if res is None and nonres is None:
        out.needs_review = True
        out.warnings.append("Цена не распознана")
    else:
        for label, val in (("резидент", res), ("нерезидент", nonres)):
            if val is not None and val <= 0:
                out.needs_review = True
                out.warnings.append(f"Некорректная цена ({label}): {val}")

    # Цена нерезидента >= цены резидента
    if res is not None and nonres is not None and nonres < res:
        out.needs_review = True
        out.warnings.append("Цена нерезидента меньше цены резидента")

    # Дата прайса не в будущем
    if effective and effective > date.today():
        out.warnings.append("Дата прайса в будущем")

    # Цена отличается от предыдущей версии > 50% → флаг аномалии
    if prev_resident_kzt and res is not None and prev_resident_kzt > 0:
        change = abs(res - prev_resident_kzt) / prev_resident_kzt
        if change > settings.price_anomaly_ratio:
            out.needs_review = True
            out.warnings.append(
                f"Аномалия цены: изменение {change:.0%} от предыдущей версии"
            )

    return out
