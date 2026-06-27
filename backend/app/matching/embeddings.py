"""Семантическое сопоставление через sentence-transformers (с кэшем векторов).

numpy импортируется лениво, чтобы модуль грузился и при выключенных эмбеддингах
(MEDARCHIVE_USE_EMBEDDINGS=false) без установленного numpy/torch.
"""
from __future__ import annotations


class EmbeddingIndex:
    """Индекс эмбеддингов справочника. Векторы считаются один раз и кэшируются."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._ids: list[str] = []
        self._matrix = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def build(self, items: list[tuple[str, str]]) -> None:
        """items: [(service_id, text)]. Кодирует и нормирует векторы."""
        if not items:
            self._ids, self._matrix = [], None
            return
        self._ids = [i for i, _ in items]
        texts = [t for _, t in items]
        vecs = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        self._matrix = vecs

    def query(self, name: str) -> tuple[str | None, float]:
        import numpy as np

        if self._matrix is None or not self._ids:
            return None, 0.0
        q = self.model.encode([name], convert_to_numpy=True, normalize_embeddings=True)[0]
        sims = self._matrix @ q  # косинус (векторы нормированы)
        idx = int(np.argmax(sims))
        return self._ids[idx], float(sims[idx])
