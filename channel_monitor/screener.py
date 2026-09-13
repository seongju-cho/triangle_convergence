"""Run the channel-breakout detector across market universes."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Sequence

import pandas as pd

from .channel import ChannelResult, detect
from .config import ChannelConfig, ScreenConfig
from .data import PriceLoader
from .markets import Market, get_market
from .universe import load_universe, read_symbol_file

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, int], None]


@dataclass
class Hit:
    market: str
    code: str
    symbol: str
    result: ChannelResult
    avg_volume: float = 0.0
    avg_turnover: float = 0.0

    def as_row(self) -> dict:
        row = {"market": self.market, "code": self.code, "symbol": self.symbol}
        row.update(self.result.as_row())
        row["avg_volume"] = int(self.avg_volume)
        row["avg_turnover"] = int(self.avg_turnover)
        return row


@dataclass
class ScanReport:
    hits: list[Hit] = field(default_factory=list)
    scanned: int = 0
    skipped: Counter = field(default_factory=Counter)
    rejected: Counter = field(default_factory=Counter)

    def to_frame(self) -> pd.DataFrame:
        if not self.hits:
            return pd.DataFrame()
        return pd.DataFrame([h.as_row() for h in self.hits])


def scan_market(
    market_key: str,
    *,
    loader: PriceLoader,
    channel_cfg: ChannelConfig | None = None,
    screen_cfg: ScreenConfig | None = None,
    lookbacks: Sequence[int] | None = None,
    symbols: Sequence[str] | None = None,
    universe_file: str | None = None,
    limit: int | None = None,
    offline_universe: bool = False,
    progress: ProgressFn | None = None,
) -> ScanReport:
    market = get_market(market_key)
    channel_cfg = channel_cfg or ChannelConfig()
    screen_cfg = screen_cfg or market.screen

    if symbols:
        codes = [s.strip().upper() for s in symbols if s.strip()]
    elif universe_file:
        codes = read_symbol_file(universe_file)
    else:
        codes = load_universe(market.key, limit=limit, offline=offline_universe)
    if limit:
        codes = codes[:limit]

    report = ScanReport()
    total = len(codes)
    if not total:
        return report

    batch = max(1, loader.cfg.chunk_size)
    for start in range(0, total, batch):
        chunk = codes[start:start + batch]
        symbol_map = {market.yahoo_symbol(c): c for c in chunk}
        frames = loader.load_many(list(symbol_map))
        for symbol, code in symbol_map.items():
            report.scanned += 1
            if progress:
                progress(f"{market.key}:{code}", report.scanned, total)
            df = frames.get(symbol)
            hit = _evaluate(market, code, symbol, df, channel_cfg, screen_cfg, lookbacks, report)
            if hit is not None:
                report.hits.append(hit)

    report.hits.sort(key=lambda h: h.result.score, reverse=True)
    return report


def scan_markets(market_keys: Sequence[str], **kwargs) -> ScanReport:
    merged = ScanReport()
    for key in market_keys:
        part = scan_market(key, **kwargs)
        merged.hits.extend(part.hits)
        merged.scanned += part.scanned
        merged.skipped.update(part.skipped)
        merged.rejected.update(part.rejected)
    merged.hits.sort(key=lambda h: h.result.score, reverse=True)
    return merged


def explain_symbol(
    market_key: str,
    code: str,
    *,
    loader: PriceLoader,
    channel_cfg: ChannelConfig | None = None,
    lookbacks: Sequence[int] | None = None,
) -> tuple[pd.DataFrame | None, ChannelResult]:
    market = get_market(market_key)
    symbol = market.yahoo_symbol(code)
    df = loader.load(symbol)
    if df is None or df.empty:
        return None, ChannelResult(False, reason="no_data")
    return df, detect(df, channel_cfg or ChannelConfig(), lookbacks=lookbacks)


def _evaluate(
    market: Market,
    code: str,
    symbol: str,
    df: pd.DataFrame | None,
    channel_cfg: ChannelConfig,
    screen_cfg: ScreenConfig,
    lookbacks: Sequence[int] | None,
    report: ScanReport,
) -> Hit | None:
    if df is None or df.empty:
        report.skipped["no_data"] += 1
        return None
    if len(df) < screen_cfg.min_history:
        report.skipped["short_history"] += 1
        return None

    close = df["Close"]
    volume = df["Volume"]
    last_close = float(close.iloc[-1])
    avg_volume = float(volume.tail(20).mean())
    avg_turnover = float((close * volume).tail(20).mean())

    if not (screen_cfg.min_price <= last_close <= screen_cfg.max_price):
        report.skipped["price_filter"] += 1
        return None
    if avg_volume < screen_cfg.min_avg_volume:
        report.skipped["volume_filter"] += 1
        return None
    if avg_turnover < screen_cfg.min_avg_turnover:
        report.skipped["turnover_filter"] += 1
        return None

    result = detect(df, channel_cfg, lookbacks=lookbacks)
    if not result.ok:
        report.rejected[result.reason or "unknown"] += 1
        return None
    return Hit(market.key, code, symbol, result, avg_volume, avg_turnover)
