"""pgvector-матчинг справочника услуг.

Вектора услуг (имя + синонимы) хранятся в Postgres в колонке `Service.embedding`,
поиск ближайшего — нативный оператор косинусной дистанции `<=>`. Это убирает
in-memory матрицу: справочник может быть большим, поиск идёт в БД.

Активен ТОЛЬКО на Postgres. На SQLite (тесты) `is_postgres` → False, и
`CatalogIndex` откатывается к in-memory `EmbeddingIndex`.

Все функции async (работают с сессией БД). Сам эмбеддинг считается синхронным
`embed_texts`, поэтому вызывается через `asyncio.to_thread`.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.embed_service import embed_texts
from app.models import Service


def is_postgres(session: AsyncSession) -> bool:
    bind = session.get_bind()
    return bind.dialect.name == "postgresql"


def _service_text(s: Service) -> str:
    """Текст для эмбеддинга услуги: имя + синонимы (для лучшего семантического охвата)."""
    parts = [s.service_name]
    parts.extend(syn for syn in (s.synonyms or []) if syn)
    seen: set[str] = set()
    uniq = [p for p in parts if not (p in seen or seen.add(p))]
    return ". ".join(uniq)


def _vec_literal(vec: list[float]) -> str:
    """Векторный литерал pgvector: '[0.1,0.2,...]' (для каста (:q)::vector)."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def ensure_extension(session: AsyncSession) -> None:
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


async def sync_catalog_vectors(session: AsyncSession, force: bool = False) -> int:
    """Посчитать и сохранить вектора активных услуг.

    force=False → только те, у кого embedding ещё NULL (инкрементально).
    Возвращает число обновлённых услуг. 0 при выключенных/недоступных эмбеддингах.
    """
    await ensure_extension(session)
    q = select(Service).where(Service.is_active.is_(True))
    if not force:
        q = q.where(Service.embedding.is_(None))
    services = (await session.execute(q)).scalars().all()
    if not services:
        return 0
    texts = [_service_text(s) for s in services]
    vecs = await asyncio.to_thread(embed_texts, texts)
    if vecs is None:
        return 0
    for s, v in zip(services, vecs):
        s.embedding = v
    await session.commit()
    return len(services)


async def query_vectors(
    session: AsyncSession, vecs: list[list[float]]
) -> list[tuple[str | None, float]]:
    """Для каждого вектора — (service_id, косинус) ближайшей услуги справочника."""
    out: list[tuple[str | None, float]] = []
    stmt = text(
        "SELECT service_id, 1 - (embedding <=> (:q)::vector) AS sim "
        "FROM services "
        "WHERE embedding IS NOT NULL AND is_active = true "
        "ORDER BY embedding <=> (:q)::vector LIMIT 1"
    )
    for v in vecs:
        row = (await session.execute(stmt, {"q": _vec_literal(v)})).first()
        out.append((row[0], float(row[1])) if row else (None, 0.0))
    return out


async def has_any_vectors(session: AsyncSession) -> bool:
    """Есть ли хоть один сохранённый вектор (иначе pgvector-путь бесполезен)."""
    row = (await session.execute(
        select(Service.service_id).where(Service.embedding.is_not(None)).limit(1)
    )).first()
    return row is not None
