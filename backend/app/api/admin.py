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


from arq import create_pool
from arq.connections import RedisSettings
from app.config import settings

@router.post("/upload")
async def upload_archive(
    background: BackgroundTasks,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
):
    """Принять ZIP-архив, сохранить файлы в S3, закинуть ID в Redis/Arq очередь."""
    suffix = Path(file.filename or "archive.zip").suffix or ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
        
    doc_ids = await ingest_zip(session, tmp_path)
    
    # Enqueue tasks in Arq Redis queue (with fallback)
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        for doc_id in doc_ids:
            await redis.enqueue_job("arq_process_document", doc_id)
    except Exception as e:
        print(f"Redis is unavailable, falling back to BackgroundTasks: {e}")
        background.add_task(_process_all)
        
    return {"queued_documents": len(doc_ids), "doc_ids": doc_ids}


@router.post("/upload-catalog")
async def upload_catalog_file(
    file: UploadFile,
    replace: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """Загрузить справочник услуг (XLSX/JSON). replace=true → старые услуги
    помечаются is_active=false (обратимо), сверка идёт только по новому файлу."""
    from sqlalchemy import update

    from app.matching.catalog import load_catalog
    from app.models import Service

    suffix = Path(file.filename or "catalog.xlsx").suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    if replace:
        await session.execute(update(Service).values(is_active=False))
        await session.commit()
    count = await load_catalog(session, tmp_path)
    return {"loaded": count, "replaced": replace}


@router.get("/status", response_model=list[DocumentStatusOut])
async def documents_status(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(PriceDocument).order_by(PriceDocument.parsed_at.desc().nullslast()))
    return list(res.scalars().all())


@router.post("/process")
async def trigger_processing(background: BackgroundTasks):
    """Запустить обработку pending-документов вручную."""
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        async with SessionLocal() as session:
            res = await session.execute(
                select(PriceDocument.doc_id).where(PriceDocument.parse_status == ParseStatus.pending)
            )
            for doc_id in res.scalars():
                await redis.enqueue_job("arq_process_document", doc_id)
    except Exception as e:
        print(f"Redis is unavailable, falling back to BackgroundTasks: {e}")
        background.add_task(_process_all)
    return {"status": "processing_started"}


@router.post("/rematch")
async def rematch_all(background: BackgroundTasks):
    """Перезапустить matching для всех позиций (после обновления справочника)."""
    async def _rematch():
        from app.pipeline.normalize import CatalogIndex
        from app.models import MatchMethod
        async with SessionLocal() as session:
            index = await CatalogIndex.build(session)
            res = await session.execute(
                select(PriceItem).where(PriceItem.is_active.is_(True))
            )
            items = res.scalars().all()
            await index.prepare(session, [item.service_name_raw or "" for item in items])
            updated = 0
            for item in items:
                match = index.match(item.service_name_raw or "")
                item.service_id = match.service_id
                item.match_score = match.score
                item.match_method = match.method if match.service_id else MatchMethod.none
                item.needs_review = match.service_id is None
                updated += 1
            await session.commit()
            return updated
    background.add_task(_rematch)
    return {"status": "rematch_started"}


@router.post("/reprocess-errors")
async def reprocess_errors(background: BackgroundTasks):
    """Сбросить error/processing документы в pending и запустить обработку."""
    from app.models import ParseStatus
    async with SessionLocal() as session:
        res = await session.execute(
            select(PriceDocument).where(
                PriceDocument.parse_status.in_([ParseStatus.error, ParseStatus.processing])
            )
        )
        docs = res.scalars().all()
        for doc in docs:
            doc.parse_status = ParseStatus.pending
            doc.parse_log = (doc.parse_log or "") + "\n[Сброшен в pending для повторной обработки]"
        await session.commit()
        
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        for doc in docs:
            await redis.enqueue_job("arq_process_document", doc.doc_id)
    except Exception as e:
        print(f"Redis is unavailable, falling back to BackgroundTasks: {e}")
        background.add_task(_process_all)
        
    return {"status": "reprocess_started"}


@router.post("/clear-db")
async def clear_database(session: AsyncSession = Depends(get_session)):
    """Очистить базу данных (все основные таблицы)."""
    from sqlalchemy import text
    try:
        # Для Postgres (быстрее, обнуляет счетчики, удаляет каскадно)
        await session.execute(text("TRUNCATE TABLE price_items, price_documents, partners, services CASCADE;"))
        await session.commit()
    except Exception:
        # Фоллбэк для SQLite (локальная разработка)
        await session.rollback()
        await session.execute(text("DELETE FROM price_items;"))
        await session.execute(text("DELETE FROM price_documents;"))
        await session.execute(text("DELETE FROM partners;"))
        await session.execute(text("DELETE FROM services;"))
        await session.commit()
        
    return {"status": "db_cleared"}



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
