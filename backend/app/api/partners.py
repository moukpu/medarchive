"""Эндпоинты партнёров."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Partner, PriceItem, Service
from app.schemas import PartnerOut, ServiceWithPrice

router = APIRouter(tags=["partners"])


@router.get("/partners", response_model=list[PartnerOut])
async def list_partners(
    city: str | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Partner)
    if city:
        stmt = stmt.where(Partner.city == city)
    if is_active is not None:
        stmt = stmt.where(Partner.is_active.is_(is_active))
    res = await session.execute(stmt.order_by(Partner.name))
    return list(res.scalars().all())


@router.get("/partners/{partner_id}/services", response_model=list[ServiceWithPrice])
async def partner_services(
    partner_id: str,
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """Прайс партнёра. include_inactive=true возвращает и архивные версии
    (для разбивки истории цен по датам на фронте)."""
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(404, "Партнёр не найден")
    stmt = (
        select(PriceItem, Service)
        .outerjoin(Service, Service.service_id == PriceItem.service_id)
        .where(PriceItem.partner_id == partner_id)
    )
    if not include_inactive:
        stmt = stmt.where(PriceItem.is_active.is_(True))
    stmt = stmt.order_by(PriceItem.effective_date.desc().nullslast(), PriceItem.service_name_raw)
    res = await session.execute(stmt)
    out: list[ServiceWithPrice] = []
    for item, svc in res.all():
        out.append(ServiceWithPrice(
            item_id=item.item_id,
            service_name_raw=item.service_name_raw,
            service_id=item.service_id,
            service_name=svc.service_name if svc else None,
            price_resident_kzt=float(item.price_resident_kzt) if item.price_resident_kzt is not None else None,
            price_nonresident_kzt=float(item.price_nonresident_kzt) if item.price_nonresident_kzt is not None else None,
            effective_date=item.effective_date,
            is_active=item.is_active,
        ))
    return out
