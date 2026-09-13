"""Trendline fitting: pick the pivot pair that best bounds a price series."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TrendLine:
    slope: float
    intercept: float
    anchors: tuple[int, int]
    touches: int
    span: int
    mean_gap: float
    score: float

    def value(self, x):
        return self.slope * np.asarray(x, dtype=float) + self.intercept

    def at(self, x: int) -> float:
        return float(self.slope * x + self.intercept)


def fit_bounding_line(
    series: np.ndarray,
    anchor_idx: np.ndarray,
    *,
    upper: bool,
    min_span: int,
    max_anchor_gap: int,
    touch_tolerance: float,
    violation_tolerance: float,
    min_touches: int = 2,
) -> TrendLine | None:
    """Best straight line that keeps `series` on one side of it.

    Anchored on two pivots; validated only inside the anchor span, then
    extrapolated forward by the caller to test a breakout.
    """
    series = np.asarray(series, dtype=float)
    n = series.size
    anchors = np.asarray(anchor_idx, dtype=int)
    if n == 0 or anchors.size < 2:
        return None

    sign = 1.0 if upper else -1.0
    best: TrendLine | None = None

    for a in range(anchors.size - 1):
        i = int(anchors[a])
        for b in range(anchors.size - 1, a, -1):
            j = int(anchors[b])
            span = j - i
            if span < min_span:
                break
            if n - 1 - j > max_anchor_gap:
                continue

            slope = (series[j] - series[i]) / span
            intercept = series[i] - slope * i

            xs = np.arange(i, j + 1, dtype=float)
            line = slope * xs + intercept
            if np.any(line <= 0):
                continue
            excess = sign * (series[i:j + 1] - line) / line
            if float(excess.max()) > violation_tolerance:
                continue

            inside = anchors[(anchors >= i) & (anchors <= j)]
            line_at = slope * inside + intercept
            gaps = np.abs(series[inside] - line_at) / line_at
            touches = int((gaps <= touch_tolerance).sum())
            if touches < min_touches:
                continue

            mean_gap = float(gaps.mean())
            score = 2.0 * touches + 1.5 * (span / n) - 2.0 * mean_gap
            if best is None or score > best.score:
                best = TrendLine(
                    slope=float(slope),
                    intercept=float(intercept),
                    anchors=(i, j),
                    touches=touches,
                    span=int(span),
                    mean_gap=mean_gap,
                    score=float(score),
                )
    return best
