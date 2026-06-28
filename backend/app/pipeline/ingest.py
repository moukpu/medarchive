"""Приём ZIP-архива: распаковка, дедуп партнёров, создание PriceDocument."""
from __future__ import annotations

import re
import shutil
import uuid
import zipfile
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.extractors.router import detect_format
from app.models import Partner, PriceDocument

_DATE_RE = re.compile(r"(\d{4})[-_.](\d{2})[-_.](\d{2})|(\d{2})[-_.](\d{2})[-_.](\d{4})")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_NOISE_RE = re.compile(r"\b(прайс|price|год|year|лист|list)\b", re.IGNORECASE)
_SUPPORTED = (".pdf", ".docx", ".xlsx", ".xls")


def parse_filename(name: str) -> tuple[str, date | None]:
    """Эвристика: вытащить дату и название клиники из имени файла.

    Извлекает дату (полную YYYY-MM-DD или standalone год → 1 января),
    затем очищает имя от даты, года, слов «прайс/год/лист».
    """
    stem = Path(name).stem
    eff: date | None = None
    m = _DATE_RE.search(stem)
    if m:
        try:
            if m.group(1):
                eff = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                eff = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        except ValueError:
            eff = None

    clinic = _DATE_RE.sub("", stem)
    if eff is None:
        ym = _YEAR_RE.search(clinic)
        if ym:
            try:
                eff = date(int(ym.group(1)), 1, 1)
            except ValueError:
                pass
    clinic = _YEAR_RE.sub("", clinic)
    clinic = _NOISE_RE.sub("", clinic)
    clinic = re.sub(r"[_\-]+", " ", clinic)
    clinic = re.sub(r"\s+", " ", clinic).strip(" .-_")
    return (clinic or stem), eff


async def get_or_create_partner(session: AsyncSession, name: str) -> Partner:
    """Дедуп по нормализованному имени (BIN приходит позже из контента)."""
    norm = re.sub(r"\s+", " ", name.strip().lower())
    res = await session.execute(select(Partner))
    for p in res.scalars():
        if re.sub(r"\s+", " ", p.name.strip().lower()) == norm:
            return p
    partner = Partner(name=name)
    session.add(partner)
    await session.flush()
    return partner


async def ingest_zip(session: AsyncSession, zip_path: str) -> list[str]:
    """Распаковать архив, загрузить файлы в S3, создать документы в БД. Вернуть doc_ids."""
    from app.storage import upload_file_to_s3, init_bucket
    import aiofiles
    from fastapi import UploadFile

    await init_bucket()
    batch_id = str(uuid.uuid4())
    batch_dir = settings.uploads_dir / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(batch_dir)

    doc_ids: list[str] = []
    for file in sorted(batch_dir.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in _SUPPORTED:
            continue
            
        clinic, eff = parse_filename(file.name)
        partner = await get_or_create_partner(session, clinic)
        fmt = detect_format(str(file))
        
        # Upload to S3
        object_name = f"{batch_id}/{file.name}"
        with open(file, "rb") as f:
            upload_file = UploadFile(file=f, filename=file.name)
            s3_uri = await upload_file_to_s3(upload_file, object_name)

        doc = PriceDocument(
            partner_id=partner.partner_id,
            file_name=file.name,
            file_path=s3_uri,
            file_format=fmt,
            effective_date=eff,
        )
        session.add(doc)
        await session.flush()
        doc_ids.append(doc.doc_id)
        
    await session.commit()
    # Cleanup local extracted batch
    shutil.rmtree(batch_dir, ignore_errors=True)
    return doc_ids


async def ingest_single_file(session: AsyncSession, src_path: str, original_name: str | None = None) -> str:
    """Принять один файл (без ZIP), загрузить в S3. Возвращает doc_id."""
    from app.storage import upload_file_to_s3, init_bucket
    from fastapi import UploadFile

    await init_bucket()
    file_name = original_name or Path(src_path).name
    batch_id = str(uuid.uuid4())

    clinic, eff = parse_filename(file_name)
    partner = await get_or_create_partner(session, clinic)
    fmt = detect_format(src_path)

    object_name = f"{batch_id}/{file_name}"
    with open(src_path, "rb") as f:
        upload_file = UploadFile(file=f, filename=file_name)
        s3_uri = await upload_file_to_s3(upload_file, object_name)

    doc = PriceDocument(
        partner_id=partner.partner_id,
        file_name=file_name,
        file_path=s3_uri,
        file_format=fmt,
        effective_date=eff,
    )
    session.add(doc)
    await session.flush()
    await session.commit()
    return doc.doc_id
