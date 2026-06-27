"""Гибридная нормализация: точное → синонимы → fuzzy → эмбеддинги.

Embedding-тир работает в двух режимах (выбор автоматический в `build`):
* **pgvector** — на Postgres: вектора справочника лежат в `Service.embedding`,
  поиск идёт SQL-оператором `<=>` (масштабируется, не держит матрицу в RAM).
* **in-memory** — фоллбэк (SQLite/тесты): матрица в numpy, как раньше.

Вектора в обоих режимах считает `embed_service` — удалённый GPU-сервис, если задан
`MEDARCHIVE_EMBED_SERVE_URL`, иначе локальная модель. Чтобы минимизировать
HTTP-раундтрипы к GPU, embedding-тир считается батчем в `prepare(...)` ДО построчного
`match(...)`: один вызов на все имена документа, результат кладётся в кэш.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.matching.embeddings import EmbeddingIndex
from app.matching.fuzzy import best_fuzzy
from app.models import MatchMethod, Service


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


@dataclass
class MatchResult:
    service_id: str | None
    score: float
    method: MatchMethod


class CatalogIndex:
    """Предрассчитанный индекс справочника для быстрого матчинга всего архива."""

    def __init__(self):
        self.exact: dict[str, str] = {}        # norm(name) -> service_id
        self.synonyms: dict[str, str] = {}     # norm(synonym) -> service_id
        self.fuzzy_choices: dict[str, str] = {}  # service_id -> name
        self.embedding: EmbeddingIndex | None = None  # in-memory фоллбэк
        self.use_pgvector: bool = False
        # кэш embedding-тира: raw_name -> (service_id, score), заполняется в prepare()
        self._emb_cache: dict[str, tuple[str | None, float]] = {}
        # строки, признанные LLM немедицинскими (мусор) — откидываются в runner
        self._garbage: set[str] = set()

    @classmethod
    async def build(cls, session: AsyncSession) -> "CatalogIndex":
        idx = cls()
        res = await session.execute(select(Service).where(Service.is_active.is_(True)))
        services = res.scalars().all()
        emb_items: list[tuple[str, str]] = []
        for s in services:
            idx.exact[_norm(s.service_name)] = s.service_id
            idx.fuzzy_choices[s.service_id] = s.service_name
            emb_items.append((s.service_id, s.service_name))
            for syn in (s.synonyms or []):
                idx.synonyms[_norm(syn)] = s.service_id
                emb_items.append((s.service_id, syn))

        if settings.use_embeddings and emb_items:
            from app.matching import pgvector_match as pgv

            # На Postgres — pgvector: синхронизируем вектора справочника один раз.
            if pgv.is_postgres(session):
                try:
                    await pgv.sync_catalog_vectors(session)
                    idx.use_pgvector = await pgv.has_any_vectors(session)
                except Exception:  # noqa: BLE001 — расширение/сервис недоступны
                    idx.use_pgvector = False
            # Иначе (или если pgvector не поднялся) — in-memory матрица.
            if not idx.use_pgvector:
                try:
                    idx.embedding = EmbeddingIndex()
                    idx.embedding.build(emb_items)
                    if idx.embedding._matrix is None:  # эмбеддер недоступен
                        idx.embedding = None
                except Exception:  # noqa: BLE001
                    idx.embedding = None
        return idx

    async def prepare(self, session: AsyncSession, raw_names: list[str]) -> None:
        """Батч-вычисление embedding-тира для имён документа → во внутренний кэш.

        Один вызов эмбеддера на все новые имена. Безопасно вызывать несколько раз
        (считает только то, чего ещё нет в кэше). Для pgvector использует
        переданную `session` (важно при конкурентной обработке — у каждого
        воркера своя сессия).
        """
        names = [n for n in dict.fromkeys(raw_names) if n and n not in self._emb_cache]
        if not names:
            return
        if self.use_pgvector:
            from app.matching import pgvector_match as pgv
            from app.matching.embed_service import embed_texts

            vecs = await asyncio.to_thread(embed_texts, names)
            if vecs is None:
                return
            results = await pgv.query_vectors(session, vecs)
        elif self.embedding is not None:
            results = await asyncio.to_thread(self.embedding.query_many, names)
        else:
            return
        for name, res in zip(names, results):
            self._emb_cache[name] = res

    async def llm_refine(self, session: AsyncSession, raw_names: list[str]) -> None:
        """Резервный LLM-слой для строк, которые embedding-тир не сматчил уверенно.

        Точечный «скальпель» (Fallback Loop): берём только строки с embedding-скором
        ниже `embedding_match_threshold`, просим LLM нормализовать каждую в
        общепринятый медицинский термин, затем ПОВТОРНО ищем по вектору уже
        нормализованное имя. Строки, которые LLM признал немедицинскими, уходят в
        `_garbage` (runner их откидывает). Безопасно при выключенном/недоступном LLM.
        """
        if not settings.use_llm_extraction:
            return
        from app.matching.llm_normalize import llm_normalize_name

        # сложные строки: embedding не нашёл уверенного совпадения
        dirty: list[str] = []
        for n in dict.fromkeys(raw_names):
            if not n or n in self._garbage:
                continue
            cached = self._emb_cache.get(n)
            if cached is None:
                continue
            sid, score = cached
            if sid is None or score < settings.embedding_match_threshold:
                dirty.append(n)
        if not dirty:
            return

        # 1. LLM нормализует каждую грязную строку по одной (скальпель, не пачкой)
        normalized: dict[str, str] = {}
        for n in dirty:
            norm = await asyncio.to_thread(llm_normalize_name, n)
            if norm is None:
                self._garbage.add(n)        # не мед. услуга → мусор
            elif norm and norm != n:
                normalized[n] = norm
        if not normalized:
            return

        # 2. повторный векторный поиск по нормализованным именам (одним батчем)
        raws = list(normalized.keys())
        texts = [normalized[r] for r in raws]
        if self.use_pgvector:
            from app.matching import pgvector_match as pgv
            from app.matching.embed_service import embed_texts

            vecs = await asyncio.to_thread(embed_texts, texts)
            if vecs is None:
                return
            results = await pgv.query_vectors(session, vecs)
        elif self.embedding is not None:
            results = await asyncio.to_thread(self.embedding.query_many, texts)
        else:
            return

        # 3. если повторный поиск дал лучший результат — обновляем кэш под ИСХОДНЫМ именем
        for raw, (e_sid, e_score) in zip(raws, results):
            old = self._emb_cache.get(raw)
            if e_sid is not None and (old is None or e_score > old[1]):
                self._emb_cache[raw] = (e_sid, e_score)

    def is_garbage(self, raw_name: str) -> bool:
        """LLM пометил строку как немедицинскую — её следует откинуть."""
        return raw_name in self._garbage

    def match(self, raw_name: str) -> MatchResult:
        n = _norm(raw_name)
        if not n:
            return MatchResult(None, 0.0, MatchMethod.none)
        # 1. точное
        if n in self.exact:
            return MatchResult(self.exact[n], 1.0, MatchMethod.exact)
        # 2. синонимы
        if n in self.synonyms:
            return MatchResult(self.synonyms[n], 0.98, MatchMethod.synonym)
        # 3. fuzzy
        sid, score = best_fuzzy(raw_name, self.fuzzy_choices)
        best = MatchResult(sid, score, MatchMethod.fuzzy)
        # 4. эмбеддинги (prepare/llm_refine) — принимаем ТОЛЬКО при жёстком пороге
        # косинусного сходства: ниже порога «притянутые за уши» матчи отбрасываем.
        if score < 0.95:
            cached = self._emb_cache.get(raw_name)
            if cached is not None:
                e_sid, e_score = cached
                if (
                    e_sid is not None
                    and e_score >= settings.embedding_match_threshold
                    and e_score > score
                ):
                    best = MatchResult(e_sid, e_score, MatchMethod.embedding)
        if best.service_id is None or best.score < settings.match_threshold:
            # не дотянули до порога — оставляем предложение, но без авто-привязки
            return MatchResult(None, best.score, MatchMethod.none)
        return best
