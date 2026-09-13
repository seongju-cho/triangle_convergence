"""Daily ascending-channel breakout monitor for NASDAQ and KOSPI."""

from .channel import ChannelResult, detect
from .config import ChannelConfig, ScreenConfig
from .data import LoaderConfig, PriceLoader
from .markets import MARKETS, get_market
from .screener import Hit, ScanReport, explain_symbol, scan_market, scan_markets

__version__ = "0.1.0"

__all__ = [
    "ChannelConfig",
    "ChannelResult",
    "Hit",
    "LoaderConfig",
    "MARKETS",
    "PriceLoader",
    "ScanReport",
    "ScreenConfig",
    "detect",
    "explain_symbol",
    "get_market",
    "scan_market",
    "scan_markets",
    "__version__",
]
