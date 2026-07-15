from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config, project_path
from .email_sender import send_email
from .feishu_sender import send_feishu
from .fetchers import fetch_all, sample_items
from .filtering import filter_relevant
from .report import build_report, save_report
from .storage import SeenStore
from .summarizer import summarize_items


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

    items = sample_items() if args.sample else fetch_all(config)
    store = SeenStore(project_path(config, config.get("database_path", "data/literature_seen.sqlite")))
    try:
        new_items = items if args.sample or args.ignore_seen else store.filter_new(items)
        relevant = filter_relevant(new_items, config)
        max_items = int(config.get("max_items_in_report", 12))
        selected = relevant[:max_items]
        summaries = summarize_items(selected, config)
        report = build_report(summaries, config.get("agent_name", "literature_agent"))
        report_path = save_report(report, project_path(config, config.get("reports_dir", "reports")))

        print(f"[info] fetched={len(items)} new={len(new_items)} relevant={len(relevant)} selected={len(selected)}")
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
        if not args.dry_run and selected and (sent or args.mark_seen):
            store.mark_seen(selected)
            print(f"[info] marked_seen={len(selected)}")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
