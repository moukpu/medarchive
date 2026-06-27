"""Абстракция поверх объектного хранилища (S3/MinIO)."""
import os
import aioboto3
from contextlib import asynccontextmanager
from fastapi import UploadFile

from app.config import settings

@asynccontextmanager
async def get_s3_client():
    session = aioboto3.Session()
    async with session.client(
        's3',
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    ) as client:
        yield client

async def init_bucket() -> None:
    """Убедиться, что бакет существует (для локального MinIO)."""
    if not settings.s3_endpoint:
        return
    async with get_s3_client() as s3:
        try:
            await s3.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            await s3.create_bucket(Bucket=settings.s3_bucket)

async def upload_file_to_s3(file: UploadFile, object_name: str) -> str:
    """Загрузить файл в S3. Возвращает s3:// URI."""
    if not settings.s3_endpoint:
        # Fallback to local
        path = settings.uploads_dir / "local_s3" / object_name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(await file.read())
        return str(path)

    async with get_s3_client() as s3:
        await s3.upload_fileobj(file.file, settings.s3_bucket, object_name)
        return f"s3://{settings.s3_bucket}/{object_name}"

async def download_s3_file(uri: str, local_path: str) -> None:
    """Скачать файл из S3 локально (нужно для extractors, ожидающих путь на диске)."""
    if not uri.startswith("s3://"):
        return  # это локальный файл
        
    bucket_key = uri[5:]  # убираем s3://
    bucket, key = bucket_key.split("/", 1)
    
    async with get_s3_client() as s3:
        await s3.download_file(bucket, key, local_path)
