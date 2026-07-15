from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Set

from .models import LiteratureItem


class SeenStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_items (
                uid TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                source TEXT,
                first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.commit()

    def seen_uids(self) -> Set[str]:
        cursor = self.connection.execute("SELECT uid FROM seen_items")
        return {row[0] for row in cursor.fetchall()}

    def filter_new(self, items: Iterable[LiteratureItem]) -> list[LiteratureItem]:
        seen = self.seen_uids()
        return [item for item in items if item.uid not in seen]

    def mark_seen(self, items: Iterable[LiteratureItem]) -> None:
        rows = [(item.uid, item.title, item.url, item.source) for item in items]
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO seen_items (uid, title, url, source)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
