from __future__ import annotations

import argparse
import json
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analyst import (
    DEFAULT_LIMIT_PER_SOURCE,
    DEFAULT_MIN_SCORE,
    DEFAULT_SIGNAL_LIMIT,
    build_daily_brief,
    next_automated_run,
)
from .config import load_market_sources, load_sources, load_watchlist
from .discovery import discover_candidate
from .earnings_analysis import enrich_candidates_with_earnings_analysis
from .earnings_calendar import collect_earnings_calendar
from .expectations import enrich_candidates_with_expectation_check
from .feeds import fetch_sources
from .financials import enrich_candidates_with_financial_snapshots
from .impact import enrich_candidates_with_impact_assessment
from .institutional_flow import enrich_candidates_with_institutional_flow
from .market import collect_market_regime
from .net import configure_logging
from .options_chain import enrich_candidates_with_options_chain_anomalies
from .options_flow import enrich_candidates_with_options_flow
from .pdf_intel import enrich_candidates_with_pdf_intel
from .price_volume import enrich_candidates_with_market_confirmation
from .quality import enrich_candidates_with_quality_screen
from .quick_model import enrich_candidates_with_quick_model
from .readthrough import enrich_candidates_with_readthrough_analysis
from .scoring import score_article
from .serenity_alpha import enrich_candidates_with_serenity_alpha
from .short_interest import enrich_candidates_with_short_interest
from .storage import (
    append_candidates,
    append_signals,
    candidate_row_key,
    load_candidate_rows,
    load_review_state,
    load_signal_rows,
    save_review_state,
)
from .technology_intel import enrich_candidates_with_technology_intel
from .ticker_resolver import enrich_candidates_with_ticker_resolution
from .timeliness import article_timeliness

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "web_static"
LAST_SCAN: dict[str, object] = {
    "articles": [],
    "errors": [],
    "fetched_count": 0,
    "scored_count": 0,
    "selected_count": 0,
    "saved_count": 0,
    "candidates": [],
    "candidate_count": 0,
    "saved_candidate_count": 0,
    "completed_at": "",
}
SCHEDULER_STARTED = False
INITIAL_SCAN_STARTED = False
MARKET_CACHE_TTL = timedelta(minutes=15)
EARNINGS_CACHE_TTL = timedelta(minutes=30)
MARKET_LOCK = threading.Lock()
EARNINGS_LOCK = threading.Lock()
LAST_MARKET_REGIME: dict[str, object] = {
    "status": "not_connected",
    "regime": "unknown",
    "score": 0,
    "summary": "Macro regime has not been collected in this server session.",
    "generated_at": "",
    "metrics": [],
    "source_health": [],
    "events": [],
    "implications": [],
    "needed_feeds": [],
}
LAST_EARNINGS_CALENDAR: dict[str, object] = {
    "status": "not_connected",
    "generated_at": "",
    "items": [],
    "summary_zh": "Earnings calendar has not been collected in this server session.",
    "errors": [],
}


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    configure_logging()
    _start_initial_scan_once()
    _start_scheduler_once()
    server = ThreadingHTTPServer((host, port), RadarRequestHandler)
    print(f"AI News Radar web terminal running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping AI News Radar web terminal.")
    finally:
        server.server_close()


class RadarRequestHandler(BaseHTTPRequestHandler):
    server_version = "AINewsRadar/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
        route = urlparse(self.path)
        if route.path == "/":
            self._send_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if route.path == "/app.css":
            self._send_file(STATIC_ROOT / "app.css", "text/css; charset=utf-8")
            return
        if route.path == "/app.js":
            self._send_file(STATIC_ROOT / "app.js", "application/javascript; charset=utf-8")
            return
        if route.path == "/api/signals":
            query = parse_qs(route.query)
            limit = _int_arg(query.get("limit", ["200"])[0], default=200)
            self._send_json(_stored_payload(limit=limit))
            return
        if route.path == "/api/sources":
            self._send_json(_sources_payload())
            return
        if route.path == "/api/candidates":
            query = parse_qs(route.query)
            limit = _int_arg(query.get("limit", ["200"])[0], default=200)
            self._send_json(_candidate_payload(limit=limit))
            return
        if route.path == "/api/brief":
            self._send_json(_brief_payload())
            return
        if route.path == "/api/daily_report":
            from .daily_report import render_daily_report

            markdown = render_daily_report(_brief_payload().get("brief", {}))
            self._send_json({"ok": True, "markdown": markdown})
            return
        if route.path == "/api/earnings":
            query = parse_qs(route.query)
            month = query.get("month", [""])[0]
            self._send_json(_earnings_month_payload(month))
            return
        if route.path == "/api/financials":
            query = parse_qs(route.query)
            ticker = query.get("ticker", [""])[0]
            self._send_json(_financials_payload(ticker))
            return
        if route.path == "/api/holders":
            query = parse_qs(route.query)
            ticker = query.get("ticker", [""])[0]
            self._send_json(_holders_payload(ticker))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API.
        route = urlparse(self.path)
        files = {
            "/": (STATIC_ROOT / "index.html", "text/html; charset=utf-8"),
            "/app.css": (STATIC_ROOT / "app.css", "text/css; charset=utf-8"),
            "/app.js": (STATIC_ROOT / "app.js", "application/javascript; charset=utf-8"),
        }
        if route.path not in files:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        path, content_type = files[route.path]
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
        route = urlparse(self.path)
        if route.path == "/api/review_status":
            try:
                request = self._read_json_body()
                self._send_json(_update_review_status(request))
            except Exception as exc:  # noqa: BLE001 - surface web API failures as JSON.
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route.path != "/api/scan":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            request = self._read_json_body()
            response = run_scan(
                limit=_int_arg(request.get("limit"), default=DEFAULT_SIGNAL_LIMIT),
                min_score=_float_arg(request.get("min_score"), default=DEFAULT_MIN_SCORE),
                limit_per_source=_int_arg(request.get("limit_per_source"), default=DEFAULT_LIMIT_PER_SOURCE),
            )
        except Exception as exc:  # noqa: BLE001 - surface web API failures as JSON.
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json(response)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return {}
        return payload

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def run_scan(limit: int, min_score: float, limit_per_source: int) -> dict[str, object]:
    source_path = PROJECT_ROOT / "config" / "sources.json"
    watchlist_path = PROJECT_ROOT / "config" / "watchlist.json"
    output_path = PROJECT_ROOT / "data" / "signals.jsonl"
    candidate_path = PROJECT_ROOT / "data" / "candidates.jsonl"

    sources = load_sources(source_path)
    watchlist = load_watchlist(watchlist_path)
    market_regime = _market_regime_payload()
    articles, source_health = fetch_sources(sources, limit_per_source=limit_per_source)
    errors = [f"{row['source']}: {row['error']}" for row in source_health if row["status"] == "error"]

    signals = []
    candidates = []
    for article in articles:
        candidate = discover_candidate(article, watchlist)
        if candidate is not None:
            candidates.append(candidate)

        signal = score_article(article, watchlist)
        if signal is not None and signal.score >= min_score:
            signals.append(signal)

    signals.sort(key=lambda item: item.score, reverse=True)
    candidates.sort(key=lambda item: item.score, reverse=True)
    selected = signals[:limit]
    selected_candidates = candidates[: max(limit, 50)]
    selected_candidate_rows = enrich_candidates_with_ticker_resolution([asdict(candidate) for candidate in selected_candidates])
    selected_candidate_rows = enrich_candidates_with_market_confirmation(selected_candidate_rows)
    selected_candidate_rows = enrich_candidates_with_impact_assessment(selected_candidate_rows)
    selected_candidate_rows = enrich_candidates_with_financial_snapshots(selected_candidate_rows)
    # Quantitative health check / fraud filter: consumes the SEC snapshot and the
    # impact amount to flag going-concern risk and order-vs-revenue elasticity.
    selected_candidate_rows = enrich_candidates_with_quality_screen(selected_candidate_rows)
    # US-specific squeeze positioning factor: high short interest + hard catalyst.
    selected_candidate_rows = enrich_candidates_with_short_interest(selected_candidate_rows)
    # Smart-money flow: 13F-derived institutional accumulation / distribution.
    selected_candidate_rows = enrich_candidates_with_institutional_flow(selected_candidate_rows)
    # Serenity Alpha: news -> small/pure/misclassified-beneficiary hypothesis
    # (read-only second lens; needs evidence + impact + financials + flow above).
    selected_candidate_rows = enrich_candidates_with_serenity_alpha(selected_candidate_rows, watchlist=watchlist)
    selected_candidate_rows = enrich_candidates_with_quick_model(selected_candidate_rows)
    selected_candidate_rows = enrich_candidates_with_earnings_analysis(selected_candidate_rows, watchlist=watchlist)
    selected_candidate_rows = enrich_candidates_with_technology_intel(selected_candidate_rows, watchlist=watchlist)
    # Download & parse public PDFs (arXiv papers, .pdf links) for full-text evidence.
    selected_candidate_rows = enrich_candidates_with_pdf_intel(selected_candidate_rows)
    selected_candidate_rows = enrich_candidates_with_readthrough_analysis(selected_candidate_rows)
    selected_candidate_rows = enrich_candidates_with_options_flow(
        selected_candidate_rows,
        articles=[_article_payload(article) for article in articles],
    )
    selected_candidate_rows = enrich_candidates_with_options_chain_anomalies(selected_candidate_rows)
    selected_candidate_rows = enrich_candidates_with_expectation_check(selected_candidate_rows)
    saved_count = append_signals(output_path, selected)
    saved_candidate_count = append_candidates(candidate_path, selected_candidate_rows)

    response = {
        "ok": True,
        "fetched_count": len(articles),
        "scored_count": len(signals),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "saved_count": saved_count,
        "saved_candidate_count": saved_candidate_count,
        "errors": errors,
        "source_health": source_health,
        "signals": [asdict(signal) for signal in selected],
        "candidates": selected_candidate_rows,
        "articles": [_article_payload(article) for article in articles],
        "source_counts": _source_counts(articles),
        "market_regime": market_regime,
        "earnings_calendar": _earnings_calendar_payload(watchlist=watchlist),
        "stored": _stored_payload()["signals"],
        "stored_candidates": _candidate_payload()["candidates"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    LAST_SCAN.update(response)
    return response


def _start_scheduler_once() -> None:
    global SCHEDULER_STARTED
    if SCHEDULER_STARTED:
        return
    SCHEDULER_STARTED = True
    thread = threading.Thread(target=_scheduler_loop, daemon=True)
    thread.start()


def _start_initial_scan_once() -> None:
    global INITIAL_SCAN_STARTED
    if INITIAL_SCAN_STARTED:
        return
    INITIAL_SCAN_STARTED = True
    thread = threading.Thread(target=_run_scheduled_scan_once, daemon=True)
    thread.start()


def _scheduler_loop() -> None:
    while True:
        wait_seconds = max(60, (next_automated_run() - datetime.now(timezone.utc)).total_seconds())
        threading.Event().wait(wait_seconds)
        _run_scheduled_scan_once()


def _run_scheduled_scan_once() -> None:
    try:
        run_scan(
            limit=DEFAULT_SIGNAL_LIMIT,
            min_score=DEFAULT_MIN_SCORE,
            limit_per_source=DEFAULT_LIMIT_PER_SOURCE,
        )
    except Exception as exc:  # noqa: BLE001 - scheduler must not kill the server.
        LAST_SCAN["errors"] = [f"scheduler: {exc}"]


def _stored_payload(limit: int = 200) -> dict[str, object]:
    source_path = PROJECT_ROOT / "config" / "sources.json"
    watchlist_path = PROJECT_ROOT / "config" / "watchlist.json"
    output_path = PROJECT_ROOT / "data" / "signals.jsonl"
    candidate_path = PROJECT_ROOT / "data" / "candidates.jsonl"
    review_path = PROJECT_ROOT / "data" / "review_state.json"

    sources = load_sources(source_path)
    market_sources = load_market_sources(source_path)
    watchlist = load_watchlist(watchlist_path)
    review_state = load_review_state(review_path)
    if LAST_SCAN.get("completed_at"):
        rows = list(LAST_SCAN.get("signals", []))[:limit]
        stored_candidates = load_candidate_rows(candidate_path, limit=limit)
        candidate_rows = _merge_candidate_rows(list(LAST_SCAN.get("candidates", [])), stored_candidates, limit)
        candidate_rows = _with_review_status(candidate_rows, review_state)
    else:
        rows = load_signal_rows(output_path, limit=limit)
        rows.sort(key=lambda row: (float(row.get("score", 0)), _article_value(row, "fetched_at")), reverse=True)
        candidate_rows = load_candidate_rows(candidate_path, limit=limit)
        candidate_rows = _with_review_status(candidate_rows, review_state)
        candidate_rows.sort(key=lambda row: (float(row.get("score", 0)), _article_value(row, "fetched_at")), reverse=True)
    return {
        "ok": True,
        "source_count": len(sources),
        "market_source_count": len(market_sources),
        "watchlist_count": len(watchlist),
        "signals": rows,
        "candidates": candidate_rows,
        "last_scan": LAST_SCAN,
    }


def _candidate_payload(limit: int = 200) -> dict[str, object]:
    candidate_path = PROJECT_ROOT / "data" / "candidates.jsonl"
    review_path = PROJECT_ROOT / "data" / "review_state.json"
    rows = load_candidate_rows(candidate_path, limit=limit)
    rows = _with_review_status(rows, load_review_state(review_path))
    rows.sort(key=lambda row: (float(row.get("score", 0)), _article_value(row, "fetched_at")), reverse=True)
    return {"ok": True, "candidates": rows}


def _merge_candidate_rows(primary: list[dict[str, object]], stored: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen = set()
    for row in [*primary, *stored]:
        if not isinstance(row, dict):
            continue
        key = candidate_row_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda row: (float(row.get("score", 0)), _article_value(row, "fetched_at")), reverse=True)
    return rows[:limit]


EARNINGS_MONTH_CACHE: dict[str, dict[str, object]] = {}
EARNINGS_MONTH_LOCK = threading.Lock()
FINANCIALS_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
FINANCIALS_CACHE_TTL_SECONDS = 6 * 3600
CIK_MAP_CACHE: dict[str, dict[str, object]] = {}
NAME_INDEX_CACHE: dict[str, dict[str, str]] = {}
FINANCIALS_LOCK = threading.Lock()


def _financials_payload(ticker: str) -> dict[str, object]:
    """Authoritative SEC companyfacts snapshot for one ticker, fetched on demand.

    Powers the earnings workbench so any company (e.g. MRVL) shows real reported
    financials even when no earnings-release article has been captured. Cached
    for a few hours since SEC data only changes quarterly.
    """
    import time as _time

    symbol = str(ticker or "").upper().strip()
    if not symbol:
        return {"ok": False, "error": "missing ticker"}

    cached = FINANCIALS_CACHE.get(symbol)
    if cached is not None and _time.time() - cached[0] < FINANCIALS_CACHE_TTL_SECONDS:
        return {"ok": True, "ticker": symbol, **cached[1]}

    with FINANCIALS_LOCK:
        cached = FINANCIALS_CACHE.get(symbol)
        if cached is not None and _time.time() - cached[0] < FINANCIALS_CACHE_TTL_SECONDS:
            return {"ok": True, "ticker": symbol, **cached[1]}
        from .filing_teardown import build_name_index, teardown_filing
        from .financials import fetch_financial_snapshot, fetch_recent_filings, load_default_cik_map

        try:
            if not CIK_MAP_CACHE:
                CIK_MAP_CACHE.update(load_default_cik_map())
            snapshot = fetch_financial_snapshot(symbol, cik_map=CIK_MAP_CACHE)
            company = CIK_MAP_CACHE.get(symbol)
            filings = fetch_recent_filings(int(company["cik"])) if company else []
            teardown = {"status": "no_filing"}
            report = next((f for f in filings if f.get("form") in {"10-Q", "10-K", "20-F", "40-F"}), None)
            if report and report.get("doc_url"):
                if not NAME_INDEX_CACHE:
                    NAME_INDEX_CACHE.update(build_name_index(CIK_MAP_CACHE, _watchlist_for_index()))
                teardown = teardown_filing(str(report["doc_url"]), NAME_INDEX_CACHE, self_ticker=symbol)
                teardown["form"] = report.get("form")
                teardown["filed"] = report.get("filed")
        except Exception as exc:  # noqa: BLE001 - degrade without breaking the view.
            return {"ok": True, "ticker": symbol, "snapshot": {"status": "unavailable", "reason": str(exc)[:160]}, "filings": [], "teardown": {"status": "unavailable"}}
        result = {"snapshot": snapshot, "filings": filings, "teardown": teardown}
        FINANCIALS_CACHE[symbol] = (_time.time(), result)
        return {"ok": True, "ticker": symbol, **result}


HOLDERS_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
HOLDERS_CACHE_TTL_SECONDS = 24 * 3600
HOLDERS_LOCK = threading.Lock()


def _holders_payload(ticker: str) -> dict[str, object]:
    """Reverse-13F: institutions that hold this ticker, from SEC filings.

    Heavy (full-text search + multiple information tables), so it is a separate
    on-demand endpoint with a long cache — 13F data only changes quarterly.
    """
    import time as _time

    symbol = str(ticker or "").upper().strip()
    if not symbol:
        return {"ok": False, "error": "missing ticker"}
    cached = HOLDERS_CACHE.get(symbol)
    if cached is not None and _time.time() - cached[0] < HOLDERS_CACHE_TTL_SECONDS:
        return {"ok": True, "ticker": symbol, **cached[1]}

    with HOLDERS_LOCK:
        cached = HOLDERS_CACHE.get(symbol)
        if cached is not None and _time.time() - cached[0] < HOLDERS_CACHE_TTL_SECONDS:
            return {"ok": True, "ticker": symbol, **cached[1]}
        from .financials import load_default_cik_map
        from .reverse_13f import find_institutional_holders

        try:
            if not CIK_MAP_CACHE:
                CIK_MAP_CACHE.update(load_default_cik_map())
            company = CIK_MAP_CACHE.get(symbol)
            issuer = str(company.get("name") or "") if company else ""
            result = find_institutional_holders(issuer) if issuer else {"status": "no_issuer", "holders": []}
        except Exception as exc:  # noqa: BLE001 - degrade without breaking the view.
            return {"ok": True, "ticker": symbol, "status": "unavailable", "holders": [], "reason": str(exc)[:160]}
        HOLDERS_CACHE[symbol] = (_time.time(), result)
        return {"ok": True, "ticker": symbol, **result}


def _watchlist_for_index() -> list[object]:
    try:
        return list(load_watchlist(PROJECT_ROOT / "config" / "watchlist.json"))
    except Exception:  # noqa: BLE001
        return []


def _earnings_month_payload(month: str) -> dict[str, object]:
    """Earnings for a specific calendar month (YYYY-MM) for the grid view, cached."""
    from datetime import date as _date

    try:
        year_str, month_str = month.split("-")
        year, month_num = int(year_str), int(month_str)
        if not (1 <= month_num <= 12):
            raise ValueError("month out of range")
    except (ValueError, AttributeError):
        today = _date.today()
        year, month_num = today.year, today.month
    key = f"{year:04d}-{month_num:02d}"

    cached = EARNINGS_MONTH_CACHE.get(key)
    if cached is not None:
        generated = str(cached.get("generated_at") or "")
        try:
            if generated and datetime.now(timezone.utc) - datetime.fromisoformat(generated) < EARNINGS_CACHE_TTL:
                return {"ok": True, "calendar": cached}
        except ValueError:
            pass

    with EARNINGS_MONTH_LOCK:
        cached = EARNINGS_MONTH_CACHE.get(key)
        if cached is not None:
            generated = str(cached.get("generated_at") or "")
            try:
                if generated and datetime.now(timezone.utc) - datetime.fromisoformat(generated) < EARNINGS_CACHE_TTL:
                    return {"ok": True, "calendar": cached}
            except ValueError:
                pass
        from .earnings_calendar import collect_earnings_month

        try:
            watchlist = load_watchlist(PROJECT_ROOT / "config" / "watchlist.json")
            calendar = collect_earnings_month(list(watchlist), year, month_num)
        except Exception as exc:  # noqa: BLE001 - degrade without breaking the view.
            calendar = {"status": "degraded", "month": key, "items": [], "errors": [str(exc)],
                        "summary_zh": f"财报月历连接失败：{exc}"}
        EARNINGS_MONTH_CACHE[key] = calendar
        return {"ok": True, "calendar": calendar}


def _brief_payload() -> dict[str, object]:
    stored = _stored_payload()
    market_regime = _market_regime_payload()
    watchlist = load_watchlist(PROJECT_ROOT / "config" / "watchlist.json")
    earnings_calendar = _earnings_calendar_payload(watchlist=watchlist)
    brief = build_daily_brief(
        signals=list(stored.get("signals", [])),
        candidates=list(stored.get("candidates", [])),
        last_scan=dict(stored.get("last_scan", {})),
        source_count=int(stored.get("source_count", 0) or 0),
        watchlist_count=int(stored.get("watchlist_count", 0) or 0),
        market_source_count=int(stored.get("market_source_count", 0) or 0),
        market_regime=market_regime,
        earnings_calendar=earnings_calendar,
    )
    return {"ok": True, "brief": brief}


def _earnings_calendar_payload(watchlist: list[object] | None = None, force: bool = False) -> dict[str, object]:
    generated_at = str(LAST_EARNINGS_CALENDAR.get("generated_at") or "")
    if not force and generated_at:
        try:
            generated = datetime.fromisoformat(generated_at)
        except ValueError:
            generated = None
        if (
            generated is not None
            and datetime.now(timezone.utc) - generated < EARNINGS_CACHE_TTL
            and _earnings_calendar_cache_matches_today(LAST_EARNINGS_CALENDAR)
        ):
            return dict(LAST_EARNINGS_CALENDAR)

    with EARNINGS_LOCK:
        generated_at = str(LAST_EARNINGS_CALENDAR.get("generated_at") or "")
        if not force and generated_at:
            try:
                generated = datetime.fromisoformat(generated_at)
            except ValueError:
                generated = None
            if (
                generated is not None
                and datetime.now(timezone.utc) - generated < EARNINGS_CACHE_TTL
                and _earnings_calendar_cache_matches_today(LAST_EARNINGS_CALENDAR)
            ):
                return dict(LAST_EARNINGS_CALENDAR)
        try:
            companies = watchlist or load_watchlist(PROJECT_ROOT / "config" / "watchlist.json")
            calendar = collect_earnings_calendar(list(companies))
        except Exception as exc:  # noqa: BLE001 - brief should still render.
            calendar = {
                "status": "degraded",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "items": [],
                "summary_zh": f"财报日历连接失败：{exc}",
                "errors": [str(exc)],
            }
        LAST_EARNINGS_CALENDAR.clear()
        LAST_EARNINGS_CALENDAR.update(calendar)
        return dict(LAST_EARNINGS_CALENDAR)


def _earnings_calendar_cache_matches_today(payload: dict[str, object]) -> bool:
    local_trading_date = str(payload.get("local_trading_date") or "")
    if not local_trading_date:
        return False
    return local_trading_date == datetime.now().astimezone().date().isoformat()


def _market_regime_payload(force: bool = False) -> dict[str, object]:
    cached = _load_market_cache()
    if not force and cached is not None:
        return cached

    generated_at = str(LAST_MARKET_REGIME.get("generated_at") or "")
    if not force and generated_at:
        try:
            generated = datetime.fromisoformat(generated_at)
        except ValueError:
            generated = None
        if generated is not None and datetime.now(timezone.utc) - generated < MARKET_CACHE_TTL:
            return dict(LAST_MARKET_REGIME)

    with MARKET_LOCK:
        if not force:
            generated_at = str(LAST_MARKET_REGIME.get("generated_at") or "")
            if generated_at:
                try:
                    generated = datetime.fromisoformat(generated_at)
                except ValueError:
                    generated = None
                if generated is not None and datetime.now(timezone.utc) - generated < MARKET_CACHE_TTL:
                    return dict(LAST_MARKET_REGIME)
        source_path = PROJECT_ROOT / "config" / "sources.json"
        try:
            market_sources = load_market_sources(source_path)
            regime = collect_market_regime(market_sources)
        except Exception as exc:  # noqa: BLE001 - brief should still render when market collection fails.
            regime = {
                "status": "not_connected",
                "regime": "unknown",
                "score": 0,
                "summary": f"Macro regime collection failed: {exc}",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "metrics": [],
                "source_health": [],
                "events": [],
                "implications": [],
                "needed_feeds": [],
            }
        LAST_MARKET_REGIME.clear()
        LAST_MARKET_REGIME.update(regime)
        _save_market_cache(dict(LAST_MARKET_REGIME))
        return dict(LAST_MARKET_REGIME)


def _load_market_cache() -> dict[str, object] | None:
    cache_path = PROJECT_ROOT / "data" / "market_regime.json"
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    generated_at = str(payload.get("generated_at") or "")
    if not generated_at:
        return None
    try:
        generated = datetime.fromisoformat(generated_at)
    except ValueError:
        return None
    if datetime.now(timezone.utc) - generated >= MARKET_CACHE_TTL:
        return None
    LAST_MARKET_REGIME.clear()
    LAST_MARKET_REGIME.update(payload)
    return dict(payload)


def _save_market_cache(payload: dict[str, object]) -> None:
    cache_path = PROJECT_ROOT / "data" / "market_regime.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_review_status(request: dict[str, object]) -> dict[str, object]:
    key = str(request.get("key") or "")
    status = str(request.get("status") or "")
    if not key:
        return {"ok": False, "error": "Missing review key"}
    if status not in {"pending", "reviewed", "dismissed", "promoted"}:
        return {"ok": False, "error": "Invalid review status"}

    review_path = PROJECT_ROOT / "data" / "review_state.json"
    state = load_review_state(review_path)
    if status == "pending":
        state.pop(key, None)
    else:
        state[key] = status
    save_review_state(review_path, state)
    return {"ok": True, "key": key, "status": status}


def _with_review_status(rows: list[dict[str, object]], state: dict[str, str]) -> list[dict[str, object]]:
    output = []
    for row in rows:
        item = dict(row)
        key = candidate_row_key(item)
        item["review_key"] = key
        item["review_status"] = state.get(key, "pending")
        output.append(item)
    return output


def _sources_payload() -> dict[str, object]:
    source_path = PROJECT_ROOT / "config" / "sources.json"
    sources = load_sources(source_path)
    market_sources = load_market_sources(source_path)
    watchlist = load_watchlist(PROJECT_ROOT / "config" / "watchlist.json")
    return {
        "ok": True,
        "sources": [
            {
                "name": source.name,
                "group": source.group,
                "type": source.type,
                "url": source.url,
                "trust": source.trust,
                "include_patterns": list(source.include_patterns),
                "exclude_patterns": list(source.exclude_patterns),
            }
            for source in sources
        ],
        "market_sources": [
            {
                "name": source.name,
                "group": source.group,
                "type": source.type,
                "url": source.url,
                "purpose": source.purpose,
                "status": source.status,
            }
            for source in market_sources
        ],
        "watchlist": [
            {
                "ticker": company.ticker,
                "name": company.name,
                "aliases": list(company.aliases),
                "themes": list(company.themes),
            }
            for company in watchlist
        ],
    }


def _article_payload(article: object) -> dict[str, object]:
    return {
        "source": getattr(article, "source", ""),
        "source_trust": getattr(article, "source_trust", 0),
        "title": getattr(article, "title", ""),
        "link": getattr(article, "link", ""),
        "published": getattr(article, "published", ""),
        "summary": getattr(article, "summary", ""),
        "fetched_at": getattr(article, "fetched_at", ""),
        "timeliness": article_timeliness(article),
    }


def _source_counts(articles: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for article in articles:
        source = str(getattr(article, "source", "") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _article_value(row: dict[str, object], key: str) -> str:
    article = row.get("article")
    if not isinstance(article, dict):
        return ""
    value = article.get(key)
    return str(value or "")


def _int_arg(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _float_arg(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-news-radar-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
