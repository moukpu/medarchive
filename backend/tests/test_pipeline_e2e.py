"""E2E на SQLite: справочник → XLSX-прайс → обработка → нормализация → дашборд."""
import openpyxl
import pytest


def _make_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Прайс-лист", None, None])
    ws.append(["Наименование услуги", "Цена резидент", "Цена нерезидент"])
    ws.append(["Общий анализ крови", 2500, 3000])
    ws.append(["Консультация терапевта", 5000, 6000])
    ws.append(["УЗИ брюшной полости", 8000, 9000])
    wb.save(path)


@pytest.mark.asyncio
async def test_full_pipeline(session, tmp_path):
    from app.matching.catalog import load_catalog
    from app.models import PriceItem
    from app.pipeline.ingest import ingest_single_file
    from app.pipeline.runner import process_pending
    from sqlalchemy import select

    # 1. справочник (JSON) с синонимом
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        '[{"service_name": "Общий анализ крови", "synonyms": ["ОАК"], "category": "лаборатория"},'
        ' {"service_name": "Консультация терапевта", "synonyms": [], "category": "консультация"},'
        ' {"service_name": "УЗИ органов брюшной полости", "synonyms": ["УЗИ брюшной полости"], "category": "диагностика"}]',
        encoding="utf-8",
    )
    n = await load_catalog(session, str(catalog))
    assert n == 3

    # 2. прайс-файл клиники
    xlsx = tmp_path / "Клиника_Альфа_2025-01-15.xlsx"
    _make_xlsx(xlsx)
    await ingest_single_file(session, str(xlsx))

    # 3. обработка очереди
    processed = await process_pending(session)
    assert processed == 1

    # 4. проверка результатов
    res = await session.execute(select(PriceItem).where(PriceItem.is_active.is_(True)))
    items = res.scalars().all()
    assert len(items) == 3
    # точное и синонимичное совпадения должны проставить service_id
    matched = [i for i in items if i.service_id is not None]
    assert len(matched) >= 2  # ОАК (синоним via fuzzy) + точные названия
    # цены сконвертированы/сохранены
    oak = next(i for i in items if "крови" in i.service_name_raw.lower())
    assert float(oak.price_resident_kzt) == 2500.0
    assert float(oak.price_nonresident_kzt) == 3000.0


@pytest.mark.asyncio
async def test_validation_nonresident_lt_resident(session):
    from app.extractors.base import RawPriceRow
    from app.pipeline.validate import validate_row
    from datetime import date

    row = RawPriceRow(service_name_raw="Тест", price_resident=5000, price_nonresident=3000)
    out = validate_row(row, date(2025, 1, 1))
    assert out.needs_review is True
    assert any("нерезидент" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_currency_conversion(session):
    from app.extractors.base import RawPriceRow
    from app.pipeline.validate import validate_row
    from datetime import date

    row = RawPriceRow(service_name_raw="Тест", price_resident=100, price_original=100, currency="USD")
    out = validate_row(row, date(2025, 1, 1))
    assert out.price_resident_kzt == 47000.0  # 100 * 470
    assert out.price_original == 100
    assert out.currency_original == "USD"
