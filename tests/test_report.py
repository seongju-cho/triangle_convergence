import json

from channel_monitor import synthetic
from channel_monitor.channel import detect
from channel_monitor.config import ChannelConfig
from channel_monitor.data import PriceLoader
from channel_monitor.report import (
    format_explain,
    format_summary,
    format_table,
    write_csv,
    write_json,
)
from channel_monitor.screener import scan_market

LOOKBACKS = (90, 120, 150)


def build_report(tmp_path):
    synthetic.ascending_channel(n=200, start="2025-11-03").to_csv(tmp_path / "HIT.csv")
    synthetic.ascending_channel(n=200, start="2025-11-03", breakout_bars=0).to_csv(tmp_path / "MISS.csv")
    loader = PriceLoader(csv_dir=tmp_path)
    return scan_market("nasdaq", loader=loader, symbols=["HIT", "MISS"], lookbacks=LOOKBACKS)


def test_format_table_empty():
    assert format_table([]) == "(no breakouts matched)"


def test_format_table_has_header_and_row(tmp_path):
    report = build_report(tmp_path)
    text = format_table(report.hits)
    assert "MARKET" in text and "HIT" in text
    assert len(text.splitlines()) == 3


def test_format_summary_mentions_counts(tmp_path):
    summary = format_summary(build_report(tmp_path))
    assert "scanned=2" in summary and "hits=1" in summary and "no_breakout" in summary


def test_write_csv_and_json(tmp_path):
    report = build_report(tmp_path)
    csv_path = write_csv(report, tmp_path / "out" / "hits.csv")
    assert csv_path.exists() and "HIT" in csv_path.read_text(encoding="utf-8")

    json_path = write_json(report, tmp_path / "out" / "hits.json")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["scanned"] == 2 and payload["hits"][0]["code"] == "HIT"


def test_format_explain_covers_both_outcomes():
    ok = detect(synthetic.ascending_channel(), ChannelConfig(), lookbacks=LOOKBACKS)
    text = format_explain("SYN", ok)
    assert "breakout:" in text and "upper line" in text

    rejected = detect(synthetic.sideways_range(), ChannelConfig(), lookbacks=LOOKBACKS)
    assert "slope_not_rising" in format_explain("SYN", rejected)
