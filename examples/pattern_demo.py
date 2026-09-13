"""Walk through the detector on a synthetic ascending-channel breakout.

The price path here is generated, not market data. It reproduces the *shape*
that the screener looks for: about six months of daily bars rising inside a
parallel channel, resistance touched three or four times, then a close above
the upper line on expanding volume.

Run:
    python examples/pattern_demo.py --out-dir charts
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from channel_monitor import synthetic
from channel_monitor.channel import detect
from channel_monitor.config import ChannelConfig
from channel_monitor.report import format_explain

LOOKBACKS = (90, 120, 150)

CASES = {
    # ~6 months of bars, the window length the 10x Genomics example spans
    "breakout": dict(n=130, start="2025-12-01", slope_pct=0.0015, width_pct=0.12, breakout_bars=3),
    "intact_channel": dict(n=130, start="2025-12-01", slope_pct=0.0015, width_pct=0.12, breakout_bars=0),
    "retest_after_breakout": dict(n=130, start="2025-12-01", breakout_bars=3, pullback_pct=0.005),
    "quiet_breakout": dict(n=130, start="2025-12-01", breakout_bars=3, breakout_volume=0.9),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="charts")
    args = ap.parse_args()

    cfg = ChannelConfig()
    out = Path(args.out_dir)
    for name, kwargs in CASES.items():
        df = synthetic.ascending_channel(**kwargs)
        result = detect(df, cfg, lookbacks=LOOKBACKS)
        print(f"\n=== {name} ===")
        print(format_explain(name, result))
        if result.upper is None:
            continue
        try:
            from channel_monitor.plotting import plot_channel

            print(f"  chart: {plot_channel(df, result, out / f'{name}.png', title=name)}")
        except ImportError:
            print("  (install matplotlib to render charts)")

    print(
        "\nTo run the same detector on the real 10x Genomics chart:\n"
        "  python -m channel_monitor explain TXG --market nasdaq --plot charts/TXG.png"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
