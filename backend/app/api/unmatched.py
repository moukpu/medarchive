"""Очередь несопоставленных позиций и ручное сопоставление."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import MatchMethod, PriceItem, Service
from app.schemas import MatchRequest, ServiceOut, UnmatchedOut

router = APIRouter(tags=["matching"])


@router.get("/unmatched", response_model=list[UnmatchedOut])
async def list_unmatched(limit: int = 100, session: AsyncSession = Depends(get_session)):
    """Активные позиции без привязки к справочнику + топ-предложения (fuzzy)."""
    svc_res = await session.execute(select(Service).where(Service.is_active.is_(True)))
    services = list(svc_res.scalars().all())
    choices = {s.service_id: s.service_name for s in services}
    by_id = {s.service_id: s for s in services}

    res = await session.execute(
        select(PriceItem)
        .where(PriceItem.service_id.is_(None), PriceItem.is_active.is_(True))
        .limit(limit)
    )
    items = res.scalars().all()
    out: list[UnmatchedOut] = []
    for it in items:
        suggestions: list[ServiceOut] = []
        if choices:
            top = process.extract(it.service_name_raw, choices, scorer=fuzz.token_set_ratio, limit=5)
            suggestions = [ServiceOut.model_validate(by_id[key]) for _, _score, key in top]
        out.append(UnmatchedOut(
            item_id=it.item_id,
            service_name_raw=it.service_name_raw,
            partner_id=it.partner_id,
            match_score=it.match_score,
            suggestions=suggestions,
        ))
    return out


@router.post("/match", response_model=UnmatchedOut)
async def manual_match(req: MatchRequest, session: AsyncSession = Depends(get_session)):
    item = await session.get(PriceItem, req.item_id)
    if item is None:
        raise HTTPException(404, "Позиция не найдена")
    svc = await session.get(Service, req.service_id)
    if svc is None:
        raise HTTPException(404, "Услуга справочника не найдена")
    item.service_id = req.service_id
    item.match_method = MatchMethod.manual
    item.match_score = 1.0
    item.is_verified = True
    item.needs_review = False
    item.verification_note = req.note
    await session.commit()
    return UnmatchedOut(
        item_id=item.item_id,
        service_name_raw=item.service_name_raw,
        partner_id=item.partner_id,
        match_score=item.match_score,
        suggestions=[],
    )
