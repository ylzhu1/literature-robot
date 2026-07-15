from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .models import ItemSummary


def _fmt_date(summary: ItemSummary) -> str:
    published = summary.item.published
    if not published:
        return "unknown date"
    return published.date().isoformat()


def build_report(summaries: List[ItemSummary], agent_name: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    if not summaries:
        return (
            f"# Literature Agent Daily Brief | {today}\n\n"
            "今天没有筛到高相关新文献。可以考虑放宽关键词或延长 lookback_days。\n"
        )

    lines = [
        f"# Literature Agent Daily Brief | {today}",
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
                f"- 来源：{item.source}" + (f" | {item.venue}" if item.venue else ""),
                f"- 日期：{_fmt_date(summary)}",
                f"- 作者：{authors or 'unknown'}",
                f"- DOI：{item.doi or 'N/A'}",
                f"- 链接：{item.url}",
                "",
                f"核心思路：{summary.summary_text}",
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
