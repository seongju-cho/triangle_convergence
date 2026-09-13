"""Tunable parameters for ascending-channel breakout detection."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Tuple


@dataclass(frozen=True)
class ChannelConfig:
    # --- window / pivots ---
    lookback: int = 120
    pivot_window: int = 3
    min_pivots_per_line: int = 2
    min_line_span: int = 30
    max_anchor_gap: int = 35

    # --- trendline fitting ---
    touch_tolerance: float = 0.015
    violation_tolerance: float = 0.020

    # --- channel shape ---
    min_slope_pct: float = 0.0005
    max_slope_pct: float = 0.0200
    parallel_tolerance: float = 0.40
    width_ratio_range: Tuple[float, float] = (0.40, 2.50)
    min_channel_width: float = 0.030
    max_channel_width: float = 0.800
    min_containment: float = 0.80

    # --- breakout ---
    breakout_window: int = 5
    fresh_window: int = 20
    min_break_pct: float = 0.005
    break_atr_mult: float = 0.25
    atr_window: int = 14
    volume_window: int = 20
    min_volume_ratio: float = 1.2
    require_volume: bool = False
    max_extension: float = 0.20
    allow_pullback: bool = True
    pullback_tolerance: float = 0.010

    # --- output ---
    min_score: float = 55.0

    def replace(self, **kwargs: Any) -> "ChannelConfig":
        known = {f.name for f in fields(self)}
        unknown = set(kwargs) - known
        if unknown:
            raise TypeError(f"unknown config keys: {sorted(unknown)}")
        current = {f.name: getattr(self, f.name) for f in fields(self)}
        current.update(kwargs)
        return ChannelConfig(**current)


@dataclass(frozen=True)
class ScreenConfig:
    min_price: float = 3.0
    max_price: float = 1.0e9
    min_avg_volume: float = 100_000.0
    min_avg_turnover: float = 3.0e6
    min_history: int = 150
    history_days: int = 400

    def replace(self, **kwargs: Any) -> "ScreenConfig":
        current = {f.name: getattr(self, f.name) for f in fields(self)}
        current.update(kwargs)
        return ScreenConfig(**current)


MARKET_PRESETS = {
    # KRX quotes are in KRW, so price/turnover thresholds differ by an order of magnitude.
    "kospi": ScreenConfig(min_price=1000.0, min_avg_volume=30_000.0, min_avg_turnover=1.0e9),
    "kosdaq": ScreenConfig(min_price=1000.0, min_avg_volume=30_000.0, min_avg_turnover=5.0e8),
    "nasdaq": ScreenConfig(),
}
