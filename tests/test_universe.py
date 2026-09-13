from channel_monitor.universe import RESOURCES, _parse_nasdaq_listing, load_universe, read_symbol_file

LISTING = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
TXG|10x Genomics, Inc. - Class A Common Stock|G|N|N|100|N|N
AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
ZZZT|NASDAQ TEST STOCK|G|Y|N|100|N|N
QQQ|Invesco QQQ Trust|G|N|N|100|Y|N
ABCDW|Some Warrant|S|N|N|100|N|N
FOO.A|Class A unit|S|N|N|100|N|N
File Creation Time: 09/12/2026
"""


def test_parse_nasdaq_listing_filters_non_common_shares():
    symbols = _parse_nasdaq_listing(LISTING)
    assert symbols == ["TXG", "AAPL"]


def test_parse_nasdaq_listing_handles_garbage():
    assert _parse_nasdaq_listing("") == []
    assert _parse_nasdaq_listing("no|header|here\n") == []


def test_read_symbol_file_strips_comments(tmp_path):
    path = tmp_path / "u.txt"
    path.write_text("aapl\n# note\n\nmsft,extra\nAAPL\n", encoding="utf-8")
    assert read_symbol_file(path) == ["AAPL", "MSFT"]


def test_bundled_fallbacks_are_usable():
    assert "TXG" in read_symbol_file(RESOURCES / "nasdaq_fallback.txt")
    assert "005930" in read_symbol_file(RESOURCES / "kospi_major.txt")


def test_load_universe_offline_uses_fallbacks(tmp_path):
    nasdaq = load_universe("nasdaq", cache_dir=tmp_path, offline=True, limit=5)
    assert len(nasdaq) == 5
    assert load_universe("kospi", cache_dir=tmp_path, offline=True)
