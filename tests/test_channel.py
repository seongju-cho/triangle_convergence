import numpy as np
import pandas as pd
import pytest

from channel_monitor import synthetic
from channel_monitor.channel import detect
from channel_monitor.config import ChannelConfig

LOOKBACKS = (90, 120, 150)


def run(df, **overrides):
    cfg = ChannelConfig().replace(**overrides) if overrides else ChannelConfig()
    return detect(df, cfg, lookbacks=LOOKBACKS)


def test_detects_ascending_channel_breakout():
    result = run(synthetic.ascending_channel())
    assert result.ok and result.reason == "ok"
    assert result.status == "breakout"
    assert result.score >= ChannelConfig.min_score
    assert result.slope_upper_pct > 0 and result.slope_lower_pct > 0
    assert result.upper.touches >= 2 and result.lower.touches >= 2
    assert result.break_excess > 0
    assert result.bars_since_break < ChannelConfig.breakout_window


def test_breakout_level_matches_resistance_line():
    result = run(synthetic.ascending_channel())
    assert result.break_close > result.break_level
    assert result.upper_now > result.lower_now


@pytest.mark.parametrize(
    "frame, reason",
    [
        (synthetic.ascending_channel(breakout_bars=0), "no_breakout"),
        (synthetic.sideways_range(), "slope_not_rising"),
        (synthetic.descending_channel(), "slope_not_rising"),
    ],
)
def test_rejects_non_breakout_patterns(frame, reason):
    result = run(frame)
    assert not result.ok
    assert result.reason == reason


def test_rejects_random_walk():
    assert not run(synthetic.random_walk()).ok


def test_stale_breakout_is_not_a_fresh_signal():
    result = run(synthetic.ascending_channel(breakout_bars=12, breakout_strength=0.06))
    assert not result.ok
    assert result.reason in ("stale_breakout", "overextended")


def test_overextended_breakout_is_rejected():
    result = run(synthetic.ascending_channel(breakout_strength=0.60), max_extension=0.20)
    assert not result.ok
    assert result.reason == "overextended"


def test_volume_gate_is_optional():
    quiet = synthetic.ascending_channel(breakout_volume=0.9)
    assert run(quiet).ok
    gated = run(quiet, require_volume=True, min_volume_ratio=1.5)
    assert not gated.ok and gated.reason == "weak_volume"


def test_retest_keeps_the_signal_when_pullback_allowed():
    frame = synthetic.ascending_channel(breakout_bars=3, pullback_pct=0.005)
    result = run(frame)
    assert result.ok and result.status == "retest"
    assert result.extension < 0

    strict = run(frame, allow_pullback=False)
    assert not strict.ok and strict.reason == "fell_back_inside"


def test_min_score_filters_marginal_setups():
    result = run(synthetic.ascending_channel(), min_score=99.5)
    assert not result.ok and result.reason == "low_score"


def test_insufficient_history():
    frame = synthetic.ascending_channel(n=50)
    result = detect(frame, ChannelConfig(), lookbacks=LOOKBACKS)
    assert not result.ok and result.reason == "insufficient_history"


def test_missing_columns_raise():
    frame = pd.DataFrame({"Close": np.arange(200.0)})
    with pytest.raises(ValueError):
        detect(frame, ChannelConfig())


def test_as_row_is_serializable():
    row = run(synthetic.ascending_channel()).as_row()
    assert row["status"] == "breakout"
    assert set(["score", "break_date", "volume_ratio", "channel_width_pct"]) <= set(row)
