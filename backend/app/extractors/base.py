"""Базовый интерфейс извлечения + общие хелперы парсинга таблиц/цен.

Ядро системы не зависит от формата: каждый extractor возвращает ExtractResult
со списком RawPriceRow. Добавление нового формата = новый плагин, без правки ядра.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class RawPriceRow:
    service_name_raw: str
    price_resident: float | None = None
    price_nonresident: float | None = None
    price_original: float | None = None
    currency: str = "KZT"
    service_code_source: str | None = None


@dataclass
class ExtractResult:
    rows: list[RawPriceRow] = field(default_factory=list)
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)


class BaseExtractor(Protocol):
    def extract(self, path: str) -> ExtractResult: ...


# --- Определение колонок по ключевым словам ---------------------------------

_SERVICE_KW = ("услуг", "наименован", "название", "сервис", "анализ", "исследован", "service", "name")
_RESIDENT_KW = ("резидент",)
_NONRESIDENT_KW = ("нерезидент", "не резидент", "non-resident", "nonresident")
_PRICE_KW = ("цена", "стоимост", "тариф", "price", "kzt", "тенге", "сум")
_CODE_KW = ("код", "code", "артикул")


def _norm_header(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def classify_columns(headers: list[str]) -> dict[str, int]:
    """Сопоставить заголовки колонок с ролями. Возвращает {role: col_index}.

    Колонки-коды размечаем ПЕРВЫМ проходом и затем исключаем их из кандидатов
    на роль «услуга»: иначе заголовок вроде «Код услуги» (содержит и «код», и
    «услуг») ошибочно становится колонкой названия, и в названия попадают коды.
    """
    mapping: dict[str, int] = {}
    code_cols: set[int] = set()

    # 1. сначала коды
    for idx, raw in enumerate(headers):
        h = _norm_header(raw)
        if h and any(k in h for k in _CODE_KW):
            mapping.setdefault("code", idx)
            code_cols.add(idx)

    # 2. цены и услуга (на колонку-код услугу не вешаем)
    for idx, raw in enumerate(headers):
        h = _norm_header(raw)
        if not h:
            continue
        if any(k in h for k in _NONRESIDENT_KW):
            mapping.setdefault("price_nonresident", idx)
        elif any(k in h for k in _RESIDENT_KW):
            mapping.setdefault("price_resident", idx)
        elif any(k in h for k in _PRICE_KW):
            mapping.setdefault("price", idx)
        if idx not in code_cols and any(k in h for k in _SERVICE_KW):
            mapping.setdefault("service", idx)
    return mapping


def _looks_like_header(row: list[str]) -> bool:
    cols = classify_columns(row)
    if "service" not in cols:
        return False
    # цена должна быть в ОТДЕЛЬНОЙ от услуги колонке — иначе это строка-заголовок
    # документа («Прайс-лист медицинских услуг»), а не шапка таблицы.
    price_cols = {cols[k] for k in ("price", "price_resident", "price_nonresident") if k in cols}
    return any(c != cols["service"] for c in price_cols)


# --- Парсинг цены -----------------------------------------------------------

_CURRENCY_MAP = {
    "$": "USD", "usd": "USD", "долл": "USD",
    "₽": "RUB", "rub": "RUB", "руб": "RUB",
    "₸": "KZT", "kzt": "KZT", "тенге": "KZT", "тг": "KZT",
}


def detect_currency(text: str, default: str = "KZT") -> str:
    t = (text or "").lower()
    for key, cur in _CURRENCY_MAP.items():
        if key in t:
            return cur
    return default


def parse_price(value) -> float | None:
    """Извлечь число из ячейки прайса. '12 500,00 ₸' → 12500.0; '—' → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    # убрать пробелы (в т.ч. неразрывные) и всё кроме цифр/разделителей
    cleaned = re.sub(r"[^\d,.\-]", "", s.replace("\xa0", " ").replace(" ", ""))
    if not re.search(r"\d", cleaned):
        return None
    neg = cleaned.startswith("-")
    cleaned = cleaned.lstrip("-")

    if "," in cleaned and "." in cleaned:
        # оба разделителя: ПОСЛЕДНИЙ — десятичный, остальные — тысячные
        dec_sep = "." if cleaned.rfind(".") > cleaned.rfind(",") else ","
        thou_sep = "," if dec_sep == "." else "."
        cleaned = cleaned.replace(thou_sep, "").replace(dec_sep, ".")
    else:
        sep = "," if "," in cleaned else ("." if "." in cleaned else "")
        if sep:
            parts = cleaned.split(sep)
            if len(parts) > 2:
                cleaned = "".join(parts)              # несколько разделителей → тысячные
            elif len(parts[1]) == 3 and parts[0]:
                cleaned = parts[0] + parts[1]          # «10.002» → 10002 (тысячный)
            else:
                cleaned = parts[0] + "." + parts[1]    # «10.50» → 10.5 (десятичный)
    try:
        val = float(cleaned)
        return -val if neg else val
    except ValueError:
        return None


# --- Универсальная сборка строк из матрицы ----------------------------------

def rows_from_matrix(matrix: list[list[str]]) -> tuple[list[RawPriceRow], list[str]]:
    """Найти строку заголовков (не обязательно первую) и собрать RawPriceRow."""
    warnings: list[str] = []
    header_idx = None
    for i, row in enumerate(matrix[:25]):  # заголовок ищем в первых 25 строках
        cells = [str(c) if c is not None else "" for c in row]
        if _looks_like_header(cells):
            header_idx = i
            break
    if header_idx is None:
        warnings.append("Не найдена строка заголовков с колонками услуги и цены")
        return [], warnings

    cols = classify_columns([str(c) if c is not None else "" for c in matrix[header_idx]])
    service_col = cols.get("service")
    rows: list[RawPriceRow] = []
    for row in matrix[header_idx + 1:]:
        cells = [str(c).strip() if c is not None else "" for c in row]
        if service_col is None or service_col >= len(cells):
            continue
        name = cells[service_col].strip()
        if not name:
            continue
        pr = parse_price(cells[cols["price_resident"]]) if cols.get("price_resident") is not None and cols["price_resident"] < len(cells) else None
        pnr = parse_price(cells[cols["price_nonresident"]]) if cols.get("price_nonresident") is not None and cols["price_nonresident"] < len(cells) else None
        pgen = parse_price(cells[cols["price"]]) if cols.get("price") is not None and cols["price"] < len(cells) else None
        resident = pr if pr is not None else pgen
        if resident is None and pnr is None:
            continue  # строка без цены — пропускаем (заголовки секций и т.п.)
        code = cells[cols["code"]] if cols.get("code") is not None and cols["code"] < len(cells) else None
        cur = detect_currency(" ".join(cells))
        rows.append(RawPriceRow(
            service_name_raw=name,
            price_resident=resident,
            price_nonresident=pnr,
            price_original=resident if resident is not None else pnr,
            currency=cur,
            service_code_source=code or None,
        ))
    return rows, warnings


# --- Парсинг плоского текста (OCR / неструктурированный PDF) -----------------

_LINE_PRICE_RE = re.compile(r"^(?P<name>.+?)[\s.\-—]{2,}(?P<price>[\d\s.,]+)\s*(?:₸|тг|kzt|руб|₽|\$)?$", re.IGNORECASE)


def rows_from_text(text: str) -> tuple[list[RawPriceRow], list[str]]:
    """Грубый построчный парсер для OCR: 'Услуга .... 12 500'."""
    rows: list[RawPriceRow] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if len(line) < 4:
            continue
        m = _LINE_PRICE_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip(" .-—\t")
        price = parse_price(m.group("price"))
        if not name or price is None:
            continue
        rows.append(RawPriceRow(
            service_name_raw=name,
            price_resident=price,
            price_original=price,
            currency=detect_currency(line),
        ))
    return rows, []
