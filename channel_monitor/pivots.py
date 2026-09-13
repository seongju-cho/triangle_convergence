"""Fractal pivot detection."""

from __future__ import annotations

import numpy as np


def pivot_highs(values: np.ndarray, window: int = 3) -> np.ndarray:
    return _pivots(np.asarray(values, dtype=float), window, high=True)


def pivot_lows(values: np.ndarray, window: int = 3) -> np.ndarray:
    return _pivots(np.asarray(values, dtype=float), window, high=False)


def _pivots(values: np.ndarray, window: int, high: bool) -> np.ndarray:
    n = values.size
    if window < 1 or n < 2 * window + 1:
        return np.empty(0, dtype=int)

    out = []
    for i in range(window, n - window):
        left = values[i - window:i]
        right = values[i + 1:i + window + 1]
        v = values[i]
        if high:
            # strict on the left breaks ties in favour of the earlier bar
            if v > left.max() and v >= right.max():
                out.append(i)
        else:
            if v < left.min() and v <= right.min():
                out.append(i)
    return np.asarray(out, dtype=int)


def edge_anchors(values: np.ndarray, window: int, high: bool) -> np.ndarray:
    """Extra anchor candidates at the window edges, where a fractal cannot form."""
    n = np.asarray(values).size
    if n == 0:
        return np.empty(0, dtype=int)
    head = np.asarray(values[:window]) if window else np.empty(0)
    tail_start = max(n - window, 0)
    tail = np.asarray(values[tail_start:])
    out = []
    if head.size:
        out.append(int(np.argmax(head) if high else np.argmin(head)))
    if tail.size:
        out.append(int(tail_start + (np.argmax(tail) if high else np.argmin(tail))))
    return np.asarray(sorted(set(out)), dtype=int)
