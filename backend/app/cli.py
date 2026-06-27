"""CLI: загрузка справочника, ingest архива, обработка, отчёт о качестве."""
from __future__ import annotations

import asyncio

import typer

from app.db import SessionLocal, init_models
from app.matching.catalog import load_catalog as _load_catalog
from app.pipeline.ingest import ingest_zip as _ingest_zip
from app.pipeline.runner import process_pending as _process_pending

app = typer.Typer(help="MedArchive CLI")


@app.command()
def initdb():
    """Создать таблицы БД."""
    asyncio.run(init_models())
    typer.echo("БД инициализирована.")


@app.command("load-catalog")
def load_catalog(path: str):
    """Загрузить справочник услуг (XLSX или JSON)."""
    async def _run():
        await init_models()
        async with SessionLocal() as s:
            return await _load_catalog(s, path)

    count = asyncio.run(_run())
    typer.echo(f"Загружено услуг: {count}")


@app.command("ingest-zip")
def ingest_zip(path: str, process: bool = typer.Option(True, help="Сразу обработать")):
    """Принять ZIP-архив прайсов и (опционально) обработать."""
    async def _run():
        await init_models()
        async with SessionLocal() as s:
            doc_ids = await _ingest_zip(s, path)
            if process:
                await _process_pending(s)
            return doc_ids

    doc_ids = asyncio.run(_run())
    typer.echo(f"Поставлено документов: {len(doc_ids)}")


@app.command()
def process():
    """Обработать все pending-документы."""
    async def _run():
        async with SessionLocal() as s:
            return await _process_pending(s)

    n = asyncio.run(_run())
    typer.echo(f"Обработано документов: {n}")


@app.command()
def report():
    """Отчёт о качестве: документы по статусам, % автонормализации, очередь."""
    from sqlalchemy import func, select

    from app.models import PriceDocument, PriceItem

    async def _run():
        async with SessionLocal() as s:
            by_status = {}
            rows = await s.execute(
                select(PriceDocument.parse_status, func.count()).group_by(PriceDocument.parse_status)
            )
            for st, c in rows.all():
                by_status[st.value] = c
            total = (await s.execute(
                select(func.count(PriceItem.item_id)).where(PriceItem.is_active.is_(True))
            )).scalar_one()
            matched = (await s.execute(
                select(func.count(PriceItem.item_id)).where(
                    PriceItem.is_active.is_(True), PriceItem.service_id.is_not(None)
                )
            )).scalar_one()
            return by_status, total, matched

    by_status, total, matched = asyncio.run(_run())
    rate = (matched / total * 100.0) if total else 0.0
    typer.echo("=== Отчёт о качестве обработки ===")
    typer.echo(f"Документы по статусам: {by_status}")
    typer.echo(f"Активных позиций: {total}")
    typer.echo(f"Сопоставлено автоматически: {matched} ({rate:.1f}%)")
    typer.echo(f"В очереди unmatched: {total - matched}")


if __name__ == "__main__":
    app()
