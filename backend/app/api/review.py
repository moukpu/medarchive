"""Очередь верификации: все позиции needs_review + approve/edit/context.

Шире, чем /unmatched: включает не только несопоставленные (service_id IS NULL),
но и сопоставленные-но-флагнутые (аномалия цены, нерезидент<резидент)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import MatchMethod, Partner, PriceDocument, PriceItem, Service
from app.schemas import ItemContextOut, ItemUpdate, ReviewItemOut, ServiceOut

router = APIRouter(tags=["review"])


def _reasons_for(item: PriceItem, doc: PriceDocument | None) -> list[str]:
    """Причины, по которым позиция попала на ревью. Часть берём из parse_log
    документа (туда runner пишет предупреждения валидации с префиксом названия)."""
    reasons: list[str] = []
    if item.service_id is None:
        reasons.append("Не сопоставлено со справочником")
    if doc and doc.parse_log:
        prefix = f"{item.service_name_raw}:"
        for line in doc.parse_log.splitlines():
            if line.startswith(prefix):
                reasons.append(line[len(prefix):].strip())
    return reasons


def _raw_snippet(raw: str | None, needle: str, radius: int = 200) -> str | None:
    """Фрагмент исходного текста вокруг названия позиции — «показать в файле»."""
    if not raw or not needle:
        return None
    idx = raw.lower().find(needle.lower())
    if idx < 0:
        # не нашли точное вхождение — отдаём начало документа как ориентир
        return raw[:2 * radius].strip() or None
    start = max(0, idx - radius)
    end = min(len(raw), idx + len(needle) + radius)
    snippet = raw[start:end].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(raw) else "")


@router.get("/review", response_model=list[ReviewItemOut])
async def list_review(limit: int = 200, session: AsyncSession = Depends(get_session)):
    """Все активные позиции, требующие ревью (несопоставленные + флагнутые)."""
    svc_res = await session.execute(select(Service).where(Service.is_active.is_(True)))
    services = list(svc_res.scalars().all())
    choices = {s.service_id: s.service_name for s in services}
    by_id = {s.service_id: s for s in services}

    res = await session.execute(
        select(PriceItem)
        .where(PriceItem.needs_review.is_(True), PriceItem.is_active.is_(True))
        .limit(limit)
    )
    items = list(res.scalars().all())

    # подтянем документы и партнёров пачкой
    doc_ids = {it.doc_id for it in items}
    partner_ids = {it.partner_id for it in items}
    docs = {}
    if doc_ids:
        d = await session.execute(select(PriceDocument).where(PriceDocument.doc_id.in_(doc_ids)))
        docs = {x.doc_id: x for x in d.scalars().all()}
    partners = {}
    if partner_ids:
        p = await session.execute(select(Partner).where(Partner.partner_id.in_(partner_ids)))
        partners = {x.partner_id: x for x in p.scalars().all()}

    out: list[ReviewItemOut] = []
    for it in items:
        suggestions: list[ServiceOut] = []
        if it.service_id is None and choices:
            top = process.extract(it.service_name_raw, choices, scorer=fuzz.token_set_ratio, limit=5)
            suggestions = [ServiceOut.model_validate(by_id[key]) for _, _score, key in top]
        doc = docs.get(it.doc_id)
        partner = partners.get(it.partner_id)
        out.append(ReviewItemOut(
            item_id=it.item_id,
            service_name_raw=it.service_name_raw,
            partner_id=it.partner_id,
            partner_name=partner.name if partner else None,
            doc_id=it.doc_id,
            file_name=doc.file_name if doc else None,
            effective_date=it.effective_date,
            service_id=it.service_id,
            service_name=by_id[it.service_id].service_name if it.service_id in by_id else None,
            price_resident_kzt=float(it.price_resident_kzt) if it.price_resident_kzt is not None else None,
            price_nonresident_kzt=float(it.price_nonresident_kzt) if it.price_nonresident_kzt is not None else None,
            match_score=it.match_score,
            match_method=it.match_method.value if it.match_method else "none",
            is_verified=it.is_verified,
            reasons=_reasons_for(it, doc),
            suggestions=suggestions,
        ))
    return out


@router.get("/items/{item_id}/context", response_model=ItemContextOut)
async def item_context(item_id: str, session: AsyncSession = Depends(get_session)):
    item = await session.get(PriceItem, item_id)
    if item is None:
        raise HTTPException(404, "Позиция не найдена")
    doc = await session.get(PriceDocument, item.doc_id)
    return ItemContextOut(
        item_id=item.item_id,
        service_name_raw=item.service_name_raw,
        doc_id=item.doc_id,
        file_name=doc.file_name if doc else None,
        file_format=doc.file_format.value if doc and doc.file_format else None,
        effective_date=item.effective_date,
        parse_log=doc.parse_log if doc else None,
        raw_snippet=_raw_snippet(doc.raw_content if doc else None, item.service_name_raw),
    )


@router.post("/items/{item_id}/approve", response_model=ReviewItemOut)
async def approve_item(item_id: str, session: AsyncSession = Depends(get_session)):
    """Утвердить позицию как есть (снять флаг ревью), не меняя сопоставление."""
    item = await session.get(PriceItem, item_id)
    if item is None:
        raise HTTPException(404, "Позиция не найдена")
    item.is_verified = True
    item.needs_review = False
    await session.commit()
    return ReviewItemOut(
        item_id=item.item_id,
        service_name_raw=item.service_name_raw,
        partner_id=item.partner_id,
        doc_id=item.doc_id,
        effective_date=item.effective_date,
        service_id=item.service_id,
        is_verified=item.is_verified,
    )


@router.patch("/items/{item_id}", response_model=ReviewItemOut)
async def update_item(item_id: str, req: ItemUpdate, session: AsyncSession = Depends(get_session)):
    """Ручная правка позиции при верификации: пересопоставление и/или цены."""
    item = await session.get(PriceItem, item_id)
    if item is None:
        raise HTTPException(404, "Позиция не найдена")
    if req.service_id is not None:
        svc = await session.get(Service, req.service_id)
        if svc is None:
            raise HTTPException(404, "Услуга справочника не найдена")
        item.service_id = req.service_id
        item.match_method = MatchMethod.manual
        item.match_score = 1.0
    if req.price_resident_kzt is not None:
        item.price_resident_kzt = req.price_resident_kzt
    if req.price_nonresident_kzt is not None:
        item.price_nonresident_kzt = req.price_nonresident_kzt
    if req.note is not None:
        item.verification_note = req.note
    item.is_verified = True
    item.needs_review = False
    await session.commit()
    return ReviewItemOut(
        item_id=item.item_id,
        service_name_raw=item.service_name_raw,
        partner_id=item.partner_id,
        doc_id=item.doc_id,
        effective_date=item.effective_date,
        service_id=item.service_id,
        price_resident_kzt=float(item.price_resident_kzt) if item.price_resident_kzt is not None else None,
        price_nonresident_kzt=float(item.price_nonresident_kzt) if item.price_nonresident_kzt is not None else None,
        match_method=item.match_method.value if item.match_method else "none",
        is_verified=item.is_verified,
    )
