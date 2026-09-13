"""Small indicator helpers used by the detector."""

from __future__ import annotations

import numpy as np


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    prev_close = np.concatenate(([close[0]], close[:-1]))
    return np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> np.ndarray:
    tr = true_range(high, low, close)
    out = np.full(tr.size, np.nan)
    if tr.size == 0:
        return out
    window = max(1, min(window, tr.size))
    out[window - 1] = tr[:window].mean()
    for i in range(window, tr.size):
        out[i] = (out[i - 1] * (window - 1) + tr[i]) / window
    out[:window - 1] = out[window - 1]
    return out


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    out = np.full(values.size, np.nan)
    if values.size == 0:
        return out
    csum = np.concatenate(([0.0], np.cumsum(values)))
    for i in range(values.size):
        start = max(0, i - window + 1)
        out[i] = (csum[i + 1] - csum[start]) / (i + 1 - start)
    return out


def linreg_r2(y: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    if y.size < 3:
        return 0.0
    x = np.arange(y.size, dtype=float)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    if ss_tot <= 0:
        return 0.0
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    return float(max(0.0, 1.0 - (resid ** 2).sum() / ss_tot))
