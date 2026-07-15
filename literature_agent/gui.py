from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Tk, messagebox
from tkinter import ttk

from .config import load_config
from .email_sender import send_email
from .feishu_sender import send_feishu
from .models import LiteratureItem
from .summarizer import summarize_items


def project_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_DIR = project_dir()
CONFIG_PATH = PROJECT_DIR / "config.json"
ENV_PATH = PROJECT_DIR / ".env"
TASK_NAME = "LiteratureAgentDailyBrief"


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env(values: dict[str, str], path: Path = ENV_PATH) -> None:
    lines = [
        "# Local credentials for Literature Agent.",
        "# This file is ignored by Git.",
        "",
        "# OpenAI-compatible LLM endpoint.",
        f"LLM_API_KEY={values.get('LLM_API_KEY', '')}",
        f"LLM_BASE_URL={values.get('LLM_BASE_URL', '')}",
        f"LLM_MODEL={values.get('LLM_MODEL', '')}",
        "",
        "# Feishu custom bot webhook.",
        f"FEISHU_WEBHOOK={values.get('FEISHU_WEBHOOK', '')}",
        "",
        "# Optional SMTP email settings.",
        f"SMTP_HOST={values.get('SMTP_HOST', '')}",
        f"SMTP_PORT={values.get('SMTP_PORT', '465')}",
        f"SMTP_USERNAME={values.get('SMTP_USERNAME', '')}",
        f"SMTP_PASSWORD={values.get('SMTP_PASSWORD', '')}",
        f"SMTP_USE_SSL={values.get('SMTP_USE_SSL', 'true')}",
        f"SMTP_USE_TLS={values.get('SMTP_USE_TLS', 'false')}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def load_json_config(path: Path = CONFIG_PATH) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json_config(config: dict, path: Path = CONFIG_PATH) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_time(value: str) -> str:
    if not re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        raise ValueError("Time must use HH:MM format, for example 09:00.")
    hour, minute = [int(part) for part in value.split(":", 1)]
    if hour > 23 or minute > 59:
        raise ValueError("Time must be between 00:00 and 23:59.")
    return f"{hour:02d}:{minute:02d}"


class SetupApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Literature Agent Setup")
        self.root.geometry("860x700")
        self.root.minsize(760, 620)

        self.env = read_env()
        self.config = load_json_config()

        self.llm_api_key = StringVar(value=self.env.get("LLM_API_KEY", ""))
        self.llm_base_url = StringVar(value=self.env.get("LLM_BASE_URL", "https://api.openai.com/v1"))
        self.llm_model = StringVar(value=self.env.get("LLM_MODEL", "gpt-4o-mini"))

        self.feishu_enabled = BooleanVar(value=bool(self.config.get("feishu", {}).get("enabled", True)))
        self.feishu_webhook = StringVar(value=self.env.get("FEISHU_WEBHOOK", ""))

        email_config = self.config.get("email", {})
        self.email_enabled = BooleanVar(value=bool(email_config.get("enabled", False)))
        smtp_username = self.env.get("SMTP_USERNAME", "")
        sender_value = email_config.get("sender", smtp_username)
        if sender_value == "your_email@example.com" and smtp_username:
            sender_value = smtp_username
        self.email_sender = StringVar(value=sender_value)
        recipients = email_config.get("recipients", [])
        if isinstance(recipients, list):
            recipients_value = ", ".join(recipients)
        else:
            recipients_value = str(recipients)
        if recipients_value == "your_email@example.com" and smtp_username:
            recipients_value = smtp_username
        self.email_recipients = StringVar(value=recipients_value)
        self.smtp_host = StringVar(value=self.env.get("SMTP_HOST", ""))
        self.smtp_port = StringVar(value=self.env.get("SMTP_PORT", "465"))
        self.smtp_username = StringVar(value=self.env.get("SMTP_USERNAME", ""))
        self.smtp_password = StringVar(value=self.env.get("SMTP_PASSWORD", ""))
        self.smtp_ssl = BooleanVar(value=self.env.get("SMTP_USE_SSL", "true").lower() == "true")
        self.smtp_tls = BooleanVar(value=self.env.get("SMTP_USE_TLS", "false").lower() == "true")

        self.schedule_time = StringVar(value="09:00")

        self._build()
        self.log("Ready. Fill in credentials, save, then run tests.")

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        title = ttk.Label(frame, text="Literature Agent Setup", font=("Segoe UI", 18, "bold"))
        title.pack(anchor="w")
        subtitle = ttk.Label(
            frame,
            text="Configure LLM, notification channels, and daily scheduling without editing files by hand.",
        )
        subtitle.pack(anchor="w", pady=(2, 14))

        notebook = ttk.Notebook(frame)
        notebook.pack(fill="both", expand=True)

        self._build_llm_tab(notebook)
        self._build_notifications_tab(notebook)
        self._build_schedule_tab(notebook)

        button_bar = ttk.Frame(frame)
        button_bar.pack(fill="x", pady=(12, 8))
        ttk.Button(button_bar, text="Save Configuration", command=self.save_config).pack(side="left")
        ttk.Button(button_bar, text="Run Literature Test", command=self.run_literature_test).pack(side="left", padx=8)
        ttk.Button(button_bar, text="Open Project Folder", command=self.open_project_folder).pack(side="right")

        self.output = Text(frame, height=11, wrap="word")
        self.output.pack(fill="both", expand=False)

    def _build_llm_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=14)
        notebook.add(tab, text="1. LLM")

        self._entry(tab, "API Key", self.llm_api_key, show="*")
        self._entry(tab, "Base URL", self.llm_base_url)
        self._entry(tab, "Model", self.llm_model)
        ttk.Button(tab, text="Test LLM", command=self.test_llm).grid(row=3, column=1, sticky="w", pady=10)

        note = (
            "Use an OpenAI-compatible endpoint. Base URL should look like "
            "https://provider.example.com/v1, not the full /chat/completions path."
        )
        ttk.Label(tab, text=note, wraplength=650).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_notifications_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=14)
        notebook.add(tab, text="2. Notifications")

        ttk.Checkbutton(tab, text="Enable Feishu", variable=self.feishu_enabled).grid(row=0, column=0, sticky="w")
        self._entry(tab, "Feishu Webhook", self.feishu_webhook, row=1)
        ttk.Button(tab, text="Test Feishu", command=self.test_feishu).grid(row=2, column=1, sticky="w", pady=(4, 16))

        ttk.Separator(tab).grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Checkbutton(tab, text="Enable Email", variable=self.email_enabled).grid(row=4, column=0, sticky="w")
        self._entry(tab, "Sender", self.email_sender, row=5)
        self._entry(tab, "Recipients", self.email_recipients, row=6)
        self._entry(tab, "SMTP Host", self.smtp_host, row=7)
        self._entry(tab, "SMTP Port", self.smtp_port, row=8)
        self._entry(tab, "SMTP Username", self.smtp_username, row=9)
        self._entry(tab, "SMTP Password", self.smtp_password, row=10, show="*")
        ttk.Checkbutton(tab, text="Use SSL", variable=self.smtp_ssl).grid(row=11, column=1, sticky="w", pady=(4, 0))
        ttk.Checkbutton(tab, text="Use TLS", variable=self.smtp_tls).grid(row=12, column=1, sticky="w", pady=(4, 0))
        ttk.Button(tab, text="Test Email", command=self.test_email).grid(row=13, column=1, sticky="w", pady=(10, 0))

    def _build_schedule_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=14)
        notebook.add(tab, text="3. Schedule")

        self._entry(tab, "Daily Time", self.schedule_time)
        ttk.Label(tab, text="Use HH:MM format, for example 09:00.").grid(row=1, column=1, sticky="w")
        ttk.Button(tab, text="Install / Update Windows Task", command=self.install_schedule).grid(
            row=2, column=1, sticky="w", pady=12
        )
        ttk.Label(
            tab,
            text=(
                "The scheduled task runs on this computer. It will not run while the computer is powered off. "
                "For cloud scheduling, use GitHub Actions or a server deployment."
            ),
            wraplength=650,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: StringVar,
        row: int | None = None,
        show: str | None = None,
    ) -> None:
        if row is None:
            row = len(parent.grid_slaves()) // 2
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
        entry = ttk.Entry(parent, textvariable=variable, width=70, show=show or "")
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)

    def collect_env(self) -> dict[str, str]:
        return {
            "LLM_API_KEY": self.llm_api_key.get().strip(),
            "LLM_BASE_URL": self.llm_base_url.get().strip().rstrip("/"),
            "LLM_MODEL": self.llm_model.get().strip(),
            "FEISHU_WEBHOOK": self.feishu_webhook.get().strip(),
            "SMTP_HOST": self.smtp_host.get().strip(),
            "SMTP_PORT": self.smtp_port.get().strip() or "465",
            "SMTP_USERNAME": self.smtp_username.get().strip(),
            "SMTP_PASSWORD": self.smtp_password.get().strip(),
            "SMTP_USE_SSL": str(self.smtp_ssl.get()).lower(),
            "SMTP_USE_TLS": str(self.smtp_tls.get()).lower(),
        }

    def save_config(self) -> None:
        env_values = self.collect_env()
        config = load_json_config()
        config.setdefault("llm", {})["enabled"] = bool(
            env_values["LLM_API_KEY"] and env_values["LLM_BASE_URL"] and env_values["LLM_MODEL"]
        )
        config.setdefault("feishu", {})["enabled"] = bool(self.feishu_enabled.get())
        email_config = config.setdefault("email", {})
        email_config["enabled"] = bool(self.email_enabled.get())
        email_config["sender"] = self.email_sender.get().strip() or env_values["SMTP_USERNAME"]
        recipients = [item.strip() for item in self.email_recipients.get().split(",") if item.strip()]
        email_config["recipients"] = recipients

        crossref = config.get("sources", {}).get("crossref", {})
        if env_values["SMTP_USERNAME"] and crossref.get("mailto") in {"", "your_email@example.com"}:
            crossref["mailto"] = env_values["SMTP_USERNAME"]

        write_env(env_values)
        write_json_config(config)
        self.config = config
        self.log("Configuration saved.")

    def test_llm(self) -> None:
        self._run_threaded("Testing LLM...", self._test_llm)

    def _test_llm(self) -> str:
        self.save_config()
        config = load_config(str(CONFIG_PATH))
        item = LiteratureItem(
            uid="gui-test",
            title="DFT study of oxygen adsorption on copper stepped surfaces",
            abstract=(
                "Density functional theory is used to study oxygen adsorption and dissociation on copper "
                "low-index surfaces and stepped surfaces, revealing the role of undercoordinated sites in "
                "early-stage surface oxidation."
            ),
            url="",
            source="GUI Test",
            published=datetime.now(timezone.utc),
            matched_keywords=["density functional theory", "oxygen adsorption", "copper", "stepped surface"],
            matched_groups={
                "method": ["density functional theory"],
                "oxidation": ["oxygen adsorption"],
                "surface_defect": ["stepped surface"],
                "metal_system": ["copper"],
            },
            score=20,
        )
        summary = summarize_items([item], config)[0].summary_text
        return "LLM test succeeded:\n" + summary

    def test_feishu(self) -> None:
        self._run_threaded("Testing Feishu...", self._test_feishu)

    def _test_feishu(self) -> str:
        self.save_config()
        config = load_config(str(CONFIG_PATH))
        send_feishu(
            "Literature Agent test message\n\nIf you can see this message, Feishu webhook delivery works.",
            config,
        )
        return "Feishu test message sent."

    def test_email(self) -> None:
        self._run_threaded("Testing Email...", self._test_email)

    def _test_email(self) -> str:
        self.save_config()
        config = load_config(str(CONFIG_PATH))
        send_email(
            "Literature Agent email test\n\nIf you can see this message, SMTP delivery works.",
            config,
        )
        return "Email test message sent."

    def run_literature_test(self) -> None:
        self._run_threaded("Running literature test. This may take a few minutes...", self._run_literature_test)

    def _run_literature_test(self) -> str:
        self.save_config()
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--run-daily", "--ignore-seen"]
        else:
            command = [
                sys.executable,
                "-m",
                "literature_agent.main",
                "--config",
                "config.json",
                "--ignore-seen",
            ]
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            raise RuntimeError(output.strip() or "Literature test failed.")
        return output.strip() or "Literature test completed."

    def install_schedule(self) -> None:
        self._run_threaded("Installing scheduled task...", self._install_schedule)

    def _install_schedule(self) -> str:
        self.save_config()
        schedule_time = validate_time(self.schedule_time.get())
        config = load_json_config()
        if not config.get("feishu", {}).get("enabled") and not config.get("email", {}).get("enabled"):
            raise RuntimeError("Enable Feishu or Email before installing a scheduled task.")

        if getattr(sys, "frozen", False):
            execute = sys.executable
            argument = "--run-daily"
        else:
            execute = sys.executable
            argument = "-m literature_agent.main --config config.json"

        script = f"""
$ErrorActionPreference = 'Stop'
$ProjectDir = '{PROJECT_DIR}'
$Executable = '{execute}'
$TaskName = '{TASK_NAME}'
$Action = New-ScheduledTaskAction -Execute $Executable -Argument '{argument}' -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Daily -At {schedule_time}
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Daily Literature Agent report' -Force | Out-Null
Write-Output "Installed scheduled task $TaskName at {schedule_time}"
"""
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            raise RuntimeError(output.strip() or "Failed to install scheduled task.")
        return output.strip()

    def open_project_folder(self) -> None:
        if os.name == "nt":
            os.startfile(PROJECT_DIR)  # type: ignore[attr-defined]
        else:
            self.log(str(PROJECT_DIR))

    def _run_threaded(self, start_message: str, target) -> None:
        self.log(start_message)

        def worker() -> None:
            try:
                result = target()
            except Exception as exc:
                self.root.after(0, lambda: self._show_error(str(exc)))
            else:
                self.root.after(0, lambda: self.log(result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, message: str) -> None:
        self.log("ERROR: " + message)
        messagebox.showerror("Literature Agent", message)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.insert("end", f"[{timestamp}] {message}\n")
        self.output.see("end")


def main() -> int:
    root = Tk()
    SetupApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
