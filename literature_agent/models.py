from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class LiteratureItem:
    uid: str
    title: str
    abstract: str
    url: str
    source: str
    published: Optional[datetime] = None
    authors: List[str] = field(default_factory=list)
    venue: str = ""
    doi: str = ""
    raw: Dict[str, object] = field(default_factory=dict)
    score: int = 0
    matched_groups: Dict[str, List[str]] = field(default_factory=dict)
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class ItemSummary:
    item: LiteratureItem
    summary_text: str
    relevance: str
