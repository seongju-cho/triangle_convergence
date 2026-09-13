"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

from . import report as reporting
from .channel import detect
from .config import ChannelConfig, ScreenConfig
from .data import LoaderConfig, PriceLoader
from .mailer import send_email, send_message
from .markets import DEFAULT_MARKETS, MARKETS, get_market
from .notify import AlertState, format_alert, post_webhook
from .screener import ScanReport, explain_symbol, scan_market
from .settings import DailySettings, load_settings, write_example_config
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

    daily = sub.add_parser("daily", help="one scheduled run: scan, then email new breakouts")
    daily.add_argument("--config", help="settings JSON (default: monitor.config.json if present)")
    daily.add_argument("--dry-run", action="store_true", help="render the report but send no email")
    daily.add_argument("--no-email", action="store_true", help="skip email delivery for this run")

    init = sub.add_parser("init-config", help="write a starter settings file")
    init.add_argument("path", nargs="?", default="monitor.config.json")

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
    p.add_argument("--limit", type=int, help="take the first N tickers of the listing (alphabetical)")
    p.add_argument("--sample", type=int, help="take a random N tickers instead of the alphabetical head")
    p.add_argument("--sample-seed", type=int, default=0)
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
            sample=args.sample,
            sample_seed=args.sample_seed,
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


def _render_charts(hits, loader, out_dir: Path) -> list[Path]:
    try:
        from .plotting import plot_channel
    except ImportError:
        print("matplotlib not installed; skipping charts", file=sys.stderr)
        return []

    written: list[Path] = []
    for hit in hits:
        df = loader.load(hit.symbol)
        if df is None:
            continue
        path = out_dir / f"{hit.market}_{hit.code}_{hit.result.break_date}.png"
        try:
            plot_channel(df, hit.result, path, title=f"{hit.market.upper()} {hit.code}")
            print(f"  chart: {path}", file=sys.stderr)
            written.append(path)
        except Exception as exc:
            print(f"  chart failed for {hit.code}: {exc}", file=sys.stderr)
    return written


def render_plots(args, hits, loader) -> None:
    if getattr(args, "plot_dir", None) and hits:
        _render_charts(hits, loader, Path(args.plot_dir))


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


def _resolve_settings(args) -> DailySettings:
    if args.config:
        return load_settings(args.config)
    default = Path("monitor.config.json")
    if default.exists():
        return load_settings(default)
    print(
        "no monitor.config.json found; running with defaults and no email\n"
        "  create one with: python -m channel_monitor init-config",
        file=sys.stderr,
    )
    settings = DailySettings()
    settings.email.enabled = False
    return settings


def _attach_file_log(path: str) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(target, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(min(root.level or logging.INFO, logging.INFO))


def _scan_with_settings(settings: DailySettings, loader: PriceLoader, cfg: ChannelConfig) -> ScanReport:
    merged = ScanReport()
    for key in settings.markets:
        market = get_market(key)
        part = scan_market(
            market.key,
            loader=loader,
            channel_cfg=cfg,
            screen_cfg=market.screen.replace(history_days=settings.history_days),
            lookbacks=settings.lookbacks,
            symbols=settings.symbols or None,
            universe_file=settings.universe_file or None,
            limit=settings.limit,
            sample=settings.sample,
            offline_universe=settings.offline_universe,
        )
        logging.getLogger(__name__).info("[%s] %s", market.label, reporting.format_summary(part))
        print(f"[{market.label}] {reporting.format_summary(part)}", file=sys.stderr)
        merged.hits.extend(part.hits)
        merged.scanned += part.scanned
        merged.skipped.update(part.skipped)
        merged.rejected.update(part.rejected)
    merged.hits.sort(key=lambda h: h.result.score, reverse=True)
    return merged


def cmd_daily(args, transport=None) -> int:
    settings = _resolve_settings(args)
    _attach_file_log(settings.log_file)
    log = logging.getLogger(__name__)

    loader = PriceLoader(
        LoaderConfig(
            cache_dir=Path(settings.cache_dir),
            ttl_hours=settings.cache_ttl,
            period_days=settings.history_days,
            chunk_size=settings.chunk_size,
        ),
        csv_dir=settings.csv_dir or None,
    )
    cfg = ChannelConfig().replace(
        min_score=settings.min_score,
        require_volume=settings.require_volume,
        min_volume_ratio=settings.min_volume_ratio,
        breakout_window=settings.breakout_window,
    )

    report = _scan_with_settings(settings, loader, cfg)
    state = AlertState(settings.state_file)
    fresh = state.new_hits(report.hits)

    stamp = date.today().isoformat()
    out_dir = Path(settings.out_dir)
    csv_path = reporting.write_csv(report, out_dir / f"hits-{stamp}.csv")

    charts: list[Path] = []
    if settings.plot and fresh:
        charts = _render_charts(fresh[: settings.email.max_charts], loader, out_dir / "charts")

    title = f"{stamp} · {len(fresh)} new breakout(s) · {', '.join(settings.markets)}"
    html = reporting.format_html(report, fresh, title=title)
    html_path = out_dir / f"report-{stamp}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")

    print(reporting.format_table(fresh or report.hits, top=40))
    print(f"report: {html_path}", file=sys.stderr)
    log.info("scan complete: %s | new=%d", reporting.format_summary(report), len(fresh))

    email = settings.email
    should_email = (
        email.enabled
        and not args.no_email
        and not args.dry_run
        and (fresh or email.send_when_empty)
    )
    if should_email:
        attachments = []
        if email.attach_csv and csv_path.exists() and csv_path.stat().st_size:
            attachments.append(csv_path)
        if email.attach_charts:
            attachments.extend(charts)
        subject = f"{email.subject_prefix} {title}" if email.subject_prefix else title
        sent = send_email(
            email.smtp(), subject, html, attachments=attachments, transport=transport or send_message
        )
        if not sent:
            print("email delivery failed; see the log for details", file=sys.stderr)
            return 2
        print(f"email sent to {', '.join(email.recipients)}", file=sys.stderr)
    elif args.dry_run:
        print("dry run: no email sent", file=sys.stderr)

    if fresh and not args.dry_run:
        state.mark(fresh)
    return 0


def cmd_init_config(args) -> int:
    path = write_example_config(args.path)
    print(f"wrote {path}")
    print("next: set the SMTP password in the environment, e.g.")
    print("  Windows  setx CHANNEL_MONITOR_SMTP_PASSWORD \"your-app-password\"")
    print("  macOS    export CHANNEL_MONITOR_SMTP_PASSWORD='your-app-password'")
    return 0


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
        "daily": cmd_daily,
        "init-config": cmd_init_config,
        "universe": cmd_universe,
        "selftest": cmd_selftest,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
