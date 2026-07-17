from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from tkinter import BooleanVar, StringVar, messagebox

import customtkinter as ctk

from .config import load_config
from .email_sender import send_email
from .feishu_sender import send_feishu
from .models import LiteratureItem
from .process_utils import subprocess_no_window_kwargs
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

# Light, modern palette used across the whole window.
PALETTE = {
    "bg": "#f3f6fb",
    "sidebar": "#ffffff",
    "card": "#ffffff",
    "card_alt": "#f6f8fc",
    "border": "#e4e9f2",
    "text": "#0f172a",
    "muted": "#64748b",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_soft": "#e4edff",
    "primary_soft_hover": "#d3e0ff",
    "primary_text": "#1d4ed8",
    "success": "#16a34a",
    "danger": "#dc2626",
    "nav_hover": "#eef2ff",
    "input": "#f7f9fc",
    "input_border": "#cbd5e1",
    "chip_border": "#e2e8f0",
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
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root.title("Literature Agent")
        self.root.geometry("1060x780")
        self.root.minsize(960, 720)
        self.root.configure(fg_color=PALETTE["bg"])

        self.f_display = ctk.CTkFont(family="Segoe UI Semibold", size=22, weight="bold")
        self.f_h1 = ctk.CTkFont(family="Segoe UI Semibold", size=17, weight="bold")
        self.f_h2 = ctk.CTkFont(family="Segoe UI Semibold", size=14, weight="bold")
        self.f_body = ctk.CTkFont(family="Segoe UI", size=13)
        self.f_body_bold = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.f_small = ctk.CTkFont(family="Segoe UI", size=12)
        self.f_nav = ctk.CTkFont(family="Segoe UI", size=14)
        self.f_mono = ctk.CTkFont(family="Consolas", size=12)

        self.env = read_env()
        self.config = load_json_config()

        self._init_vars()

        self.pages: dict[str, ctk.CTkFrame] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.email_required_stars: list[ctk.CTkLabel] = []
        self.email_inputs: list[ctk.CTkBaseClass] = []
        self.busy_widgets: list[ctk.CTkBaseClass] = []
        self.is_busy = False

        self._build()
        self.select_page("llm")
        self.log("Ready. Fill in credentials, save, then run the tests.", "info")

    def _init_vars(self) -> None:
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

        # Topics & filtering.
        self.max_items = StringVar(value=str(self.config.get("max_items_in_report", 8)))
        self.lookback_days = StringVar(value=str(self.config.get("lookback_days", 7)))
        self.min_score = StringVar(value=str(self.config.get("min_score", 12)))
        self.group_min_matches = StringVar(value=str(self.config.get("group_min_matches", 3)))
        self.group_entries: list[dict] = []
        self.groups_container: ctk.CTkFrame | None = None
        self.strong_kw_box: ctk.CTkTextbox | None = None
        self.negative_kw_box: ctk.CTkTextbox | None = None

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 22), pady=22)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        self._build_header(main)

        self.page_container = ctk.CTkFrame(main, fg_color="transparent")
        self.page_container.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        self.page_container.grid_columnconfigure(0, weight=1)
        self.page_container.grid_rowconfigure(0, weight=1)

        self._build_llm_page()
        self._build_topics_page()
        self._build_notifications_page()
        self._build_run_page()
        self._build_schedule_page()

        self._build_action_bar(main)
        self._build_activity(main)

    NAV_ITEMS = [
        ("llm", "  1   Model API", "Connect your OpenAI-compatible LLM"),
        ("topics", "  2   Topics & Filter", "Pick keywords and how many papers to keep"),
        ("notifications", "  3   Notifications", "Choose how the daily brief reaches you"),
        ("run", "  4   Run a Test", "Do one full end-to-end brief now"),
        ("schedule", "  5   Schedule", "Run the brief automatically every day"),
    ]

    def _build_sidebar(self) -> None:
        bar = ctk.CTkFrame(self.root, width=248, corner_radius=0, fg_color=PALETTE["sidebar"])
        bar.grid(row=0, column=0, sticky="nsew")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(2, weight=1)

        logo = ctk.CTkFrame(bar, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=22, pady=(26, 8))
        mark = ctk.CTkLabel(
            logo, text="📚", font=ctk.CTkFont(size=30), width=52, height=52,
            fg_color=PALETTE["primary_soft"], corner_radius=14, text_color=PALETTE["primary"],
        )
        mark.pack(side="left")
        text = ctk.CTkFrame(logo, fg_color="transparent")
        text.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(text, text="Literature", font=self.f_h1, text_color=PALETTE["text"]).pack(anchor="w")
        ctk.CTkLabel(text, text="Agent", font=self.f_h1, text_color=PALETTE["primary"]).pack(anchor="w", pady=(0, 0))

        ctk.CTkLabel(
            bar, text="SETUP", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=PALETTE["muted"], anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=26, pady=(18, 6))

        nav = ctk.CTkFrame(bar, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="new", padx=14)
        for key, label, _sub in self.NAV_ITEMS:
            btn = ctk.CTkButton(
                nav, text=label, anchor="w", font=self.f_nav, height=44,
                corner_radius=12, fg_color="transparent", text_color=PALETTE["muted"],
                hover_color=PALETTE["nav_hover"], command=lambda k=key: self.select_page(k),
            )
            btn.pack(fill="x", pady=3)
            self.nav_buttons[key] = btn

        footer = ctk.CTkFrame(bar, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="sew", padx=14, pady=(0, 18))
        ctk.CTkButton(
            footer, text="📁  Open Project Folder", font=self.f_small, height=38, corner_radius=10,
            fg_color=PALETTE["card_alt"], text_color=PALETTE["text"], hover_color=PALETTE["nav_hover"],
            border_width=1, border_color=PALETTE["border"], command=self.open_project_folder,
        ).pack(fill="x")
        ctk.CTkLabel(
            footer, text="Papers · arXiv & Crossref → LLM → Feishu / Email",
            font=ctk.CTkFont(family="Segoe UI", size=10), text_color=PALETTE["muted"], wraplength=210,
        ).pack(anchor="w", pady=(12, 0))

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        self.header_title = ctk.CTkLabel(header, text="", font=self.f_display, text_color=PALETTE["text"], anchor="w")
        self.header_title.pack(anchor="w")
        self.header_sub = ctk.CTkLabel(header, text="", font=self.f_body, text_color=PALETTE["muted"], anchor="w")
        self.header_sub.pack(anchor="w", pady=(2, 0))

    # ------------------------------------------------------------- components
    def _card(self, parent, title: str, subtitle: str = "") -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=PALETTE["card"], corner_radius=16,
                            border_width=1, border_color=PALETTE["border"])
        card.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 0))
        ctk.CTkLabel(head, text=title, font=self.f_h2, text_color=PALETTE["text"], anchor="w").pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(head, text=subtitle, font=self.f_small, text_color=PALETTE["muted"], anchor="w").pack(anchor="w", pady=(2, 0))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=22, pady=(14, 20))
        body.grid_columnconfigure(0, weight=1)
        card.body = body  # type: ignore[attr-defined]
        return card

    def _field(self, parent, label: str, variable: StringVar, row: int,
               show: str | None = None, required: bool = False,
               placeholder: str = "", star_store: list | None = None,
               track: bool = False):
        line = ctk.CTkFrame(parent, fg_color="transparent")
        line.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        line.grid_columnconfigure(0, weight=1)
        lab = ctk.CTkFrame(line, fg_color="transparent")
        lab.grid(row=0, column=0, sticky="w", pady=(0, 5))
        ctk.CTkLabel(lab, text=label, font=self.f_body_bold, text_color=PALETTE["text"]).pack(side="left")
        if required:
            star = ctk.CTkLabel(lab, text=" *", font=self.f_body_bold, text_color=PALETTE["danger"])
            star.pack(side="left")
            if star_store is not None:
                star_store.append(star)
        entry = ctk.CTkEntry(
            line, textvariable=variable, show=show or "", height=40, corner_radius=10,
            font=self.f_body, border_color=PALETTE["input_border"], border_width=1,
            fg_color=PALETTE["input"], text_color=PALETTE["text"], placeholder_text=placeholder,
        )
        entry.grid(row=1, column=0, sticky="ew")
        if track:
            self.email_inputs.append(entry)
        return entry

    def _hint(self, parent, text: str, row: int) -> None:
        ctk.CTkLabel(parent, text=text, font=self.f_small, text_color=PALETTE["muted"],
                     wraplength=640, justify="left", anchor="w").grid(row=row, column=0, sticky="w", pady=(0, 4))

    def _primary_btn(self, parent, text: str, command, soft: bool = False) -> ctk.CTkButton:
        if soft:
            return ctk.CTkButton(
                parent, text=text, command=command, height=40, corner_radius=10, font=self.f_body_bold,
                fg_color=PALETTE["primary_soft"], hover_color=PALETTE["primary_soft_hover"],
                text_color=PALETTE["primary_text"],
            )
        return ctk.CTkButton(
            parent, text=text, command=command, height=42, corner_radius=10, font=self.f_body_bold,
            fg_color=PALETTE["primary"], hover_color=PALETTE["primary_hover"], text_color="#ffffff",
        )

    def _switch(self, parent, text: str, variable: BooleanVar, command=None) -> ctk.CTkSwitch:
        return ctk.CTkSwitch(
            parent, text=text, variable=variable, command=command, font=self.f_body_bold,
            text_color=PALETTE["text"], progress_color=PALETTE["primary"], button_color="#ffffff",
            button_hover_color="#f1f5f9", fg_color=PALETTE["input_border"],
        )

    def _new_page(self) -> ctk.CTkScrollableFrame:
        page = ctk.CTkScrollableFrame(self.page_container, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_remove()
        return page

    # ------------------------------------------------------------------ pages
    def _build_llm_page(self) -> None:
        page = self._new_page()
        self.pages["llm"] = page

        card = self._card(page, "OpenAI-compatible endpoint",
                          "Used to write the Chinese summaries in every report.")
        card.grid(row=0, column=0, sticky="ew")
        body = card.body  # type: ignore[attr-defined]
        self._field(body, "API Key", self.llm_api_key, 0, show="*", required=True, placeholder="sk-...")
        self._field(body, "Base URL", self.llm_base_url, 1, required=True,
                    placeholder="https://provider.example.com/v1")
        self._field(body, "Model", self.llm_model, 2, required=True, placeholder="gpt-4o-mini")
        self._hint(body,
                   "Base URL should end at /v1, not the full /chat/completions path.", 3)
        self.llm_test_button = self._primary_btn(body, "Test LLM Connection", self.test_llm, soft=True)
        self.llm_test_button.grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.busy_widgets.append(self.llm_test_button)

    def _num_field(self, parent, label: str, variable: StringVar, hint: str, row: int) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(wrap, text=label, font=self.f_body_bold, text_color=PALETTE["text"], width=190, anchor="w").grid(
            row=0, column=0, sticky="w")
        entry = ctk.CTkEntry(
            wrap, textvariable=variable, width=90, height=38, corner_radius=10, font=self.f_body,
            border_color=PALETTE["input_border"], border_width=1, fg_color=PALETTE["input"], text_color=PALETTE["text"],
            justify="center",
        )
        entry.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(wrap, text=hint, font=self.f_small, text_color=PALETTE["muted"], anchor="w").grid(
            row=0, column=2, sticky="w", padx=(12, 0))

    def _kw_box(self, parent, initial: str, height: int = 90) -> ctk.CTkTextbox:
        box = ctk.CTkTextbox(
            parent, height=height, corner_radius=10, font=self.f_body, wrap="word",
            fg_color=PALETTE["input"], text_color=PALETTE["text"], border_width=1, border_color=PALETTE["input_border"],
        )
        box.insert("1.0", initial)
        return box

    def _build_topics_page(self) -> None:
        page = self._new_page()
        self.pages["topics"] = page

        # Report size card.
        size = self._card(page, "Report size", "How far back to look and how many papers each brief keeps.")
        size.grid(row=0, column=0, sticky="ew")
        sbody = size.body  # type: ignore[attr-defined]
        self._num_field(sbody, "Papers per report", self.max_items, "top papers kept in each daily brief", 0)
        self._num_field(sbody, "Look-back window (days)", self.lookback_days, "only papers published in the last N days", 1)

        # Keyword groups card (fully user-editable).
        gcard = self._card(page, "Keyword groups",
                           "Build your own topics. A paper scores higher when it matches more groups. "
                           "One keyword per line; rename or delete any group freely.")
        gcard.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        gbody = gcard.body  # type: ignore[attr-defined]
        self.groups_container = ctk.CTkFrame(gbody, fg_color="transparent")
        self.groups_container.grid(row=0, column=0, sticky="ew")
        self.groups_container.grid_columnconfigure(0, weight=1)

        require_any = set(self.config.get("require_any_groups", []))
        for name, keywords in self.config.get("keyword_groups", {}).items():
            self._add_group_block(name, keywords, name in require_any)

        addbar = ctk.CTkFrame(gbody, fg_color="transparent")
        addbar.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ctk.CTkButton(
            addbar, text="＋  Add keyword group", command=self._add_group_block, height=38, corner_radius=10,
            font=self.f_body_bold, fg_color=PALETTE["primary_soft"], hover_color=PALETTE["primary_soft_hover"],
            text_color=PALETTE["primary_text"],
        ).pack(side="left")
        ctk.CTkLabel(
            addbar, text="Tick 'must appear' on the groups a paper is required to match (any one of them).",
            font=self.f_small, text_color=PALETTE["muted"],
        ).pack(side="left", padx=(12, 0))

        # Strong keywords card.
        strong = self._card(page, "Strong keywords",
                            "Extra weight for hot topics. Any line here adds points on top of the group score.")
        strong.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self.strong_kw_box = self._kw_box(strong.body, "\n".join(self.config.get("strong_keywords", [])), height=110)  # type: ignore[attr-defined]
        self.strong_kw_box.grid(row=0, column=0, sticky="ew")

        # Negative keywords card.
        neg = self._card(page, "Excluded keywords",
                        "Papers matching any of these lose points, filtering out unrelated fields.")
        neg.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        self.negative_kw_box = self._kw_box(neg.body, "\n".join(self.config.get("negative_keywords", [])), height=130)  # type: ignore[attr-defined]
        self.negative_kw_box.grid(row=0, column=0, sticky="ew")

        # Advanced strictness card.
        adv = self._card(page, "Matching strictness (advanced)",
                        "Raise these to keep fewer, more on-topic papers. Lower them if the brief comes back empty.")
        adv.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        abody = adv.body  # type: ignore[attr-defined]
        self._num_field(abody, "Minimum score", self.min_score, "a paper must reach this to be kept", 0)
        self._num_field(abody, "Minimum groups matched", self.group_min_matches, "distinct groups a paper must hit", 1)

    def _add_group_block(self, name: str = "", keywords: list[str] | None = None,
                         required: bool = False) -> None:
        block = ctk.CTkFrame(self.groups_container, fg_color=PALETTE["card_alt"], corner_radius=12)
        block.pack(fill="x", pady=(0, 12))
        block.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(block, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        head.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(head, text="Group", font=self.f_small, text_color=PALETTE["muted"]).grid(row=0, column=0, padx=(0, 8))
        name_var = StringVar(value=name.replace("_", " "))
        name_entry = ctk.CTkEntry(
            head, textvariable=name_var, height=34, corner_radius=8, font=self.f_body_bold,
            border_color=PALETTE["input_border"], border_width=1, fg_color=PALETTE["card"],
            text_color=PALETTE["text"], placeholder_text="e.g. materials, methods, keywords...",
        )
        name_entry.grid(row=0, column=1, sticky="ew")
        req_var = BooleanVar(value=required)
        ctk.CTkCheckBox(
            head, text="must appear", variable=req_var, font=self.f_small, text_color=PALETTE["muted"],
            fg_color=PALETTE["primary"], hover_color=PALETTE["primary_hover"], checkbox_height=18, checkbox_width=18,
        ).grid(row=0, column=2, sticky="e", padx=(10, 8))
        entry: dict = {}
        ctk.CTkButton(
            head, text="🗑", width=34, height=34, corner_radius=8, font=ctk.CTkFont(size=14),
            fg_color=PALETTE["card"], hover_color="#fde8e8", text_color=PALETTE["danger"],
            border_width=1, border_color=PALETTE["border"], command=lambda: self._remove_group_block(entry),
        ).grid(row=0, column=3, sticky="e")

        box = self._kw_box(block, "\n".join(keywords or []))
        box.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))

        entry.update({"frame": block, "name": name_var, "required": req_var, "box": box})
        self.group_entries.append(entry)

    def _remove_group_block(self, entry: dict) -> None:
        entry["frame"].destroy()
        if entry in self.group_entries:
            self.group_entries.remove(entry)

    def _build_notifications_page(self) -> None:
        page = self._new_page()
        self.pages["notifications"] = page

        # Feishu card
        fcard = self._card(page, "Feishu bot", "Push the daily brief to a Feishu group via a custom bot webhook.")
        fcard.grid(row=0, column=0, sticky="ew")
        fbody = fcard.body  # type: ignore[attr-defined]
        self._switch(fbody, "Enable Feishu delivery", self.feishu_enabled).grid(row=0, column=0, sticky="w", pady=(0, 14))
        self._field(fbody, "Webhook URL", self.feishu_webhook, 1, required=True,
                    placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/...")
        self.feishu_test_button = self._primary_btn(fbody, "Send Test Message", self.test_feishu, soft=True)
        self.feishu_test_button.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.busy_widgets.append(self.feishu_test_button)

        # Email card
        ecard = self._card(page, "Email (optional)", "Deliver the same report over SMTP. Leave disabled if you only use Feishu.")
        ecard.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        ebody = ecard.body  # type: ignore[attr-defined]
        self._switch(ebody, "Enable email delivery", self.email_enabled, command=self._toggle_email_fields).grid(
            row=0, column=0, sticky="w", pady=(0, 14))

        prov_line = ctk.CTkFrame(ebody, fg_color="transparent")
        prov_line.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        plab = ctk.CTkFrame(prov_line, fg_color="transparent")
        plab.pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(plab, text="Provider", font=self.f_body_bold, text_color=PALETTE["text"]).pack(side="left")
        star = ctk.CTkLabel(plab, text=" *", font=self.f_body_bold, text_color=PALETTE["danger"])
        star.pack(side="left")
        self.email_required_stars.append(star)
        self.email_provider_combo = ctk.CTkOptionMenu(
            prov_line, variable=self.email_provider, values=list(EMAIL_PROVIDERS.keys()),
            width=220, height=40, corner_radius=10, font=self.f_body,
            fg_color=PALETTE["input"], text_color=PALETTE["text"], button_color=PALETTE["primary"],
            button_hover_color=PALETTE["primary_hover"], command=lambda _v: self._apply_email_provider(),
        )
        self.email_provider_combo.pack(anchor="w")

        self._field(ebody, "Email Address", self.email_address, 2, required=True,
                    placeholder="you@example.com", star_store=self.email_required_stars, track=True)
        self._field(ebody, "SMTP Authorization Code", self.email_auth_code, 3, show="*", required=True,
                    placeholder="app / authorization code", star_store=self.email_required_stars, track=True)
        self._field(ebody, "Recipient (optional)", self.email_recipient, 4,
                    placeholder="leave empty to send to yourself", track=True)
        self._hint(ebody, "For QQ Mail, pick QQ Mail and use the SMTP authorization code, not the login password.", 5)

        self.advanced_smtp_check = ctk.CTkCheckBox(
            ebody, text="Show advanced SMTP settings", variable=self.show_advanced_smtp,
            command=self._toggle_advanced_smtp, font=self.f_small, text_color=PALETTE["muted"],
            fg_color=PALETTE["primary"], hover_color=PALETTE["primary_hover"], checkbox_height=20, checkbox_width=20,
        )
        self.advanced_smtp_check.grid(row=6, column=0, sticky="w", pady=(4, 8))

        self.advanced_smtp_frame = ctk.CTkFrame(ebody, fg_color=PALETTE["card_alt"], corner_radius=12)
        self.advanced_smtp_frame.grid(row=7, column=0, sticky="ew", pady=(0, 8))
        self.advanced_smtp_frame.grid_columnconfigure(0, weight=1)
        inner = ctk.CTkFrame(self.advanced_smtp_frame, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        inner.grid_columnconfigure(0, weight=1)
        self._field(inner, "SMTP Host", self.smtp_host, 0, required=True, star_store=self.email_required_stars, track=True)
        self._field(inner, "SMTP Port", self.smtp_port, 1, required=True, star_store=self.email_required_stars, track=True)
        toggles = ctk.CTkFrame(inner, fg_color="transparent")
        toggles.grid(row=2, column=0, sticky="w")
        ssl_cb = ctk.CTkCheckBox(toggles, text="Use SSL", variable=self.smtp_ssl, font=self.f_small,
                                 text_color=PALETTE["text"], fg_color=PALETTE["primary"], checkbox_height=20, checkbox_width=20)
        ssl_cb.pack(side="left", padx=(0, 20))
        tls_cb = ctk.CTkCheckBox(toggles, text="Use TLS", variable=self.smtp_tls, font=self.f_small,
                                 text_color=PALETTE["text"], fg_color=PALETTE["primary"], checkbox_height=20, checkbox_width=20)
        tls_cb.pack(side="left")
        self.email_inputs.extend([ssl_cb, tls_cb])

        self.email_test_button = self._primary_btn(ebody, "Send Test Email", self.test_email, soft=True)
        self.email_test_button.grid(row=8, column=0, sticky="w", pady=(4, 0))
        self.email_inputs.append(self.email_test_button)
        self.busy_widgets.append(self.email_test_button)

        self._apply_email_provider()
        self._toggle_advanced_smtp()
        self._toggle_email_fields()

    def _build_run_page(self) -> None:
        page = self._new_page()
        self.pages["run"] = page

        card = self._card(page, "Run one full brief now",
                          "Fetch papers, filter, summarize, and push to every enabled channel — a real run.")
        card.grid(row=0, column=0, sticky="ew")
        body = card.body  # type: ignore[attr-defined]

        steps = ctk.CTkFrame(body, fg_color=PALETTE["card_alt"], corner_radius=12)
        steps.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        for i, (icon, text) in enumerate([
            ("🔎", "Fetch recent papers from arXiv and Crossref"),
            ("🧮", "Filter by your positive / negative keyword groups"),
            ("✍️", "Summarize each match in Chinese with the LLM"),
            ("📨", "Deliver the report to Feishu and/or email"),
        ]):
            row = ctk.CTkFrame(steps, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(12 if i == 0 else 4, 12 if i == 3 else 4))
            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=16), width=26).pack(side="left")
            ctk.CTkLabel(row, text=text, font=self.f_body, text_color=PALETTE["text"], anchor="w").pack(side="left", padx=(6, 0))

        self.run_test_button = self._primary_btn(body, "▶  Run Literature Test", self.run_literature_test)
        self.run_test_button.grid(row=1, column=0, sticky="w")
        self.busy_widgets.append(self.run_test_button)

        progress_row = ctk.CTkFrame(body, fg_color="transparent")
        progress_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        progress_row.grid_columnconfigure(0, weight=1)
        self.run_progress = ctk.CTkProgressBar(
            progress_row, mode="indeterminate", height=8, progress_color=PALETTE["primary"]
        )
        self.run_progress.grid(row=0, column=0, sticky="ew")
        self.run_progress.grid_remove()
        self.run_status = ctk.CTkLabel(
            progress_row, text="", font=self.f_small, text_color=PALETTE["muted"],
            wraplength=620, justify="left", anchor="w",
        )
        self.run_status.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.run_status.grid_remove()

        note = ctk.CTkFrame(body, fg_color="transparent")
        note.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkLabel(
            note, text=("This sends a real message and may take a few minutes. It ignores the "
                        "already-seen database so you always get results. Watch the Activity log below."),
            font=self.f_small, text_color=PALETTE["muted"], wraplength=620, justify="left", anchor="w",
        ).pack(anchor="w")

    def _build_schedule_page(self) -> None:
        page = self._new_page()
        self.pages["schedule"] = page

        card = self._card(page, "Daily Windows task", "Register a scheduled task on this computer to send the brief every day.")
        card.grid(row=0, column=0, sticky="ew")
        body = card.body  # type: ignore[attr-defined]
        entry = self._field(body, "Daily time (HH:MM)", self.schedule_time, 0, required=True, placeholder="09:00")
        entry.configure(width=160)
        self._hint(body, "24-hour format, for example 09:00 or 18:30.", 1)
        self.schedule_button = self._primary_btn(body, "Install / Update Windows Task", self.install_schedule, soft=True)
        self.schedule_button.grid(row=2, column=0, sticky="w", pady=(8, 12))
        self.busy_widgets.append(self.schedule_button)
        note = ctk.CTkFrame(body, fg_color=PALETTE["card_alt"], corner_radius=12)
        note.grid(row=3, column=0, sticky="ew")
        ctk.CTkLabel(
            note, text=("ℹ  The task runs only while this computer is on. For cloud scheduling that "
                        "works with the machine off, use the GitHub Actions workflow described in the README."),
            font=self.f_small, text_color=PALETTE["muted"], wraplength=620, justify="left",
        ).pack(anchor="w", padx=14, pady=12)

    def _build_action_bar(self, parent: ctk.CTkFrame) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self.save_button = self._primary_btn(bar, "💾  Save Configuration", self.save_config)
        self.save_button.pack(side="left")
        self.busy_widgets.append(self.save_button)
        ctk.CTkLabel(
            bar, text="Saves credentials to .env and settings to config.json.",
            font=self.f_small, text_color=PALETTE["muted"],
        ).pack(side="left", padx=(14, 0))

    def _build_activity(self, parent: ctk.CTkFrame) -> None:
        card = ctk.CTkFrame(parent, fg_color=PALETTE["card"], corner_radius=16,
                            border_width=1, border_color=PALETTE["border"])
        card.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        card.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        ctk.CTkLabel(head, text="Activity", font=self.f_h2, text_color=PALETTE["text"]).pack(side="left")
        ctk.CTkLabel(head, text="Test results, saves, and scheduled-task output appear here.",
                     font=self.f_small, text_color=PALETTE["muted"]).pack(side="left", padx=(10, 0))
        self.output = ctk.CTkTextbox(
            card, height=150, corner_radius=12, font=self.f_mono, wrap="word",
            fg_color=PALETTE["card_alt"], text_color=PALETTE["text"], border_width=1,
            border_color=PALETTE["border"],
        )
        self.output.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 18))
        self.output.tag_config("success", foreground=PALETTE["success"])
        self.output.tag_config("error", foreground=PALETTE["danger"])
        self.output.tag_config("info", foreground=PALETTE["muted"])
        self.output.configure(state="disabled")

    def select_page(self, key: str) -> None:
        for name, page in self.pages.items():
            if name == key:
                page.grid()
            else:
                page.grid_remove()
        for name, btn in self.nav_buttons.items():
            if name == key:
                btn.configure(fg_color=PALETTE["primary_soft"], text_color=PALETTE["primary_text"])
            else:
                btn.configure(fg_color="transparent", text_color=PALETTE["muted"])
        titles = {
            "llm": ("Model API", "Connect the LLM that summarizes each paper."),
            "topics": ("Topics & Filter", "Tune keywords, report size, and how strict the filter is."),
            "notifications": ("Notifications", "Decide where the daily brief is delivered."),
            "run": ("Run a Test", "Send one full brief now to confirm everything works."),
            "schedule": ("Schedule", "Automate the brief with a daily Windows task."),
        }
        title, sub = titles.get(key, ("", ""))
        self.header_title.configure(text=title)
        self.header_sub.configure(text=sub)

    # ----------------------------------------------------------------- toggles
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
        state = "normal" if enabled else "disabled"
        star_color = PALETTE["danger"] if enabled else PALETTE["muted"]
        if hasattr(self, "email_provider_combo"):
            self.email_provider_combo.configure(state=state)
        if hasattr(self, "advanced_smtp_check"):
            self.advanced_smtp_check.configure(state=state)
        for widget in self.email_inputs:
            try:
                widget.configure(state=state)
            except Exception:
                pass
        for star in self.email_required_stars:
            star.configure(text_color=star_color)

    # -------------------------------------------------------------- persistence
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

    @staticmethod
    def _lines(box: ctk.CTkTextbox) -> list[str]:
        raw = box.get("1.0", "end")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _apply_topics(self, config: dict) -> None:
        def as_int(variable: StringVar, fallback: int, minimum: int = 0) -> int:
            try:
                return max(minimum, int(str(variable.get()).strip()))
            except (TypeError, ValueError):
                return fallback

        config["max_items_in_report"] = as_int(self.max_items, config.get("max_items_in_report", 8), 1)
        config["lookback_days"] = as_int(self.lookback_days, config.get("lookback_days", 7), 1)
        config["min_score"] = as_int(self.min_score, config.get("min_score", 12))
        config["group_min_matches"] = as_int(self.group_min_matches, config.get("group_min_matches", 3))

        groups: dict[str, list[str]] = {}
        require_any: list[str] = []
        used: set[str] = set()
        for entry in self.group_entries:
            raw_name = entry["name"].get().strip()
            keywords = self._lines(entry["box"])
            if not raw_name or not keywords:
                continue
            key = re.sub(r"\s+", "_", raw_name.lower())
            base = key
            suffix = 2
            while key in used:  # avoid clobbering two groups with the same name
                key = f"{base}_{suffix}"
                suffix += 1
            used.add(key)
            groups[key] = keywords
            if entry["required"].get():
                require_any.append(key)
        config["keyword_groups"] = groups
        config["require_any_groups"] = require_any
        if self.strong_kw_box is not None:
            config["strong_keywords"] = self._lines(self.strong_kw_box)
        if self.negative_kw_box is not None:
            config["negative_keywords"] = self._lines(self.negative_kw_box)

    def save_config(self) -> None:
        env_values = self.collect_env()
        config = load_json_config()
        self._apply_topics(config)
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
        self.log("Configuration saved.", "success")

    # -------------------------------------------------------------------- tests
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
            **subprocess_no_window_kwargs(),
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
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $ExistingTask) {{
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}}
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
            **subprocess_no_window_kwargs(),
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            raise RuntimeError(output.strip() or "Failed to install scheduled task.")
        return output.strip()

    def open_project_folder(self) -> None:
        if os.name == "nt":
            os.startfile(PROJECT_DIR)  # type: ignore[attr-defined]
        else:
            self.log(str(PROJECT_DIR), "info")

    # ------------------------------------------------------------------ helpers
    def _run_threaded(self, start_message: str, target) -> None:
        if self.is_busy:
            self.log("Another operation is already running. Please wait for it to finish.", "info")
            return
        self._set_busy(True, start_message)
        self.log(start_message, "info")

        def worker() -> None:
            try:
                result = target()
            except Exception as exc:
                message = str(exc)
                self.root.after(0, lambda msg=message: self._finish_error(msg))
            else:
                self.root.after(0, lambda text=result: self._finish_success(text))

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.is_busy = busy
        state = "disabled" if busy else "normal"
        for widget in self.busy_widgets:
            try:
                widget.configure(state=state)
            except Exception:
                pass
        if hasattr(self, "run_progress"):
            if busy:
                self.run_progress.grid()
                self.run_progress.start()
                self.run_status.configure(text=message)
                self.run_status.grid()
            else:
                self.run_progress.stop()
                self.run_progress.grid_remove()
                self.run_status.configure(text="")
                self.run_status.grid_remove()
        if not busy:
            self._toggle_email_fields()

    def _finish_success(self, message: str) -> None:
        self._set_busy(False)
        self.log(message, "success")

    def _finish_error(self, message: str) -> None:
        self._set_busy(False)
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self.log("ERROR: " + message, "error")
        messagebox.showerror("Literature Agent", message)

    def log(self, message: str, level: str = "info") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output.configure(state="normal")
        self.output.insert("end", f"[{timestamp}] {message}\n", level)
        self.output.see("end")
        self.output.configure(state="disabled")


def main() -> int:
    root = ctk.CTk()
    SetupApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
