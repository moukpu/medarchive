import asyncio
import os
import aioboto3

from arq.connections import RedisSettings
from app.config import settings
from app.db import SessionLocal
from app.pipeline.runner import process_document, PriceDocument, ParseStatus

async def arq_process_document(ctx, doc_id: str):
    """Задача обработки документа в фоне.
    Эта функция вызывается воркером arq."""
    
    # 1. Скачиваем файл из S3 во временную директорию
    from app.storage import download_s3_file
    
    async with SessionLocal() as session:
        doc = await session.get(PriceDocument, doc_id)
        if not doc or not doc.file_path:
            return
            
        s3_uri = doc.file_path
        
    local_path = os.path.join("/tmp", os.path.basename(s3_uri))
    if not os.path.exists("/tmp"):
        os.makedirs("/tmp", exist_ok=True)
        
    if s3_uri.startswith("s3://"):
        await download_s3_file(s3_uri, local_path)
    else:
        # Локальный fallback (если не S3)
        local_path = s3_uri
        
    # 2. Вызываем логику парсинга.
    #    process_document читает путь из doc.file_path, поэтому подменяем его на
    #    локально скачанный файл (3-й позиционный аргумент — это CatalogIndex,
    #    НЕ путь; раньше сюда ошибочно передавался local_path → падение задачи).
    async with SessionLocal() as session:
        try:
            doc = await session.get(PriceDocument, doc_id)
            if doc and doc.file_path != local_path:
                doc.file_path = local_path
                await session.commit()
            await process_document(session, doc_id)
        except Exception as e:
            # Обновляем статус в БД в случае ошибки вне process_document
            doc = await session.get(PriceDocument, doc_id)
            if doc:
                doc.parse_status = ParseStatus.error
                doc.parse_log = (doc.parse_log or "") + f"\n[Worker] {str(e)}"
                await session.commit()
    
    # 3. Подметаем за собой
    if s3_uri.startswith("s3://") and os.path.exists(local_path):
        os.remove(local_path)

class WorkerSettings:
    functions = [arq_process_document]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    
    # Ограничиваем количество конкурентных задач
    max_jobs = settings.process_concurrency
