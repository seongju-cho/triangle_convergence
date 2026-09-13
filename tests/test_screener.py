import pandas as pd

from channel_monitor import synthetic
from channel_monitor.config import ScreenConfig
from channel_monitor.data import PriceLoader
from channel_monitor.screener import explain_symbol, scan_market, scan_markets

LOOKBACKS = (90, 120, 150)


def make_dir(tmp_path):
    synthetic.ascending_channel(n=200, start="2025-11-03").to_csv(tmp_path / "HIT.csv")
    synthetic.ascending_channel(n=200, start="2025-11-03", breakout_bars=0).to_csv(tmp_path / "MISS.csv")
    synthetic.ascending_channel(n=60, start="2026-06-01").to_csv(tmp_path / "SHORT.csv")
    return PriceLoader(csv_dir=tmp_path)


def test_scan_finds_the_breakout(tmp_path):
    loader = make_dir(tmp_path)
    report = scan_market(
        "nasdaq", loader=loader, symbols=["HIT", "MISS", "SHORT"], lookbacks=LOOKBACKS
    )
    assert report.scanned == 3
    assert [h.code for h in report.hits] == ["HIT"]
    assert report.skipped["short_history"] == 1
    assert report.rejected["no_breakout"] == 1
    assert not report.to_frame().empty


def test_liquidity_filters_skip_everything(tmp_path):
    loader = make_dir(tmp_path)
    report = scan_market(
        "nasdaq",
        loader=loader,
        symbols=["HIT"],
        screen_cfg=ScreenConfig(min_price=1e9),
        lookbacks=LOOKBACKS,
    )
    assert not report.hits and report.skipped["price_filter"] == 1

    report = scan_market(
        "nasdaq",
        loader=loader,
        symbols=["HIT"],
        screen_cfg=ScreenConfig(min_avg_turnover=1e15),
        lookbacks=LOOKBACKS,
    )
    assert not report.hits and report.skipped["turnover_filter"] == 1


def test_missing_data_is_counted(tmp_path):
    report = scan_market("nasdaq", loader=make_dir(tmp_path), symbols=["NOPE"], lookbacks=LOOKBACKS)
    assert report.skipped["no_data"] == 1


def test_universe_file_is_honoured(tmp_path):
    loader = make_dir(tmp_path)
    listing = tmp_path / "list.txt"
    listing.write_text("HIT\n# comment\nMISS\n", encoding="utf-8")
    report = scan_market("nasdaq", loader=loader, universe_file=str(listing), lookbacks=LOOKBACKS)
    assert report.scanned == 2


def test_scan_markets_merges_and_sorts(tmp_path):
    loader = make_dir(tmp_path)
    synthetic.ascending_channel(n=200, start="2025-11-03", base=52000).to_csv(tmp_path / "005930_KS.csv")
    report = scan_markets(
        ["nasdaq", "kospi"], loader=loader, symbols=["HIT", "005930"], lookbacks=LOOKBACKS
    )
    scores = [h.result.score for h in report.hits]
    assert scores == sorted(scores, reverse=True)
    assert {h.market for h in report.hits} == {"nasdaq", "kospi"}


def test_explain_symbol(tmp_path):
    loader = make_dir(tmp_path)
    df, result = explain_symbol("nasdaq", "HIT", loader=loader, lookbacks=LOOKBACKS)
    assert isinstance(df, pd.DataFrame) and result.ok

    df, result = explain_symbol("nasdaq", "NOPE", loader=loader, lookbacks=LOOKBACKS)
    assert df is None and result.reason == "no_data"
