import numpy as np
import pytest

from channel_monitor.trendline import fit_bounding_line

KWARGS = dict(min_span=10, max_anchor_gap=10, touch_tolerance=0.01, violation_tolerance=0.02)


def test_recovers_exact_upper_line():
    x = np.arange(60, dtype=float)
    series = 100.0 + 0.5 * x
    series[5:55] -= 5.0  # leave only the endpoints on the line
    anchors = np.array([0, 20, 40, 59])
    line = fit_bounding_line(series, anchors, upper=True, **KWARGS)
    assert line is not None
    assert line.slope == pytest.approx(0.5, rel=1e-6)
    assert line.at(30) == pytest.approx(115.0, rel=1e-6)


def test_rejects_lines_violated_inside_span():
    x = np.arange(40, dtype=float)
    series = 100.0 + 0.1 * x
    series[20] = 200.0  # a spike the candidate line cannot contain
    anchors = np.array([0, 39])
    assert fit_bounding_line(series, anchors, upper=True, **KWARGS) is None


def test_spike_itself_can_anchor_a_valid_line():
    x = np.arange(40, dtype=float)
    series = 100.0 + 0.1 * x
    series[20] = 200.0
    anchors = np.array([0, 10, 20, 30, 39])
    line = fit_bounding_line(series, anchors, upper=True, **KWARGS)
    assert line is not None
    assert np.all(series[line.anchors[0]:line.anchors[1] + 1] <= line.value(
        np.arange(line.anchors[0], line.anchors[1] + 1)) * 1.02)


def test_lower_line_sits_below_series():
    x = np.arange(50, dtype=float)
    series = 100.0 + 0.4 * x
    series[5:45] += 6.0
    anchors = np.array([0, 15, 30, 49])
    line = fit_bounding_line(series, anchors, upper=False, **KWARGS)
    assert line is not None
    assert np.all(series >= line.value(x) * 0.99)


def test_requires_min_span_and_recent_anchor():
    series = np.linspace(100, 110, 60)
    anchors = np.array([0, 5])
    assert fit_bounding_line(series, anchors, upper=True, **KWARGS) is None


def test_counts_touches():
    x = np.arange(60, dtype=float)
    series = 100.0 + 0.2 * x
    series[1:59] -= 4.0
    for i in (0, 20, 40, 59):
        series[i] = 100.0 + 0.2 * i
    line = fit_bounding_line(series, np.array([0, 20, 40, 59]), upper=True, **KWARGS)
    assert line is not None and line.touches == 4
