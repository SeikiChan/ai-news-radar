from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_sources, load_watchlist
from .feeds import fetch_all
from .scoring import score_article
from .storage import append_signals

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

    args = parser.parse_args()
    if args.command == "scan":
        run_scan(args)
    elif args.command == "web":
        from .web import serve

        serve(host=args.host, port=args.port)


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
