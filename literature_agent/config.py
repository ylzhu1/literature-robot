from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(config_path: str) -> Dict[str, Any]:
    path = Path(config_path).resolve()
    load_env_file(path.parent / ".env")
    with path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)
    config["_config_dir"] = str(path.parent)
    return config


def project_path(config: Dict[str, Any], relative_path: str) -> Path:
    base = Path(config["_config_dir"])
    return (base / relative_path).resolve()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
