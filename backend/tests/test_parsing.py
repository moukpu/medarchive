"""Юнит-тесты чистых функций извлечения (без БД и тяжёлых зависимостей)."""
from app.extractors.base import (
    classify_columns,
    detect_currency,
    parse_price,
    rows_from_matrix,
    rows_from_text,
    _looks_like_index,
    _looks_like_price_column,
    _sanity_check_prices,
    _is_garbage_service_name,
    _MIN_PLAUSIBLE_PRICE,
    RawPriceRow,
)


# === Базовые тесты (оригинальные) ===

def test_parse_price_variants():
    assert parse_price("12 500,00 ₸") == 12500.0
    assert parse_price("1 234.56") == 1234.56
    assert parse_price("12,500.00") == 12500.0
    assert parse_price("—") is None
    assert parse_price("") is None
    assert parse_price(5000) == 5000.0


def test_detect_currency():
    assert detect_currency("1000 ₸") == "KZT"
    assert detect_currency("50 USD") == "USD"
    assert detect_currency("300 руб") == "RUB"
    assert detect_currency("1000") == "KZT"


def test_classify_columns():
    cols = classify_columns(["Наименование услуги", "Цена резидент", "Цена нерезидент", "Код"])
    assert cols["service"] == 0
    assert cols["price_resident"] == 1
    assert cols["price_nonresident"] == 2
    assert cols["code"] == 3


def test_rows_from_matrix_header_not_first():
    matrix = [
        ["Прайс-лист клиники", "", ""],
        ["Услуга", "Цена резидент", "Цена нерезидент"],
        ["Общий анализ крови", "2 500", "3 000"],
        ["", "", ""],
        ["Консультация терапевта", "5 000", ""],
    ]
    rows, warnings = rows_from_matrix(matrix)
    assert len(rows) == 2
    assert rows[0].service_name_raw == "Общий анализ крови"
    assert rows[0].price_resident == 2500.0
    assert rows[0].price_nonresident == 3000.0
    assert rows[1].price_resident == 5000.0


def test_rows_from_text_ocr():
    text = "Общий анализ крови .......... 2 500\nКонсультация врача -- 5000 ₸\nмусор"
    rows, _ = rows_from_text(text)
    names = {r.service_name_raw for r in rows}
    assert "Общий анализ крови" in names


# === Тесты _looks_like_index ===

def test_looks_like_index_strict_sequence():
    assert _looks_like_index([1, 2, 3, 4, 5]) is True


def test_looks_like_index_with_gaps():
    assert _looks_like_index([1, 2, 4, 5, 7, 8, 10]) is True
    assert _looks_like_index([1, 3, 5, 7, 9, 11]) is True


def test_looks_like_index_monotonic_small():
    """Номера с большими пропусками — как в проблемном файле."""
    assert _looks_like_index([4, 24, 25, 89, 90, 91, 101, 111, 116, 117]) is True


def test_looks_like_index_all_below_min_price():
    assert _looks_like_index([15, 42, 78, 93, 120, 155]) is True


def test_looks_like_index_not_prices():
    """Реальные цены НЕ должны быть приняты за индекс."""
    assert _looks_like_index([2500, 5000, 3000, 15000, 8000]) is False
    assert _looks_like_index([500, 1200, 800, 3500]) is False


# === Тесты _looks_like_price_column ===

def test_looks_like_price_column_valid():
    assert _looks_like_price_column([2500, 5000, 3000, 15000, 8000]) is True
    assert _looks_like_price_column([500, 1200, 800, 3500, 250]) is True


def test_looks_like_price_column_garbage():
    assert _looks_like_price_column([4, 24, 25, 89, 90, 91, 101]) is False
    assert _looks_like_price_column([1, 2, 3, 4, 5]) is False


# === Тесты _is_garbage_service_name ===

def test_garbage_name_pure_number():
    """Чисто числовые строки — это номера строк, не услуги."""
    assert _is_garbage_service_name("2") is True
    assert _is_garbage_service_name("123") is True
    assert _is_garbage_service_name("15.3") is True
    assert _is_garbage_service_name("1 234") is True


def test_garbage_name_med_code():
    """Мед. коды — не названия услуг."""
    assert _is_garbage_service_name("A02.004.001") is True
    assert _is_garbage_service_name("B03.015.002") is True


def test_garbage_name_metadata():
    """Метаданные документа — не услуги."""
    assert _is_garbage_service_name("Итого") is True
    assert _is_garbage_service_name("Всего") is True
    assert _is_garbage_service_name("Примечание к прайсу") is True
    assert _is_garbage_service_name("Прайс-лист медицинских услуг") is True
    assert _is_garbage_service_name("Договор оказания услуг") is True


def test_garbage_name_section():
    """Разделители секций — не услуги."""
    assert _is_garbage_service_name("Раздел 1. Консультации") is True
    assert _is_garbage_service_name("Глава II. Анализы") is True


def test_garbage_name_empty():
    assert _is_garbage_service_name("") is True
    assert _is_garbage_service_name("   ") is True
    assert _is_garbage_service_name("X") is True  # 1 символ


def test_not_garbage_real_services():
    """Реальные мед. услуги НЕ должны быть мусором."""
    assert _is_garbage_service_name("Общий анализ крови") is False
    assert _is_garbage_service_name("ЭКГ") is False
    assert _is_garbage_service_name("МРТ мозга") is False
    assert _is_garbage_service_name("УЗИ 3 триместра") is False
    assert _is_garbage_service_name("Ампутация и дезартикуляция пальца кисти") is False
    assert _is_garbage_service_name("Видео ЭЭГ мониторинг сна 12 часов") is False
    assert _is_garbage_service_name("Блокада новокаиновая") is False


# === Тесты classify_columns с колонкой № ===

def test_classify_columns_excludes_index():
    """Колонка '№' должна быть исключена из кандидатов на цену/услугу."""
    cols = classify_columns(["№", "Наименование услуги", "Цена"])
    assert "service" in cols
    assert cols["service"] == 1  # не 0 (№)


def test_classify_columns_excludes_pp():
    """Колонка 'п/п' или '№ п/п' исключается."""
    cols = classify_columns(["№ п/п", "Услуга", "Стоимость"])
    assert cols.get("service") == 1
    # № п/п не должна стать ценой
    price_col = cols.get("price")
    assert price_col != 0


# === Тесты sanity_check_prices (5 эшелонов) ===

def test_sanity_check_rejects_garbage_prices():
    """Эшелон 1: >60% цен < 200 → сброс."""
    rows = [
        RawPriceRow(service_name_raw="Услуга 1", price_resident=24),
        RawPriceRow(service_name_raw="Услуга 2", price_resident=90),
        RawPriceRow(service_name_raw="Услуга 3", price_resident=117),
        RawPriceRow(service_name_raw="Услуга 4", price_resident=14500),
        RawPriceRow(service_name_raw="Услуга 5", price_resident=25),
    ]
    result, warnings = _sanity_check_prices(rows, [])
    assert len(result) == 0
    assert any("низкие цены" in w for w in warnings)


def test_sanity_check_keeps_good_prices():
    rows = [
        RawPriceRow(service_name_raw="ОАК", price_resident=2500),
        RawPriceRow(service_name_raw="УЗИ", price_resident=5000),
        RawPriceRow(service_name_raw="МРТ", price_resident=15000),
    ]
    result, warnings = _sanity_check_prices(rows, [])
    assert len(result) == 3


def test_sanity_check_rejects_sequential_prices():
    """Эшелон 2: цены выглядят как 1,2,3,4,5 → сброс."""
    rows = [
        RawPriceRow(service_name_raw=f"Услуга {i}", price_resident=float(i))
        for i in range(1, 8)
    ]
    result, warnings = _sanity_check_prices(rows, [])
    assert len(result) == 0
    assert any("последовательные" in w or "низкие цены" in w for w in warnings)


def test_sanity_check_rejects_clone_prices():
    """Эшелон 3: >80% цен одинаковые → сброс."""
    rows = [
        RawPriceRow(service_name_raw=f"Услуга {i}", price_resident=5000.0)
        for i in range(10)
    ]
    result, warnings = _sanity_check_prices(rows, [])
    assert len(result) == 0
    assert any("клоны" in w for w in warnings)


def test_sanity_check_rejects_garbage_names():
    """Эшелон 5: >50% мусорных названий → сброс."""
    rows = [
        RawPriceRow(service_name_raw="123", price_resident=5000),
        RawPriceRow(service_name_raw="456", price_resident=3000),
        RawPriceRow(service_name_raw="789", price_resident=8000),
        RawPriceRow(service_name_raw="ОАК", price_resident=2500),
    ]
    result, warnings = _sanity_check_prices(rows, [])
    assert len(result) == 0
    assert any("названия" in w for w in warnings)


# === Интеграционные тесты ===

def test_rows_from_matrix_index_column_not_as_price():
    """Таблица с колонкой № п/п — номера НЕ должны попасть в цену."""
    matrix = [
        ["№", "Услуга", "Цена"],
        ["1", "Общий анализ крови", "2 500"],
        ["2", "Консультация терапевта", "5 000"],
        ["3", "ЭКГ", "3 000"],
    ]
    rows, _ = rows_from_matrix(matrix)
    assert len(rows) == 3
    assert rows[0].price_resident == 2500.0
    assert rows[1].price_resident == 5000.0
    assert rows[2].price_resident == 3000.0
    for r in rows:
        assert r.price_resident >= _MIN_PLAUSIBLE_PRICE


def test_rows_from_matrix_no_header_with_index():
    """Таблица без шапки: 1-колонка номера, 2-названия, 3-цены."""
    matrix = [
        ["1", "Общий анализ крови", "2 500"],
        ["2", "Консультация терапевта", "5 000"],
        ["3", "ЭКГ", "3 000"],
        ["4", "УЗИ органов брюшной полости", "8 000"],
        ["5", "МРТ головного мозга", "15 000"],
    ]
    rows, _ = rows_from_matrix(matrix)
    if rows:
        for r in rows:
            if r.price_resident is not None:
                assert r.price_resident >= _MIN_PLAUSIBLE_PRICE, \
                    f"Номер строки попал в цену: {r.service_name_raw} = {r.price_resident}"


def test_rows_from_matrix_filters_garbage_names():
    """Мусорные service_name (числа, коды) фильтруются из результата."""
    matrix = [
        ["Услуга", "Цена"],
        ["Общий анализ крови", "2500"],
        ["123", "3000"],       # мусор: чисто числовое
        ["", "5000"],          # мусор: пустое
        ["Итого", "50000"],    # мусор: метаданные
        ["A02.004.001", "8000"],  # мусор: мед. код
        ["МРТ мозга", "15000"],
    ]
    rows, _ = rows_from_matrix(matrix)
    names = [r.service_name_raw for r in rows]
    assert "Общий анализ крови" in names
    assert "МРТ мозга" in names
    assert "123" not in names
    assert "Итого" not in names
    assert "A02.004.001" not in names


def test_rows_from_text_rejects_low_prices():
    """Текстовый парсер: строки с ценой < 200 отсеиваются sanity check."""
    text = (
        "Общий анализ крови  24\n"
        "Консультация терапевта  25\n"
        "ЭКГ 90\n"
        "МРТ головного мозга 15000\n"
    )
    rows, warnings = rows_from_text(text)
    if rows:
        prices = [r.price_resident for r in rows if r.price_resident is not None]
        for p in prices:
            assert p >= _MIN_PLAUSIBLE_PRICE or len(rows) == 1


def test_real_world_problem_case():
    """Воспроизведение бага со скриншота: номера строк как цены."""
    matrix = [
        ["№", "Наименование услуги", "Цена резидент"],
        ["1", "Ампутация и дезартикуляция пальца кисти", "45 000"],
        ["2", "Ампутация пальца стопы", "38 000"],
        ["3", "Аутогемотерапия", "5 000"],
        ["4", "Биологическая терапия", "25 000"],
        ["5", "Блокада новокаиновая", "3 500"],
        ["6", "Блокада паравертебральная", "4 000"],
        ["7", "Блокада спинальная", "15 000"],
        ["8", "Видео ЭЭГ мониторинг сна 12 часов", "35 000"],
        ["9", "Видео ЭЭГ мониторинг сна 1,5 часа.", "14 500"],
        ["10", "Видео ЭЭГ мониторинг сна 24 часа.", "55 000"],
    ]
    rows, _ = rows_from_matrix(matrix)
    assert len(rows) >= 8
    for r in rows:
        # Ни одна цена не должна быть номером строки (1-10)
        assert r.price_resident is None or r.price_resident >= _MIN_PLAUSIBLE_PRICE, \
            f"FAIL: {r.service_name_raw} = {r.price_resident} (номер строки в цене!)"
        # Названия не должны быть числами
        assert not r.service_name_raw.strip().isdigit(), \
            f"FAIL: '{r.service_name_raw}' — число попало в название услуги!"
