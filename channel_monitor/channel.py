"""Ascending-channel breakout detection on daily bars."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from .config import ChannelConfig
from .indicators import atr as atr_series
from .indicators import linreg_r2
from .pivots import edge_anchors, pivot_highs, pivot_lows
from .trendline import TrendLine, fit_bounding_line

REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


@dataclass
class ChannelResult:
    ok: bool
    reason: str = ""
    score: float = 0.0
    lookback: int = 0
    pivot_window: int = 0

    upper: TrendLine | None = None
    lower: TrendLine | None = None
    window_start: int = 0

    slope_upper_pct: float = 0.0
    slope_lower_pct: float = 0.0
    parallel_ratio: float = 0.0
    width_start: float = 0.0
    width_end: float = 0.0
    containment: float = 0.0
    trend_r2: float = 0.0

    status: str = ""
    break_index: int = -1
    break_date: Any = None
    break_close: float = 0.0
    break_level: float = 0.0
    break_excess: float = 0.0
    volume_ratio: float = 0.0
    bars_since_break: int = 0
    extension: float = 0.0
    last_close: float = 0.0
    last_date: Any = None

    upper_now: float = 0.0
    lower_now: float = 0.0
    rank: float = 0.0
    diagnostics: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        return {
            "score": round(self.score, 1),
            "status": self.status,
            "break_date": self.break_date,
            "bars_since_break": self.bars_since_break,
            "break_excess_pct": round(self.break_excess * 100, 2),
            "volume_ratio": round(self.volume_ratio, 2),
            "extension_pct": round(self.extension * 100, 2),
            "channel_width_pct": round(self.width_end * 100, 1),
            "slope_upper_pct_per_day": round(self.slope_upper_pct * 100, 3),
            "slope_lower_pct_per_day": round(self.slope_lower_pct * 100, 3),
            "parallel_ratio": round(self.parallel_ratio, 2),
            "containment": round(self.containment, 3),
            "trend_r2": round(self.trend_r2, 2),
            "touches_upper": self.upper.touches if self.upper else 0,
            "touches_lower": self.lower.touches if self.lower else 0,
            "lookback": self.lookback,
            "last_close": round(self.last_close, 4),
            "upper_now": round(self.upper_now, 4),
            "lower_now": round(self.lower_now, 4),
        }


def detect(frame, cfg: ChannelConfig | None = None, lookbacks: Sequence[int] | None = None) -> ChannelResult:
    """Scan a (lookback x pivot_window) grid and return the strongest setup."""
    cfg = cfg or ChannelConfig()
    arrays = _to_arrays(frame)
    n = arrays["close"].size

    windows = sorted({int(w) for w in (lookbacks or [cfg.lookback]) if int(w) >= 40}, reverse=True)
    if not windows:
        windows = [cfg.lookback]

    pivot_windows = []
    for pw in (cfg.pivot_window, cfg.pivot_window + 1, cfg.pivot_window - 1):
        if pw >= 2 and pw not in pivot_windows:
            pivot_windows.append(pw)

    best: ChannelResult | None = None
    fallback: ChannelResult | None = None
    for lb in windows:
        if n < lb:
            fallback = fallback or ChannelResult(False, reason="insufficient_history")
            continue
        for pw in pivot_windows:
            res = _detect_once(arrays, cfg, lookback=lb, pivot_window=pw)
            if res.ok:
                if best is None or res.score > best.score:
                    best = res
            elif fallback is None or _reason_rank(res.reason) > _reason_rank(fallback.reason):
                fallback = res
    return best or fallback or ChannelResult(False, reason="no_channel")


_REASON_ORDER = [
    "insufficient_history",
    "no_pivots",
    "no_upper_line",
    "no_lower_line",
    "lines_cross",
    "slope_not_rising",
    "slope_too_steep",
    "not_parallel",
    "width_unstable",
    "width_out_of_range",
    "low_containment",
    "no_breakout",
    "stale_breakout",
    "overextended",
    "fell_back_inside",
    "weak_volume",
    "low_score",
]


def _reason_rank(reason: str) -> int:
    return _REASON_ORDER.index(reason) if reason in _REASON_ORDER else -1


def _to_arrays(frame) -> dict:
    if isinstance(frame, dict):
        data = {k: np.asarray(v, dtype=float) for k, v in frame.items() if k != "index"}
        data = {k.lower(): v for k, v in data.items()}
        data["index"] = frame.get("index")
        return data
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    out = {c.lower(): frame[c].to_numpy(dtype=float) for c in REQUIRED_COLUMNS}
    out["index"] = frame.index
    return out


def _detect_once(arrays: dict, cfg: ChannelConfig, lookback: int, pivot_window: int) -> ChannelResult:
    close_all = arrays["close"]
    n = close_all.size
    start = n - lookback
    high = arrays["high"][start:]
    low = arrays["low"][start:]
    close = arrays["close"][start:]
    volume = arrays["volume"][start:]
    w = close.size
    last_x = w - 1

    res = ChannelResult(False, lookback=lookback, pivot_window=pivot_window, window_start=start)
    index = arrays.get("index")
    res.last_close = float(close[-1])
    res.last_date = _label(index, n - 1)

    ph = np.union1d(pivot_highs(high, pivot_window), edge_anchors(high, pivot_window, high=True))
    pl = np.union1d(pivot_lows(low, pivot_window), edge_anchors(low, pivot_window, high=False))
    if ph.size < 2 or pl.size < 2:
        res.reason = "no_pivots"
        return res

    upper = fit_bounding_line(
        high, ph, upper=True,
        min_span=cfg.min_line_span, max_anchor_gap=cfg.max_anchor_gap,
        touch_tolerance=cfg.touch_tolerance, violation_tolerance=cfg.violation_tolerance,
        min_touches=cfg.min_pivots_per_line,
    )
    if upper is None:
        res.reason = "no_upper_line"
        return res
    lower = fit_bounding_line(
        low, pl, upper=False,
        min_span=cfg.min_line_span, max_anchor_gap=cfg.max_anchor_gap,
        touch_tolerance=cfg.touch_tolerance, violation_tolerance=cfg.violation_tolerance,
        min_touches=cfg.min_pivots_per_line,
    )
    if lower is None:
        res.reason = "no_lower_line"
        return res

    res.upper, res.lower = upper, lower

    xs = np.arange(w, dtype=float)
    u_line = upper.value(xs)
    l_line = lower.value(xs)
    if np.any(u_line <= l_line) or np.any(l_line <= 0):
        res.reason = "lines_cross"
        return res

    mid = (u_line + l_line) / 2.0
    res.slope_upper_pct = float(upper.slope / mid[w // 2])
    res.slope_lower_pct = float(lower.slope / mid[w // 2])
    if res.slope_upper_pct < cfg.min_slope_pct or res.slope_lower_pct < cfg.min_slope_pct:
        res.reason = "slope_not_rising"
        return res
    if max(res.slope_upper_pct, res.slope_lower_pct) > cfg.max_slope_pct:
        res.reason = "slope_too_steep"
        return res

    res.parallel_ratio = float(
        min(res.slope_upper_pct, res.slope_lower_pct) / max(res.slope_upper_pct, res.slope_lower_pct)
    )
    if res.parallel_ratio < cfg.parallel_tolerance:
        res.reason = "not_parallel"
        return res

    width = (u_line - l_line) / mid
    res.width_start = float(width[0])
    res.width_end = float(width[-1])
    lo_ratio, hi_ratio = cfg.width_ratio_range
    if not (lo_ratio <= res.width_end / res.width_start <= hi_ratio):
        res.reason = "width_unstable"
        return res
    if not (cfg.min_channel_width <= res.width_end <= cfg.max_channel_width):
        res.reason = "width_out_of_range"
        return res

    res.upper_now = float(u_line[-1])
    res.lower_now = float(l_line[-1])

    # channel quality is judged on the bars before the potential breakout,
    # so the same region is measured whether or not a breakout is found
    pre_end = max(1, w - cfg.breakout_window)
    pre = slice(0, pre_end)
    inside = (close[pre] <= u_line[pre] * (1.0 + cfg.violation_tolerance)) & (
        close[pre] >= l_line[pre] * (1.0 - cfg.violation_tolerance)
    )
    res.containment = float(inside.mean())
    res.trend_r2 = linreg_r2(close[pre])
    if res.containment < cfg.min_containment:
        res.reason = "low_containment"
        return res

    atr = atr_series(arrays["high"], arrays["low"], arrays["close"], cfg.atr_window)[start:]
    thresholds = np.maximum(cfg.min_break_pct, cfg.break_atr_mult * atr / u_line)
    above = close > u_line * (1.0 + thresholds)

    scan_from = max(0, w - cfg.breakout_window)
    candidates = np.nonzero(above[scan_from:])[0] + scan_from
    if candidates.size == 0:
        res.reason = "no_breakout"
        return res
    b = int(candidates[0])

    fresh_lo = max(0, b - cfg.fresh_window)
    if np.any(above[fresh_lo:b]):
        res.reason = "stale_breakout"
        return res

    res.break_index = start + b
    res.break_date = _label(index, start + b)
    res.break_close = float(close[b])
    res.break_level = float(u_line[b])
    res.break_excess = float((close[b] - u_line[b]) / u_line[b])
    res.bars_since_break = int(last_x - b)

    vol_lo = max(0, b - cfg.volume_window)
    base_vol = float(volume[vol_lo:b].mean()) if b > vol_lo else 0.0
    res.volume_ratio = float(volume[b] / base_vol) if base_vol > 0 else 0.0
    if cfg.require_volume and res.volume_ratio < cfg.min_volume_ratio:
        res.reason = "weak_volume"
        return res

    res.extension = float((close[-1] - u_line[-1]) / u_line[-1])
    if res.extension > cfg.max_extension:
        res.reason = "overextended"
        return res

    if res.extension >= 0:
        res.status = "breakout"
    elif cfg.allow_pullback and res.extension >= -cfg.pullback_tolerance:
        res.status = "retest"
    else:
        res.reason = "fell_back_inside"
        return res

    res.score = _score(res, cfg)
    res.rank = res.score
    res.diagnostics = {
        "pivot_highs": ph.tolist(),
        "pivot_lows": pl.tolist(),
        "upper_anchors": list(upper.anchors),
        "lower_anchors": list(lower.anchors),
    }
    if res.score < cfg.min_score:
        res.reason = "low_score"
        return res

    res.ok = True
    res.reason = "ok"
    return res


def _score(res: ChannelResult, cfg: ChannelConfig) -> float:
    upper_touch = min(res.upper.touches, 4) / 4.0 * 15.0
    lower_touch = min(res.lower.touches, 4) / 4.0 * 10.0
    span = 1.0 - cfg.min_containment
    containment = (res.containment - cfg.min_containment) / span * 10.0 if span > 0 else 10.0
    parallel = res.parallel_ratio * 10.0
    trend = res.trend_r2 * 5.0

    excess = min(res.break_excess / 0.05, 1.0) * 20.0
    volume = min(max(res.volume_ratio - 1.0, 0.0) / 1.0, 1.0) * 15.0
    recency = (1.0 - res.bars_since_break / max(cfg.breakout_window, 1)) * 5.0
    room = (1.0 - min(max(res.extension, 0.0) / max(cfg.max_extension, 1e-9), 1.0)) * 10.0

    total = upper_touch + lower_touch + containment + parallel + trend + excess + volume + recency + room
    return float(max(0.0, min(100.0, total)))


def _label(index, i: int):
    if index is None:
        return i
    try:
        value = index[i]
    except Exception:
        return i
    date = getattr(value, "date", None)
    return date().isoformat() if callable(date) else str(value)
