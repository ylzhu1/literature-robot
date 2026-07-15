from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def run_daily() -> int:
    os.chdir(app_dir())
    from .main import main as cli_main

    args = ["literature-agent", "--config", "config.json"]
    if "--ignore-seen" in sys.argv:
        args.append("--ignore-seen")
    if "--dry-run" in sys.argv:
        args.append("--dry-run")
    sys.argv = args
    return cli_main()


def run_gui() -> int:
    os.chdir(app_dir())
    from .gui import main as gui_main

    return gui_main()


def main() -> int:
    if "--run-daily" in sys.argv:
        return run_daily()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
