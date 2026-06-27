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
        await conn.run_sync(Base.metadata.create_all)
