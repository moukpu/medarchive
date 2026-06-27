"""Тестовая конфигурация: sqlite вместо Postgres, эмбеддинги выключены."""
import os

# Должно быть установлено ДО импорта app.config (settings читается при импорте).
os.environ.setdefault("MEDARCHIVE_DATABASE_URL", "sqlite+aiosqlite:///./test_medarchive.db")
os.environ.setdefault("MEDARCHIVE_USE_EMBEDDINGS", "false")

import pathlib

import pytest_asyncio


@pytest_asyncio.fixture
async def session():
    # чистая БД на каждый тест
    db_file = pathlib.Path("test_medarchive.db")
    if db_file.exists():
        db_file.unlink()

    from app.db import SessionLocal, engine, init_models

    await init_models()
    async with SessionLocal() as s:
        yield s
    await engine.dispose()
    if db_file.exists():
        db_file.unlink()
