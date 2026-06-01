"""Short-squeeze potential — the US-market "hidden pistol".

A US-specific, regime-type *positioning* factor (not a fundamental number).
Many contested or temporarily-unprofitable small caps are heavily shorted
(short interest can reach 20-40% of float). When the radar catches a hard
catalyst (named order, capacity, production ramp) on such a name, shorts are
forced to cover, and the buy-to-cover resonates with the good news into a
violent 1-3 day squeeze (think GME / AMC).

Golden alert: high hard-evidence score AND short interest above a threshold ->
the most prominent red blow-up tag on the TOP CALL.

Data source: Yahoo's ``defaultKeyStatistics.shortPercentOfFloat`` — the same
field ``yfinance`` exposes, fetched here with the standard library (cookie +
crumb handshake) so the runtime stays dependency-light. Every failure degrades
to ``unavailable`` (the alert simply does not fire); it never fabricates and
never breaks the scan.
"""

from __future__ import annotations

import json

from .scoring import HARD_BAND
from .yahoo import make_yahoo_fetcher, quote_summary_url
from .yahoo import raw as _raw

#: Short interest above this share of float is squeeze-prone.
SQUEEZE_FLOAT_THRESHOLD = 0.15
ELEVATED_FLOAT_THRESHOLD = 0.10
#: The catalyst must be strong (top action tier) for the squeeze alert to fire.
SQUEEZE_MIN_EVIDENCE_SCORE = HARD_BAND

ALERT_LABEL = "[警告：极高空头轧空爆发潜力]"


def enrich_candidates_with_short_interest(
    candidates: list[dict[str, object]],
    fetcher: object | None = None,
    max_tickers: int = 20,
) -> list[dict[str, object]]:
    tickers = _candidate_tickers(candidates)[:max_tickers]
    readings: dict[str, dict[str, object]] = {}
    if tickers:
        fetch = fetcher or make_yahoo_fetcher()
        for ticker in tickers:
            readings[ticker] = fetch_short_percent_of_float(ticker, fetch)

    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["short_squeeze"] = _assess_candidate(row, readings)
        enriched.append(row)
    return enriched


def fetch_short_percent_of_float(ticker: str, fetch: object) -> dict[str, object]:
    symbol = ticker.strip().upper()
    if not symbol:
        return {"status": "no_ticker"}
    url = quote_summary_url(symbol, "defaultKeyStatistics")
    try:
        payload = json.loads(fetch(url))  # type: ignore[operator]
        result = (((payload.get("quoteSummary") or {}).get("result")) or [None])[0]
        if not isinstance(result, dict):
            return {"status": "unavailable", "ticker": symbol, "reason": "no result"}
        stats = result.get("defaultKeyStatistics")
        if not isinstance(stats, dict):
            return {"status": "unavailable", "ticker": symbol, "reason": "no key statistics"}
        spf = _raw(stats.get("shortPercentOfFloat"))
        return {
            "status": "ok" if spf is not None else "no_short_data",
            "ticker": symbol,
            "short_percent_of_float": spf,
            "shares_short": _raw(stats.get("sharesShort")),
            "float_shares": _raw(stats.get("floatShares")),
            "short_ratio_days": _raw(stats.get("shortRatio")),
            "as_of": _raw(stats.get("dateShortInterest")),
            "source": "Yahoo defaultKeyStatistics",
        }
    except Exception as exc:  # noqa: BLE001 - degrade cleanly; never break the scan.
        return {"status": "unavailable", "ticker": symbol, "reason": str(exc)[:160]}


def _assess_candidate(candidate: dict[str, object], readings: dict[str, dict[str, object]]) -> dict[str, object]:
    tickers = [str(t).upper() for t in (candidate.get("tickers") or []) if str(t).strip()]
    if not tickers:
        return {"status": "no_ticker", "alert": False, "potential": "unknown",
                "summary_zh": "尚无确认 ticker，无法评估空头轧空潜力。"}
    rows = [readings[t] for t in tickers if t in readings]
    ok_rows = [r for r in rows if r.get("status") == "ok" and isinstance(r.get("short_percent_of_float"), (int, float))]
    if not ok_rows:
        return {"status": "unavailable", "alert": False, "potential": "unknown",
                "summary_zh": "未取得空头数据（Yahoo 限流或无披露），不触发轧空判断。"}

    best = max(ok_rows, key=lambda r: float(r.get("short_percent_of_float") or 0))
    spf = float(best["short_percent_of_float"])
    score = float(candidate.get("score", 0) or 0)
    potential = _potential(spf)
    alert = spf >= SQUEEZE_FLOAT_THRESHOLD and score >= SQUEEZE_MIN_EVIDENCE_SCORE
    return {
        "status": "ok",
        "ticker": best.get("ticker"),
        "short_percent_of_float": round(spf, 4),
        "short_percent_display": f"{spf * 100:.1f}%",
        "shares_short": best.get("shares_short"),
        "short_ratio_days": best.get("short_ratio_days"),
        "as_of": best.get("as_of"),
        "potential": potential,
        "alert": alert,
        "label": ALERT_LABEL if alert else "",
        "summary_zh": _summary_zh(spf, score, potential, alert),
        "source": best.get("source"),
    }


def _potential(spf: float) -> str:
    if spf >= SQUEEZE_FLOAT_THRESHOLD:
        return "high"
    if spf >= ELEVATED_FLOAT_THRESHOLD:
        return "elevated"
    return "low"


def _summary_zh(spf: float, score: float, potential: str, alert: bool) -> str:
    pct = f"{spf * 100:.1f}%"
    if alert:
        return f"空头占流通盘 {pct}（高），叠加硬证据分 {score:.0f}，具备剧烈空头轧空（short squeeze）爆发潜力。"
    if potential == "high":
        return f"空头占流通盘 {pct}（高），但当前催化剂强度不足，暂不触发轧空警报；若出现具名大单/量产证据需立刻重估。"
    if potential == "elevated":
        return f"空头占流通盘 {pct}（偏高），有一定轧空弹性，关注催化剂。"
    return f"空头占流通盘 {pct}（低），轧空弹性有限。"


def _candidate_tickers(candidates: list[dict[str, object]]) -> list[str]:
    output: list[str] = []
    for candidate in candidates:
        for ticker in candidate.get("tickers", []) or []:
            text = str(ticker).upper().strip()
            if text and text not in output:
                output.append(text)
    return output
