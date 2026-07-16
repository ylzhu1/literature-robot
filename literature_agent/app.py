from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from .gui import main as gui_main
from .main import main as cli_main


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def run_daily() -> int:
    os.chdir(app_dir())
    args = ["literature-agent", "--config", "config.json"]
    if "--ignore-seen" in sys.argv:
        args.append("--ignore-seen")
    if "--dry-run" in sys.argv:
        args.append("--dry-run")
    sys.argv = args
    return cli_main()


def run_gui() -> int:
    os.chdir(app_dir())
    return gui_main()


def write_runtime_error() -> None:
    """Persist scheduled-task failures because the packaged app has no console window."""
    logs_dir = app_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "last_error.log").write_text(traceback.format_exc(), encoding="utf-8")


def main() -> int:
    try:
        if "--run-daily" in sys.argv:
            return run_daily()
        return run_gui()
    except Exception:
        write_runtime_error()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
