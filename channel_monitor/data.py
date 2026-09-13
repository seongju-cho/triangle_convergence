"""Daily OHLCV loading with an on-disk cache."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

log = logging.getLogger(__name__)

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


@dataclass
class LoaderConfig:
    cache_dir: Path = Path(".cache/prices")
    ttl_hours: float = 12.0
    period_days: int = 400
    chunk_size: int = 80
    retries: int = 4
    sleep_between_chunks: float = 0.4
    use_cache: bool = True


class PriceLoader:
    """Fetches daily bars from Yahoo Finance, or reads them from a local directory."""

    def __init__(self, cfg: LoaderConfig | None = None, csv_dir: str | Path | None = None):
        self.cfg = cfg or LoaderConfig()
        self.csv_dir = Path(csv_dir) if csv_dir else None
        self.cfg.cache_dir = Path(self.cfg.cache_dir)
        if self.csv_dir is None and self.cfg.use_cache:
            self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ public

    def load_many(self, symbols: Sequence[str]) -> dict[str, pd.DataFrame]:
        symbols = [s for s in dict.fromkeys(symbols) if s]
        if self.csv_dir is not None:
            return {s: df for s in symbols if (df := self._read_local(s)) is not None}

        out: dict[str, pd.DataFrame] = {}
        pending: list[str] = []
        for symbol in symbols:
            cached = self._read_cache(symbol)
            if cached is not None:
                out[symbol] = cached
            else:
                pending.append(symbol)

        for chunk in _chunks(pending, self.cfg.chunk_size):
            fetched = self._download(chunk)
            for symbol, df in fetched.items():
                self._write_cache(symbol, df)
                out[symbol] = df
            if self.cfg.sleep_between_chunks:
                time.sleep(self.cfg.sleep_between_chunks)
        return out

    def load(self, symbol: str) -> pd.DataFrame | None:
        return self.load_many([symbol]).get(symbol)

    # ----------------------------------------------------------------- private

    def _cache_path(self, symbol: str) -> Path:
        safe = symbol.replace("/", "_").replace("\\", "_")
        return self.cfg.cache_dir / f"{safe}.csv"

    def _read_cache(self, symbol: str) -> pd.DataFrame | None:
        if not self.cfg.use_cache:
            return None
        path = self._cache_path(symbol)
        if not path.exists():
            return None
        if (time.time() - path.stat().st_mtime) > self.cfg.ttl_hours * 3600:
            return None
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
        except Exception:
            return None
        return _normalize(df)

    def _write_cache(self, symbol: str, df: pd.DataFrame) -> None:
        if not self.cfg.use_cache or df is None or df.empty:
            return
        try:
            df.to_csv(self._cache_path(symbol))
        except Exception as exc:
            log.debug("cache write failed for %s: %s", symbol, exc)

    def _read_local(self, symbol: str) -> pd.DataFrame | None:
        for name in (f"{symbol}.csv", f"{symbol.replace('.', '_')}.csv", f"{symbol.upper()}.csv"):
            path = self.csv_dir / name
            if path.exists():
                try:
                    return _normalize(pd.read_csv(path, index_col=0, parse_dates=True))
                except Exception as exc:
                    log.warning("failed to read %s: %s", path, exc)
                    return None
        return None

    def _download(self, symbols: Sequence[str]) -> dict[str, pd.DataFrame]:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("yfinance is required for downloads: pip install yfinance") from exc

        period = f"{max(self.cfg.period_days, 60)}d"
        pending = list(symbols)
        out: dict[str, pd.DataFrame] = {}

        # yfinance swallows per-symbol failures and returns an empty frame, so an
        # empty result is retried (network trouble) while a partial one is not
        # (the missing symbols are most likely delisted or misspelled).
        for attempt in range(max(1, self.cfg.retries)):
            try:
                raw = yf.download(
                    pending,
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
                got = _split_frames(raw, pending)
            except Exception as exc:
                got = {}
                log.warning("download failed (attempt %d/%d): %s", attempt + 1, self.cfg.retries, exc)

            out.update(got)
            if got:
                break
            if attempt + 1 < max(1, self.cfg.retries):
                time.sleep(2.0 * (2 ** attempt))

        missing = [s for s in pending if s not in out]
        if missing:
            log.warning("no data for %d/%d symbols (e.g. %s)", len(missing), len(pending), missing[:5])
        return out


def _split_frames(raw: pd.DataFrame, symbols: Sequence[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        for symbol in symbols:
            if symbol in level0:
                frame = raw[symbol]
            elif symbol in set(raw.columns.get_level_values(-1)):
                frame = raw.xs(symbol, axis=1, level=-1)
            else:
                continue
            df = _normalize(frame)
            if df is not None and not df.empty:
                out[symbol] = df
    else:
        df = _normalize(raw)
        if df is not None and not df.empty and len(symbols) == 1:
            out[symbols[0]] = df
    return out


def _normalize(frame: pd.DataFrame) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    df = frame.copy()
    df.columns = [str(c).strip().title() for c in df.columns]
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df["Close"] = df["Adj Close"]
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        return None
    df = df[COLUMNS].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0.0)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), max(1, size)):
        yield items[i:i + size]
