from channel_monitor import synthetic
from channel_monitor.data import PriceLoader
from channel_monitor.notify import AlertState, format_alert
from channel_monitor.screener import scan_market


def hits(tmp_path):
    synthetic.ascending_channel(n=200, start="2025-11-03").to_csv(tmp_path / "HIT.csv")
    loader = PriceLoader(csv_dir=tmp_path)
    return scan_market("nasdaq", loader=loader, symbols=["HIT"], lookbacks=(120,)).hits


def test_alert_state_dedupes_across_runs(tmp_path):
    found = hits(tmp_path)
    assert found

    state_path = tmp_path / "state.json"
    state = AlertState(state_path)
    assert state.new_hits(found) == found
    state.mark(found)
    assert state.new_hits(found) == []

    reloaded = AlertState(state_path)
    assert reloaded.new_hits(found) == []


def test_alert_state_without_file_is_in_memory_only(tmp_path):
    found = hits(tmp_path)
    state = AlertState(None)
    state.mark(found)
    assert state.new_hits(found) == []


def test_format_alert_lists_each_hit(tmp_path):
    text = format_alert(hits(tmp_path))
    assert "HIT" in text and "breakout" in text
    assert format_alert([]) == ""
