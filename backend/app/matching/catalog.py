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


def _load_records(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("services", [])

    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    headers = [str(h).strip().lower() if h else "" for h in rows[0]]

    def col(name: str) -> int | None:
        for i, h in enumerate(headers):
            if name in h:
                return i
        return None

    ci = {k: col(k) for k in ("service_id", "service_name", "synonyms", "category", "icd")}
    records = []
    for row in rows[1:]:
        def get(key):
            idx = ci.get(key)
            return row[idx] if idx is not None and idx < len(row) else None

        name = get("service_name") or (row[1] if len(row) > 1 else None)
        if not name:
            continue
        records.append({
            "service_id": get("service_id"),
            "service_name": str(name).strip(),
            "synonyms": get("synonyms"),
            "category": get("category"),
            "icd_code": get("icd"),
        })
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
