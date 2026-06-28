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
_NONRESIDENT_KW = ("нерезидент", "не резидент", "non-resident", "nonresident", "иностран")
_PRICE_KW = ("цена", "стоимост", "тариф", "price", "kzt", "тенге", "сум")
_CODE_KW = ("код", "code", "артикул")
# Ключевые слова колонки порядковых номеров — ЯВНО исключаем из кандидатов
# на цену/услугу. Без этого колонка «№ п/п» ловит тысячи ложных «цен».
_INDEX_KW = ("№", "п/п", "n/n", "номер", "#", "row", "item")


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
    index_cols: set[int] = set()  # колонки-номера (№ п/п)

    # 0. сначала колонки-нумерации (№ п/п, #)
    for idx, raw in enumerate(headers):
        h = _norm_header(raw)
        if h and any(k in h for k in _INDEX_KW):
            # «№ п/п» — точно не цена и не услуга
            index_cols.add(idx)

    # 1. затем коды
    for idx, raw in enumerate(headers):
        h = _norm_header(raw)
        if h and idx not in index_cols and any(k in h for k in _CODE_KW):
            mapping.setdefault("code", idx)
            code_cols.add(idx)

    # 2. цены и услуга. Колонку-код и колонку-нумерацию НЕ назначаем ни ценой,
    # ни услугой: заголовок вроде «Код по тарифу» содержит и «код», и «тариф» —
    # без этого исключения код-колонка получает роль цены.
    skip_cols = code_cols | index_cols
    for idx, raw in enumerate(headers):
        h = _norm_header(raw)
        if not h or idx in skip_cols:
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
        # Если цена больше 20 млн (нереалистично для медицины) - это 100% склейка кода и цены или нескольких цен.
        # Например, 2782020865 (код 2782.020 + цена 865) или 250028003200 (цены 2500, 2800, 3200).
        if abs(val) > 20_000_000:
            s_val = str(int(abs(val)))
            # Если это слипшиеся цены (например 250028003200), логично брать первую (2500), 
            # так как она обычно соответствует базовой цене (резиденту).
            m = re.search(r'^([1-9]\d{2,4})', s_val)
            if m:
                val = float(m.group(1))
            else:
                # Если в начале не нашлось (например, код начинался с нулей или это странный формат), ищем в конце
                m = re.search(r'([1-9]\d{2,4})$', s_val)
                if m:
                    val = float(m.group(1))
                else:
                    return None
        return -val if neg else val
    except ValueError:
        return None


# --- Эвристика типов данных (когда шапки нет) -------------------------------

# Минимальная правдоподобная цена за мед. услугу (KZT).
# Реальные прайсы: даже самый дешёвый анализ стоит ≥ 200 ₸.
# Ниже — почти наверняка номер строки / код / мусор парсинга.
_MIN_PLAUSIBLE_PRICE = 200

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

    def service_score(col: int) -> tuple[float, float, float]:
        vals = [r[col].strip() for r in sample_rows if col < len(r) and r[col].strip()]
        if not vals:
            return (0.0, 0.0, 0.0)
        avg_len = sum(len(v) for v in vals) / len(vals)
        unique_ratio = len(set(vals)) / len(vals)
        return (text_frac[col], unique_ratio, avg_len)

    # «услуга» — самая текстовая колонка. При равенстве выигрывает более разнообразная и длинная (реальные названия)
    service_col = max(range(ncols), key=service_score)
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
    """Колонка — порядковый номер (№ п/п), а не цена.

    Расширенные проверки:
    1. Строго последовательные (1,2,3...) → точно индекс.
    2. Монотонно возрастающие целые с маленьким шагом (1,2,5,8,...) → индекс.
    3. Все значения ≤ 500 и монотонно возрастают → индекс с пропусками.
    4. Все значения — маленькие целые (< MIN_PLAUSIBLE_PRICE) → вряд ли цена.
    """
    ints = [v for v in vals if v is not None and float(v).is_integer()]
    if len(ints) < 3:
        return False
    seq = ints[:12]

    # 1. Классика: строгая последовательность 1,2,3,...
    if seq[0] in (0, 1) and all(b - a == 1 for a, b in zip(seq, seq[1:])):
        return True

    # 2. Монотонно возрастающие целые с маленьким шагом (≤5)
    #    и стартуют от маленького числа — типично для «№ п/п» с пропусками
    if seq[0] <= 10 and all(0 < b - a <= 5 for a, b in zip(seq, seq[1:])):
        return True

    # 3. Все целые, ≤ 500, и МОНОТОННО ВОЗРАСТАЮТ — индекс с большими пропусками
    if (all(0 < v <= 500 for v in seq)
            and all(b > a for a, b in zip(seq, seq[1:]))):
        return True

    # 4. Все значения < MIN_PLAUSIBLE_PRICE и все целые → вряд ли мед. цены
    if all(0 < v < _MIN_PLAUSIBLE_PRICE for v in seq):
        return True

    return False


def _looks_like_price_column(vals: list[float]) -> bool:
    """Значения похожи на цены мед. услуг, а не на порядковые номера/коды.

    Если > 50% значений < MIN_PLAUSIBLE_PRICE — это скорее номера/коды.
    Также отсекаем колонки, где все значения — маленькие монотонные целые.
    """
    clean = [v for v in vals if v is not None and v > 0]
    if len(clean) < 3:
        return False
    # Если > 50% значений < MIN_PLAUSIBLE_PRICE — не цены
    low = sum(1 for v in clean if v < _MIN_PLAUSIBLE_PRICE)
    if low / len(clean) > 0.5:
        return False
    return True


def _infer_price_col(
    data: list[list[str]], exclude: set[int], sample: int = 30
) -> int | None:
    """Найти ценовую колонку среди данных, когда шапка её не назвала.

    Берём числовую колонку (доля чисел ≥ 0.6), исключая `service`/`code` и
    колонку-нумерацию (№ п/п). Из кандидатов выбираем с наибольшей медианой
    значения — цены крупнее порядкового номера/количества. Дополнительно
    проверяем, что колонка-кандидат содержит правдоподобные цены (≥ 200 ₸).
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
        # Новая проверка: колонка должна содержать правдоподобные цены
        if not _looks_like_price_column(vals):
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

# Чисто цифровое значение (возможно с пробелами/точками) — НЕ название услуги.
# Ловит: «2», «15.3», «1 234», «001.002.003» (коды), «123456».
_PURE_NUMBER_RE = re.compile(r"^[\d\s.,\-/]+$")

# Мусорные строки: метаданные документа, шапки, итоги, реквизиты — не услуги.
# Матчим по НАЧАЛУ строки: если строка начинается с любого из паттернов — мусор.
_METADATA_RE = re.compile(
    r"^\s*("
    r"итого|всего|итог|total|subtotal|подитог"
    r"|примечан|прайс\s*-?\s*лист|price\s*-?\s*list"
    r"|дата\b|date\b|тариф утв|утвержд"
    r"|договор|контракт|реквизит|адрес\b|телефон|email|e-mail|www\."
    r"|\*{2,}|скидк|акци"
    r")",
    re.IGNORECASE,
)

# Мед. код (A02.004.001, B03.015.002) — не название услуги, это код.
_MED_CODE_RE = re.compile(r"^[A-Z]\d{2}\.\d{3}(\.\d{3})?$", re.IGNORECASE)


def _is_garbage_service_name(name: str) -> bool:
    """Проверить, что строка НЕ является реальным названием мед. услуги.

    Отсекает:
    - Чисто цифровые значения (номера строк, коды)
    - Слишком короткие строки без букв
    - Разделители секций
    - Мед. коды (A02.004.001)
    - Метаданные (итого, примечание, дата, адрес...)
    """
    s = (name or "").strip()
    if not s:
        return True
    # Чистое число (порядковый номер, код)
    if _PURE_NUMBER_RE.fullmatch(s):
        return True
    # Нет ни одной буквы
    if not _LETTER_RE.search(s):
        return True
    # Мед. код (не название)
    if _MED_CODE_RE.fullmatch(s):
        return True
    # Раздел/секция
    if _SECTION_RE.match(s):
        return True
    # Метаданные (итого, примечание, прайс-лист...)
    if _METADATA_RE.match(s):
        return True
    # Слишком короткая строка (1 символ) — не может быть названием
    if len(s) < 2:
        return True
    return False


def _build_rows(data: list[list[str]], cols: dict[str, int]) -> list[RawPriceRow]:
    service_col = cols.get("service")
    rows: list[RawPriceRow] = []
    current_section = ""
    for row in data:
        cells = [str(c).strip() if c is not None else "" for c in row]
        if service_col is None or service_col >= len(cells):
            continue
        name = cells[service_col].strip()
        if _is_garbage_service_name(name):
            continue
        pr = _read_price(cells, cols.get("price_resident"))
        pnr = _read_price(cells, cols.get("price_nonresident"))
        pgen = _read_price(cells, cols.get("price"))
        resident = pr if pr is not None else pgen
        
        if resident is None and pnr is None:
            # строка без цены — возможно, заголовок секции!
            # Если это осмысленный текст (и не слишком длинный абзац), запоминаем его.
            if 3 < len(name) < 100 and not _is_garbage_service_name(name):
                current_section = name
            continue

        code = cells[cols["code"]] if cols.get("code") is not None and cols["code"] < len(cells) else None
        cur = detect_currency(" ".join(cells))
        
        # Предотвращаем потерю контекста для коротких названий (например "свинина", "ИФА")
        final_name = name
        if current_section and len(name) < 40 and name.lower() not in current_section.lower():
            if len(name) < 15 or "панель" in current_section.lower() or "аллерг" in current_section.lower():
                final_name = f"{current_section}: {name}"

        rows.append(RawPriceRow(
            service_name_raw=final_name,
            price_resident=resident,
            price_nonresident=pnr,
            price_original=resident if resident is not None else pnr,
            currency=cur,
            service_code_source=code or None,
        ))
    return rows


def _sanity_check_prices(
    rows: list[RawPriceRow], warnings: list[str]
) -> tuple[list[RawPriceRow], list[str]]:
    """Многоуровневая пост-проверка результата парсинга.

    Эшелоны защиты:
    1. Массовые низкие цены (>60% < 200₸) → номера строк в цене
    2. Последовательные цены (1,2,3... или монотонные) → индексы
    3. Цены-клоны (>80% одинаковые) → неверная колонка
    4. Слишком низкая дисперсия (std/mean < 0.1) → подозрительно
    5. Мусорные service_name (>50% — числа/коды) → неверная колонка services
    """
    if not rows:
        return rows, warnings
    n = len(rows)

    # --- Эшелон 1: массовые низкие цены ---
    prices: list[float] = []
    low = 0
    for r in rows:
        price = r.price_resident if r.price_resident is not None else r.price_nonresident
        if price is not None:
            prices.append(price)
            if price < _MIN_PLAUSIBLE_PRICE:
                low += 1
    if prices and low / len(prices) > 0.6:
        warnings.append(
            f"Sanity check [низкие цены]: {low}/{len(prices)} ({low*100//len(prices)}%) "
            f"цен < {_MIN_PLAUSIBLE_PRICE} ₸ → сброс для LLM-фоллбэка."
        )
        return [], warnings

    # --- Эшелон 2: последовательные цены (монотонно возрастающие целые) ---
    if len(prices) >= 5:
        int_prices = [p for p in prices if float(p).is_integer() and p > 0]
        if len(int_prices) >= 5:
            sample = int_prices[:20]
            # Строго последовательные (1,2,3,...)
            if (sample[0] <= 5
                    and all(b - a >= 0 and b - a <= 3 for a, b in zip(sample, sample[1:]))):
                warnings.append(
                    "Sanity check [последовательные]: цены выглядят как "
                    f"порядковые номера ({sample[:5]}...) → сброс."
                )
                return [], warnings
            # Монотонно возрастающие маленькие целые
            if (all(0 < p < 500 for p in sample)
                    and all(b >= a for a, b in zip(sample, sample[1:]))):
                warnings.append(
                    "Sanity check [монотонные]: цены монотонно возрастают в диапазоне "
                    f"{min(sample):.0f}–{max(sample):.0f} → сброс."
                )
                return [], warnings

    # --- Эшелон 3: цены-клоны (>80% одинаковые) ---
    if len(prices) >= 5:
        from collections import Counter
        freq = Counter(prices)
        most_common_count = freq.most_common(1)[0][1]
        if most_common_count / len(prices) > 0.8:
            warnings.append(
                f"Sanity check [клоны]: {most_common_count}/{len(prices)} цен одинаковые "
                f"({freq.most_common(1)[0][0]}) → сброс."
            )
            return [], warnings

    # --- Эшелон 4: слишком низкая дисперсия ---
    if len(prices) >= 10:
        mean = sum(prices) / len(prices)
        if mean > 0:
            variance = sum((p - mean) ** 2 for p in prices) / len(prices)
            std = variance ** 0.5
            cv = std / mean  # коэффициент вариации
            if cv < 0.05 and mean < _MIN_PLAUSIBLE_PRICE:
                # Все цены кучкуются вокруг маленького значения
                warnings.append(
                    f"Sanity check [дисперсия]: mean={mean:.0f}, std={std:.1f}, "
                    f"CV={cv:.2f} → все цены ≈{mean:.0f} ₸ → сброс."
                )
                return [], warnings

    # --- Эшелон 5: мусорные названия услуг ---
    garbage_names = sum(1 for r in rows if _is_garbage_service_name(r.service_name_raw))
    if garbage_names / n > 0.5:
        warnings.append(
            f"Sanity check [названия]: {garbage_names}/{n} ({garbage_names*100//n}%) "
            "названий — мусор (числа/коды/метаданные) → сброс."
        )
        return [], warnings

    # --- Эшелон 6: дубликаты названий (выбрана неверная колонка) ---
    if len(rows) >= 10:
        from collections import Counter
        names = [r.service_name_raw.strip() for r in rows if r.service_name_raw]
        if names:
            name_freq = Counter(names)
            most_common_name, count = name_freq.most_common(1)[0]
            unique_ratio = len(name_freq) / len(names)
            # Если уникальных названий слишком мало (<30%), или самое частое повторяется >30% раз
            if unique_ratio < 0.3 or (count >= 5 and count / len(names) > 0.3):
                warnings.append(
                    f"Sanity check [дубликаты имен]: слишком много одинаковых названий "
                    f"('{most_common_name}' x{count}, уникальных {unique_ratio:.0%}) → сброс."
                )
                return [], warnings

    return rows, warnings


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

    rows = _build_rows(data, cols)
    return _sanity_check_prices(rows, warnings)


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
    return _sanity_check_prices(rows, [])
