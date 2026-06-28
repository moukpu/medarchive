"""Обработка документов: извлечение → валидация → нормализация → версионирование."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionLocal
from app.extractors.router import get_extractor
from app.models import (
    FileFormat,
    MatchMethod,
    ParseStatus,
    PriceDocument,
    PriceItem,
)
from app.pipeline.normalize import CatalogIndex
from app.pipeline.validate import validate_row


def _looks_low_quality(rows) -> bool:
    """Эвристика «детерминированный результат — мусор» → стоит звать LLM.

    Срабатывает при 0 строк или когда >30% строк подозрительны: цена < 200
    (номер строки/код принят за цену), цена/валюта затекла в название, либо
    название аномально длинное (слитые ячейки), либо цена > 5 млн (код позиции).
    """
    n = len(rows)
    if n < settings.llm_min_rows:
        return True
    suspicious = 0
    for r in rows:
        name = (r.service_name_raw or "")
        low = name.lower()
        # Цена < 200 ₸ — почти наверняка номер строки/код, не реальная цена
        bad_price = (
            (r.price_resident is not None and r.price_resident < 200)
            and (r.price_nonresident is None or r.price_nonresident < 200)
        )
        # нереально большая цена за услугу (> 5 млн ₸) — почти всегда в колонку
        # цены затёк код позиции
        for p in (r.price_resident, r.price_nonresident):
            if p is not None and p > 5_000_000:
                bad_price = True
        bad_name = len(name) > 80 or any(t in low for t in ("тенге", " тг", "₸", " тен"))
        if bad_price or bad_name:
            suspicious += 1
    return suspicious / n > 0.3


async def _prev_resident(session: AsyncSession, partner_id: str, service_name_raw: str) -> float | None:
    """Цена резидента из предыдущей активной версии (для детекта аномалии/дедупа)."""
    res = await session.execute(
        select(PriceItem).where(
            PriceItem.partner_id == partner_id,
            PriceItem.service_name_raw == service_name_raw,
            PriceItem.is_active.is_(True),
        )
    )
    item = res.scalars().first()
    return float(item.price_resident_kzt) if item and item.price_resident_kzt is not None else None


async def process_document(session: AsyncSession, doc_id: str, index: CatalogIndex | None = None) -> None:
    doc = await session.get(PriceDocument, doc_id)
    if doc is None:
        return
    doc.parse_status = ParseStatus.processing
    await session.commit()

    log: list[str] = []
    try:
        from app.extractors.base import ExtractResult

        # 1. Быстрый и дешевый путь: всегда пробуем локальный экстрактор (например, pdfplumber для PDF)
        extractor = get_extractor(doc.file_format)
        result = await asyncio.to_thread(extractor.extract, doc.file_path)
        doc.raw_content = (result.raw_text or "")[:200_000]
        log.extend(result.warnings)

        is_pdf = doc.file_format in (FileFormat.pdf, FileFormat.scan_pdf)
        # Скан — только если строк НЕ извлеклось И текста почти нет. Если локальный
        # extractor (для scan_pdf это уже vision-OCR) дал строки — это НЕ «пустой скан»,
        # и тяжёлый путь запускать нельзя, иначе он затрёт хороший результат.
        is_scan = (
            is_pdf
            and not result.rows
            and len((result.raw_text or "").strip()) < 50
        )
        if is_scan:
            log.append("Текст не извлечён — документ похож на скан/картинку.")

        # 2. LLM-фоллбэк по тексту: только если ТЕКСТ есть, но строки мусорные.
        llm_succeeded = False
        if not is_scan and _looks_low_quality(result.rows) and settings.use_llm_extraction:
            from app.extractors.llm import llm_available, rows_from_text_llm
            if llm_available() and result.raw_text:
                log.append("Сырой текст отправлен в LLM для нормализации...")
                llm_rows, llm_warnings = rows_from_text_llm(result.raw_text)
                log.extend(llm_warnings)
                if llm_rows:
                    result.rows = llm_rows
                    llm_succeeded = True
                else:
                    log.append("LLM не смогла найти позиции (вероятно, слишком сложная структура).")

        # 2b. Vision-OCR для скана, если строк до сих пор нет (например, текстовый PDF
        #     ошибочно не распознан как скан, либо vision в extractor дал пусто).
        if is_scan and not result.rows and settings.use_llm_extraction:
            from app.extractors.llm import llm_available, rows_from_pdf_images_llm
            if llm_available():
                log.append("Скан → распознаём таблицу через vision-OCR...")
                v_rows, v_warnings = await asyncio.to_thread(rows_from_pdf_images_llm, doc.file_path)
                log.extend(v_warnings)
                if v_rows:
                    result.rows = v_rows

        # 3. Тяжёлый путь (Docling) — ТОЛЬКО когда строк по-прежнему нет.
        #    Никогда не перезаписываем уже извлечённые строки: на кривых сканах
        #    docling берёт мусор и затёр бы хороший vision/таблично-парсенный результат.
        needs_heavy_ocr = is_pdf and not result.rows

        if needs_heavy_ocr:
            from app.extractors.docling_extractor import docling_available, rows_from_pdf_docling
            if docling_available():
                log.append("Переход на тяжелый визуальный анализ (Docling на GPU)...")
                d_rows, d_warnings = await asyncio.to_thread(rows_from_pdf_docling, doc.file_path)
                log.extend(d_warnings)
                if d_rows:
                    result.rows = d_rows
                    try:
                        doc.raw_content = f"[PDF обработан через Docling GPU, {len(d_rows)} позиций]"
                    except Exception:
                        pass
                else:
                    log.append("Docling также не смог найти позиции.")
            else:
                log.append("Docling недоступен на RunPod, пропускаем тяжелый OCR.")

        if not result.rows:
            doc.parse_status = ParseStatus.error
            log.append("Документ не содержит распознаваемых данных")
            doc.parse_log = "\n".join(log)
            doc.parsed_at = datetime.now(timezone.utc)
            await session.commit()
            return

        if index is None:
            index = await CatalogIndex.build(session)

        # Embedding-тир — одним батчем на все имена документа (минимум вызовов GPU).
        raw_names = [r.service_name_raw for r in result.rows]
        await index.prepare(session, raw_names)
        # LLM-фоллбэк (скальпель): нормализуем строки, не дотянувшие до порога, и
        # помечаем немедицинские как мусор.
        await index.llm_refine(session, raw_names)

        needs_review_doc = False
        for row in result.rows:
            if index.is_garbage(row.service_name_raw):
                log.append(f"{row.service_name_raw}: отброшено — LLM счёл немедицинской позицией")
                continue
            prev = await _prev_resident(session, doc.partner_id, row.service_name_raw)
            v = validate_row(row, doc.effective_date, prev_resident_kzt=prev)
            if v.skip:
                log.extend(v.warnings)
                continue

            # Версионирование/дедуп: старую активную позицию (та же клиника+услуга)
            # архивируем (is_active=false), новую делаем активной.
            old = await session.execute(
                select(PriceItem).where(
                    PriceItem.partner_id == doc.partner_id,
                    PriceItem.service_name_raw == row.service_name_raw,
                    PriceItem.is_active.is_(True),
                )
            )
            for prev_item in old.scalars():
                prev_item.is_active = False

            match = index.match(row.service_name_raw)
            item = PriceItem(
                doc_id=doc.doc_id,
                partner_id=doc.partner_id,
                service_name_raw=row.service_name_raw,
                service_code_source=row.service_code_source,
                service_id=match.service_id,
                price_resident_kzt=v.price_resident_kzt,
                price_nonresident_kzt=v.price_nonresident_kzt,
                price_original=v.price_original,
                currency_original=v.currency_original,
                effective_date=doc.effective_date,
                is_active=True,
                match_score=match.score,
                match_method=match.method if match.service_id else MatchMethod.none,
                needs_review=v.needs_review or match.service_id is None,
            )
            session.add(item)
            if item.needs_review:
                needs_review_doc = True
            if v.warnings:
                log.append(f"{row.service_name_raw}: " + "; ".join(v.warnings))

        # Документ обрезан по лимитам LLM (страницы/чанки) → часть строк потеряна,
        # требуется ручная проверка. Маркер ставят экстракторы (TRUNCATED_MARK).
        if any("ОБРЕЗАНО" in line for line in log):
            needs_review_doc = True

        doc.parse_status = ParseStatus.needs_review if needs_review_doc else ParseStatus.done
        doc.parsed_at = datetime.now(timezone.utc)
        doc.parse_log = "\n".join(log)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        doc = await session.get(PriceDocument, doc_id)
        if doc:
            doc.parse_status = ParseStatus.error
            doc.parse_log = (doc.parse_log or "") + f"\nОшибка обработки: {exc}"
            doc.parsed_at = datetime.now(timezone.utc)
            await session.commit()


async def process_pending(session: AsyncSession) -> int:
    """Обработать все документы в статусе pending.

    Индекс справочника строится один раз и шарится (read-only, только строки —
    безопасно между сессиями и потоками). Документы обрабатываются конкурентно
    с ограничением `settings.process_concurrency`; каждая задача берёт свою сессию,
    т.к. async-сессия SQLAlchemy не рассчитана на конкурентное использование.
    """
    res = await session.execute(
        select(PriceDocument.doc_id, PriceDocument.file_path).where(PriceDocument.parse_status == ParseStatus.pending)
    )
    docs = res.all()
    if not docs:
        return 0
    
    import os
    def get_size(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return float('inf')
            
    docs_sorted = sorted(docs, key=lambda d: get_size(d[1]))
    doc_ids = [d[0] for d in docs_sorted]
    
    index = await CatalogIndex.build(session)

    sem = asyncio.Semaphore(max(1, settings.process_concurrency))

    async def _worker(doc_id: str) -> None:
        async with sem:
            async with SessionLocal() as task_session:
                await process_document(task_session, doc_id, index=index)

    # Запускаем задачи в порядке возрастания размера
    tasks = [_worker(doc_id) for doc_id in doc_ids]
    running_tasks = []
    for task in tasks:
        running_tasks.append(asyncio.create_task(task))
        await asyncio.sleep(0.5) # Небольшая задержка, чтобы семафор захватывался строго в нужном порядке
        
    # Обязательно дожидаемся выполнения всех задач, иначе BackgroundTasks завершится,
    # а задачи могут быть убиты сборщиком мусора.
    if running_tasks:
        await asyncio.gather(*running_tasks, return_exceptions=True)
        
    return len(doc_ids)
