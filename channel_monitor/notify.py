"""Alert delivery for watch mode, with de-duplication across runs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

from .screener import Hit

log = logging.getLogger(__name__)


class AlertState:
    """Remembers which (symbol, breakout bar) pairs have already been alerted."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self.seen: set[str] = set()
        if self.path and self.path.exists():
            try:
                self.seen = set(json.loads(self.path.read_text(encoding="utf-8")).get("seen", []))
            except Exception as exc:
                log.warning("could not read alert state %s: %s", self.path, exc)

    @staticmethod
    def key(hit: Hit) -> str:
        return f"{hit.market}:{hit.code}:{hit.result.break_date}"

    def new_hits(self, hits: Sequence[Hit]) -> list[Hit]:
        return [h for h in hits if self.key(h) not in self.seen]

    def mark(self, hits: Sequence[Hit]) -> None:
        self.seen.update(self.key(h) for h in hits)
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(
                json.dumps({"seen": sorted(self.seen)}, indent=0), encoding="utf-8"
            )
        except Exception as exc:
            log.warning("could not write alert state %s: %s", self.path, exc)


def format_alert(hits: Sequence[Hit]) -> str:
    if not hits:
        return ""
    lines = [f"Ascending-channel breakout: {len(hits)} new"]
    for h in hits:
        r = h.result
        lines.append(
            f"- [{h.market.upper()}] {h.code} score {r.score:.0f} | {r.status} on {r.break_date}"
            f" | close {r.last_close:,.2f} vs upper {r.upper_now:,.2f}"
            f" | excess {r.break_excess * 100:.1f}% | vol x{r.volume_ratio:.1f}"
        )
    return "\n".join(lines)


def post_webhook(url: str, text: str, timeout: float = 15.0) -> bool:
    if not url or not text:
        return False
    try:
        import requests

        resp = requests.post(url, json={"text": text, "content": text}, timeout=timeout)
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.error("webhook post failed: %s", exc)
        return False
