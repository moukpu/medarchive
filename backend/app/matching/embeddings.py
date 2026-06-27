"""In-memory семантический индекс справочника (фоллбэк, когда pgvector недоступен —
напр. на SQLite в тестах). Векторы берутся через `embed_service.embed_texts`
(удалённый GPU-сервис ИЛИ локальная модель — без разницы для этого модуля).

numpy импортируется лениво, чтобы модуль грузился и при выключенных эмбеддингах.
"""
from __future__ import annotations

from app.matching.embed_service import embed_texts


class EmbeddingIndex:
    """Индекс эмбеддингов справочника. Векторы считаются один раз и кэшируются."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._matrix = None  # (n_items, dim), L2-нормирован

    def build(self, items: list[tuple[str, str]]) -> None:
        """items: [(service_id, text)]. Кодирует и кэширует матрицу векторов."""
        if not items:
            self._ids, self._matrix = [], None
            return
        ids = [i for i, _ in items]
        texts = [t for _, t in items]
        vecs = embed_texts(texts)
        if vecs is None:
            self._ids, self._matrix = [], None
            return
        import numpy as np

        self._ids = ids
        self._matrix = np.asarray(vecs, dtype="float32")

    def query_many(self, names: list[str]) -> list[tuple[str | None, float]]:
        """Для каждого имени — (service_id, косинус) лучшего совпадения.

        Один батч-вызов эмбеддера на все имена (важно для удалённого GPU-сервиса —
        минимум HTTP-раундтрипов).
        """
        if self._matrix is None or not self._ids or not names:
            return [(None, 0.0)] * len(names)
        qv = embed_texts(names)
        if qv is None:
            return [(None, 0.0)] * len(names)
        import numpy as np

        q = np.asarray(qv, dtype="float32")          # (m, dim)
        sims = self._matrix @ q.T                     # (n_items, m), косинус (всё нормировано)
        out: list[tuple[str | None, float]] = []
        for j in range(q.shape[0]):
            i = int(np.argmax(sims[:, j]))
            out.append((self._ids[i], float(sims[i, j])))
        return out

    def query(self, name: str) -> tuple[str | None, float]:
        return self.query_many([name])[0]
