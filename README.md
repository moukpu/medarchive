# MedArchive — обработка архива прайсов клиник-партнёров (Кейс 2, MedPartners)

Система автоматической обработки архива прайс-листов клиник: извлечение из
**PDF / PDF-скан / DOCX / XLSX**, нормализация по целевому справочнику услуг,
валидация и верификация, REST API и UI поиска «кто оказывает услугу и по какой цене».

## Архитектура

```
ZIP → Ingest → Router(формат) → Extractor(plugin) → Валидация(§4.4)
   → Нормализация(точное→синонимы→fuzzy→embeddings) → PostgreSQL
   → FastAPI REST API → React UI (поиск + админка верификации + дашборд)
```

Каждый формат — отдельный extractor-плагин с единым интерфейсом
(`app/extractors/*`), ядро (валидация/нормализация/хранение) от формата не зависит
→ новый формат добавляется без правки ядра (НФТ «масштабируемость»).

## Стек
- Backend: Python 3.11 + FastAPI + SQLAlchemy (async)
- БД: PostgreSQL
- Извлечение: pdfplumber / PyMuPDF, python-docx, openpyxl
- OCR: Tesseract (`rus+kaz+eng`) + pdf2image
- Нормализация: RapidFuzz + sentence-transformers (гибрид)
- Очередь: FastAPI BackgroundTasks (статусы в БД)
- Frontend: React + Vite + TypeScript

## Быстрый запуск (Docker)

```bash
docker compose up --build
```
- API + Swagger: http://localhost:8000/docs
- UI: http://localhost:5173

## Запуск backend локально (без Docker)

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -e .
# По умолчанию указывает на Postgres; для локального теста можно sqlite:
export MEDARCHIVE_DATABASE_URL="sqlite+aiosqlite:///./medarchive.db"
uvicorn app.main:app --reload
```

> Для OCR нужны системные пакеты: `tesseract-ocr` (+ языковые пакеты rus/kaz) и
> `poppler-utils`. В Docker они уже установлены.

## Деплой (Render / Railway)

Прод-сборка не использует Vite dev-сервер: фронт собирается в статику и отдаётся
через **nginx**, бэкенд читает `$PORT`, `DATABASE_URL` любого вида (`postgres://`,
`postgresql://`) автоматически приводится к async-драйверу.

### Render (Blueprint, рекомендуется)
1. Push репозитория в GitHub.
2. Render → **New → Blueprint** → выбрать репозиторий (там лежит `render.yaml`:
   Postgres + `medarchive-api` + `medarchive-web`).
3. После первого деплоя задать у `medarchive-web` переменную `VITE_API_URL` =
   публичный URL API (например `https://medarchive-api.onrender.com`) и пересобрать
   фронт. У `medarchive-api` опционально задать `MEDARCHIVE_HF_API_KEY` (HF токен).
4. Справочник услуг засевается автоматически при пустой БД
   (`MEDARCHIVE_SEED_CATALOG_PATH`, по умолчанию `data/samples/catalog.json`).
   Свой каталог — `python -m app.cli load-catalog <path>` через Shell сервиса.

> На free-инстансах держите `MEDARCHIVE_USE_EMBEDDINGS=false` (в `render.yaml` уже так):
> torch ~ГБ может не влезть по памяти. Fuzzy-нормализация остаётся.

### Railway
То же самое вручную: Postgres-плагин + два сервиса из `backend/Dockerfile` и
`frontend/Dockerfile`. Переменные: `MEDARCHIVE_DATABASE_URL` (из Postgres),
`MEDARCHIVE_USE_EMBEDDINGS=false`, для фронта build-arg `VITE_API_URL` = URL API.

## Docling-фоллбэк для PDF (опционально)

Для PDF, где детерминированный парсер даёт мусор, перед LLM пробуется **Docling**
(ML-модель структуры таблиц). Цепочка: `pdfplumber → docling → LLM`. Включён по
умолчанию, но без установленного пакета/URL просто пропускается.

- **Удалённо (рекомендуется, быстро):** поднять [`docling-serve`](https://github.com/docling-project/docling-serve)
  на GPU (RunPod/Vast/Modal, CUDA-образ) и задать `MEDARCHIVE_DOCLING_SERVE_URL=https://…`.
  Локально ставить ничего не нужно — бэкенд шлёт файл на `POST /v1/convert/file`.
- **Локально (тяжело, CPU):** `pip install -e ".[docling]"` (~1ГБ моделей при первом
  запуске). Прогон ограничен `MEDARCHIVE_DOCLING_MAX_PAGES` (по умолчанию 12) — защита
  от OOM/многоминутных прогонов на длинных файлах.
- Выключить совсем: `MEDARCHIVE_USE_DOCLING=false`.

## Рабочий сценарий (CLI)

```bash
cd backend
python scripts/make_samples.py                       # сгенерировать демо-данные
python -m app.cli load-catalog data/samples/catalog.json
python -m app.cli ingest-zip data/samples/archive.zip   # принять + обработать архив
python -m app.cli report                             # отчёт о качестве
```

`report` печатает: документы по статусам, число позиций, **% автонормализации**,
размер очереди `unmatched` — это и есть отчёт о качестве обработки для сдачи.

## REST API (ТЗ §4.5)

| Метод | Endpoint | Описание |
|---|---|---|
| GET | `/services` | справочник услуг (фильтр `category`) |
| GET | `/services/{id}/partners` | партнёры с ценами по услуге |
| GET | `/partners` | партнёры (фильтр `city`, `is_active`) |
| GET | `/partners/{id}/services` | весь прайс партнёра |
| GET | `/search?q=` | поиск по услугам и партнёрам |
| GET | `/unmatched` | очередь несопоставленных позиций + предложения |
| POST | `/match` | ручное сопоставление позиции с услугой |
| POST | `/admin/upload` | загрузка ZIP-архива (обработка в фоне) |
| GET | `/admin/status` | статусы документов |
| GET | `/admin/dashboard` | метрики качества |

Полная OpenAPI-спека — на `/docs` и `/openapi.json`.

## Загрузка справочника
Поддерживаются **XLSX** и **JSON**. Минимальные поля: `service_name`, `synonyms`,
`category` (+ опционально `service_id`, `icd_code`). Загрузка через
`app.cli load-catalog <path>`.

## Модель данных (ТЗ §3)
`Partner` · `PriceDocument` · `PriceItem` · `Service` — см. `app/models.py`.
Версионирование цен: при новом прайсе старая позиция получает `is_active=false`,
ничего не удаляется (история бессрочно). Исходные файлы хранятся в
`backend/data/uploads/`.

## Тесты
```bash
cd backend
pip install -e ".[dev]"
pytest -q
```
Покрытие: парсинг цен/валют/колонок, разбор таблиц (заголовок не в первой строке),
OCR-парсер, полный E2E (справочник → XLSX → обработка → нормализация), правила
валидации (нерезидент < резидент, конвертация валют).

## Что сделано по критериям оценки
- **Извлечение (30%)** — 4 плагина форматов, accept tracked changes в DOCX, OCR-постобработка.
- **Нормализация (25%)** — гибридный каскад с настраиваемым порогом, очередь unmatched.
- **Валидация (20%)** — все правила §4.4, версионирование, конвертация валют, детект аномалий.
- **API (15%)** — все эндпоинты + OpenAPI.
- **UX (10%)** — поиск, страница партнёра, очередь верификации, дашборд.
