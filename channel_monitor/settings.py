"""Settings file for the scheduled `daily` run."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .mailer import SmtpConfig

log = logging.getLogger(__name__)


@dataclass
class EmailSettings:
    enabled: bool = True
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    use_ssl: bool = False
    username: str = ""
    password: str = ""
    password_env: str = "CHANNEL_MONITOR_SMTP_PASSWORD"
    sender: str = ""
    recipients: list[str] = field(default_factory=list)
    send_when_empty: bool = False
    attach_csv: bool = True
    attach_charts: bool = True
    max_charts: int = 8
    subject_prefix: str = "[channel-monitor]"

    def smtp(self) -> SmtpConfig:
        password = self.password or os.environ.get(self.password_env, "")
        return SmtpConfig(
            host=self.smtp_host,
            port=self.smtp_port,
            username=self.username,
            password=password,
            use_ssl=self.use_ssl,
            sender=self.sender or self.username,
            recipients=tuple(self.recipients),
        )


@dataclass
class DailySettings:
    markets: list[str] = field(default_factory=lambda: ["nasdaq", "kospi"])
    lookbacks: list[int] = field(default_factory=lambda: [90, 120, 150])
    limit: int | None = None
    sample: int | None = None
    symbols: list[str] = field(default_factory=list)
    universe_file: str = ""
    offline_universe: bool = False

    min_score: float = 55.0
    require_volume: bool = False
    min_volume_ratio: float = 1.2
    breakout_window: int = 5

    cache_dir: str = ".cache/prices"
    cache_ttl: float = 12.0
    history_days: int = 400
    chunk_size: int = 80
    csv_dir: str = ""

    out_dir: str = "out"
    state_file: str = ".cache/alerts.json"
    plot: bool = True
    log_file: str = "logs/daily.log"

    email: EmailSettings = field(default_factory=EmailSettings)

    def to_dict(self) -> dict:
        return asdict(self)


def load_settings(path: str | Path | None) -> DailySettings:
    if not path:
        return DailySettings()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"settings file not found: {p}\n"
            "create one with:  python -m channel_monitor init-config monitor.config.json"
        )
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p}: expected a JSON object at the top level")
    return from_dict(raw)


def from_dict(raw: dict[str, Any]) -> DailySettings:
    email_raw = raw.get("email", {}) or {}
    if not isinstance(email_raw, dict):
        raise ValueError("'email' must be a JSON object")

    settings = _build(DailySettings, {k: v for k, v in raw.items() if k != "email"})
    settings.email = _build(EmailSettings, email_raw)
    return settings


def _build(cls, raw: dict[str, Any]):
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(raw) - known)
    if unknown:
        log.warning("ignoring unknown %s keys: %s", cls.__name__, ", ".join(unknown))
    return cls(**{k: v for k, v in raw.items() if k in known})


EXAMPLE_CONFIG = {
    "markets": ["nasdaq", "kospi"],
    "lookbacks": [90, 120, 150],
    "limit": None,
    "sample": None,
    "min_score": 55.0,
    "require_volume": False,
    "out_dir": "out",
    "state_file": ".cache/alerts.json",
    "plot": True,
    "log_file": "logs/daily.log",
    "email": {
        "enabled": True,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "use_ssl": False,
        "username": "you@gmail.com",
        "password_env": "CHANNEL_MONITOR_SMTP_PASSWORD",
        "sender": "you@gmail.com",
        "recipients": ["you@gmail.com"],
        "send_when_empty": False,
        "attach_csv": True,
        "attach_charts": True,
        "max_charts": 8,
    },
}


def write_example_config(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(EXAMPLE_CONFIG, indent=2) + "\n", encoding="utf-8")
    return p
