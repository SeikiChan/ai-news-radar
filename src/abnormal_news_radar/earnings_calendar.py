from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from .model import Company
from .net import fetch_text

NASDAQ_EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings?date={date}"
FETCH_TIMEOUT_SECONDS = 8
USER_AGENT = "Mozilla/5.0 (AI-News-Radar earnings-calendar)"

#: Default look-ahead window. ~5 weeks forward covers the rolling month an
#: analyst wants to browse; pass a larger ``days_forward`` (e.g. 95) for a full
#: quarter at the cost of more per-day API calls.
DEFAULT_DAYS_BACK = 2
DEFAULT_DAYS_FORWARD = 35
MAX_DAY_WORKERS = 6


def collect_earnings_calendar(
    watchlist: list[Company],
    fetcher: object | None = None,
    today: date | None = None,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
) -> dict[str, object]:
    if today is None:
        today = _local_today()
    targets = [today + timedelta(days=offset) for offset in range(-days_back, days_forward + 1)]
    return _collect_for_dates(watchlist, targets, fetcher, today)


def collect_earnings_month(
    watchlist: list[Company],
    year: int,
    month: int,
    fetcher: object | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """Collect a full calendar month of focused-watchlist earnings (for the grid view)."""
    import calendar as _calendar

    if today is None:
        today = _local_today()
    last_day = _calendar.monthrange(year, month)[1]
    targets = [date(year, month, day) for day in range(1, last_day + 1)]
    payload = _collect_for_dates(watchlist, targets, fetcher, today)
    payload["month"] = f"{year:04d}-{month:02d}"
    return payload


def _collect_for_dates(
    watchlist: list[Company],
    targets: list[date],
    fetcher: object | None,
    today: date,
) -> dict[str, object]:
    focus = {company.ticker.upper(): company for company in watchlist}
    fetch = fetcher or _fetch_text
    rows: list[dict[str, object]] = []
    errors: list[str] = []

    def fetch_one(target: date) -> tuple[date, list[dict[str, object]] | None, str | None]:
        try:
            return target, _fetch_day(target, focus, fetch), None
        except Exception as exc:  # noqa: BLE001 - calendar should degrade without killing brief.
            return target, None, str(exc)

    workers = max(1, min(MAX_DAY_WORKERS, len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for target, day_rows, error in pool.map(fetch_one, targets):
            if error is not None:
                errors.append(f"{target.isoformat()}: {error}")
            else:
                rows.extend(day_rows or [])

    rows.sort(key=lambda row: (str(row.get("date") or ""), _time_rank(str(row.get("time") or "")), str(row.get("ticker") or "")))
    return {
        "status": "connected" if rows or not errors else "degraded",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_trading_date": today.isoformat(),
        "window": {"from": targets[0].isoformat(), "to": targets[-1].isoformat()} if targets else {},
        "source": "Nasdaq public earnings calendar API",
        "source_url": NASDAQ_EARNINGS_URL.format(date=today.isoformat()),
        "items": rows,
        "focus_tickers": sorted(focus),
        "errors": errors[:10],
        "summary_zh": _summary_zh(rows, errors),
    }


def _fetch_day(target: date, focus: dict[str, Company], fetch: object) -> list[dict[str, object]]:
    payload = json.loads(fetch(NASDAQ_EARNINGS_URL.format(date=target.isoformat())))
    rows = (((payload.get("data") or {}).get("rows")) or [])
    output = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("symbol") or "").upper().strip()
        if ticker not in focus:
            continue
        company = focus[ticker]
        output.append(
            {
                "ticker": ticker,
                "name": row.get("name") or company.name,
                "date": target.isoformat(),
                "time": row.get("time") or "",
                "eps_forecast": row.get("epsForecast") or "",
                "fiscal_quarter_ending": row.get("fiscalQuarterEnding") or "",
                "market_cap": row.get("marketCap") or "",
                "last_year_report_date": row.get("lastYearRptDt") or "",
                "last_year_eps": row.get("lastYearEPS") or "",
                "themes": list(company.themes),
                "priority": _priority(company, str(row.get("time") or ""), target),
                "status_zh": _status_zh(target, str(row.get("time") or "")),
            }
        )
    return output


def _priority(company: Company, report_time: str, target: date) -> int:
    score = 2
    if any(theme in company.themes for theme in ("ai_datacenter", "ai_software", "cloud", "custom_silicon", "ai_supply_chain")):
        score += 2
    if target == _local_today():
        score += 1
    if "after" in report_time or "before" in report_time:
        score += 1
    return min(score, 5)


def _status_zh(target: date, report_time: str) -> str:
    today = _local_today()
    if target < today:
        return "刚发布/待复盘"
    if target == today:
        if "after" in report_time:
            return "今日盘后重点"
        if "before" in report_time:
            return "今日盘前/已发布"
        return "今日重点"
    return "即将发布"


def _time_rank(value: str) -> int:
    if "before" in value:
        return 0
    if "during" in value:
        return 1
    if "after" in value:
        return 2
    return 3


def _summary_zh(rows: list[dict[str, object]], errors: list[str]) -> str:
    today = _local_today().isoformat()
    today_rows = [row for row in rows if row.get("date") == today]
    upcoming = [row for row in rows if str(row.get("date") or "") > today]
    if rows:
        return f"未来窗口内有 {len(rows)} 个主流观察标的财报；今日 {len(today_rows)} 个，后续 {len(upcoming)} 个。"
    if errors:
        return "财报日历连接降级，当前没有可用主流观察标的结果。"
    return "未来窗口内暂无主流观察标的财报。"


def _fetch_text(url: str) -> str:
    # Nasdaq blocks non-browser agents, so keep the Mozilla UA while still
    # getting shared retry/backoff from the hardened client.
    return fetch_text(url, accept="application/json", timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})


def _local_today() -> date:
    return datetime.now().astimezone().date()
