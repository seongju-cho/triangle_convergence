import numpy as np

from channel_monitor.pivots import edge_anchors, pivot_highs, pivot_lows


def test_pivot_highs_finds_local_peaks():
    values = np.array([1, 2, 3, 9, 3, 2, 1, 2, 8, 2, 1], dtype=float)
    assert pivot_highs(values, window=3).tolist() == [3]
    assert pivot_highs(values, window=2).tolist() == [3, 8]


def test_pivot_lows_finds_local_troughs():
    values = np.array([9, 8, 7, 1, 7, 8, 9, 8, 2, 8, 9], dtype=float)
    assert pivot_lows(values, window=2).tolist() == [3, 8]


def test_pivots_need_enough_bars():
    assert pivot_highs(np.arange(5, dtype=float), window=3).size == 0


def test_flat_series_has_no_pivots():
    assert pivot_highs(np.ones(30), window=3).size == 0
    assert pivot_lows(np.ones(30), window=3).size == 0


def test_edge_anchors_pick_window_extremes():
    values = np.array([5, 9, 4, 3, 2, 1, 7, 8, 6], dtype=float)
    assert edge_anchors(values, 3, high=True).tolist() == [1, 7]
    assert edge_anchors(values, 3, high=False).tolist() == [2, 8]
