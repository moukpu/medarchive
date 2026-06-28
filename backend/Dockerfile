FROM python:3.11-slim

# Системные зависимости для OCR и PDF→image
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000
# shell-форма, чтобы развернуть $PORT (Render/Railway задают порт через эту переменную)
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
