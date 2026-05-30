from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

USER_AGENT = "AI-News-Radar/0.1 research-tool contact=local@example.com"
FETCH_TIMEOUT_SECONDS = 8
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
GROSS_PROFIT_CONCEPTS = ("GrossProfit",)
COST_REVENUE_CONCEPTS = (
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",
    "CostOfGoodsSold",
    "CostOfRevenueGoodsAndServices",
)


def enrich_candidates_with_financial_snapshots(
    candidates: list[dict[str, object]],
    fetcher: object | None = None,
    max_tickers: int = 12,
) -> list[dict[str, object]]:
    fetch = fetcher or _fetch_text
    tickers = _candidate_tickers(candidates)[:max_tickers]
    snapshots: dict[str, dict[str, object]] = {}
    cik_map = _load_cik_map(fetch)
    for ticker in tickers:
        snapshots[ticker] = fetch_financial_snapshot(ticker, cik_map, fetch)

    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["financial_snapshot"] = _candidate_snapshot(row, snapshots)
        enriched.append(row)
    return enriched


def fetch_financial_snapshot(
    ticker: str,
    cik_map: dict[str, dict[str, object]] | None = None,
    fetcher: object | None = None,
) -> dict[str, object]:
    symbol = ticker.strip().upper()
    if not symbol:
        return _snapshot_unavailable(symbol, "missing ticker")
    fetch = fetcher or _fetch_text
    cik_lookup = cik_map if cik_map is not None else _load_cik_map(fetch)
    company = cik_lookup.get(symbol)
    if not company:
        return _snapshot_unavailable(symbol, "ticker not found in SEC company_tickers.json")

    cik = int(company["cik"])
    source_url = _companyfacts_url(cik)
    try:
        payload = json.loads(fetch(source_url))
        facts = payload.get("facts", {}).get("us-gaap", {})
        revenue = _latest_annual_fact(facts, REVENUE_CONCEPTS)
        gross_profit = _latest_annual_fact(facts, GROSS_PROFIT_CONCEPTS)
        cost_revenue = _latest_annual_fact(facts, COST_REVENUE_CONCEPTS)
    except Exception as exc:  # noqa: BLE001 - one ticker must not fail the scan.
        return _snapshot_unavailable(symbol, str(exc), source_url, cik=cik, company_name=str(company.get("name") or ""))

    if revenue is None:
        return {
            "ticker": symbol,
            "status": "missing",
            "company_name": str(company.get("name") or ""),
            "cik": cik,
            "source": "SEC companyfacts",
            "source_url": source_url,
            "missing_fields": ["annual revenue"],
            "summary_zh": f"{symbol} SEC companyfacts 未找到可用年度收入字段。",
        }

    revenue_musd = _usd_to_millions(float(revenue["value"]))
    gross_profit_musd = _fact_to_musd(gross_profit)
    cost_revenue_musd = _fact_to_musd(cost_revenue)
    gross_margin_pct = _gross_margin_pct(revenue_musd, gross_profit_musd, cost_revenue_musd)
    missing_fields = []
    if gross_margin_pct is None:
        missing_fields.append("gross margin")
    snapshot = {
        "ticker": symbol,
        "status": "ok" if not missing_fields else "partial",
        "company_name": str(company.get("name") or payload.get("entityName") or ""),
        "cik": cik,
        "fiscal_year": revenue.get("fy"),
        "period_end": revenue.get("end"),
        "filed": revenue.get("filed"),
        "form": revenue.get("form"),
        "revenue_musd": revenue_musd,
        "revenue_concept": revenue.get("concept"),
        "gross_profit_musd": gross_profit_musd,
        "gross_profit_concept": gross_profit.get("concept") if gross_profit else None,
        "cost_revenue_musd": cost_revenue_musd,
        "cost_revenue_concept": cost_revenue.get("concept") if cost_revenue else None,
        "gross_margin_pct": gross_margin_pct,
        "source": "SEC companyfacts",
        "source_url": source_url,
        "missing_fields": missing_fields,
        "summary_zh": _snapshot_summary_zh(symbol, revenue_musd, gross_margin_pct, revenue),
    }
    return snapshot


def _load_cik_map(fetch: object) -> dict[str, dict[str, object]]:
    payload = json.loads(fetch(SEC_TICKERS_URL))
    output = {}
    if isinstance(payload, dict):
        rows = payload.values()
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper().strip()
        cik = row.get("cik_str")
        if ticker and cik is not None:
            output[ticker] = {
                "cik": int(cik),
                "name": str(row.get("title") or ""),
            }
    return output


def _latest_annual_fact(facts: dict[str, object], concepts: tuple[str, ...]) -> dict[str, object] | None:
    candidates = []
    for concept in concepts:
        fact = facts.get(concept)
        if not isinstance(fact, dict):
            continue
        units = fact.get("units", {})
        rows = units.get("USD") if isinstance(units, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if not _is_annual(row):
                continue
            value = _to_float(row.get("val"))
            if value is None:
                continue
            item = dict(row)
            item["concept"] = concept
            item["value"] = value
            candidates.append(item)
    if not candidates:
        return None
    candidates.sort(key=lambda row: (str(row.get("end") or ""), str(row.get("filed") or "")))
    return candidates[-1]


def _is_annual(row: dict[str, object]) -> bool:
    form = str(row.get("form") or "")
    fp = str(row.get("fp") or "")
    if fp == "FY" and form in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
        return True
    frame = str(row.get("frame") or "")
    return frame.startswith("CY") and not any(frame.endswith(f"Q{quarter}") for quarter in range(1, 5))


def _candidate_snapshot(candidate: dict[str, object], snapshots: dict[str, dict[str, object]]) -> dict[str, object]:
    tickers = [str(ticker).upper() for ticker in candidate.get("tickers", []) or [] if str(ticker).strip()]
    if not tickers:
        return {
            "status": "no_ticker",
            "summary_zh": "没有已确认 ticker，无法拉取 SEC 财务事实。",
            "snapshots": [],
        }
    rows = [snapshots[ticker] for ticker in tickers if ticker in snapshots]
    if not rows:
        return {
            "status": "unavailable",
            "summary_zh": "已识别 ticker，但本次扫描没有拿到 SEC 财务事实。",
            "snapshots": [],
        }
    row_statuses = {str(row.get("status") or "missing") for row in rows}
    if row_statuses == {"ok"}:
        status = "ok"
    elif "ok" in row_statuses:
        status = "partial"
    else:
        status = str(rows[0].get("status") or "missing")
    return {
        "status": status,
        "primary_ticker": str(rows[0].get("ticker") or tickers[0]),
        "summary_zh": _combined_summary_zh(rows),
        "snapshots": rows,
    }


def _combined_summary_zh(rows: list[dict[str, object]]) -> str:
    parts = []
    for row in rows[:3]:
        revenue = row.get("revenue_musd")
        gross_margin = row.get("gross_margin_pct")
        parts.append(
            f"{row.get('ticker')}: revenue={_fmt_musd(revenue)}, gross_margin={_fmt_pct(gross_margin)}, FY={row.get('fiscal_year') or 'n/a'}"
        )
    return "；".join(parts)


def _snapshot_summary_zh(symbol: str, revenue_musd: float, gross_margin_pct: float | None, revenue: dict[str, object]) -> str:
    return (
        f"{symbol} SEC 最新年度收入={_fmt_musd(revenue_musd)}，"
        f"毛利率={_fmt_pct(gross_margin_pct)}，"
        f"FY={revenue.get('fy') or 'n/a'}，filed={revenue.get('filed') or 'n/a'}。"
    )


def _gross_margin_pct(
    revenue_musd: float | None,
    gross_profit_musd: float | None,
    cost_revenue_musd: float | None,
) -> float | None:
    if revenue_musd is None or revenue_musd == 0:
        return None
    if gross_profit_musd is not None:
        return round((gross_profit_musd / revenue_musd) * 100, 2)
    if cost_revenue_musd is not None:
        return round(((revenue_musd - cost_revenue_musd) / revenue_musd) * 100, 2)
    return None


def _fact_to_musd(fact: dict[str, object] | None) -> float | None:
    if not fact:
        return None
    return _usd_to_millions(float(fact["value"]))


def _usd_to_millions(value: float) -> float:
    return round(value / 1_000_000, 2)


def _companyfacts_url(cik: int) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def _snapshot_unavailable(symbol: str, reason: str, source_url: str = "", cik: int | None = None, company_name: str = "") -> dict[str, object]:
    return {
        "ticker": symbol,
        "status": "unavailable",
        "company_name": company_name,
        "cik": cik,
        "reason": reason,
        "source": "SEC companyfacts",
        "source_url": source_url,
        "missing_fields": ["annual revenue", "gross margin"],
        "summary_zh": f"{symbol or 'ticker'} SEC 财务事实不可用：{reason}",
    }


def _candidate_tickers(candidates: list[dict[str, object]]) -> list[str]:
    output: list[str] = []
    for candidate in candidates:
        for ticker in candidate.get("tickers", []) or []:
            text = str(ticker).upper().strip()
            if text and text not in output:
                output.append(text)
    return output


def _to_float(value: object) -> float | None:
    try:
        if value in {None, "", ".", "-"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_musd(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.1f}百万美元"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "n/a"
