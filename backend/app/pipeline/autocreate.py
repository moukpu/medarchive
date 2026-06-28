"""Умное авто-создание услуг: кластеризация несопоставленных позиций по fuzzy-схожести.

Раньше группировка шла только по точному совпадению нормализованного имени —
"Генетический тест на предрасположенность" и "Генетическое тестирование" считались
разными и не объединялись, хотя обе описывают одну услугу. Здесь группируем сначала
по точному имени (быстрый путь), затем объединяем бакеты в кластеры single-linkage
по token_set_ratio (RapidFuzz) — ловит синонимичные формулировки.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.pipeline.normalize import _norm

GROUP_SIMILARITY = 0.8  # порог схожести для объединения бакетов в один кластер

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("лаборатория", ["анализ", "кровь", "моча", "биохими", "гормон", "мазок", "спермограмм", "коагулог", "глюкоз", "холестерин", "оак", "пцр", "ифа"]),
    ("диагностика", ["узи", "мрт", "кт", "рентген", "эхо", "эгдс", "колоноскоп", "флюорограф", "маммограф", "эндоскоп", "томограф"]),
    ("консультация", ["консультаци", "приём", "прием", "осмотр", "телемед"]),
    ("процедура", ["массаж", "физиотерап", "инъекц", "укол", "капельниц", "процедур", "вливан"]),
    ("хирургия", ["операци", "удаление", "иссечени", "хирург", "биопси", "лапароск"]),
    ("вакцинация", ["вакцин", "прививк", "иммуниз"]),
    ("стоматология", ["зуб", "стоматолог", "имплант", "пломб", "ортодонт", "челюст"]),
]


def guess_category(names: list[str]) -> str | None:
    text = " ".join(names).lower()
    best: str | None = None
    best_hits = 0
    for category, keywords in _CATEGORY_KEYWORDS:
        hits = sum(1 for k in keywords if k in text)
        if hits > best_hits:
            best_hits = hits
            best = category
    return best


def _title_case(s: str) -> str:
    t = s.strip()
    return t[0].upper() + t[1:] if t else t


@dataclass
class UnmatchedCluster:
    item_ids: list[str]
    variants: dict[str, int]  # raw name -> count
    display_name: str = ""
    category: str | None = None
    cohesion: float = 1.0


def cluster_unmatched(items: list[tuple[str, str]]) -> list[UnmatchedCluster]:
    """items: [(item_id, service_name_raw), ...]. Возвращает кластеры размера >= 1,
    отсортированные по убыванию размера. Кластеры single-linkage по token_set_ratio."""
    # 1. бакеты по точному нормализованному имени (быстрый путь)
    buckets: dict[str, dict] = {}
    for item_id, raw in items:
        n = _norm(raw)
        if not n:
            continue
        b = buckets.setdefault(n, {"item_ids": [], "variants": {}})
        b["item_ids"].append(item_id)
        b["variants"][raw] = b["variants"].get(raw, 0) + 1

    keys = list(buckets.keys())
    m = len(keys)
    parent = list(range(m))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # 2. объединяем бакеты по fuzzy-схожести представителей (single-linkage)
    for i in range(m):
        for j in range(i + 1, m):
            sim = fuzz.token_set_ratio(keys[i], keys[j]) / 100.0
            if sim >= GROUP_SIMILARITY:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(m):
        groups.setdefault(find(i), []).append(i)

    clusters: list[UnmatchedCluster] = []
    for idxs in groups.values():
        item_ids: list[str] = []
        variants: dict[str, int] = {}
        for i in idxs:
            b = buckets[keys[i]]
            item_ids.extend(b["item_ids"])
            for raw, cnt in b["variants"].items():
                variants[raw] = variants.get(raw, 0) + cnt

        if len(idxs) > 1:
            total = 0.0
            pairs = 0
            for a in range(len(idxs)):
                for b_ in range(a + 1, len(idxs)):
                    total += fuzz.token_set_ratio(keys[idxs[a]], keys[idxs[b_]]) / 100.0
                    pairs += 1
            cohesion = total / pairs if pairs else 1.0
        else:
            cohesion = 1.0

        display_name = ""
        max_count = 0
        for raw, cnt in variants.items():
            if cnt > max_count or (cnt == max_count and len(raw) < len(display_name)):
                max_count = cnt
                display_name = raw

        clusters.append(UnmatchedCluster(
            item_ids=item_ids,
            variants=variants,
            display_name=_title_case(display_name),
            category=guess_category(list(variants.keys())),
            cohesion=cohesion,
        ))

    return sorted(clusters, key=lambda c: len(c.item_ids), reverse=True)
