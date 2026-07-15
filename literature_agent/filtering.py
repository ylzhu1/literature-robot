from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from .models import LiteratureItem


def _contains(text: str, keyword: str) -> bool:
    keyword_norm = keyword.lower().strip()
    if not keyword_norm:
        return False
    if len(keyword_norm) <= 4 and keyword_norm.isalnum():
        return bool(re.search(rf"\b{re.escape(keyword_norm)}\b", text))
    return keyword_norm in text


def score_item(item: LiteratureItem, config: Dict[str, Any]) -> LiteratureItem:
    text = " ".join([item.title, item.abstract, item.venue]).lower()
    score = 0
    matched_groups: Dict[str, List[str]] = {}
    matched_keywords: List[str] = []

    for group_name, keywords in config.get("keyword_groups", {}).items():
        group_hits = []
        for keyword in keywords:
            if _contains(text, keyword):
                group_hits.append(keyword)
                matched_keywords.append(keyword)
        if group_hits:
            matched_groups[group_name] = group_hits
            score += 2 + min(len(group_hits), 4)

    for keyword in config.get("strong_keywords", []):
        if _contains(text, keyword):
            score += 4

    for keyword in config.get("negative_keywords", []):
        if _contains(text, keyword):
            score -= 5

    group_count = len(matched_groups)
    if {"method", "oxidation"}.issubset(matched_groups):
        score += 5
    if {"oxidation", "surface_defect"}.issubset(matched_groups):
        score += 3
    if {"method", "surface_defect", "metal_system"}.issubset(matched_groups):
        score += 3
    if group_count >= 3:
        score += 2

    item.score = score
    item.matched_groups = matched_groups
    item.matched_keywords = sorted(set(matched_keywords), key=str.lower)
    return item


def filter_relevant(items: Iterable[LiteratureItem], config: Dict[str, Any]) -> List[LiteratureItem]:
    min_score = int(config.get("min_score", 7))
    group_min_matches = int(config.get("group_min_matches", 2))
    require_any_groups = set(config.get("require_any_groups", []))
    seen = set()
    relevant: List[LiteratureItem] = []

    for item in items:
        if not item.title:
            continue
        uid = item.uid or item.url or item.title
        if uid in seen:
            continue
        seen.add(uid)
        scored = score_item(item, config)
        if require_any_groups and not any(group in scored.matched_groups for group in require_any_groups):
            continue
        if scored.score >= min_score and len(scored.matched_groups) >= group_min_matches:
            relevant.append(scored)

    relevant.sort(
        key=lambda item: (
            item.score,
            item.published.isoformat() if item.published else "",
        ),
        reverse=True,
    )
    return relevant
