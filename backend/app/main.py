"""Точка входа FastAPI: роутеры, CORS, OpenAPI."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, partners, review, search, services, unmatched
from app.config import settings
from app.db import init_models


async def _seed_catalog_if_empty() -> None:
    """Свежий деплой: если справочник пуст и есть seed-файл — загрузить его,
    иначе matching не работает и Партнёры пусты до ручной загрузки каталога."""
    import os

    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.matching.catalog import load_catalog
    from app.models import Service

    path = settings.seed_catalog_path
    if not path or not os.path.exists(path):
        return
    async with SessionLocal() as session:
        count = (await session.execute(select(func.count(Service.service_id)))).scalar_one()
        if count == 0:
            await load_catalog(session, path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    await _seed_catalog_if_empty()
    yield


app = FastAPI(
    title="MedArchive API",
    description="Обработка архива прайс-листов клиник-партнёров: поиск услуг, цен и партнёров.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(services.router)
app.include_router(partners.router)
app.include_router(search.router)
app.include_router(unmatched.router)
app.include_router(review.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
