"""Тесты docling-фоллбэка: парсинг markdown-таблиц и гейтинг доступности.

Тяжёлый локальный прогон docling (torch, ~7 мин, риск OOM) тут НЕ запускается —
проверяется только чистая логика: разбор md-таблиц через rows_from_matrix и
docling_available() при разных настройках."""
from app.config import settings
from app.extractors import docling_extractor as dx


def test_markdown_table_to_rows():
    md = """
Прайс-лист клиники

| Наименование услуги | Цена резидент | Цена нерезидент |
| --- | --- | --- |
| Общий анализ крови | 2 500 | 3 000 |
| УЗИ брюшной полости | 8000 | 9000 |

Примечание ниже таблицы.
"""
    rows = dx._rows_from_markdown(md)
    assert len(rows) == 2
    by_name = {r.service_name_raw: r for r in rows}
    assert by_name["Общий анализ крови"].price_resident == 2500.0
    assert by_name["Общий анализ крови"].price_nonresident == 3000.0
    assert by_name["УЗИ брюшной полости"].price_resident == 8000.0


def test_markdown_multiple_tables():
    md = """
| Услуга | Цена |
| - | - |
| Консультация | 5000 |

| Наименование | Стоимость |
| - | - |
| Рентген | 4000 |
"""
    rows = dx._rows_from_markdown(md)
    names = {r.service_name_raw for r in rows}
    assert names == {"Консультация", "Рентген"}


def test_separator_rows_ignored():
    # строка-разделитель не должна попасть в данные как позиция
    md = "| Услуга | Цена |\n|:---|---:|\n| Анализ | 1000 |\n"
    matrices = dx._matrices_from_markdown(md)
    assert len(matrices) == 1
    assert matrices[0] == [["Услуга", "Цена"], ["Анализ", "1000"]]


def test_docling_available_gating():
    original = settings.use_docling
    try:
        settings.use_docling = False
        assert dx.docling_available() is False  # выключено настройкой → недоступно
        settings.use_docling = True
        # включено: доступно, если стоит локальный пакет ИЛИ задан serve_url
        expected = bool(settings.docling_serve_url) or dx._local_package_available()
        assert dx.docling_available() is expected
    finally:
        settings.use_docling = original
