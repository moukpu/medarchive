"""Гибридная нормализация: точное → синонимы → fuzzy → эмбеддинги."""
from __future__ import annotations

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
        self.embedding: EmbeddingIndex | None = None

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
            try:
                idx.embedding = EmbeddingIndex(settings.embedding_model)
                idx.embedding.build(emb_items)
            except Exception:
                idx.embedding = None  # модель недоступна — деградируем до fuzzy
        return idx

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
        # 4. эмбеддинги (если доступны и fuzzy не уверен)
        if self.embedding is not None and score < 0.95:
            e_sid, e_score = self.embedding.query(raw_name)
            if e_score > score:
                best = MatchResult(e_sid, e_score, MatchMethod.embedding)
        if best.service_id is None or best.score < settings.match_threshold:
            # не дотянули до порога — оставляем предложение, но без авто-привязки
            return MatchResult(None, best.score, MatchMethod.none)
        return best
