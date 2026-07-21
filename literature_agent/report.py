from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from .models import ItemSummary


def _fmt_date(summary: ItemSummary) -> str:
    published = summary.item.published
    if not published:
        return "unknown date"
    return published.date().isoformat()


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _fmt_window(start: datetime | None, end: datetime | None) -> str:
    if not start or not end:
        return "unknown"
    return f"{start.strftime('%Y-%m-%d %H:%M UTC')} -> {end.strftime('%Y-%m-%d %H:%M UTC')}"


def build_report(
    summaries: List[ItemSummary],
    agent_name: str,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    window_mode: str = "current",
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    window_text = _fmt_window(window_start, window_end)
    mode_text = {
        "current": "\u5f53\u524d\u7a97\u53e3",
        "backfill": "\u56de\u6eaf\u7a97\u53e3",
        "current+backfill": "\u5f53\u524d+\u56de\u6eaf\u7a97\u53e3",
        "sample": "\u6837\u4f8b\u6a21\u5f0f",
    }.get(window_mode, window_mode)
    if not summaries:
        return (
            f"# Literature Agent Daily Brief | {today}\n\n"
            f"- \u641c\u7d22\u7a97\u53e3\uff1a{window_text}\n"
            f"- \u8fd0\u884c\u6a21\u5f0f\uff1a{mode_text}\n\n"
            "\u4eca\u5929\u6ca1\u6709\u7b5b\u5230\u9ad8\u76f8\u5173\u6587\u732e\u3002"
            "\u7a0b\u5e8f\u4f1a\u5728\u4e0b\u4e00\u6b21\u65e0\u7ed3\u679c\u65f6\u7ee7\u7eed\u56de\u6eaf\u5230\u66f4\u65e9\u7684\u65f6\u95f4\u7a97\u3002\n"
        )

    lines = [
        f"# Literature Agent Daily Brief | {today}",
        "",
        f"- \u641c\u7d22\u7a97\u53e3\uff1a{window_text}",
        f"- \u8fd0\u884c\u6a21\u5f0f\uff1a{mode_text}",
        "",
        f"Agent: {agent_name}",
        f"Items: {len(summaries)}",
        "",
    ]
    for index, summary in enumerate(summaries, start=1):
        item = summary.item
        demo_note = " (demo item, no DOI)" if item.uid.startswith("sample:") else ""
        authors = ", ".join(item.authors[:4])
        if len(item.authors) > 4:
            authors += " et al."
        lines.extend(
            [
                f"## {index}. {item.title}{demo_note}",
                "",
                f"- \u6765\u6e90\uff1a{item.source}" + (f" | {item.venue}" if item.venue else ""),
                f"- \u65e5\u671f\uff1a{_fmt_date(summary)}",
                f"- \u4f5c\u8005\uff1a{authors or 'unknown'}",
                f"- DOI\uff1a{item.doi or 'N/A'}",
                f"- \u94fe\u63a5\uff1a{item.url}",
                "",
                "### \u6458\u8981\u539f\u6587",
                "",
                _blockquote(item.abstract or "Abstract unavailable."),
                "",
                "### \u4e2d\u6587\u6458\u8981\u4e0e\u6df1\u5ea6\u89e3\u8bfb",
                "",
                summary.summary_text,
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def save_report(report: str, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    latest = reports_dir / "latest_report.md"
    dated = reports_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    latest.write_text(report, encoding="utf-8-sig")
    dated.write_text(report, encoding="utf-8-sig")
    return latest
