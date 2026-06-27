"""ORM-модели по ТЗ §3: Partner, PriceDocument, PriceItem, Service."""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base

# pgvector опционален: на Postgres колонка Service.embedding — нативный vector
# (поиск через оператор `<=>`), на SQLite (тесты) / без установленного пакета
# деградирует до JSON, чтобы create_all и импорт моделей не падали.
try:
    from pgvector.sqlalchemy import Vector

    _EmbeddingType = Vector(settings.embedding_dim).with_variant(JSON(), "sqlite")
except Exception:  # noqa: BLE001 — pgvector не установлен
    _EmbeddingType = JSON


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FileFormat(str, enum.Enum):
    pdf = "pdf"
    docx = "docx"
    xlsx = "xlsx"
    scan_pdf = "scan_pdf"


class ParseStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    error = "error"
    needs_review = "needs_review"


class Currency(str, enum.Enum):
    KZT = "KZT"
    USD = "USD"
    RUB = "RUB"


class MatchMethod(str, enum.Enum):
    exact = "exact"
    synonym = "synonym"
    fuzzy = "fuzzy"
    embedding = "embedding"
    manual = "manual"
    none = "none"


class Partner(Base):
    __tablename__ = "partners"

    partner_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512), index=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    bin: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    documents: Mapped[list["PriceDocument"]] = relationship(back_populates="partner")
    items: Mapped[list["PriceItem"]] = relationship(back_populates="partner")


class PriceDocument(Base):
    __tablename__ = "price_documents"

    doc_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    partner_id: Mapped[str] = mapped_column(ForeignKey("partners.partner_id"), index=True)
    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # путь к оригиналу
    file_format: Mapped[FileFormat] = mapped_column(Enum(FileFormat))
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parse_status: Mapped[ParseStatus] = mapped_column(Enum(ParseStatus), default=ParseStatus.pending)
    parse_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)  # сырьё для аудита

    partner: Mapped[Partner] = relationship(back_populates="documents")
    items: Mapped[list["PriceItem"]] = relationship(back_populates="document")


class PriceItem(Base):
    __tablename__ = "price_items"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(ForeignKey("price_documents.doc_id"), index=True)
    partner_id: Mapped[str] = mapped_column(ForeignKey("partners.partner_id"), index=True)
    service_name_raw: Mapped[str] = mapped_column(String(1024), index=True)
    service_code_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("services.service_id"), nullable=True, index=True
    )
    price_resident_kzt: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_nonresident_kzt: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_original: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency_original: Mapped[Currency] = mapped_column(Enum(Currency), default=Currency.KZT)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)  # версионирование
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_method: Mapped[MatchMethod] = mapped_column(Enum(MatchMethod), default=MatchMethod.none)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    document: Mapped[PriceDocument] = relationship(back_populates="items")
    partner: Mapped[Partner] = relationship(back_populates="items")
    service: Mapped["Service | None"] = relationship(back_populates="items")


class Service(Base):
    __tablename__ = "services"

    service_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    service_name: Mapped[str] = mapped_column(String(512), index=True)
    synonyms: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    icd_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Семантический вектор услуги (имя + синонимы), pgvector. None → ещё не посчитан.
    embedding: Mapped[list[float] | None] = mapped_column(_EmbeddingType, nullable=True)

    items: Mapped[list[PriceItem]] = relationship(back_populates="service")
