"""Ticker universes for the supported markets."""

from __future__ import annotations

import logging
import time
from pathlib import Path
log = logging.getLogger(__name__)

RESOURCES = Path(__file__).parent / "resources"
NASDAQ_LISTING_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
CACHE_TTL_HOURS = 24.0


def load_universe(
    market: str,
    *,
    cache_dir: str | Path = ".cache/universe",
    limit: int | None = None,
    offline: bool = False,
) -> list[str]:
    market = market.lower()
    if market == "nasdaq":
        codes = _nasdaq(Path(cache_dir), offline=offline)
    elif market in ("kospi", "kosdaq"):
        codes = _krx(market, offline=offline)
    else:
        raise KeyError(f"no universe provider for market '{market}'")
    return codes[:limit] if limit else codes


def read_symbol_file(path: str | Path) -> list[str]:
    out: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].split(",")[0].strip()
        if token:
            out.append(token.upper())
    return list(dict.fromkeys(out))


def _nasdaq(cache_dir: Path, offline: bool) -> list[str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / "nasdaqlisted.txt"
    text: str | None = None

    if cached.exists() and (time.time() - cached.stat().st_mtime) < CACHE_TTL_HOURS * 3600:
        text = cached.read_text(encoding="utf-8", errors="replace")
    elif not offline:
        try:
            import requests

            resp = requests.get(NASDAQ_LISTING_URL, timeout=30)
            resp.raise_for_status()
            text = resp.text
            cached.write_text(text, encoding="utf-8")
        except Exception as exc:
            log.warning("NASDAQ listing download failed (%s); using cache or fallback", exc)
            if cached.exists():
                text = cached.read_text(encoding="utf-8", errors="replace")

    if not text:
        log.warning("using bundled NASDAQ fallback list")
        return read_symbol_file(RESOURCES / "nasdaq_fallback.txt")
    return _parse_nasdaq_listing(text)


def _parse_nasdaq_listing(text: str) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split("|")]
    try:
        i_sym = header.index("Symbol")
        i_test = header.index("Test Issue")
        i_etf = header.index("ETF")
    except ValueError:
        return []

    out: list[str] = []
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) <= max(i_sym, i_test, i_etf):
            continue
        symbol = parts[i_sym].strip().upper()
        if not symbol or parts[i_test].strip() == "Y" or parts[i_etf].strip() == "Y":
            continue
        # skip warrants, units, preferreds and other non-common share classes
        if any(ch in symbol for ch in ("$", ".", "^")) or (len(symbol) == 5 and symbol.endswith(("W", "R", "U"))):
            continue
        out.append(symbol)
    return list(dict.fromkeys(out))


def _krx(market: str, offline: bool) -> list[str]:
    if not offline:
        try:
            from pykrx import stock

            today = time.strftime("%Y%m%d")
            codes = stock.get_market_ticker_list(today, market=market.upper())
            if not codes:  # non-trading day: pykrx returns an empty list
                codes = stock.get_market_ticker_list(market=market.upper())
            if codes:
                return [str(c).zfill(6) for c in codes]
        except ImportError:
            log.warning("pykrx not installed; using bundled %s fallback list", market)
        except Exception as exc:
            log.warning("pykrx lookup failed (%s); using bundled %s fallback list", exc, market)

    if market == "kospi":
        return read_symbol_file(RESOURCES / "kospi_major.txt")
    log.warning("no bundled fallback list for %s", market)
    return []
