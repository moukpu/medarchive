"""Эндпоинты справочника услуг."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Partner, PriceItem, Service
from app.schemas import PartnerOut, PartnerWithPrice, ServiceOut

router = APIRouter(tags=["services"])


@router.get("/services", response_model=list[ServiceOut])
async def list_services(category: str | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(Service).where(Service.is_active.is_(True))
    if category:
        stmt = stmt.where(Service.category == category)
    res = await session.execute(stmt.order_by(Service.service_name))
    return list(res.scalars().all())


@router.get("/services/{service_id}/partners", response_model=list[PartnerWithPrice])
async def service_partners(service_id: str, session: AsyncSession = Depends(get_session)):
    svc = await session.get(Service, service_id)
    if svc is None:
        raise HTTPException(404, "Услуга не найдена")
    stmt = (
        select(PriceItem, Partner)
        .join(Partner, Partner.partner_id == PriceItem.partner_id)
        .where(PriceItem.service_id == service_id, PriceItem.is_active.is_(True))
        .order_by(PriceItem.price_resident_kzt)
    )
    res = await session.execute(stmt)
    out: list[PartnerWithPrice] = []
    for item, partner in res.all():
        out.append(PartnerWithPrice(
            partner=PartnerOut.model_validate(partner),
            price_resident_kzt=float(item.price_resident_kzt) if item.price_resident_kzt is not None else None,
            price_nonresident_kzt=float(item.price_nonresident_kzt) if item.price_nonresident_kzt is not None else None,
            effective_date=item.effective_date,
            item_id=item.item_id,
        ))
    return out
