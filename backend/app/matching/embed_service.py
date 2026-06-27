"""Единая точка получения эмбеддингов текста.

Два пути, выбор по настройке `embed_serve_url`:

* **remote** — POST на GPU-сервис (HF text-embeddings-inference / RunPod).
  Контракт TEI: `POST {url}/embed` с телом `{"inputs": [...]}` → `[[float, ...], ...]`.
  Этим способом официально сервится bge-m3. 2-ГБ модель НЕ грузится в веб-контейнер —
  сюда приходят готовые вектора.
* **local** — ленивый `SentenceTransformer(embedding_model)` в процессе (старое
  поведение; тяжёлый, нужен torch).

Везде на выходе — L2-нормированные векторы (косинус = скалярное произведение).
`embed_texts` НИКОГДА не бросает наружу: при сбое возвращает None, чтобы матчинг
тихо деградировал к fuzzy. Функция синхронная (httpx.Client / encode) — вызывать
из async-кода через `asyncio.to_thread`.
"""
from __future__ import annotations

import math

from app.config import settings

# Ленивый кэш локальной модели (чтобы не грузить torch на каждый вызов).
_local_model = None


def embeddings_enabled() -> bool:
    return settings.use_embeddings


def remote_mode() -> bool:
    """Используется ли удалённый GPU-сервис (а не локальная модель)."""
    return bool(settings.embed_serve_url)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _embed_remote(texts: list[str]) -> list[list[float]]:
    import httpx

    url = settings.embed_serve_url.rstrip("/") + "/embed"
    headers = {}
    if settings.embed_api_key:
        headers["Authorization"] = f"Bearer {settings.embed_api_key}"

    out: list[list[float]] = []
    batch = max(1, settings.embed_batch_size)
    with httpx.Client(timeout=settings.embed_timeout_seconds) as client:
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            resp = client.post(url, json={"inputs": chunk}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # TEI отдаёт список векторов; некоторые обёртки — {"embeddings": [...]}.
            vecs = data["embeddings"] if isinstance(data, dict) else data
            out.extend(_l2_normalize([float(x) for x in v]) for v in vecs)
    return out


def _embed_local(texts: list[str]) -> list[list[float]]:
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer(settings.embedding_model)
    vecs = _local_model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Список нормированных векторов в порядке `texts`.

    None — если эмбеддинги выключены, вход пуст или сервис/модель недоступны
    (пайплайн должен продолжить работу на fuzzy).
    """
    if not texts or not settings.use_embeddings:
        return None
    try:
        if remote_mode():
            return _embed_remote(texts)
        return _embed_local(texts)
    except Exception:  # noqa: BLE001 — любой сбой → деградируем к fuzzy
        return None
