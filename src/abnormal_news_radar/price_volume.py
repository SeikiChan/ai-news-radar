from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

FETCH_TIMEOUT_SECONDS = 6
USER_AGENT = "AI-News-Radar/0.1 (+price-volume-confirmation)"


def enrich_candidates_with_market_confirmation(
    candidates: list[dict[str, object]],
    fetcher: object | None = None,
    max_tickers: int = 20,
) -> list[dict[str, object]]:
    fetch = fetcher or _fetch_text
    tickers = _candidate_tickers(candidates)[:max_tickers]
    confirmations: dict[str, dict[str, object]] = {}
    for ticker in tickers:
        confirmations[ticker] = fetch_price_volume_confirmation(ticker, fetch)

    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["market_confirmation"] = _candidate_confirmation(row, confirmations)
        enriched.append(row)
    return enriched


def fetch_price_volume_confirmation(ticker: str, fetcher: object | None = None) -> dict[str, object]:
    symbol = ticker.strip().upper()
    if not symbol:
        return _unavailable(symbol, "missing ticker")
    fetch = fetcher or _fetch_text
    url = _yahoo_chart_url(symbol)
    try:
        payload = json.loads(fetch(url))
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not isinstance(result, dict):
            return _unavailable(symbol, "missing Yahoo chart result", url)
        points = _chart_points(result)
        if len(points) < 6:
            return _unavailable(symbol, "not enough daily observations", url)
        metric = _confirmation_metric(symbol, points, url)
    except Exception as exc:  # noqa: BLE001 - one failed ticker must not fail the scan.
        return _unavailable(symbol, str(exc), url)
    return metric


def _confirmation_metric(symbol: str, points: list[dict[str, object]], url: str) -> dict[str, object]:
    latest = points[-1]
    price = float(latest["close"])
    volume = int(latest["volume"])
    change_1d = _pct_change(points, 1)
    change_5d = _pct_change(points, 5)
    change_20d = _pct_change(points, 20)
    volume_ratio = _volume_ratio(points)
    status = _confirmation_status(change_1d, change_5d, change_20d, volume_ratio)
    return {
        "ticker": symbol,
        "status": status,
        "as_of": latest["date"],
        "latest_price": round(price, 4),
        "change_1d_pct": change_1d,
        "change_5d_pct": change_5d,
        "change_20d_pct": change_20d,
        "latest_volume": volume,
        "volume_ratio_vs_20d": volume_ratio,
        "source": "Yahoo chart API",
        "source_url": url,
        "summary_zh": _summary_zh(symbol, status, change_1d, change_5d, change_20d, volume_ratio),
    }


def _confirmation_status(
    change_1d: float | None,
    change_5d: float | None,
    change_20d: float | None,
    volume_ratio: float | None,
) -> str:
    strongest_price = max(_none_to_floor(change_1d), _none_to_floor(change_5d))
    weakest_price = min(_none_to_ceiling(change_1d), _none_to_ceiling(change_5d))
    if weakest_price <= -5 or _none_to_ceiling(change_1d) <= -3:
        return "negative_reaction"
    if volume_ratio is not None and volume_ratio >= 1.5 and strongest_price >= 3:
        return "confirmed"
    if volume_ratio is not None and volume_ratio >= 1.2 and strongest_price >= 1:
        return "early_confirmation"
    if strongest_price >= 4:
        return "price_only_confirmation"
    if change_20d is not None and change_20d >= 20 and strongest_price < 2:
        return "already_extended"
    return "unconfirmed"


def _candidate_confirmation(
    candidate: dict[str, object],
    confirmations: dict[str, dict[str, object]],
) -> dict[str, object]:
    tickers = [str(ticker).upper() for ticker in candidate.get("tickers", []) or [] if str(ticker).strip()]
    if not tickers:
        return {
            "status": "no_ticker",
            "summary_zh": "没有已确认 ticker，无法做价格/成交量确认。",
            "confirmations": [],
        }
    rows = [confirmations[ticker] for ticker in tickers if ticker in confirmations]
    if not rows:
        return {
            "status": "unavailable",
            "summary_zh": "已识别 ticker，但当前扫描没有拿到市场数据。",
            "confirmations": [],
        }
    status = _strongest_status(row.get("status") for row in rows)
    return {
        "status": status,
        "primary_ticker": str(rows[0].get("ticker") or tickers[0]),
        "summary_zh": _combined_summary_zh(status, rows),
        "confirmations": rows,
    }


def _strongest_status(statuses: object) -> str:
    rank = {
        "confirmed": 5,
        "early_confirmation": 4,
        "price_only_confirmation": 3,
        "already_extended": 2,
        "unconfirmed": 1,
        "negative_reaction": 0,
        "unavailable": -1,
    }
    best = "unavailable"
    best_rank = -2
    for status in statuses:
        text = str(status or "unavailable")
        if rank.get(text, -1) > best_rank:
            best = text
            best_rank = rank.get(text, -1)
    return best


def _combined_summary_zh(status: str, rows: list[dict[str, object]]) -> str:
    lead = {
        "confirmed": "市场已确认：股价上涨伴随成交量放大。",
        "early_confirmation": "早期确认：价格和成交量有初步反应。",
        "price_only_confirmation": "只有价格确认：股价有反应，但成交量证据不足。",
        "already_extended": "价格已明显延伸：需要警惕新闻前已有预期。",
        "negative_reaction": "负面反应：新闻后市场反应偏弱或下跌。",
        "unconfirmed": "尚未确认：价格/成交量没有证明新闻已被重估。",
        "unavailable": "市场数据不可用。",
    }.get(status, "市场确认状态未知。")
    details = []
    for row in rows[:3]:
        details.append(
            f"{row.get('ticker')}: 1d={_fmt_pct(row.get('change_1d_pct'))}, "
            f"5d={_fmt_pct(row.get('change_5d_pct'))}, vol={row.get('volume_ratio_vs_20d', 'n/a')}x"
        )
    return f"{lead} {'; '.join(details)}"


def _summary_zh(
    symbol: str,
    status: str,
    change_1d: float | None,
    change_5d: float | None,
    change_20d: float | None,
    volume_ratio: float | None,
) -> str:
    return (
        f"{symbol} 状态={status}；1d={_fmt_pct(change_1d)}，"
        f"5d={_fmt_pct(change_5d)}，20d={_fmt_pct(change_20d)}，"
        f"成交量={volume_ratio if volume_ratio is not None else 'n/a'}x。"
    )


def _chart_points(result: dict[str, object]) -> list[dict[str, object]]:
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    points: list[dict[str, object]] = []
    for timestamp, close, volume in zip(timestamps, closes, volumes):
        if close is None or volume is None:
            continue
        date = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()
        points.append({"date": date, "close": float(close), "volume": int(volume)})
    return points


def _pct_change(points: list[dict[str, object]], lookback: int) -> float | None:
    if len(points) <= lookback:
        return None
    latest = float(points[-1]["close"])
    previous = float(points[-lookback - 1]["close"])
    if previous == 0:
        return None
    return round((latest / previous - 1) * 100, 2)


def _volume_ratio(points: list[dict[str, object]]) -> float | None:
    if len(points) < 21:
        return None
    latest = int(points[-1]["volume"])
    history = [int(point["volume"]) for point in points[-21:-1] if int(point["volume"]) > 0]
    if not history:
        return None
    return round(latest / (sum(history) / len(history)), 2)


def _candidate_tickers(candidates: list[dict[str, object]]) -> list[str]:
    output: list[str] = []
    for candidate in candidates:
        for ticker in candidate.get("tickers", []) or []:
            text = str(ticker).upper().strip()
            if text and text not in output:
                output.append(text)
    return output


def _yahoo_chart_url(symbol: str) -> str:
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=3mo&interval=1d"


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def _unavailable(symbol: str, reason: str, url: str = "") -> dict[str, object]:
    return {
        "ticker": symbol,
        "status": "unavailable",
        "reason": reason,
        "source": "Yahoo chart API",
        "source_url": url or (_yahoo_chart_url(symbol) if symbol else ""),
        "summary_zh": f"{symbol or 'ticker'} 市场数据不可用：{reason}",
    }


def _none_to_floor(value: float | None) -> float:
    return -1_000_000.0 if value is None else value


def _none_to_ceiling(value: float | None) -> float:
    return 1_000_000.0 if value is None else value


def _fmt_pct(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "n/a"
