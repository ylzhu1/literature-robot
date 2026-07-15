from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict

from .config import env_bool


def send_email(report: str, config: Dict[str, Any]) -> None:
    email_config = config.get("email", {})
    sender = email_config.get("sender") or os.environ.get("SMTP_USERNAME", "")
    recipients = email_config.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [recipients]
    recipients = [recipient for recipient in recipients if recipient and "@" in recipient]
    if not sender or not recipients:
        raise RuntimeError("Email sender or recipients are not configured")

    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "465"))
    username = os.environ.get("SMTP_USERNAME", sender)
    password = os.environ.get("SMTP_PASSWORD", "")
    use_ssl = env_bool("SMTP_USE_SSL", True)
    use_tls = env_bool("SMTP_USE_TLS", False)
    if not host or not password:
        raise RuntimeError("SMTP_HOST or SMTP_PASSWORD is not configured")

    subject_prefix = email_config.get("subject_prefix", "Literature Agent")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"{subject_prefix} Daily Brief"
    message.set_content(report)

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
