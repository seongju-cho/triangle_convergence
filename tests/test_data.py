import numpy as np
import pandas as pd
import pytest

from channel_monitor.data import LoaderConfig, PriceLoader, _normalize, _split_frames
from channel_monitor import synthetic


def test_normalize_promotes_adj_close_and_sorts():
    index = pd.to_datetime(["2026-01-05", "2026-01-02", "2026-01-02"])
    raw = pd.DataFrame(
        {
            "open": [1.0, 2.0, 2.5],
            "high": [2.0, 3.0, 3.5],
            "low": [0.5, 1.0, 1.5],
            "adj close": [1.5, 2.5, 3.0],
            "volume": [10, 20, 30],
        },
        index=index,
    )
    df = _normalize(raw)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index.is_monotonic_increasing
    assert len(df) == 2
    assert df["Close"].iloc[-1] == 1.5


def test_normalize_rejects_incomplete_frames():
    assert _normalize(pd.DataFrame()) is None
    assert _normalize(pd.DataFrame({"Close": [1.0]})) is None


def test_normalize_drops_rows_without_prices():
    index = pd.to_datetime(["2026-01-02", "2026-01-05"])
    raw = pd.DataFrame(
        {"Open": [1.0, np.nan], "High": [2.0, np.nan], "Low": [0.5, np.nan],
         "Close": [1.5, np.nan], "Volume": [10, np.nan]},
        index=index,
    )
    assert len(_normalize(raw)) == 1


def _multi_frame(order: str) -> pd.DataFrame:
    index = pd.bdate_range("2026-01-02", periods=3)
    fields = ["Open", "High", "Low", "Close", "Volume"]
    tickers = ["AAA", "BBB"]
    pairs = [(t, f) for t in tickers for f in fields] if order == "ticker" else [
        (f, t) for f in fields for t in tickers
    ]
    columns = pd.MultiIndex.from_tuples(pairs)
    data = np.tile(np.array([1.0, 2.0, 0.5, 1.5, 100.0]), (3, len(tickers)))
    return pd.DataFrame(data, index=index, columns=columns)


@pytest.mark.parametrize("order", ["ticker", "field"])
def test_split_frames_handles_both_column_orders(order):
    out = _split_frames(_multi_frame(order), ["AAA", "BBB"])
    assert set(out) == {"AAA", "BBB"}
    assert list(out["AAA"].columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_split_frames_single_ticker_flat_columns():
    index = pd.bdate_range("2026-01-02", periods=2)
    flat = pd.DataFrame(
        {"Open": [1.0, 1.0], "High": [2.0, 2.0], "Low": [0.5, 0.5],
         "Close": [1.5, 1.5], "Volume": [10.0, 10.0]},
        index=index,
    )
    assert set(_split_frames(flat, ["AAA"])) == {"AAA"}


def test_csv_dir_loader(tmp_path):
    synthetic.ascending_channel(n=160).to_csv(tmp_path / "FAKE.csv")
    loader = PriceLoader(csv_dir=tmp_path)
    df = loader.load("FAKE")
    assert df is not None and len(df) == 160
    assert loader.load("MISSING") is None


def test_csv_dir_loader_accepts_suffixed_symbols(tmp_path):
    synthetic.ascending_channel(n=60).to_csv(tmp_path / "005930_KS.csv")
    assert PriceLoader(csv_dir=tmp_path).load("005930.KS") is not None


def test_cache_roundtrip_and_expiry(tmp_path):
    import os
    import time

    loader = PriceLoader(LoaderConfig(cache_dir=tmp_path, ttl_hours=1.0))
    df = synthetic.ascending_channel(n=80)
    loader._write_cache("FAKE", df)
    assert loader._read_cache("FAKE") is not None

    path = loader._cache_path("FAKE")
    stale = time.time() - 7200
    os.utime(path, (stale, stale))
    assert loader._read_cache("FAKE") is None


class _FakeYF:
    """Stands in for the yfinance module inside PriceLoader._download."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def download(self, symbols, **kwargs):
        self.calls.append(list(symbols))
        return self.responses.pop(0) if self.responses else pd.DataFrame()


def _fake_multi(tickers):
    index = pd.bdate_range("2026-01-02", periods=3)
    fields = ["Open", "High", "Low", "Close", "Volume"]
    columns = pd.MultiIndex.from_tuples([(t, f) for t in tickers for f in fields])
    data = np.tile(np.array([1.0, 2.0, 0.5, 1.5, 100.0]), (3, len(tickers)))
    return pd.DataFrame(data, index=index, columns=columns)


def test_download_retries_when_nothing_comes_back(tmp_path, monkeypatch):
    fake = _FakeYF([pd.DataFrame(), _fake_multi(["AAA", "BBB"])])
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake)
    monkeypatch.setattr("channel_monitor.data.time.sleep", lambda *_: None)

    loader = PriceLoader(LoaderConfig(cache_dir=tmp_path, retries=3))
    out = loader._download(["AAA", "BBB"])
    assert set(out) == {"AAA", "BBB"}
    assert len(fake.calls) == 2


def test_download_does_not_retry_partial_results(tmp_path, monkeypatch):
    fake = _FakeYF([_fake_multi(["AAA"])])
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake)
    monkeypatch.setattr("channel_monitor.data.time.sleep", lambda *_: None)

    loader = PriceLoader(LoaderConfig(cache_dir=tmp_path, retries=3))
    out = loader._download(["AAA", "BBB"])
    assert set(out) == {"AAA"}
    assert len(fake.calls) == 1


def test_download_gives_up_and_caches_nothing(tmp_path, monkeypatch):
    fake = _FakeYF([])
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake)
    monkeypatch.setattr("channel_monitor.data.time.sleep", lambda *_: None)

    loader = PriceLoader(LoaderConfig(cache_dir=tmp_path, retries=2))
    assert loader.load_many(["AAA"]) == {}
    assert not list(tmp_path.glob("*.csv"))
    assert len(fake.calls) == 2
