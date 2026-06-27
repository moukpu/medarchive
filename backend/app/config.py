"""Настройки приложения. Импортируется в db.py, main.py и pipeline/*."""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEDARCHIVE_", env_file=".env", extra="ignore")

    # БД. По умолчанию async-Postgres; для тестов подменяется на sqlite+aiosqlite.
    database_url: str = "postgresql+asyncpg://medarchive:medarchive@db:5432/medarchive"

    @field_validator("database_url", mode="before")
    @classmethod
    def _coerce_async_driver(cls, v: str) -> str:
        """Render/Railway отдают DATABASE_URL как postgres://… или postgresql://… —
        приводим к async-драйверу asyncpg, чтобы переменную можно было прокинуть как есть."""
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return "postgresql+asyncpg://" + v[len("postgres://"):]
            if v.startswith("postgresql://") and "+" not in v.split("://", 1)[0]:
                return "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    # Хранилище оригиналов (НЕ удаляются — НФТ «сохранность данных»).
    data_dir: Path = BASE_DIR / "data"

    # Нормализация
    match_threshold: float = 0.70  # >= порог → авто-матч, иначе очередь unmatched
    # Лидер русских STS-бенчмарков (Encodechka/RusBEIR), 1024-dim, контекст 8192.
    # Обучен под semantic similarity (AnglE Loss) — точнее MiniLM на медицинской
    # номенклатуре. Тяжелее (~2 ГБ); для быстрого старта без модели — use_embeddings=false.
    embedding_model: str = "deepvk/USER-bge-m3"
    use_embeddings: bool = True  # можно отключить для быстрого старта без модели
    embedding_dim: int = 1024    # размерность векторов модели (bge-m3 = 1024); колонка pgvector

    # Удалённый GPU-сервис эмбеддингов (HF text-embeddings-inference / RunPod).
    # serve_url задан → вектора считает GPU (POST {url}/embed, контракт TEI),
    # модель НЕ грузится в веб-контейнер. Пусто → локальный SentenceTransformer.
    embed_serve_url: str | None = None     # MEDARCHIVE_EMBED_SERVE_URL
    embed_api_key: str | None = None       # Bearer для защищённого эндпоинта
    embed_batch_size: int = 64             # размер батча на один HTTP-вызов
    embed_timeout_seconds: int = 60        # таймаут вызова GPU-сервиса

    # OCR
    tesseract_lang: str = "rus+kaz+eng"
    # DPI рендера страниц скан-PDF для vision-OCR. 220 точнее на плотных таблицах,
    # чем 200; выше — больше токенов/времени. Tesseract-fallback всегда 300 DPI.
    vision_ocr_dpi: int = 220

    # LLM-извлечение (OpenAI). Используется как fallback, когда детерминированный
    # парсер дал мало строк, и как vision-OCR для скан-PDF. Без ключа — тихо
    # деградирует к Tesseract/regex (пайплайн остаётся рабочим).
    openai_api_key: str | None = None  # MEDARCHIVE_OPENAI_API_KEY или OPENAI_API_KEY
    openai_model: str = "gpt-5.4-mini"
    use_llm_extraction: bool = True
    llm_min_rows: int = 1     # если детерминированный парсер дал < N строк → пробуем LLM
    llm_max_pages: int = 10   # лимит страниц для vision-OCR (контроль стоимости)
    llm_max_chunks: int = 12  # лимит текстовых чанков на документ (контроль стоимости)

    # Валюты и курсы к KZT (на дату прайса; для MVP — статическая таблица, см. fx.py)
    base_currency: str = "KZT"

    # Аномалия цены
    price_anomaly_ratio: float = 0.5  # изменение > 50% → флаг аномалии

    # Конкурентная обработка документов в фоне (каждая задача — своя сессия БД)
    process_concurrency: int = 1  # 1 для free-tier Render (512 МБ RAM)

    # Авто-сид справочника при пустой БД (для свежего деплоя). Пустая строка → не сидить.
    seed_catalog_path: str = str(BASE_DIR / "data" / "samples" / "catalog.json")

    # Docling-фоллбэк для PDF (ML-структура таблиц). Пробуется перед LLM, если
    # детерминированный парсер дал мусор. serve_url задан → удалённый GPU-путь
    # (docling-serve/RunPod), иначе локальный пакет (тяжёлый, CPU-медленный).
    use_docling: bool = True
    docling_serve_url: str | None = None   # MEDARCHIVE_DOCLING_SERVE_URL; пусто → локальный путь
    docling_max_pages: int = 12            # жёсткий лимит страниц для ЛОКАЛЬНОГО CPU-прогона
    docling_timeout_seconds: int = 120     # таймаут HTTP-вызова docling-serve

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def samples_dir(self) -> Path:
        return self.data_dir / "samples"


settings = Settings()
