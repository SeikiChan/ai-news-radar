"""Institutional ownership & flow — "follow the smart money" (13F-derived).

Form 13F is the quarterly long-equity disclosure of institutional managers
(>$100M AUM). Reconstructing it from raw EDGAR filings means downloading every
manager's filing and reverse-indexing CUSIP -> ticker — impractical for a local
tool. The standard free shortcut (also what ``yfinance`` uses) is Yahoo's
``institutionOwnership`` / ``majorHoldersBreakdown`` modules, which are
themselves built from 13F/13D/G filings and are queryable per ticker.

For a candidate ticker we read:
* ``majorHoldersBreakdown`` -> % of shares held by institutions, holder count;
* ``institutionOwnership`` -> top holders with their quarter-over-quarter
  position change (``pctChange``), i.e. who is accumulating vs distributing.

The resulting flow (accumulation / distribution / mixed) is the third leg of
conviction alongside hard evidence and short-squeeze positioning. Network
failures degrade to ``unavailable`` — never fabricated, never fatal.
"""

from __future__ import annotations

import json

from .yahoo import make_yahoo_fetcher, quote_summary_url
from .yahoo import raw as _raw

MODULES = "majorHoldersBreakdown,institutionOwnership"

#: Per-holder position change magnitude that counts as a real move.
MOVE_THRESHOLD = 0.01
#: Net top-holder share change (as a share of those holders' position) that
#: tips the aggregate verdict into accumulation / distribution.
NET_FLOW_THRESHOLD = 0.02


def enrich_candidates_with_institutional_flow(
    candidates: list[dict[str, object]],
    fetcher: object | None = None,
    max_tickers: int = 20,
) -> list[dict[str, object]]:
    tickers = _candidate_tickers(candidates)[:max_tickers]
    readings: dict[str, dict[str, object]] = {}
    if tickers:
        fetch = fetcher or make_yahoo_fetcher()
        for ticker in tickers:
            readings[ticker] = fetch_institutional_flow(ticker, fetch)

    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["institutional_flow"] = _assess_candidate(row, readings)
        enriched.append(row)
    return enriched


def fetch_institutional_flow(ticker: str, fetch: object) -> dict[str, object]:
    symbol = ticker.strip().upper()
    if not symbol:
        return {"status": "no_ticker"}
    url = quote_summary_url(symbol, MODULES)
    try:
        payload = json.loads(fetch(url))  # type: ignore[operator]
        result = (((payload.get("quoteSummary") or {}).get("result")) or [None])[0]
        if not isinstance(result, dict):
            return {"status": "unavailable", "ticker": symbol, "reason": "no result"}
        breakdown = result.get("majorHoldersBreakdown") if isinstance(result.get("majorHoldersBreakdown"), dict) else {}
        ownership = result.get("institutionOwnership") if isinstance(result.get("institutionOwnership"), dict) else {}
        holders = ownership.get("ownershipList") if isinstance(ownership.get("ownershipList"), list) else []
        return {
            "status": "ok",
            "ticker": symbol,
            "institutions_pct_held": _raw(breakdown.get("institutionsPercentHeld")),
            "institutions_count": _raw(breakdown.get("institutionsCount")),
            "holders": [_holder(h) for h in holders if isinstance(h, dict)],
            "source": "Yahoo institutionOwnership (13F-derived)",
        }
    except Exception as exc:  # noqa: BLE001 - degrade cleanly; never break the scan.
        return {"status": "unavailable", "ticker": symbol, "reason": str(exc)[:160]}


def _holder(node: dict[str, object]) -> dict[str, object]:
    return {
        "organization": node.get("organization") or "",
        "pct_held": _num(_raw(node.get("pctHeld"))),
        "position": _num(_raw(node.get("position"))),
        "pct_change": _num(_raw(node.get("pctChange"))),
    }


def _assess_candidate(candidate: dict[str, object], readings: dict[str, dict[str, object]]) -> dict[str, object]:
    tickers = [str(t).upper() for t in (candidate.get("tickers") or []) if str(t).strip()]
    if not tickers:
        return {"status": "no_ticker", "flow": "unknown",
                "summary_zh": "尚无确认 ticker，无法评估机构持仓流向。"}
    rows = [readings[t] for t in tickers if t in readings and readings[t].get("status") == "ok"]
    if not rows:
        return {"status": "unavailable", "flow": "unknown",
                "summary_zh": "未取得机构持仓数据（Yahoo 限流或无披露）。"}

    reading = rows[0]
    holders = [h for h in reading.get("holders", []) if isinstance(h, dict)]
    accumulators = sum(1 for h in holders if _num(h.get("pct_change")) > MOVE_THRESHOLD)
    reducers = sum(1 for h in holders if _num(h.get("pct_change")) < -MOVE_THRESHOLD)
    net_delta, base_position = 0.0, 0.0
    for h in holders:
        position = _num(h.get("position"))
        change = _num(h.get("pct_change"))
        if position <= 0 or change <= -1:
            continue
        prior = position / (1.0 + change)
        net_delta += position - prior
        base_position += position

    net_ratio = (net_delta / base_position) if base_position > 0 else 0.0
    flow = _flow(net_ratio, accumulators, reducers)
    return {
        "status": "ok",
        "ticker": reading.get("ticker"),
        "flow": flow,
        "institutions_pct_held": reading.get("institutions_pct_held"),
        "institutions_pct_display": _pct(reading.get("institutions_pct_held")),
        "institutions_count": reading.get("institutions_count"),
        "accumulators": accumulators,
        "reducers": reducers,
        "net_share_change": int(net_delta),
        "net_ratio_pct": round(net_ratio * 100, 2),
        "top_holders": holders[:5],
        "summary_zh": _summary_zh(flow, reading, accumulators, reducers, net_ratio),
        "source": reading.get("source"),
    }


def _flow(net_ratio: float, accumulators: int, reducers: int) -> str:
    if net_ratio >= NET_FLOW_THRESHOLD and accumulators >= reducers:
        return "accumulation"
    if net_ratio <= -NET_FLOW_THRESHOLD and reducers >= accumulators:
        return "distribution"
    if accumulators or reducers:
        return "mixed"
    return "stable"


def _summary_zh(flow: str, reading: dict[str, object], accumulators: int, reducers: int, net_ratio: float) -> str:
    held = _pct(reading.get("institutions_pct_held"))
    count = reading.get("institutions_count")
    base = f"机构持股 {held}，持有机构 {count if count is not None else 'n/a'} 家；前列机构加仓 {accumulators}、减仓 {reducers}（净 {net_ratio * 100:+.1f}%）。"
    head = {
        "accumulation": "聪明钱净加仓（机构在吸筹），与硬证据形成共振。",
        "distribution": "机构净减仓（聪明钱在派发），与利好背离需警惕。",
        "mixed": "机构增减仓分化，方向不明。",
        "stable": "机构持仓基本稳定。",
    }.get(flow, "")
    return f"{head} {base}"


def _pct(value: object) -> str:
    number = _num(value)
    return f"{number * 100:.1f}%" if number else "n/a"


def _num(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _candidate_tickers(candidates: list[dict[str, object]]) -> list[str]:
    output: list[str] = []
    for candidate in candidates:
        for ticker in candidate.get("tickers", []) or []:
            text = str(ticker).upper().strip()
            if text and text not in output:
                output.append(text)
    return output
