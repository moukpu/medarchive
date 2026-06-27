"""Тесты новых эндпоинтов верификации и истории цен партнёра."""
from datetime import date

import pytest

from app.models import (
    FileFormat,
    MatchMethod,
    ParseStatus,
    Partner,
    PriceDocument,
    PriceItem,
    Service,
)


async def _seed(session):
    partner = Partner(name="Клиника Бета", city="Алматы")
    session.add(partner)
    await session.flush()

    svc = Service(service_name="Общий анализ крови", synonyms=["ОАК"], category="лаб")
    session.add(svc)
    await session.flush()

    doc = PriceDocument(
        partner_id=partner.partner_id,
        file_name="beta_2020.xlsx",
        file_format=FileFormat.xlsx,
        effective_date=date(2020, 1, 1),
        parse_status=ParseStatus.needs_review,
        parse_log="Тест аномалия: цена\nОАК: Аномалия цены: изменение 80% от предыдущей версии",
        raw_content="…строка ОАК 2500 3000…",
    )
    session.add(doc)
    await session.flush()

    # A: несопоставленная позиция на ревью
    unmatched = PriceItem(
        doc_id=doc.doc_id, partner_id=partner.partner_id, service_name_raw="Анализ непонятный",
        service_id=None, needs_review=True, is_active=True, match_method=MatchMethod.none,
        effective_date=date(2020, 1, 1),
    )
    # B: сопоставленная, но флагнутая (аномалия)
    flagged = PriceItem(
        doc_id=doc.doc_id, partner_id=partner.partner_id, service_name_raw="ОАК",
        service_id=svc.service_id, needs_review=True, is_active=True,
        match_method=MatchMethod.synonym, match_score=0.98,
        price_resident_kzt=2500, price_nonresident_kzt=3000, effective_date=date(2020, 1, 1),
    )
    # C: архивная версия (для истории по датам)
    archived = PriceItem(
        doc_id=doc.doc_id, partner_id=partner.partner_id, service_name_raw="ОАК",
        service_id=svc.service_id, needs_review=False, is_active=False,
        price_resident_kzt=1500, effective_date=date(2016, 1, 1),
    )
    session.add_all([unmatched, flagged, archived])
    await session.commit()
    return partner, svc, unmatched, flagged


@pytest.mark.asyncio
async def test_review_lists_unmatched_and_flagged(session):
    from app.api.review import list_review

    await _seed(session)
    out = await list_review(session=session)
    assert len(out) == 2  # и несопоставленная, и флагнутая-сопоставленная
    by_raw = {r.service_name_raw: r for r in out}
    assert "Не сопоставлено со справочником" in by_raw["Анализ непонятный"].reasons
    assert any("Аномалия" in r for r in by_raw["ОАК"].reasons)
    # у несопоставленной есть предложения справочника
    assert by_raw["Анализ непонятный"].suggestions != []


@pytest.mark.asyncio
async def test_approve_item(session):
    from app.api.review import approve_item, list_review

    _, _, _, flagged = await _seed(session)
    await approve_item(flagged.item_id, session=session)
    await session.refresh(flagged)
    assert flagged.is_verified is True and flagged.needs_review is False
    # после approve очередь короче
    out = await list_review(session=session)
    assert flagged.item_id not in {r.item_id for r in out}


@pytest.mark.asyncio
async def test_update_item_rematch_and_price(session):
    from app.api.review import update_item
    from app.schemas import ItemUpdate

    _, svc, unmatched, _ = await _seed(session)
    await update_item(unmatched.item_id, ItemUpdate(service_id=svc.service_id, price_resident_kzt=999), session=session)
    await session.refresh(unmatched)
    assert unmatched.service_id == svc.service_id
    assert unmatched.match_method == MatchMethod.manual
    assert float(unmatched.price_resident_kzt) == 999.0
    assert unmatched.needs_review is False


@pytest.mark.asyncio
async def test_item_context(session):
    from app.api.review import item_context

    _, _, _, flagged = await _seed(session)
    ctx = await item_context(flagged.item_id, session=session)
    assert ctx.file_name == "beta_2020.xlsx"
    assert ctx.raw_snippet and "ОАК" in ctx.raw_snippet
    assert "Аномалия" in (ctx.parse_log or "")


@pytest.mark.asyncio
async def test_partner_services_include_inactive(session):
    from app.api.partners import partner_services

    partner, _, _, _ = await _seed(session)
    active_only = await partner_services(partner.partner_id, include_inactive=False, session=session)
    assert all(s.is_active for s in active_only)
    with_history = await partner_services(partner.partner_id, include_inactive=True, session=session)
    dates = {str(s.effective_date) for s in with_history}
    assert "2016-01-01" in dates and "2020-01-01" in dates  # архивная + актуальная
    assert any(not s.is_active for s in with_history)
