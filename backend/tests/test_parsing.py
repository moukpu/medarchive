"""Юнит-тесты чистых функций извлечения (без БД и тяжёлых зависимостей)."""
from app.extractors.base import (
    classify_columns,
    detect_currency,
    parse_price,
    rows_from_matrix,
    rows_from_text,
)


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
        ["", "", ""],  # пустая строка
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
