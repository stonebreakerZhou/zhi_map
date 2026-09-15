"""Email sender abstraction.

ConsoleSender is the default — it prints the verification code to stdout
and the front-end dev-mode UI offers an "auto-fill" button.

SmtpSender is engaged when SMTP_HOST is in the environment, so production
deployment can swap in any cloud mail service (Aliyun DirectMail, Tencent
Cloud SES, AWS SES, Resend, …) by setting 5 env vars.
"""
from __future__ import annotations
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Protocol


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


_CODE_RE = re.compile(r"\b(\d{6})\b")


class ConsoleSender:
    """Development mode — prints verification code to stdout."""

    def send(self, to: str, subject: str, body: str) -> None:
        match = _CODE_RE.search(body)
        code = match.group(1) if match else "??"
        print(f"[AUTH EMAIL] to={to} subject={subject!r} code={code}", flush=True)


class SmtpSender:
    """Production mode — reads SMTP creds from environment."""

    def __init__(self) -> None:
        self.host = os.environ["SMTP_HOST"]
        self.port = int(os.environ.get("SMTP_PORT", "465"))
        self.user = os.environ["SMTP_USER"]
        self.password = os.environ["SMTP_PASS"]
        self.from_addr = os.environ.get("SMTP_FROM", self.user)
        self.use_ssl = os.environ.get("SMTP_SSL", "1") != "0"

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if self.use_ssl:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as s:
                s.login(self.user, self.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as s:
                s.starttls()
                s.login(self.user, self.password)
                s.send_message(msg)


_instance: EmailSender | None = None


def get_sender() -> EmailSender:
    """Lazy singleton — picks SmtpSender iff SMTP_HOST is set."""
    global _instance
    if _instance is None:
        if os.environ.get("SMTP_HOST"):
            _instance = SmtpSender()
        else:
            _instance = ConsoleSender()
    return _instance