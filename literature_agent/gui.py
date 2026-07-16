from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from tkinter import BooleanVar, Button, Label, StringVar, Text, Tk, messagebox
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

EMAIL_PROVIDERS = {
    "QQ Mail": {"host": "smtp.qq.com", "port": "465", "ssl": True, "tls": False},
    "163 Mail": {"host": "smtp.163.com", "port": "465", "ssl": True, "tls": False},
    "Outlook": {"host": "smtp.office365.com", "port": "587", "ssl": False, "tls": True},
    "Gmail": {"host": "smtp.gmail.com", "port": "465", "ssl": True, "tls": False},
    "Custom": {"host": "", "port": "465", "ssl": True, "tls": False},
}


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


def detect_email_provider(host: str) -> str:
    host = host.lower().strip()
    for name, settings in EMAIL_PROVIDERS.items():
        if settings["host"] and settings["host"] == host:
            return name
    return "Custom"


class SetupApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Literature Agent Setup")
        self.root.geometry("960x760")
        self.root.minsize(820, 680)
        self.colors = {
            "bg": "#f4f7fb",
            "panel": "#ffffff",
            "border": "#d8e0ea",
            "text": "#172033",
            "muted": "#667085",
            "primary": "#2563eb",
            "primary_soft": "#eaf1ff",
            "danger": "#d32f2f",
            "disabled": "#a0a7b4",
        }
        self.root.configure(bg=self.colors["bg"])

        self.env = read_env()
        self.config = load_json_config()

        style = ttk.Style()
        try:
            available = set(style.theme_names())
            for theme in ("vista", "xpnative", "clam", "alt"):
                if theme in available:
                    style.theme_use(theme)
                    break
        except Exception:
            pass
        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Banner.TFrame", background=self.colors["panel"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("Title.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Segoe UI", 18, "bold"))
        style.configure("Hero.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Segoe UI", 13, "bold"))
        style.configure("Body.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.colors["panel"], foreground=self.colors["muted"])
        style.configure("Section.TLabelframe", background=self.colors["panel"])
        style.configure("Section.TLabelframe.Label", background=self.colors["panel"], foreground=self.colors["text"], font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook", background=self.colors["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8))
        style.map("TNotebook.Tab", padding=[("selected", (14, 8))])
        style.configure("Primary.TButton", padding=(12, 7), background=self.colors["primary"], foreground="white")
        style.map(
            "Primary.TButton",
            background=[("active", "#1d4ed8"), ("disabled", "#93b2f5")],
            foreground=[("disabled", "#f1f5f9")],
        )
        style.configure("TButton", padding=(10, 6))
        style.configure("Output.TLabel", background=self.colors["panel"], foreground=self.colors["muted"], font=("Segoe UI", 9))

        self.llm_api_key = StringVar(value=self.env.get("LLM_API_KEY", ""))
        self.llm_base_url = StringVar(value=self.env.get("LLM_BASE_URL", "https://api.openai.com/v1"))
        self.llm_model = StringVar(value=self.env.get("LLM_MODEL", "gpt-4o-mini"))

        self.feishu_enabled = BooleanVar(value=bool(self.config.get("feishu", {}).get("enabled", True)))
        self.feishu_webhook = StringVar(value=self.env.get("FEISHU_WEBHOOK", ""))

        email_config = self.config.get("email", {})
        smtp_username = self.env.get("SMTP_USERNAME", "")
        recipients = email_config.get("recipients", [])
        if isinstance(recipients, list):
            recipients_value = ", ".join(recipients)
        else:
            recipients_value = str(recipients)
        if recipients_value == "your_email@example.com" and smtp_username:
            recipients_value = smtp_username
        if recipients_value == smtp_username:
            recipients_value = ""
        self.email_enabled = BooleanVar(value=bool(email_config.get("enabled", False)))
        detected_provider = detect_email_provider(self.env.get("SMTP_HOST", "")) if self.env.get("SMTP_HOST") else "QQ Mail"
        self.email_provider = StringVar(value=detected_provider)
        self.email_address = StringVar(value=smtp_username)
        self.email_auth_code = StringVar(value=self.env.get("SMTP_PASSWORD", ""))
        self.email_recipient = StringVar(value=recipients_value)
        self.show_advanced_smtp = BooleanVar(value=False)
        self.smtp_host = StringVar(value=self.env.get("SMTP_HOST", ""))
        self.smtp_port = StringVar(value=self.env.get("SMTP_PORT", "465"))
        self.smtp_ssl = BooleanVar(value=self.env.get("SMTP_USE_SSL", "true").lower() == "true")
        self.smtp_tls = BooleanVar(value=self.env.get("SMTP_USE_TLS", "false").lower() == "true")

        self.schedule_time = StringVar(value="09:00")
        self.email_required_stars: list[Label] = []
        self.email_inputs: list[ttk.Widget] = []

        self._build()
        self.log("Ready. Fill in credentials, save, then run tests.")

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=18, style="App.TFrame")
        frame.pack(fill="both", expand=True)

        banner = ttk.Frame(frame, padding=(18, 16), style="Banner.TFrame")
        banner.pack(fill="x", pady=(0, 14))
        banner.columnconfigure(0, weight=1)
        left = ttk.Frame(banner, style="Banner.TFrame")
        left.grid(row=0, column=0, sticky="w")
        ttk.Label(left, text="Literature Agent Setup", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="One place to configure paper crawling, Feishu, optional email, and the daily schedule.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        right = ttk.Frame(banner, style="Banner.TFrame")
        right.grid(row=0, column=1, sticky="e")
        self._badge(right, "Feishu", "#dbeafe", "#1d4ed8").pack(side="left", padx=(0, 8))
        self._badge(right, "Email", "#ecfdf3", "#15803d").pack(side="left", padx=(0, 8))
        self._badge(right, "Schedule", "#f3e8ff", "#7c3aed").pack(side="left")

        notebook = ttk.Notebook(frame)
        notebook.pack(fill="both", expand=True)

        self._build_llm_tab(notebook)
        self._build_notifications_tab(notebook)
        self._build_schedule_tab(notebook)

        button_bar = ttk.Frame(frame, style="App.TFrame")
        button_bar.pack(fill="x", pady=(14, 10))
        self._action_button(button_bar, "Save Configuration", self.save_config, primary=True).pack(side="left")
        self._action_button(button_bar, "Run Literature Test", self.run_literature_test, primary=True).pack(side="left", padx=8)
        self._action_button(button_bar, "Open Project Folder", self.open_project_folder).pack(side="right")

        output_panel = ttk.Frame(frame, padding=(16, 14), style="Panel.TFrame")
        output_panel.pack(fill="both", expand=False)
        ttk.Label(output_panel, text="Activity", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(
            output_panel,
            text="Tests, saves, and scheduled-task results appear here.",
            style="Output.TLabel",
        ).pack(anchor="w", pady=(2, 8))
        self.output = Text(
            output_panel,
            height=11,
            wrap="word",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["primary"],
        )
        self.output.pack(fill="both", expand=True)

    def _build_llm_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=16, style="App.TFrame")
        notebook.add(tab, text="1. LLM")

        section = ttk.LabelFrame(tab, text="Model API", padding=16, style="Section.TLabelframe")
        section.pack(fill="x", anchor="n")

        self._entry(section, "API Key", self.llm_api_key, show="*", required=True)
        self._entry(section, "Base URL", self.llm_base_url, required=True)
        self._entry(section, "Model", self.llm_model, required=True)
        ttk.Button(section, text="Test LLM", command=self.test_llm).grid(row=3, column=1, sticky="w", pady=10)

        note = (
            "Use an OpenAI-compatible endpoint. Base URL should look like "
            "https://provider.example.com/v1, not the full /chat/completions path."
        )
        ttk.Label(section, text=note, wraplength=650, style="Muted.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

    def _build_notifications_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=16, style="App.TFrame")
        notebook.add(tab, text="2. Notifications")

        feishu_box = ttk.LabelFrame(tab, text="Feishu", padding=16, style="Section.TLabelframe")
        feishu_box.pack(fill="x", anchor="n")
        ttk.Checkbutton(feishu_box, text="Enable Feishu", variable=self.feishu_enabled).grid(row=0, column=0, sticky="w")
        self._entry(feishu_box, "Webhook", self.feishu_webhook, row=1, required=True)
        ttk.Button(feishu_box, text="Test Feishu", command=self.test_feishu).grid(row=2, column=1, sticky="w", pady=(4, 4))

        email_box = ttk.LabelFrame(tab, text="Email", padding=16, style="Section.TLabelframe")
        email_box.pack(fill="x", anchor="n", pady=(14, 0))
        ttk.Checkbutton(email_box, text="Enable Email", variable=self.email_enabled, command=self._toggle_email_fields).grid(
            row=0, column=0, sticky="w"
        )

        self.email_provider_combo = self._provider_combo(email_box, row=1, star_store=self.email_required_stars)
        self.email_inputs.append(self._entry(email_box, "Email Address", self.email_address, row=2, required=True, star_store=self.email_required_stars))
        self.email_inputs.append(
            self._entry(
                email_box,
                "SMTP Authorization Code",
                self.email_auth_code,
                row=3,
                show="*",
                required=True,
                star_store=self.email_required_stars,
            )
        )
        self.email_inputs.append(self._entry(email_box, "Recipient (optional)", self.email_recipient, row=4))
        ttk.Label(
            email_box,
            text="For QQ Mail, choose QQ Mail, enter the QQ email address and SMTP authorization code. Leave recipient empty to send to the same address.",
            wraplength=650,
            style="Muted.TLabel",
        ).grid(
            row=5, column=1, sticky="w", pady=(0, 6)
        )
        self.advanced_smtp_check = ttk.Checkbutton(
            email_box,
            text="Show advanced SMTP settings",
            variable=self.show_advanced_smtp,
            command=self._toggle_advanced_smtp,
        )
        self.advanced_smtp_check.grid(row=6, column=1, sticky="w", pady=(2, 4))

        self.advanced_smtp_frame = ttk.Frame(email_box)
        self.advanced_smtp_frame.grid(row=7, column=0, columnspan=2, sticky="ew")
        self.email_inputs.append(
            self._entry(self.advanced_smtp_frame, "SMTP Host", self.smtp_host, row=0, required=True, star_store=self.email_required_stars)
        )
        self.email_inputs.append(
            self._entry(self.advanced_smtp_frame, "SMTP Port", self.smtp_port, row=1, required=True, star_store=self.email_required_stars)
        )
        ttk.Checkbutton(self.advanced_smtp_frame, text="Use SSL", variable=self.smtp_ssl).grid(
            row=2, column=1, sticky="w", pady=(4, 0)
        )
        ttk.Checkbutton(self.advanced_smtp_frame, text="Use TLS", variable=self.smtp_tls).grid(
            row=3, column=1, sticky="w", pady=(4, 0)
        )
        self.email_test_button = ttk.Button(email_box, text="Test Email", command=self.test_email)
        self.email_test_button.grid(row=8, column=1, sticky="w", pady=(10, 0))
        self._apply_email_provider()
        self._toggle_advanced_smtp()
        self._toggle_email_fields()

    def _build_schedule_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=16, style="App.TFrame")
        notebook.add(tab, text="3. Schedule")

        section = ttk.LabelFrame(tab, text="Daily Schedule", padding=16, style="Section.TLabelframe")
        section.pack(fill="x", anchor="n")
        self._entry(section, "Daily Time", self.schedule_time, required=True)
        ttk.Label(section, text="Use HH:MM format, for example 09:00.").grid(row=1, column=1, sticky="w")
        ttk.Button(section, text="Install / Update Windows Task", command=self.install_schedule).grid(
            row=2, column=1, sticky="w", pady=12
        )
        ttk.Label(
            section,
            text=(
                "The scheduled task runs on this computer. It will not run while the computer is powered off. "
                "For cloud scheduling, use GitHub Actions or a server deployment."
            ),
            wraplength=650,
            style="Muted.TLabel",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: StringVar,
        row: int | None = None,
        show: str | None = None,
        required: bool = False,
        star_store: list[Label] | None = None,
    ) -> ttk.Entry:
        if row is None:
            row = len(parent.grid_slaves()) // 2
        label_frame = ttk.Frame(parent)
        label_frame.grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
        if required:
            star = Label(label_frame, text="*", fg=self.colors["danger"], bg=self.colors["panel"])
            star.pack(side="left", padx=(0, 3))
            if star_store is not None:
                star_store.append(star)
        ttk.Label(label_frame, text=label).pack(side="left")
        entry = ttk.Entry(parent, textvariable=variable, width=70, show=show or "")
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)
        return entry

    def _provider_combo(self, parent: ttk.Frame, row: int, star_store: list[Label] | None = None) -> ttk.Combobox:
        label_frame = ttk.Frame(parent)
        label_frame.grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
        star = Label(label_frame, text="*", fg=self.colors["danger"], bg=self.colors["panel"])
        star.pack(side="left", padx=(0, 3))
        if star_store is not None:
            star_store.append(star)
        ttk.Label(label_frame, text="Email Provider").pack(side="left")
        combo = ttk.Combobox(
            parent,
            textvariable=self.email_provider,
            values=list(EMAIL_PROVIDERS.keys()),
            state="readonly",
            width=28,
        )
        combo.grid(row=row, column=1, sticky="w", pady=6)
        combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_email_provider())
        return combo

    def _badge(self, parent: ttk.Frame, text: str, bg: str, fg: str) -> Label:
        return Label(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            relief="flat",
        )

    def _action_button(self, parent: ttk.Frame, text: str, command, primary: bool = False) -> Button:
        bg = self.colors["primary"] if primary else self.colors["panel"]
        fg = "white" if primary else self.colors["text"]
        active_bg = "#1d4ed8" if primary else "#eef2f7"
        active_fg = "white" if primary else self.colors["text"]
        return Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=active_fg,
            disabledforeground=self.colors["disabled"],
            relief="flat",
            bd=0,
            padx=18,
            pady=8,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["primary"],
            takefocus=True,
        )

    def _apply_email_provider(self) -> None:
        provider = self.email_provider.get()
        if provider == "Custom":
            return
        settings = EMAIL_PROVIDERS.get(provider, EMAIL_PROVIDERS["QQ Mail"])
        self.smtp_host.set(settings["host"])
        self.smtp_port.set(settings["port"])
        self.smtp_ssl.set(bool(settings["ssl"]))
        self.smtp_tls.set(bool(settings["tls"]))

    def _toggle_advanced_smtp(self) -> None:
        if self.show_advanced_smtp.get():
            self.advanced_smtp_frame.grid()
        else:
            self.advanced_smtp_frame.grid_remove()

    def _toggle_email_fields(self) -> None:
        enabled = self.email_enabled.get()
        entry_state = "normal" if enabled else "disabled"
        combo_state = "readonly" if enabled else "disabled"
        button_state = "normal" if enabled else "disabled"
        star_color = "#d32f2f" if enabled else "#a0a7b4"

        if hasattr(self, "email_provider_combo"):
            self.email_provider_combo.configure(state=combo_state)
        for widget in self.email_inputs:
            widget.configure(state=entry_state)
        if hasattr(self, "advanced_smtp_check"):
            self.advanced_smtp_check.configure(state=button_state)
        if hasattr(self, "email_test_button"):
            self.email_test_button.configure(state=button_state)
        for star in self.email_required_stars:
            star.configure(fg=star_color)

    def collect_env(self) -> dict[str, str]:
        self._apply_email_provider()
        email_address = self.email_address.get().strip()
        return {
            "LLM_API_KEY": self.llm_api_key.get().strip(),
            "LLM_BASE_URL": self.llm_base_url.get().strip().rstrip("/"),
            "LLM_MODEL": self.llm_model.get().strip(),
            "FEISHU_WEBHOOK": self.feishu_webhook.get().strip(),
            "SMTP_HOST": self.smtp_host.get().strip(),
            "SMTP_PORT": self.smtp_port.get().strip() or "465",
            "SMTP_USERNAME": email_address,
            "SMTP_PASSWORD": self.email_auth_code.get().strip(),
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
        email_config["sender"] = env_values["SMTP_USERNAME"]
        recipients_raw = self.email_recipient.get().strip() or env_values["SMTP_USERNAME"]
        recipients = [item.strip() for item in recipients_raw.split(",") if item.strip()]
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
        result = summarize_items([item], config)[0]
        if result.used_fallback:
            raise RuntimeError(
                "LLM test failed. Check the API key, base URL, model name, and network connection."
            )
        return "LLM test succeeded:\n" + result.summary_text

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
