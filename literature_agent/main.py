from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load_config, project_path
from .email_sender import send_email
from .feishu_sender import send_feishu
from .fetchers import fetch_all, sample_items
from .filtering import filter_relevant
from .report import build_report, save_report
from .storage import SeenStore
from .summarizer import summarize_items


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _format_window(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%Y-%m-%d %H:%M UTC')} -> {end.strftime('%Y-%m-%d %H:%M UTC')}"


def _record_window_state(store: SeenStore, mode: str, start: datetime, end: datetime) -> None:
    store.set_state("last_search_mode", mode)
    store.set_state("last_search_window_start", start.isoformat())
    store.set_state("last_search_window_end", end.isoformat())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch, filter, summarize, and push literature updates.")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--sample", action="store_true", help="Use built-in sample items instead of network fetchers")
    parser.add_argument("--dry-run", action="store_true", help="Build report but do not send or mark items as seen")
    parser.add_argument("--send-email", action="store_true", help="Send report by email")
    parser.add_argument("--send-feishu", action="store_true", help="Send report to Feishu")
    parser.add_argument("--mark-seen", action="store_true", help="Mark reported items as seen even when no sender is enabled")
    parser.add_argument("--ignore-seen", action="store_true", help="Include already-seen items, useful for resending with a new report format")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    config = load_config(args.config)
    lookback_days = int(config.get("lookback_days", 7))
    search_end = datetime.now(timezone.utc)
    search_start = search_end - timedelta(days=lookback_days)

    store = SeenStore(project_path(config, config.get("database_path", "data/literature_seen.sqlite")))
    try:
        if args.sample:
            items = sample_items()
            window_start = search_start
            window_end = search_end
            window_mode = "sample"
        else:
            items = fetch_all(config, since=search_start, until=search_end)
            window_start = search_start
            window_end = search_end
            window_mode = "current"

        new_items = items if args.sample or args.ignore_seen else store.filter_new(items)
        relevant = filter_relevant(new_items, config)
        max_items = int(config.get("max_items_in_report", 12))
        selected = relevant[:max_items]
        if not selected and not args.sample:
            backfill_end = _parse_utc(store.get_state("backfill_next_end")) or search_start
            if backfill_end > search_start:
                backfill_end = search_start
            backfill_start = backfill_end - timedelta(days=lookback_days)
            items = fetch_all(config, since=backfill_start, until=backfill_end)
            new_items = items if args.sample or args.ignore_seen else store.filter_new(items)
            relevant = filter_relevant(new_items, config)
            selected = relevant[:max_items]
            window_start = backfill_start
            window_end = backfill_end
            window_mode = "backfill"
            if not args.dry_run:
                store.set_state("backfill_next_end", backfill_start.isoformat())

        summaries = summarize_items(selected, config)
        report = build_report(
            summaries,
            config.get("agent_name", "literature_agent"),
            window_start=window_start,
            window_end=window_end,
            window_mode=window_mode,
        )
        report_path = save_report(report, project_path(config, config.get("reports_dir", "reports")))

        print(
            f"[info] window={_format_window(window_start, window_end)} mode={window_mode} "
            f"fetched={len(items)} new={len(new_items)} relevant={len(relevant)} selected={len(selected)}"
        )
        print(f"[info] report={report_path}")

        email_enabled = bool(config.get("email", {}).get("enabled", False)) or args.send_email
        feishu_enabled = bool(config.get("feishu", {}).get("enabled", False)) or args.send_feishu

        sent = False
        if not args.dry_run and email_enabled:
            send_email(report, config)
            sent = True
            print("[info] email sent")
        if not args.dry_run and feishu_enabled:
            send_feishu(report, config)
            sent = True
            print("[info] feishu sent")
        if not args.dry_run and not args.sample:
            _record_window_state(store, window_mode, window_start, window_end)
        if not args.dry_run and not args.sample and selected and (sent or args.mark_seen):
            store.mark_seen(selected)
            print(f"[info] marked_seen={len(selected)}")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
