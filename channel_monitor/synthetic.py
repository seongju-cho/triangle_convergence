"""Synthetic OHLCV generators used by tests and examples.

These are fabricated price paths for validating the detector, not market data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ascending_channel(
    n: int = 130,
    base: float = 100.0,
    slope_pct: float = 0.0015,
    width_pct: float = 0.12,
    period: int = 30,
    noise: float = 0.004,
    breakout_bars: int = 3,
    breakout_strength: float = 0.05,
    breakout_volume: float = 2.5,
    pullback_pct: float | None = None,
    start: str = "2025-12-01",
    seed: int = 7,
) -> pd.DataFrame:
    """Rising parallel channel with pivot touches, optionally broken at the end.

    `pullback_pct` drags the final close back below resistance to model a retest.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)
    slope = base * slope_pct
    lower = base + slope * t
    width = base * width_pct
    upper = lower + width

    pos = (1.0 - np.cos(2.0 * np.pi * t / period)) / 2.0
    pos = np.clip(pos + rng.normal(0.0, noise * 5, n), 0.02, 0.98)

    close = lower + pos * width
    high = lower + np.minimum(pos + 0.04, 1.0) * width
    low = lower + np.maximum(pos - 0.04, 0.0) * width
    volume = rng.normal(1_000_000, 120_000, n).clip(200_000)

    if breakout_bars > 0:
        for k in range(breakout_bars):
            i = n - breakout_bars + k
            step = breakout_strength * (k + 1) / breakout_bars
            close[i] = upper[i] * (1.0 + step)
            high[i] = close[i] * 1.01
            low[i] = min(low[i], upper[i] * 0.995)
            volume[i] *= breakout_volume

    if pullback_pct is not None and breakout_bars > 0:
        close[-1] = upper[-1] * (1.0 - pullback_pct)
        high[-1] = max(high[-1], close[-1] * 1.005)
        low[-1] = min(low[-1], close[-1] * 0.99)

    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum.reduce([high, close, open_])
    low = np.minimum.reduce([low, close, open_])

    index = pd.bdate_range(start=start, periods=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


def sideways_range(n: int = 130, base: float = 100.0, width_pct: float = 0.1, seed: int = 3) -> pd.DataFrame:
    return ascending_channel(
        n=n, base=base, slope_pct=0.0, width_pct=width_pct, breakout_bars=0, seed=seed
    )


def random_walk(n: int = 200, base: float = 100.0, vol: float = 0.02, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, vol, n)
    close = base * np.exp(np.cumsum(steps))
    open_ = np.concatenate(([close[0]], close[:-1]))
    spread = close * vol
    high = np.maximum(close, open_) + spread * rng.random(n)
    low = np.minimum(close, open_) - spread * rng.random(n)
    volume = rng.normal(800_000, 100_000, n).clip(100_000)
    index = pd.bdate_range(start="2025-01-02", periods=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


def descending_channel(n: int = 130, base: float = 100.0, seed: int = 5) -> pd.DataFrame:
    df = ascending_channel(n=n, base=base, slope_pct=0.0015, breakout_bars=0, seed=seed)
    flipped = df.copy()
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    pivot = float(df["Close"].to_numpy()[0] * 2)
    flipped["Open"] = pivot - df["Open"]
    flipped["Close"] = pivot - df["Close"]
    flipped["High"] = pivot - low
    flipped["Low"] = pivot - high
    return flipped
