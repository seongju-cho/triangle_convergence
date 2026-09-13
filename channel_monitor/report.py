"""Console and file output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from .channel import ChannelResult
from .screener import Hit, ScanReport

TABLE_COLUMNS = [
    ("market", "MARKET", 7, "<"),
    ("code", "CODE", 8, "<"),
    ("score", "SCORE", 6, ">"),
    ("status", "STATUS", 9, "<"),
    ("break_date", "BREAK", 11, "<"),
    ("bars_since_break", "AGE", 4, ">"),
    ("break_excess_pct", "EXC%", 6, ">"),
    ("volume_ratio", "VOL x", 6, ">"),
    ("extension_pct", "EXT%", 6, ">"),
    ("channel_width_pct", "WIDTH%", 7, ">"),
    ("slope_upper_pct_per_day", "SLOPE%", 7, ">"),
    ("parallel_ratio", "PAR", 5, ">"),
    ("containment", "CONT", 6, ">"),
    ("touches_upper", "TU", 3, ">"),
    ("touches_lower", "TL", 3, ">"),
    ("lookback", "LB", 4, ">"),
    ("last_close", "CLOSE", 11, ">"),
    ("upper_now", "UPPER", 11, ">"),
]


def format_table(hits: Sequence[Hit], top: int | None = None) -> str:
    rows = [h.as_row() for h in (hits[:top] if top else hits)]
    if not rows:
        return "(no breakouts matched)"

    header = " ".join(f"{title:{align}{width}}" for _, title, width, align in TABLE_COLUMNS)
    lines = [header, "-" * len(header)]
    for row in rows:
        cells = []
        for key, _, width, align in TABLE_COLUMNS:
            value = row.get(key, "")
            text = f"{value:.2f}" if isinstance(value, float) else str(value)
            if len(text) > width:
                text = text[:width]
            cells.append(f"{text:{align}{width}}")
        lines.append(" ".join(cells))
    return "\n".join(lines)


def format_summary(report: ScanReport) -> str:
    parts = [f"scanned={report.scanned}", f"hits={len(report.hits)}"]
    if report.skipped:
        parts.append("skipped=" + ",".join(f"{k}:{v}" for k, v in report.skipped.most_common()))
    if report.rejected:
        top = ",".join(f"{k}:{v}" for k, v in report.rejected.most_common(8))
        parts.append(f"rejected={top}")
    return " | ".join(parts)


def format_explain(symbol: str, result: ChannelResult) -> str:
    lines = [f"{symbol}: ok={result.ok} reason={result.reason} score={result.score:.1f}"]
    if result.upper is None or result.lower is None:
        return "\n".join(lines)

    lines += [
        f"  lookback={result.lookback} pivot_window={result.pivot_window}",
        f"  upper line: slope={result.slope_upper_pct * 100:.3f}%/day touches={result.upper.touches}"
        f" anchors={result.upper.anchors} span={result.upper.span}",
        f"  lower line: slope={result.slope_lower_pct * 100:.3f}%/day touches={result.lower.touches}"
        f" anchors={result.lower.anchors} span={result.lower.span}",
        f"  parallel_ratio={result.parallel_ratio:.2f} width {result.width_start * 100:.1f}%"
        f" -> {result.width_end * 100:.1f}% containment={result.containment:.2f} r2={result.trend_r2:.2f}",
    ]
    if result.break_index >= 0:
        lines += [
            f"  breakout: {result.break_date} close={result.break_close:.4f} level={result.break_level:.4f}"
            f" excess={result.break_excess * 100:.2f}% volume_x={result.volume_ratio:.2f}"
            f" age={result.bars_since_break}",
            f"  now: close={result.last_close:.4f} upper={result.upper_now:.4f}"
            f" lower={result.lower_now:.4f} extension={result.extension * 100:.2f}%"
            f" status={result.status or '-'}",
        ]
    return "\n".join(lines)


def write_csv(report: ScanReport, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = report.to_frame()
    if frame.empty:
        path.write_text("", encoding="utf-8")
    else:
        frame.to_csv(path, index=False)
    return path


def write_json(report: ScanReport, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scanned": report.scanned,
        "skipped": dict(report.skipped),
        "rejected": dict(report.rejected),
        "hits": [h.as_row() for h in report.hits],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
