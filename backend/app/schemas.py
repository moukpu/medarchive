"""Pydantic-схемы для API (request/response)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    service_id: str
    service_name: str
    synonyms: list[str] = []
    category: str | None = None
    icd_code: str | None = None
    is_active: bool = True


class PartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    partner_id: str
    name: str
    city: str | None = None
    address: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    is_active: bool = True


class PriceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: str
    service_name_raw: str
    service_id: str | None = None
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    price_original: float | None = None
    currency_original: str = "KZT"
    effective_date: date | None = None
    is_verified: bool = False
    match_score: float | None = None
    match_method: str = "none"
    needs_review: bool = False


class PartnerWithPrice(BaseModel):
    """Для /services/{id}/partners — партнёр + его цена на услугу."""
    partner: PartnerOut
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    effective_date: date | None = None
    item_id: str


class ServiceWithPrice(BaseModel):
    """Для /partners/{id}/services — услуга + цена партнёра."""
    item_id: str
    service_name_raw: str
    service_id: str | None = None
    service_name: str | None = None
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    effective_date: date | None = None
    is_active: bool = True  # false → архивная (предыдущая) версия цены


class UnmatchedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: str
    service_name_raw: str
    partner_id: str
    match_score: float | None = None
    suggestions: list[ServiceOut] = []


class MatchRequest(BaseModel):
    item_id: str
    service_id: str
    note: str | None = None


class DocumentStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    doc_id: str
    file_name: str
    file_format: str
    parse_status: str
    effective_date: date | None = None
    parsed_at: datetime | None = None


class DashboardOut(BaseModel):
    documents_total: int
    documents_by_status: dict[str, int]
    items_total: int
    items_matched: int
    items_unmatched: int
    items_needs_review: int
    auto_match_rate: float  # % автосопоставления


class ReviewItemOut(BaseModel):
    """Позиция в очереди верификации — несопоставленная ИЛИ флагнутая (аномалия и т.п.)."""
    item_id: str
    service_name_raw: str
    partner_id: str
    partner_name: str | None = None
    doc_id: str
    file_name: str | None = None
    effective_date: date | None = None
    service_id: str | None = None
    service_name: str | None = None
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    match_score: float | None = None
    match_method: str = "none"
    is_verified: bool = False
    reasons: list[str] = []          # причины ревью (нет матча / аномалия / нерезидент<резидент)
    suggestions: list[ServiceOut] = []


class ItemUpdate(BaseModel):
    """PATCH /items/{id} — ручная правка позиции при верификации."""
    service_id: str | None = None
    price_resident_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    note: str | None = None


class ItemContextOut(BaseModel):
    """Исходный контекст позиции — «показать в файле»."""
    item_id: str
    service_name_raw: str
    doc_id: str
    file_name: str | None = None
    file_format: str | None = None
    effective_date: date | None = None
    parse_log: str | None = None
    raw_snippet: str | None = None   # фрагмент исходного текста вокруг названия позиции
