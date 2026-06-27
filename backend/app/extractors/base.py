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

    # 2. цены и услуга. Колонку-код НЕ назначаем ни ценой, ни услугой: заголовок
    # вроде «Код по тарифу» содержит и «код», и «тариф» — без этого исключения
    # код-колонка получает роль цены, и parse_price дробит код в число-миллионник.
    for idx, raw in enumerate(headers):
        h = _norm_header(raw)
        if not h or idx in code_cols:
            continue
        if any(k in h for k in _NONRESIDENT_KW):
            mapping.setdefault("price_nonresident", idx)
        elif any(k in h for k in _RESIDENT_KW):
            mapping.setdefault("price_resident", idx)
        elif any(k in h for k in _PRICE_KW):
            mapping.setdefault("price", idx)
        if any(k in h for k in _SERVICE_KW):
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

# Символьные маркеры валют (однозначные, не требуют word boundary)
_CURRENCY_SYMBOLS = {
    "$": "USD",
    "₽": "RUB",
    "₸": "KZT",
}

# Текстовые маркеры валют — матчим по word boundary, чтобы не ловить
# "руб" в "рубец", "rub" в "Anti-Rub IgG" и т.д.
_CURRENCY_WORDS = [
    (re.compile(r"\busd\b", re.IGNORECASE), "USD"),
    (re.compile(r"\bдолл", re.IGNORECASE), "USD"),
    (re.compile(r"(?<![-\w])rub(?![\w-])", re.IGNORECASE), "RUB"),
    (re.compile(r"(?<![-\w])руб(?![\w-])\.?", re.IGNORECASE), "RUB"),
    (re.compile(r"\bkzt\b", re.IGNORECASE), "KZT"),
    (re.compile(r"\bтенге\b", re.IGNORECASE), "KZT"),
    (re.compile(r"\bтг\b\.?", re.IGNORECASE), "KZT"),
]


def detect_currency(text: str, default: str = "KZT") -> str:
    t = text or ""
    # Сначала проверяем однозначные символы
    for sym, cur in _CURRENCY_SYMBOLS.items():
        if sym in t:
            return cur
    # Затем текстовые маркеры с word boundary
    for pattern, cur in _CURRENCY_WORDS:
        if pattern.search(t):
            return cur
    return default


# Дата (10.05.2024 / 5-12-24 / 2024.05.12) — НЕ цена. Без этого парсер склеивает
# разряды даты в число-миллионник (12.05.2024 → 12052024) и засоряет прайс.
_DATELIKE_RE = re.compile(r"\d{1,4}[.\-/]\d{1,2}[.\-/]\d{1,4}")


def parse_price(value) -> float | None:
    """Извлечь число из ячейки прайса. '12 500,00 ₸' → 12500.0; '—' → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    if _DATELIKE_RE.fullmatch(s.replace("\xa0", "").replace(" ", "")):
        return None  # это дата, а не цена
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


# --- Эвристика типов данных (когда шапки нет) -------------------------------

_NUM_CELL_RE = re.compile(r"^[\d\s.,]+$")
_FRAGMENT_RE = re.compile(r"0{2,3}")        # «тысячный» обрывок ячейки: 00 / 000
_HEAD_FRAGMENT_RE = re.compile(r"\d{1,3}")  # старшие разряды до обрыва: 15 / 150
# Валютные маркеры, которые можно снять перед проверкой «ячейка — число».
# Иначе колонка цен вида «12 000 ₸» не распознаётся как числовая и вся таблица
# без шапки теряется.
_CURRENCY_STRIP_RE = re.compile(
    r"[₸₽$€]|\b(?:тг|тенге|kzt|руб|rub|usd|eur|сум|сом)\b\.?", re.IGNORECASE
)
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)  # любая буква (рус/каз/лат)


def _is_text_cell(s: str) -> bool:
    """Ячейка-«услуга»: содержит буквы и не является числом.

    Длину НЕ требуем большой — реальные прайсы полны коротких названий
    («ЭКГ», «МРТ мозга»), и жёсткий порог по длине ронял бы всю колонку.
    """
    s = (s or "").strip()
    if len(s) < 3 or _is_num_cell(s):
        return False
    return bool(_LETTER_RE.search(s))


def _is_num_cell(s: str) -> bool:
    """Ячейка — число (в т.ч. формат `XX XXX` и с валютным суффиксом `12 000 ₸`).

    Даты (`10.05.2024`) исключаем — иначе колонка дат принимается за колонку цен.
    """
    s = (s or "").strip().replace("\xa0", " ")
    if not s:
        return False
    if _DATELIKE_RE.fullmatch(s.replace(" ", "")):
        return False
    core = _CURRENCY_STRIP_RE.sub("", s).strip()
    if not core or not any(c.isdigit() for c in core):
        return False
    return bool(_NUM_CELL_RE.match(core))


def _infer_columns_by_content(
    matrix: list[list[str]], sample: int = 10
) -> dict[str, int] | None:
    """Назначить колонки по типам данных, если шапки нет.

    Берём срез первых непустых строк. Колонка с долей длинного текста ≥ 0.9 →
    `service`; колонка с долей чисел ≥ 0.6 (и не служебная) → `price`.
    """
    sample_rows: list[list[str]] = []
    for row in matrix:
        cells = [str(c).strip() if c is not None else "" for c in row]
        if any(cells):
            sample_rows.append(cells)
        if len(sample_rows) >= sample:
            break
    if len(sample_rows) < 3:
        return None

    ncols = max(len(r) for r in sample_rows)
    text_frac = [0.0] * ncols
    num_frac = [0.0] * ncols
    for col in range(ncols):
        vals = [r[col] for r in sample_rows if col < len(r) and r[col]]
        if not vals:
            continue
        text_frac[col] = sum(_is_text_cell(v) for v in vals) / len(vals)
        num_frac[col] = sum(_is_num_cell(v) for v in vals) / len(vals)

    # «услуга» — самая текстовая колонка, где текст уверенно преобладает над числами
    service_col = max(range(ncols), key=lambda c: text_frac[c])
    if text_frac[service_col] < 0.7 or text_frac[service_col] <= num_frac[service_col]:
        return None
    # «цена» — самая числовая из ОСТАЛЬНЫХ, где числа преобладают над текстом
    price_candidates = [
        c for c in range(ncols)
        if c != service_col and num_frac[c] >= 0.6 and num_frac[c] > text_frac[c]
    ]
    if not price_candidates:
        return None
    price_col = max(price_candidates, key=lambda c: num_frac[c])
    return {"service": service_col, "price": price_col}


# --- Склейка разорванных по ячейкам цен -------------------------------------

def _glue_fragments(cells: list[str], col: int) -> str:
    """Склеить тысячи, разбитые на соседние ячейки: '15' | '000' → '15000'.

    Excel часто бьёт разряд по столбцам. Если текущая ячейка — обрывок `00`/`000`,
    приклеиваем её к предыдущей; если обрывок в следующей — приклеиваем к текущей.
    """
    if col < 0 or col >= len(cells):
        return ""
    cur = (cells[col] or "").strip().replace("\xa0", " ")
    prev = (cells[col - 1] or "").strip() if col - 1 >= 0 else ""
    nxt = (cells[col + 1] or "").strip() if col + 1 < len(cells) else ""
    if _FRAGMENT_RE.fullmatch(cur) and _HEAD_FRAGMENT_RE.fullmatch(prev):
        return prev + cur
    if _HEAD_FRAGMENT_RE.fullmatch(cur.replace(" ", "")) and _FRAGMENT_RE.fullmatch(nxt):
        return cur + nxt
    return cur


def _read_price(cells: list[str], idx: int | None) -> float | None:
    if idx is None or idx >= len(cells):
        return None
    return parse_price(_glue_fragments(cells, idx))


# --- Поиск ценовой колонки по контенту (шапка-цена съехала / двухстрочная) ---

def _looks_like_index(vals: list[float]) -> bool:
    """Похоже на колонку «№ п/п»: подряд идущие целые 1,2,3,… — это не цена."""
    ints = [v for v in vals if v is not None and float(v).is_integer()]
    if len(ints) < 3:
        return False
    seq = ints[:6]
    return seq[0] in (0, 1) and all(b - a == 1 for a, b in zip(seq, seq[1:]))


def _infer_price_col(
    data: list[list[str]], exclude: set[int], sample: int = 30
) -> int | None:
    """Найти ценовую колонку среди данных, когда шапка её не назвала.

    Берём числовую колонку (доля чисел ≥ 0.6), исключая `service`/`code` и
    колонку-нумерацию (№ п/п). Из кандидатов выбираем с наибольшей медианой
    значения — цены крупнее порядкового номера/количества.
    """
    stats: dict[int, list[float]] = {}
    counts: dict[int, int] = {}
    seen = 0
    for row in data:
        cells = [str(c).strip() if c is not None else "" for c in row]
        if not any(cells):
            continue
        for col, v in enumerate(cells):
            if col in exclude or not v:
                continue
            counts[col] = counts.get(col, 0) + 1
            if _is_num_cell(v):
                p = parse_price(v)
                if p is not None:
                    stats.setdefault(col, []).append(p)
        seen += 1
        if seen >= sample:
            break

    best, best_median = None, -1.0
    for col, vals in stats.items():
        total = counts.get(col, 0)
        if not total or len(vals) / total < 0.6:
            continue
        if _looks_like_index(vals):
            continue
        median = sorted(vals)[len(vals) // 2]
        if median > best_median:
            best, best_median = col, median
    return best


def _merge_header_rows(matrix: list[list[str]], i: int, span: int) -> list[str]:
    """Склеить span подряд строк в одну шапку (двухстрочные заголовки).

    На колонку берём первую непустую ячейку сверху вниз — так подзаголовок
    «Утв. тариф…», уехавший во вторую строку, попадает в ту же колонку.
    """
    block = [
        [str(c).strip() if c is not None else "" for c in matrix[j]]
        for j in range(i, min(i + span, len(matrix)))
    ]
    ncols = max((len(r) for r in block), default=0)
    merged: list[str] = []
    for col in range(ncols):
        val = ""
        for r in block:
            if col < len(r) and r[col]:
                val = r[col]
                break
        merged.append(val)
    return merged


def _is_header_cols(cols: dict[str, int]) -> bool:
    """Это шапка таблицы? Есть «услуга» и в ДРУГОЙ колонке — цена или код.

    Требование цены/кода (а не только «услуги») отсекает строки-титулы вроде
    «Цены на медицинские услуги» (одна ячейка со словом «услуг»). Слова «код»/
    «цена» встречаются в шапках, но не в значениях данных, поэтому ложаков мало.
    """
    if "service" not in cols:
        return False
    s = cols["service"]
    price_cols = {cols[k] for k in ("price", "price_resident", "price_nonresident") if k in cols}
    if any(c != s for c in price_cols):
        return True
    return "code" in cols and cols["code"] != s


def _text_frac(data: list[list[str]], col: int, sample: int = 40) -> float:
    text = total = 0
    for row in data[:sample]:
        cells = [str(c).strip() if c is not None else "" for c in row]
        if col < len(cells) and cells[col]:
            total += 1
            text += _is_text_cell(cells[col])
    return text / total if total else 0.0


def _fix_service_col(cols: dict[str, int], data: list[list[str]]) -> None:
    """Перевесить роль «услуга» на реально текстовую колонку.

    Из-за съехавших шапок «услугой» иногда становится колонка № п/п (числа) —
    тогда в названия попадают порядковые номера. Если данные текущей service-
    колонки не текстовые, ищем самую текстовую колонку (кроме цены/кода).
    """
    s = cols.get("service")
    if s is not None and _text_frac(data, s) >= 0.5:
        return
    exclude = {cols[k] for k in ("price", "price_resident", "price_nonresident", "code") if k in cols}
    ncols = max((len(r) for r in data[:40]), default=0)
    best, best_frac = None, 0.0
    for col in range(ncols):
        if col in exclude:
            continue
        frac = _text_frac(data, col)
        if frac >= 0.5 and frac > best_frac:
            best, best_frac = col, frac
    if best is not None:
        cols["service"] = best


def _drop_nonnumeric_price_cols(cols: dict[str, int], data: list[list[str]]) -> None:
    """Снять ценовые роли с колонок, чьи ДАННЫЕ на деле не числовые.

    Из-за merged-ячеек заголовок «Цена (тариф)» нередко стоит над колонкой кодов
    («A02.004.000.1»). Если в колонке < 50% чисел — это не цена, роль убираем,
    а настоящую ценовую колонку потом находит `_infer_price_col`.
    """
    for role in ("price", "price_resident", "price_nonresident"):
        col = cols.get(role)
        if col is None:
            continue
        num = total = 0
        for row in data[:40]:
            cells = [str(c).strip() if c is not None else "" for c in row]
            if col < len(cells) and cells[col]:
                total += 1
                num += _is_num_cell(cells[col])
        if total and num / total < 0.5:
            del cols[role]


# --- Универсальная сборка строк из матрицы ----------------------------------

# Строки-разделители прайса («Раздел 1. Консультации», «Глава II …») — не услуги.
# Без отсева номер раздела утекает в цену (price=1.0), а текст — в колонку кода.
_SECTION_RE = re.compile(r"^\s*(раздел|подраздел|глава|часть)\b", re.IGNORECASE)


def _build_rows(data: list[list[str]], cols: dict[str, int]) -> list[RawPriceRow]:
    service_col = cols.get("service")
    rows: list[RawPriceRow] = []
    for row in data:
        cells = [str(c).strip() if c is not None else "" for c in row]
        if service_col is None or service_col >= len(cells):
            continue
        name = cells[service_col].strip()
        if not name or _SECTION_RE.match(name):
            continue
        pr = _read_price(cells, cols.get("price_resident"))
        pnr = _read_price(cells, cols.get("price_nonresident"))
        pgen = _read_price(cells, cols.get("price"))
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
    return rows


def rows_from_matrix(matrix: list[list[str]]) -> tuple[list[RawPriceRow], list[str]]:
    """Собрать RawPriceRow из матрицы.

    1. Ищем строку заголовков (по ключевым словам) в первых 25 строках.
    2. Если шапки нет — переходим к эвристике типов данных по контенту.
    """
    warnings: list[str] = []
    header_idx = None
    header_span = 1
    cols: dict[str, int] | None = None
    # 1. одиночная строка-шапка: услуга + (цена ИЛИ код) в разных колонках
    for i, row in enumerate(matrix[:25]):
        c = classify_columns([str(x) if x is not None else "" for x in row])
        if _is_header_cols(c):
            header_idx, header_span, cols = i, 1, c
            break
    # 2. фоллбэк — двухстрочная шапка (подзаголовок цены уехал в след. строку)
    if header_idx is None:
        for i in range(min(24, len(matrix) - 1)):
            merged = _merge_header_rows(matrix, i, 2)
            c = classify_columns(merged)
            if _is_header_cols(c):
                header_idx, header_span, cols = i, 2, c
                break

    if header_idx is not None and cols is not None:
        data = matrix[header_idx + header_span:]
        # Снять «ложные» ценовые колонки (заголовок «Цена» над колонкой кодов).
        _drop_nonnumeric_price_cols(cols, data)
        # Услугу — на реально текстовую колонку (а не № п/п).
        _fix_service_col(cols, data)
        # Цена так и не определена → ищем числовую колонку по контенту данных.
        price_roles = {"price", "price_resident", "price_nonresident"}
        if "service" in cols and not (price_roles & cols.keys()):
            exclude = {cols[k] for k in ("service", "code") if k in cols}
            pcol = _infer_price_col(data, exclude)
            if pcol is not None:
                cols["price"] = pcol
                warnings.append("Цена определена по контенту (заголовок не совпал с данными)")
    else:
        cols = _infer_columns_by_content(matrix)
        if not cols:
            warnings.append("Не найдена шапка и не удалось определить колонки по типам данных")
            return [], warnings
        warnings.append("Шапка не найдена — колонки определены эвристикой по типам данных")
        data = matrix

    return _build_rows(data, cols), warnings


# --- Парсинг плоского текста (OCR / неструктурированный PDF) -----------------

# Цена — это ТРАЙЛИНГ-число в конце строки. Класс группы цены не содержит букв,
# поэтому числа внутри названия ("УЗИ 3 триместра 12000") в цену не попадают:
# движок откатывает name вправо, пока цена не дотянется до конца строки.
_LINE_PRICE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<price>\d[\d\s.,]*\d|\d)\s*"
    r"(?:₸|тг|тенге|kzt|руб|₽|\$)?[\s.;:)]*$",
    re.IGNORECASE,
)
def rows_from_text(text: str) -> tuple[list[RawPriceRow], list[str]]:
    """Грубый построчный парсер для OCR: 'Услуга .... 12 500'.

    Цена берётся ИЗ КОНЦА строки; название должно содержать хотя бы одну букву
    (чисто числовые строки — итоги/нумерация — отбрасываются).
    """
    rows: list[RawPriceRow] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if len(line) < 4:
            continue
        m = _LINE_PRICE_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip(" .-—\t")
        if not name or not _LETTER_RE.search(name):
            continue
        price = parse_price(m.group("price"))
        if price is None:
            continue
        rows.append(RawPriceRow(
            service_name_raw=name,
            price_resident=price,
            price_original=price,
            currency=detect_currency(line),
        ))
    return rows, []
