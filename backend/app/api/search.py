"""Полнотекстовый поиск по услугам и партнёрам.

Для переносимости (Postgres/SQLite) используется ILIKE. На Postgres дополнительно
работают индексы pg_trgm; при необходимости можно заменить на tsvector/FTS.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Partner, Service
from app.schemas import PartnerOut, ServiceOut

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(q: str, session: AsyncSession = Depends(get_session)):
    like = f"%{q.strip()}%"
    svc_res = await session.execute(
        select(Service).where(
            Service.is_active.is_(True),
            or_(Service.service_name.ilike(like)),
        ).limit(50)
    )
    services = [ServiceOut.model_validate(s) for s in svc_res.scalars().all()]

    part_res = await session.execute(
        select(Partner).where(
            or_(Partner.name.ilike(like), Partner.city.ilike(like))
        ).limit(50)
    )
    partners = [PartnerOut.model_validate(p) for p in part_res.scalars().all()]

    return {"query": q, "services": services, "partners": partners}
