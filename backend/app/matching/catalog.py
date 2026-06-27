"""Загрузка целевого справочника услуг (XLSX или JSON) в таблицу Service."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Service


def _parse_synonyms(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            return [str(v).strip() for v in json.loads(s)]
        except json.JSONDecodeError:
            pass
    # синонимы через ; или |
    for sep in (";", "|", ","):
        if sep in s:
            return [p.strip() for p in s.split(sep) if p.strip()]
    return [s]


# Псевдонимы заголовков колонок справочника (реальные файлы — на русском/смешанные).
# Порядок алиасов = приоритет. ВАЖНО: bare "id"/"code" НЕ берём как service_id —
# в реальном файле это id специальности/порядковый номер (не уникальны на услугу).
_HEADER_ALIASES: dict[str, list[str]] = {
    "service_id": ["service_id", "service id", "service-id", "uuid", "guid"],
    "service_name": ["name_ru", "name_rus", "service_name", "service name",
                     "наименование услуги", "наименование", "название услуги",
                     "название", "услуга", "name"],
    "synonyms": ["synonyms", "синонимы", "синоним", "альтернативные названия"],
    "category": ["специальность", "категория", "category", "отделение", "раздел", "профиль"],
    "icd_code": ["tarificatrcode", "tarificator", "тарификатор", "код тарификатора",
                 "icd_code", "icd", "мкб", "код мкб", "code_mkb"],
}


def _resolve_columns(headers: list) -> dict[str, int | None]:
    """Сопоставить поля справочника с индексами колонок по псевдонимам заголовков."""
    norm = [str(h).strip().lower() if h is not None else "" for h in headers]
    ci: dict[str, int | None] = {}
    for field, aliases in _HEADER_ALIASES.items():
        idx = None
        for a in aliases:                       # 1) точное совпадение заголовка
            if a in norm:
                idx = norm.index(a)
                break
        if idx is None:                         # 2) подстрока
            for i, h in enumerate(norm):
                if h and any(a in h for a in aliases):
                    idx = i
                    break
        ci[field] = idx
    return ci


def _guess_name_column(rows: list, ci: dict[str, int | None]) -> int | None:
    """Если колонка названия не нашлась по заголовку — берём ту, где в среднем самый
    длинный текст (имена услуг длиннее кодов/категорий), исключая уже размеченные."""
    used = {ci[k] for k in ("service_id", "category", "icd_code") if ci.get(k) is not None}
    width = max((len(r) for r in rows[1:21]), default=0)
    best_idx, best_len = None, 0.0
    for i in range(width):
        if i in used:
            continue
        vals = [str(r[i]) for r in rows[1:21] if i < len(r) and r[i] is not None]
        if not vals:
            continue
        avg = sum(len(v) for v in vals) / len(vals)
        non_numeric = sum(1 for v in vals if not v.replace(".", "").replace(",", "").isdigit())
        if non_numeric >= len(vals) * 0.7 and avg > best_len:
            best_idx, best_len = i, avg
    return best_idx


def _records_from_sheet(rows: list) -> list[dict]:
    if not rows:
        return []
    ci = _resolve_columns(rows[0])
    if ci.get("service_name") is None:
        ci["service_name"] = _guess_name_column(rows, ci)
    name_idx = ci.get("service_name")
    if name_idx is None:
        return []
    records = []
    for row in rows[1:]:
        def get(key):
            idx = ci.get(key)
            return row[idx] if idx is not None and idx < len(row) else None

        name = row[name_idx] if name_idx < len(row) else None
        if not name or not str(name).strip():
            continue
        records.append({
            "service_id": get("service_id"),
            "service_name": str(name).strip(),
            "synonyms": get("synonyms"),
            "category": get("category"),
            "icd_code": get("icd_code"),
        })
    return records


def _load_records(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("services", [])

    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    records: list[dict] = []
    seen: set[str] = set()
    # читаем ВСЕ листы (справочник может быть разбит по отделениям/категориям)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        for rec in _records_from_sheet(rows):
            key = rec["service_name"].lower()
            if key in seen:
                continue
            seen.add(key)
            records.append(rec)
    wb.close()
    return records


async def load_catalog(session: AsyncSession, path: str) -> int:
    """Загрузить/обновить справочник. Возвращает число услуг."""
    records = _load_records(path)
    count = 0
    for rec in records:
        name = rec["service_name"]
        synonyms = _parse_synonyms(rec.get("synonyms"))
        existing = None
        if rec.get("service_id"):
            existing = await session.get(Service, str(rec["service_id"]))
        if existing is None:
            res = await session.execute(select(Service).where(Service.service_name == name))
            existing = res.scalar_one_or_none()
        if existing:
            existing.service_name = name
            existing.synonyms = synonyms
            existing.category = rec.get("category")
            existing.icd_code = rec.get("icd_code")
            existing.is_active = True  # услуга есть в загружаемом файле → активна
        else:
            kwargs = dict(
                service_name=name,
                synonyms=synonyms,
                category=rec.get("category"),
                icd_code=rec.get("icd_code"),
            )
            if rec.get("service_id"):
                kwargs["service_id"] = str(rec["service_id"])
            session.add(Service(**kwargs))
        count += 1
    await session.commit()
    return count
