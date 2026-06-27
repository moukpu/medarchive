"""Админ-эндпоинты: загрузка архива, статусы, дашборд."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, get_session
from app.models import PriceDocument, PriceItem
from app.pipeline.ingest import ingest_zip
from app.pipeline.runner import process_pending
from app.schemas import DashboardOut, DocumentStatusOut

router = APIRouter(prefix="/admin", tags=["admin"])


async def _process_all() -> None:
    """Фоновая обработка очереди в собственной сессии."""
    async with SessionLocal() as session:
        await process_pending(session)


@router.post("/upload")
async def upload_archive(
    background: BackgroundTasks,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
):
    """Принять ZIP-архив, поставить документы в очередь, запустить обработку в фоне."""
    suffix = Path(file.filename or "archive.zip").suffix or ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    doc_ids = await ingest_zip(session, tmp_path)
    background.add_task(_process_all)
    return {"queued_documents": len(doc_ids), "doc_ids": doc_ids}


@router.get("/status", response_model=list[DocumentStatusOut])
async def documents_status(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(PriceDocument).order_by(PriceDocument.parsed_at.desc().nullslast()))
    return list(res.scalars().all())


@router.post("/process")
async def trigger_processing(background: BackgroundTasks):
    """Запустить обработку pending-документов вручную."""
    background.add_task(_process_all)
    return {"status": "processing_started"}


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(session: AsyncSession = Depends(get_session)):
    docs_total = (await session.execute(select(func.count(PriceDocument.doc_id)))).scalar_one()
    by_status_rows = await session.execute(
        select(PriceDocument.parse_status, func.count(PriceDocument.doc_id)).group_by(PriceDocument.parse_status)
    )
    by_status = {row[0].value: row[1] for row in by_status_rows.all()}

    items_total = (await session.execute(
        select(func.count(PriceItem.item_id)).where(PriceItem.is_active.is_(True))
    )).scalar_one()
    items_matched = (await session.execute(
        select(func.count(PriceItem.item_id)).where(
            PriceItem.is_active.is_(True), PriceItem.service_id.is_not(None)
        )
    )).scalar_one()
    items_needs_review = (await session.execute(
        select(func.count(PriceItem.item_id)).where(
            PriceItem.is_active.is_(True), PriceItem.needs_review.is_(True)
        )
    )).scalar_one()
    unmatched = items_total - items_matched
    rate = (items_matched / items_total * 100.0) if items_total else 0.0

    return DashboardOut(
        documents_total=docs_total,
        documents_by_status=by_status,
        items_total=items_total,
        items_matched=items_matched,
        items_unmatched=unmatched,
        items_needs_review=items_needs_review,
        auto_match_rate=round(rate, 1),
    )
