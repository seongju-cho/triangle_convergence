"""Optional chart rendering for detected setups (requires matplotlib)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .channel import ChannelResult


def plot_channel(
    df,
    result: ChannelResult,
    path: str | Path,
    title: str = "",
    context: int = 20,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if result.upper is None or result.lower is None:
        raise ValueError("result has no channel to plot")

    w_start = result.window_start
    plot_start = max(0, w_start - context)
    view = df.iloc[plot_start:]
    x = np.arange(len(view))
    # window-local coordinates the trendlines were fitted in
    xl = x + (plot_start - w_start)

    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(13, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )

    o = view["Open"].to_numpy()
    h = view["High"].to_numpy()
    l = view["Low"].to_numpy()
    c = view["Close"].to_numpy()
    up = c >= o
    ax.vlines(x, l, h, color="#555555", linewidth=0.8)
    ax.vlines(x[up], o[up], c[up], color="#1a7f37", linewidth=3.0)
    ax.vlines(x[~up], o[~up], c[~up], color="#cf222e", linewidth=3.0)

    ax.plot(x, result.upper.value(xl), color="#0969da", linewidth=1.6, label="resistance")
    ax.plot(x, result.lower.value(xl), color="#8250df", linewidth=1.6, label="support")

    for p in result.diagnostics.get("pivot_highs", []):
        i = p + w_start - plot_start
        if 0 <= i < len(x):
            ax.plot(i, h[i], marker="v", color="#0969da", markersize=5)
    for p in result.diagnostics.get("pivot_lows", []):
        i = p + w_start - plot_start
        if 0 <= i < len(x):
            ax.plot(i, l[i], marker="^", color="#8250df", markersize=5)

    if result.break_index >= 0:
        bi = result.break_index - plot_start
        if 0 <= bi < len(x):
            ax.axvline(bi, color="#bf8700", linestyle="--", linewidth=1.2)
            ax.annotate(
                f"breakout {result.break_excess * 100:.1f}%",
                xy=(bi, c[bi]),
                xytext=(6, 12),
                textcoords="offset points",
                fontsize=9,
                color="#bf8700",
            )

    vol = view["Volume"].to_numpy()
    axv.bar(x, vol, color=np.where(up, "#1a7f37", "#cf222e"), width=0.8, alpha=0.6)
    axv.set_ylabel("volume")

    labels = [str(d.date()) if hasattr(d, "date") else str(d) for d in view.index]
    step = max(1, len(labels) // 10)
    axv.set_xticks(x[::step])
    axv.set_xticklabels(labels[::step], rotation=45, ha="right", fontsize=8)

    head = title or "ascending channel breakout"
    ax.set_title(
        f"{head} | score {result.score:.0f} | lookback {result.lookback}"
        f" | slope {result.slope_upper_pct * 100:.2f}%/day | vol x{result.volume_ratio:.1f}"
    )
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.2)
    axv.grid(alpha=0.2)
    fig.tight_layout()

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
