"""Тесты GPU-клиента эмбеддингов (app.matching.embed_service).

Сеть не трогаем: httpx.Client подменяется заглушкой, имитирующей TEI-ответ.
"""
from __future__ import annotations

import math

import httpx

from app.config import settings
from app.matching import embed_service


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Заглушка httpx.Client: TEI-ответ [3,4] (норма 5) на каждый вход."""

    last_payloads: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json, headers=None):
        _FakeClient.last_payloads.append(json)
        return _FakeResponse([[3.0, 4.0] for _ in json["inputs"]])


def test_remote_embed_normalizes(monkeypatch):
    monkeypatch.setattr(settings, "use_embeddings", True)
    monkeypatch.setattr(settings, "embed_serve_url", "http://gpu.local:8080")
    monkeypatch.setattr(settings, "embed_api_key", "secret")
    monkeypatch.setattr(httpx, "Client", _FakeClient)

    out = embed_service.embed_texts(["анализ крови", "узи"])

    assert out is not None and len(out) == 2
    for vec in out:
        assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-6)
    assert math.isclose(out[0][0], 0.6, rel_tol=1e-6)
    assert math.isclose(out[0][1], 0.8, rel_tol=1e-6)


def test_remote_sends_inputs_payload(monkeypatch):
    _FakeClient.last_payloads = []
    monkeypatch.setattr(settings, "use_embeddings", True)
    monkeypatch.setattr(settings, "embed_serve_url", "http://gpu.local:8080")
    monkeypatch.setattr(httpx, "Client", _FakeClient)

    embed_service.embed_texts(["x"])
    assert _FakeClient.last_payloads == [{"inputs": ["x"]}]


def test_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "use_embeddings", False)
    assert embed_service.embed_texts(["x"]) is None


def test_empty_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "use_embeddings", True)
    assert embed_service.embed_texts([]) is None


def test_remote_failure_degrades_to_none(monkeypatch):
    class _BoomClient(_FakeClient):
        def post(self, *a, **k):
            raise RuntimeError("gpu down")

    monkeypatch.setattr(settings, "use_embeddings", True)
    monkeypatch.setattr(settings, "embed_serve_url", "http://gpu.local:8080")
    monkeypatch.setattr(httpx, "Client", _BoomClient)
    assert embed_service.embed_texts(["x"]) is None
