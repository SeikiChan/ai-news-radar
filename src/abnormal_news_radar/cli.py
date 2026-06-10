from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_sources, load_watchlist
from .feeds import fetch_all
from .net import configure_logging
from .performance import build_performance_report
from .scoring import score_article
from .storage import append_signals, load_candidate_rows, load_signal_rows

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-news-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Fetch feeds and score news items.")
    scan.add_argument("--limit", type=int, default=30, help="Maximum scored signals to print.")
    scan.add_argument("--limit-per-source", type=int, default=50, help="Maximum articles to read from each source.")
    scan.add_argument("--min-score", type=float, default=10, help="Minimum adjusted score to print.")
    scan.add_argument("--sources", default=str(PROJECT_ROOT / "config" / "sources.json"))
    scan.add_argument("--watchlist", default=str(PROJECT_ROOT / "config" / "watchlist.json"))
    scan.add_argument("--output", default=str(PROJECT_ROOT / "data" / "signals.jsonl"))

    web = subparsers.add_parser("web", help="Start the local web terminal.")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)

    report = subparsers.add_parser(
        "report",
        help="Backtest stored signals against forward returns to validate the score model.",
    )
    report.add_argument("--signals", default=str(PROJECT_ROOT / "data" / "signals.jsonl"))
    report.add_argument("--candidates", default=str(PROJECT_ROOT / "data" / "candidates.jsonl"))
    report.add_argument("--limit", type=int, default=500, help="Max stored rows to evaluate per file.")
    report.add_argument("--json", action="store_true", help="Print the raw report as JSON.")

    diagnose = subparsers.add_parser(
        "diagnose",
        help="Diagnose one ticker for mispricing (错杀): attribution, positioning, gamma, evidence.",
    )
    diagnose.add_argument("ticker", help="Ticker symbol, e.g. CRDO")
    diagnose.add_argument("--json", action="store_true", help="Print the raw diagnosis as JSON.")

    daily = subparsers.add_parser(
        "daily",
        help="Render a one-page institutional morning report (Markdown) from the latest brief.",
    )
    daily.add_argument("--output", default="", help="Write the report to this file instead of stdout.")
    daily.add_argument("--top", type=int, default=5, help="Number of TOP CALLS to include.")
    daily.add_argument(
        "--export-dir",
        default="",
        help="Write latest-daily-report.md + dated archive + JSON companion into this dir "
        "(for a Claude Desktop scheduled task / Windows Task Scheduler).",
    )
    daily.add_argument(
        "--scan",
        action="store_true",
        help="Run a fresh scan before rendering, so a standalone daily cron works without the web server.",
    )

    args = parser.parse_args()
    configure_logging()
    if args.command == "scan":
        run_scan(args)
    elif args.command == "web":
        from .web import serve

        serve(host=args.host, port=args.port)
    elif args.command == "report":
        run_report(args)
    elif args.command == "daily":
        run_daily(args)
    elif args.command == "diagnose":
        run_diagnose(args)


def run_diagnose(args: argparse.Namespace) -> None:
    from .diagnose import diagnose_ticker

    result = diagnose_ticker(args.ticker)
    if args.json:
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    _print_diagnosis(result)


def _print_diagnosis(result: dict[str, object]) -> None:
    status = str(result.get("status") or "")
    if status != "ok":
        print(result.get("summary_zh") or f"诊断失败：{result.get('reason')}")
        return
    print(f"\n{result.get('summary_zh')}\n")
    print("评分构成:")
    for component in result.get("score_components", []) or []:
        print(f"  {component['name']:<6} {component['points']:>3}/{component['max']:<3} {component['reason_zh']}")
    print("\n触发条件（出现后才升级为可行动）:")
    for trigger in result.get("triggers_zh", []) or []:
        print(f"  - {trigger}")
    components = result.get("components") if isinstance(result.get("components"), dict) else {}
    for key in ("relative_strength", "positioning", "options_structure", "vix"):
        section = components.get(key) if isinstance(components.get(key), dict) else {}
        summary = section.get("summary_zh")
        if summary:
            print(f"\n[{key}] {summary}")
    news = components.get("radar_news") if isinstance(components.get("radar_news"), dict) else {}
    recent = news.get("recent") or []
    if recent:
        print(f"\n[radar_news] 近{news.get('lookback_days')}天命中 {news.get('total_hits')} 条（硬证据 {news.get('hard_evidence_hits')} 条）:")
        for hit in recent[:5]:
            print(f"  - [{hit.get('evidence_tier') or 'signal'}] {hit.get('title')}")
    gaps = result.get("data_gaps") or []
    if gaps:
        print(f"\n缺失数据: {', '.join(str(g) for g in gaps)}")
    print(f"\n方法说明: {result.get('method_zh')}")


def run_daily(args: argparse.Namespace) -> None:
    from .daily_report import export_daily_report, render_daily_report
    from .web import (
        DEFAULT_LIMIT_PER_SOURCE,
        DEFAULT_MIN_SCORE,
        DEFAULT_SIGNAL_LIMIT,
        _brief_payload,
    )
    from .web import run_scan as web_run_scan

    if args.scan:
        web_run_scan(
            limit=DEFAULT_SIGNAL_LIMIT,
            min_score=DEFAULT_MIN_SCORE,
            limit_per_source=DEFAULT_LIMIT_PER_SOURCE,
        )

    brief = _brief_payload().get("brief", {})
    if args.export_dir:
        paths = export_daily_report(brief, args.export_dir, top_n=args.top)
        print(f"Daily report exported:\n  {paths['markdown']}\n  {paths['dated']}\n  {paths['json']}")
        return

    markdown = render_daily_report(brief, top_n=args.top)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        print(f"Daily report written to {path}")
    else:
        print(markdown)


def run_report(args: argparse.Namespace) -> None:
    rows = load_signal_rows(Path(args.signals), limit=args.limit)
    rows += load_candidate_rows(Path(args.candidates), limit=args.limit)
    if not rows:
        print("No stored signals or candidates to evaluate. Run a scan first.")
        return

    print(f"Evaluating {len(rows)} stored rows against forward returns (this fetches prices)...")
    report = build_performance_report(rows)

    if args.json:
        import json

        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    _print_report(report)


def _print_report(report: dict[str, object]) -> None:
    horizons = report.get("horizons", [])
    print(
        f"\nSignal performance vs {report.get('benchmark')} "
        f"({report.get('total_outcomes', 0)} unique ticker/day outcomes)\n"
    )
    header = f"{'band':<7}{'total':>7}" + "".join(f"{f'+{h}d n/hit/exc':>22}" for h in horizons)
    print(header)
    print("-" * len(header))
    by_band = report.get("by_band", {}) if isinstance(report.get("by_band"), dict) else {}
    for band in ("hard", "watch", "weak", "ignore"):
        stats = by_band.get(band)
        if not isinstance(stats, dict):
            continue
        cells = ""
        for horizon in horizons:
            cell = stats.get("horizons", {}).get(str(horizon), {})
            n = cell.get("matured_n", 0)
            hit = cell.get("hit_rate")
            exc = cell.get("mean_excess_pct")
            hit_str = f"{hit:.0%}" if isinstance(hit, (int, float)) else "n/a"
            exc_str = f"{exc:+.2f}%" if isinstance(exc, (int, float)) else "n/a"
            cells += f"{f'{n}/{hit_str}/{exc_str}':>22}"
        print(f"{band:<7}{stats.get('total_n', 0):>7}{cells}")

    print("\nCalibration (does a higher band earn higher excess return?):")
    calibration = report.get("calibration", {}) if isinstance(report.get("calibration"), dict) else {}
    for horizon in horizons:
        cell = calibration.get(str(horizon), {})
        mono = cell.get("monotonic_rank")
        spread = cell.get("hard_minus_weak_excess_pct")
        if not cell.get("sufficient_sample"):
            mono_str = "insufficient"
        else:
            mono_str = {True: "yes", False: "NO", None: "n/a"}[mono if mono in (True, False) else None]
        spread_str = f"{spread:+.2f}%" if isinstance(spread, (int, float)) else "n/a"
        print(f"  +{horizon}d: hard>=watch>=weak? {mono_str:<12} | hard-minus-weak excess = {spread_str}")
    print(
        "\nNote: only matured horizons are counted. Recent signals need more "
        "trading days to elapse before they appear in the longer horizons."
    )


def run_scan(args: argparse.Namespace) -> None:
    sources = load_sources(Path(args.sources))
    watchlist = load_watchlist(Path(args.watchlist))
    articles, errors = fetch_all(sources, limit_per_source=args.limit_per_source)

    signals = []
    for article in articles:
        signal = score_article(article, watchlist)
        if signal is not None and signal.score >= args.min_score:
            signals.append(signal)

    signals.sort(key=lambda item: item.score, reverse=True)
    selected = signals[: args.limit]
    saved_count = append_signals(Path(args.output), selected)

    print(f"Fetched articles: {len(articles)}")
    print(f"Scored signals:   {len(signals)}")
    print(f"Saved signals:    {saved_count} new / {len(selected)} selected -> {args.output}")
    if errors:
        print("\nSource errors:")
        for error in errors:
            print(f"  - {error}")

    if not selected:
        print("\nNo signals met the threshold.")
        return

    print("\nTop signals:")
    for index, signal in enumerate(selected, start=1):
        tickers = ", ".join(signal.tickers) if signal.tickers else "unmatched"
        terms = ", ".join(signal.matched_terms[:6])
        title = _truncate(signal.article.title, 120)
        print(f"\n{index}. [{signal.band}] score={signal.score} raw={signal.raw_score} tickers={tickers}")
        print(f"   {title}")
        print(f"   source={signal.article.source} published={signal.article.published or 'n/a'}")
        if terms:
            print(f"   terms={terms}")
        if signal.article.link:
            print(f"   link={signal.article.link}")


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."
