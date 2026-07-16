from __future__ import annotations

import json
import os
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Dict


def _split_by_utf8_bytes(text: str, max_bytes: int = 26000) -> list[str]:
    chunks: list[str] = []
    current_lines: list[str] = []
    current_size = 0

    for line in text.splitlines(keepends=True):
        line_size = len(line.encode("utf-8"))
        if current_lines and current_size + line_size > max_bytes:
            chunks.append("".join(current_lines).strip())
            current_lines = []
            current_size = 0

        if line_size > max_bytes:
            buffer = ""
            for char in line:
                if len((buffer + char).encode("utf-8")) > max_bytes:
                    chunks.append(buffer)
                    buffer = char
                else:
                    buffer += char
            if buffer:
                current_lines.append(buffer)
                current_size = len(buffer.encode("utf-8"))
        else:
            current_lines.append(line)
            current_size += line_size

    if current_lines:
        chunks.append("".join(current_lines).strip())
    return [chunk for chunk in chunks if chunk]


def _post_text(webhook: str, text: str) -> None:
    if not webhook:
        raise RuntimeError("FEISHU_WEBHOOK is not configured")

    payload = json.dumps(
        {
            "msg_type": "text",
            "content": {
                "text": text,
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read()
            return
        except (urllib.error.URLError, ssl.SSLError) as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(1.5 * (attempt + 1))
    try:
        _post_text_with_curl(webhook, payload)
        return
    except Exception as curl_error:
        raise RuntimeError(
            f"Feishu send failed after urllib retries: {last_error}; curl fallback failed: {curl_error}"
        ) from curl_error


def _post_text_with_curl(webhook: str, payload: bytes) -> None:
    if os.name != "nt":
        raise RuntimeError("curl fallback is only enabled on Windows")

    temp_dir = tempfile.gettempdir()
    timestamp = f"{int(time.time() * 1000)}"
    payload_path = os.path.join(temp_dir, f"literature_agent_feishu_{timestamp}.json")
    config_path = os.path.join(temp_dir, f"literature_agent_curl_{timestamp}.conf")
    curl_payload_path = payload_path.replace("\\", "/")
    try:
        with open(payload_path, "wb") as fh:
            fh.write(payload)
        with open(config_path, "w", encoding="utf-8") as fh:
            fh.write("silent\n")
            fh.write("show-error\n")
            fh.write("fail-with-body\n")
            fh.write("request = \"POST\"\n")
            fh.write("header = \"Content-Type: application/json\"\n")
            fh.write(f"data-binary = \"@{curl_payload_path}\"\n")
            fh.write(f"url = \"{webhook}\"\n")

        completed = subprocess.run(
            ["curl.exe", "--config", config_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
        if completed.returncode != 0:
            output = ((completed.stdout or "") + (completed.stderr or "")).strip()
            raise RuntimeError(output or f"curl exited with code {completed.returncode}")
    finally:
        for path in (payload_path, config_path):
            try:
                os.remove(path)
            except OSError:
                pass


def send_feishu(report: str, config: Dict[str, Any]) -> None:
    webhook = os.environ.get("FEISHU_WEBHOOK", "")
    if not webhook:
        raise RuntimeError("FEISHU_WEBHOOK is not configured")

    chunks = _split_by_utf8_bytes(report)
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"[Literature Agent {index}/{total}]\n" if total > 1 else ""
        _post_text(webhook, prefix + chunk)
        if index < total:
            time.sleep(0.5)
