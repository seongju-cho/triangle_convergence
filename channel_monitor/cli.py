"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from . import report as reporting
from .channel import detect
from .config import ChannelConfig, ScreenConfig
from .data import LoaderConfig, PriceLoader
from .markets import DEFAULT_MARKETS, MARKETS, get_market
from .notify import AlertState, format_alert, post_webhook
from .screener import ScanReport, explain_symbol, scan_market
from .universe import load_universe

DEFAULT_LOOKBACKS = (90, 120, 150)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="channel-monitor",
        description="Monitor NASDAQ / KOSPI daily charts for ascending-channel breakouts.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan universes once and print matches")
    _add_common(scan)
    scan.add_argument("--csv", help="write matches to this CSV path")
    scan.add_argument("--json", dest="json_path", help="write matches to this JSON path")
    scan.add_argument("--plot-dir", help="render a chart per match into this directory")
    scan.add_argument("--top", type=int, default=40, help="rows to print (default 40)")

    watch = sub.add_parser("watch", help="scan repeatedly and alert on new breakouts")
    _add_common(watch)
    watch.add_argument("--interval", type=float, default=60.0, help="minutes between scans")
    watch.add_argument("--webhook", help="Slack/Discord-compatible webhook URL for alerts")
    watch.add_argument("--state-file", default=".cache/alerts.json")
    watch.add_argument("--plot-dir", help="render a chart per new match into this directory")
    watch.add_argument("--once", action="store_true", help="run a single cycle and exit")

    explain = sub.add_parser("explain", help="show the detector's reasoning for one ticker")
    _add_common(explain)
    explain.add_argument("ticker", help="e.g. TXG or 005930")
    explain.add_argument("--market", default="nasdaq", choices=sorted(MARKETS))
    explain.add_argument("--plot", help="write a chart to this path")

    uni = sub.add_parser("universe", help="print a market universe")
    uni.add_argument("market", choices=sorted(MARKETS))
    uni.add_argument("--limit", type=int)
    uni.add_argument("--offline", action="store_true")

    selftest = sub.add_parser("selftest", help="run the detector against synthetic patterns")
    selftest.add_argument("--plot-dir", help="render the synthetic charts into this directory")
    return p


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--markets",
        default=",".join(DEFAULT_MARKETS),
        help=f"comma-separated markets (default: {','.join(DEFAULT_MARKETS)})",
    )
    p.add_argument("--symbols", help="comma-separated tickers instead of the full universe")
    p.add_argument("--universe-file", help="file with one ticker per line")
    p.add_argument("--limit", type=int, help="cap the number of tickers per market")
    p.add_argument("--offline-universe", action="store_true", help="skip listing downloads")

    p.add_argument("--lookbacks", default=",".join(str(x) for x in DEFAULT_LOOKBACKS))
    p.add_argument("--min-score", type=float, default=ChannelConfig.min_score)
    p.add_argument("--breakout-window", type=int, default=ChannelConfig.breakout_window)
    p.add_argument("--min-break-pct", type=float, default=ChannelConfig.min_break_pct)
    p.add_argument("--min-volume-ratio", type=float, default=ChannelConfig.min_volume_ratio)
    p.add_argument("--require-volume", action="store_true", help="reject breakouts without a volume surge")
    p.add_argument("--min-slope-pct", type=float, default=ChannelConfig.min_slope_pct)
    p.add_argument("--parallel-tolerance", type=float, default=ChannelConfig.parallel_tolerance)
    p.add_argument("--min-containment", type=float, default=ChannelConfig.min_containment)
    p.add_argument("--max-extension", type=float, default=ChannelConfig.max_extension)
    p.add_argument("--touch-tolerance", type=float, default=ChannelConfig.touch_tolerance)

    p.add_argument("--min-price", type=float, help="override the market's price floor")
    p.add_argument("--min-avg-volume", type=float, help="override the market's volume floor")
    p.add_argument("--min-avg-turnover", type=float, help="override the market's turnover floor")

    p.add_argument("--cache-dir", default=".cache/prices")
    p.add_argument("--cache-ttl", type=float, default=12.0, help="hours before cached bars go stale")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--csv-dir", help="read OHLCV from local CSV files instead of downloading")
    p.add_argument("--history-days", type=int, default=400)
    p.add_argument("--chunk-size", type=int, default=80)


def channel_config(args) -> ChannelConfig:
    return ChannelConfig().replace(
        min_score=args.min_score,
        breakout_window=args.breakout_window,
        min_break_pct=args.min_break_pct,
        min_volume_ratio=args.min_volume_ratio,
        require_volume=args.require_volume,
        min_slope_pct=args.min_slope_pct,
        parallel_tolerance=args.parallel_tolerance,
        min_containment=args.min_containment,
        max_extension=args.max_extension,
        touch_tolerance=args.touch_tolerance,
    )


def screen_overrides(args, base: ScreenConfig) -> ScreenConfig:
    kwargs = {"history_days": args.history_days}
    if args.min_price is not None:
        kwargs["min_price"] = args.min_price
    if args.min_avg_volume is not None:
        kwargs["min_avg_volume"] = args.min_avg_volume
    if args.min_avg_turnover is not None:
        kwargs["min_avg_turnover"] = args.min_avg_turnover
    return base.replace(**kwargs)


def make_loader(args) -> PriceLoader:
    cfg = LoaderConfig(
        cache_dir=Path(args.cache_dir),
        ttl_hours=args.cache_ttl,
        period_days=args.history_days,
        chunk_size=args.chunk_size,
        use_cache=not args.no_cache,
    )
    return PriceLoader(cfg, csv_dir=args.csv_dir)


def parse_lookbacks(text: str) -> list[int]:
    values = [int(x) for x in str(text).replace(" ", "").split(",") if x]
    return values or list(DEFAULT_LOOKBACKS)


def _progress(label: str, done: int, total: int) -> None:
    if done % 50 == 0 or done == total:
        print(f"\r  {done}/{total} {label:<24}", end="", file=sys.stderr, flush=True)


def run_scan(args) -> ScanReport:
    loader = make_loader(args)
    cfg = channel_config(args)
    lookbacks = parse_lookbacks(args.lookbacks)
    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None

    merged = ScanReport()
    for key in [m.strip() for m in args.markets.split(",") if m.strip()]:
        market = get_market(key)
        print(f"[{market.label}] scanning...", file=sys.stderr)
        part = scan_market(
            market.key,
            loader=loader,
            channel_cfg=cfg,
            screen_cfg=screen_overrides(args, market.screen),
            lookbacks=lookbacks,
            symbols=symbols,
            universe_file=args.universe_file,
            limit=args.limit,
            offline_universe=args.offline_universe,
            progress=_progress,
        )
        print(f"\r[{market.label}] {reporting.format_summary(part)}", file=sys.stderr)
        merged.hits.extend(part.hits)
        merged.scanned += part.scanned
        merged.skipped.update(part.skipped)
        merged.rejected.update(part.rejected)
    merged.hits.sort(key=lambda h: h.result.score, reverse=True)
    return merged


def render_plots(args, hits, loader) -> None:
    if not getattr(args, "plot_dir", None) or not hits:
        return
    from .plotting import plot_channel

    out = Path(args.plot_dir)
    for hit in hits:
        df = loader.load(hit.symbol)
        if df is None:
            continue
        path = out / f"{hit.market}_{hit.code}_{hit.result.break_date}.png"
        try:
            plot_channel(df, hit.result, path, title=f"{hit.market.upper()} {hit.code}")
            print(f"  chart: {path}", file=sys.stderr)
        except Exception as exc:
            print(f"  chart failed for {hit.code}: {exc}", file=sys.stderr)


def cmd_scan(args) -> int:
    report = run_scan(args)
    print(reporting.format_table(report.hits, top=args.top))
    if args.csv:
        print(f"csv: {reporting.write_csv(report, args.csv)}", file=sys.stderr)
    if args.json_path:
        print(f"json: {reporting.write_json(report, args.json_path)}", file=sys.stderr)
    render_plots(args, report.hits[: args.top], make_loader(args))
    return 0


def cmd_watch(args) -> int:
    state = AlertState(args.state_file)
    while True:
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        report = run_scan(args)
        fresh = state.new_hits(report.hits)
        print(f"\n=== {started} | hits {len(report.hits)} | new {len(fresh)} ===")
        print(reporting.format_table(fresh or report.hits, top=40))
        if fresh:
            text = format_alert(fresh)
            if args.webhook:
                post_webhook(args.webhook, text)
            render_plots(args, fresh, make_loader(args))
            state.mark(fresh)
        if args.once:
            return 0
        time.sleep(max(1.0, args.interval) * 60)


def cmd_explain(args) -> int:
    loader = make_loader(args)
    df, result = explain_symbol(
        args.market,
        args.ticker,
        loader=loader,
        channel_cfg=channel_config(args),
        lookbacks=parse_lookbacks(args.lookbacks),
    )
    print(reporting.format_explain(f"{args.market}:{args.ticker}", result))
    if args.plot and df is not None and result.upper is not None:
        from .plotting import plot_channel

        print(f"chart: {plot_channel(df, result, args.plot, title=f'{args.market.upper()} {args.ticker}')}")
    return 0 if result.ok else 1


def cmd_universe(args) -> int:
    for code in load_universe(args.market, limit=args.limit, offline=args.offline):
        print(code)
    return 0


def cmd_selftest(args) -> int:
    from . import synthetic

    cases = {
        "ascending_channel_breakout": (synthetic.ascending_channel(), True),
        "ascending_channel_intact": (synthetic.ascending_channel(breakout_bars=0), False),
        "sideways_range": (synthetic.sideways_range(), False),
        "descending_channel": (synthetic.descending_channel(), False),
        "random_walk": (synthetic.random_walk(), False),
    }
    cfg = ChannelConfig()
    failures = 0
    for name, (df, expected) in cases.items():
        result = detect(df, cfg, lookbacks=DEFAULT_LOOKBACKS)
        ok = result.ok == expected
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: ok={result.ok} reason={result.reason} score={result.score:.1f}")
        if args.plot_dir and result.upper is not None:
            from .plotting import plot_channel

            plot_channel(df, result, Path(args.plot_dir) / f"{name}.png", title=name)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    handlers = {
        "scan": cmd_scan,
        "watch": cmd_watch,
        "explain": cmd_explain,
        "universe": cmd_universe,
        "selftest": cmd_selftest,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
