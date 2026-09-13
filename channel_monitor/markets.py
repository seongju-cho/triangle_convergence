"""Market definitions and ticker-symbol conventions."""

from __future__ import annotations

from dataclasses import dataclass

from .config import MARKET_PRESETS, ScreenConfig


@dataclass(frozen=True)
class Market:
    key: str
    label: str
    yahoo_suffix: str
    currency: str
    screen: ScreenConfig

    def yahoo_symbol(self, code: str) -> str:
        code = code.strip().upper()
        if self.yahoo_suffix and not code.endswith(self.yahoo_suffix):
            return f"{code}{self.yahoo_suffix}"
        return code

    def code(self, yahoo_symbol: str) -> str:
        if self.yahoo_suffix and yahoo_symbol.endswith(self.yahoo_suffix):
            return yahoo_symbol[: -len(self.yahoo_suffix)]
        return yahoo_symbol


MARKETS = {
    "nasdaq": Market("nasdaq", "NASDAQ", "", "USD", MARKET_PRESETS["nasdaq"]),
    "kospi": Market("kospi", "KOSPI", ".KS", "KRW", MARKET_PRESETS["kospi"]),
    "kosdaq": Market("kosdaq", "KOSDAQ", ".KQ", "KRW", MARKET_PRESETS["kosdaq"]),
}

DEFAULT_MARKETS = ("nasdaq", "kospi")


def get_market(key: str) -> Market:
    key = key.strip().lower()
    if key not in MARKETS:
        raise KeyError(f"unknown market '{key}' (available: {', '.join(sorted(MARKETS))})")
    return MARKETS[key]
