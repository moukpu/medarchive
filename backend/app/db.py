"""Async SQLAlchemy engine/session. Импортируется в api/*, pipeline/*, cli.py."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: одна сессия на запрос."""
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Создать таблицы (для dev/тестов без Alembic)."""
    from app import models  # noqa: F401  (регистрация моделей)

    async with engine.begin() as conn:
        # pgvector: расширение должно существовать ДО create_all, иначе колонка
        # Service.embedding (тип vector) не создастся («type vector does not exist»).
        if conn.dialect.name == "postgresql":
            from sqlalchemy import text

            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # На уже развёрнутой БД create_all не добавляет новые колонки к
        # существующим таблицам — докидываем Service.embedding идемпотентно.
        if conn.dialect.name == "postgresql":
            from sqlalchemy import text

            await conn.execute(text(
                f"ALTER TABLE services ADD COLUMN IF NOT EXISTS embedding vector({settings.embedding_dim})"
            ))
