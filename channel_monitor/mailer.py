"""SMTP email delivery (standard library only)."""

from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Sequence

log = logging.getLogger(__name__)


@dataclass
class SmtpConfig:
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    use_ssl: bool = False
    sender: str = ""
    recipients: tuple[str, ...] = ()
    timeout: float = 30.0

    @property
    def configured(self) -> bool:
        return bool(self.host and self.sender and self.recipients)

    def missing(self) -> list[str]:
        gaps = []
        if not self.host:
            gaps.append("smtp_host")
        if not self.sender:
            gaps.append("sender")
        if not self.recipients:
            gaps.append("recipients")
        if self.username and not self.password:
            gaps.append("password")
        return gaps


def config_from_env(prefix: str = "CHANNEL_MONITOR_") -> SmtpConfig:
    """Read SMTP settings from PREFIX_SMTP_HOST, _SMTP_PORT, _SMTP_USER, ..."""
    get = lambda name, default="": os.environ.get(f"{prefix}{name}", default)  # noqa: E731
    recipients = tuple(r.strip() for r in get("MAIL_TO").replace(";", ",").split(",") if r.strip())
    return SmtpConfig(
        host=get("SMTP_HOST"),
        port=int(get("SMTP_PORT", "587") or 587),
        username=get("SMTP_USER"),
        password=get("SMTP_PASSWORD"),
        use_ssl=get("SMTP_SSL", "").lower() in ("1", "true", "yes"),
        sender=get("MAIL_FROM") or get("SMTP_USER"),
        recipients=recipients,
    )


def build_message(
    cfg: SmtpConfig,
    subject: str,
    html: str,
    text: str = "",
    attachments: Sequence[str | Path] = (),
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.sender
    msg["To"] = ", ".join(cfg.recipients)
    msg.set_content(text or _strip_tags(html))
    msg.add_alternative(html, subtype="html")

    for item in attachments:
        path = Path(item)
        if not path.exists():
            log.warning("attachment missing, skipped: %s", path)
            continue
        guessed, _ = mimetypes.guess_type(path.name)
        maintype, _, subtype = (guessed or "application/octet-stream").partition("/")
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=path.name,
        )
    return msg


def send_message(cfg: SmtpConfig, msg: EmailMessage) -> None:
    context = ssl.create_default_context()
    if cfg.use_ssl:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout, context=context) as smtp:
            _login_and_send(cfg, smtp, msg)
    else:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            _login_and_send(cfg, smtp, msg)


def _login_and_send(cfg: SmtpConfig, smtp, msg: EmailMessage) -> None:
    if cfg.username:
        smtp.login(cfg.username, cfg.password)
    smtp.send_message(msg)


def send_email(
    cfg: SmtpConfig,
    subject: str,
    html: str,
    text: str = "",
    attachments: Sequence[str | Path] = (),
    transport=send_message,
) -> bool:
    gaps = cfg.missing()
    if gaps:
        log.error("email not sent, incomplete SMTP config: %s", ", ".join(gaps))
        return False
    try:
        transport(cfg, build_message(cfg, subject, html, text, attachments))
        log.info("email sent to %s", ", ".join(cfg.recipients))
        return True
    except Exception as exc:
        log.error("email delivery failed: %s", exc)
        return False


def _strip_tags(html: str) -> str:
    import re

    text = re.sub(r"<br\s*/?>|</tr>|</h[1-6]>|</p>", "\n", html)
    text = re.sub(r"</t[dh]>", "\t", text)
    return re.sub(r"<[^>]+>", "", text).strip()
