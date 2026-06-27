"""Поиск по услугам, партнёрам и СЫРЫМ позициям прайсов.

Ключевое: ищем не только в кураторском справочнике `Service`, но и в реальных
позициях прайсов `PriceItem.service_name_raw`. Из-за строгих порогов матчинга
большинство позиций не привязаны к справочнику — без поиска по сырым именам
выдача была пустой («ничего не находит»). Теперь любой термин, встречающийся в
прайсе хоть одной клиники, находится сразу с ценой и партнёром.

Переносимо (Postgres/SQLite) через ILIKE; на Postgres ускоряется pg_trgm.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Partner, PriceItem, Service
from app.schemas import PartnerOut, ServiceOut

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(q: str, session: AsyncSession = Depends(get_session)):
    term = (q or "").strip()
    if not term:
        return {"query": term, "services": [], "partners": [], "items": []}
    like = f"%{term}%"

    # 1. Справочник услуг (имя или категория)
    svc_res = await session.execute(
        select(Service)
        .where(
            Service.is_active.is_(True),
            or_(Service.service_name.ilike(like), Service.category.ilike(like)),
        )
        .order_by(Service.service_name)
        .limit(50)
    )
    services = [ServiceOut.model_validate(s) for s in svc_res.scalars().all()]

    # 2. Партнёры (название или город)
    part_res = await session.execute(
        select(Partner)
        .where(or_(Partner.name.ilike(like), Partner.city.ilike(like)))
        .limit(50)
    )
    partners = [PartnerOut.model_validate(p) for p in part_res.scalars().all()]

    # 3. Сырые позиции прайсов — самое полезное: реальные услуги клиник с ценой.
    item_res = await session.execute(
        select(PriceItem, Partner)
        .join(Partner, Partner.partner_id == PriceItem.partner_id)
        .where(
            PriceItem.is_active.is_(True),
            PriceItem.service_name_raw.ilike(like),
        )
        .order_by(PriceItem.price_resident_kzt.is_(None), PriceItem.price_resident_kzt)
        .limit(100)
    )
    items = [
        {
            "item_id": item.item_id,
            "service_name_raw": item.service_name_raw,
            "service_id": item.service_id,
            "partner_id": partner.partner_id,
            "partner_name": partner.name,
            "city": partner.city,
            "price_resident_kzt": float(item.price_resident_kzt)
            if item.price_resident_kzt is not None
            else None,
            "price_nonresident_kzt": float(item.price_nonresident_kzt)
            if item.price_nonresident_kzt is not None
            else None,
            "effective_date": item.effective_date.isoformat()
            if item.effective_date
            else None,
        }
        for item, partner in item_res.all()
    ]

    return {"query": term, "services": services, "partners": partners, "items": items}
