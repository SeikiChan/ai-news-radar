from __future__ import annotations

from .financials import enrich_candidates_with_financial_snapshots
from .price_volume import enrich_candidates_with_market_confirmation


def enrich_candidates_with_readthrough_analysis(
    candidates: list[dict[str, object]],
    max_tickers: int = 8,
) -> list[dict[str, object]]:
    mentioned = _mentioned_rows(candidates, max_tickers=max_tickers)
    mentioned = enrich_candidates_with_financial_snapshots(mentioned, max_tickers=max_tickers) if mentioned else []
    mentioned = enrich_candidates_with_market_confirmation(mentioned, max_tickers=max_tickers) if mentioned else []
    by_ticker = {str(row.get("tickers", [""])[0]).upper(): row for row in mentioned if row.get("tickers")}

    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["readthrough_analysis"] = _candidate_readthrough(row, by_ticker)
        enriched.append(row)
    return enriched


def _mentioned_rows(candidates: list[dict[str, object]], max_tickers: int) -> list[dict[str, object]]:
    output = []
    seen = set()
    for candidate in candidates:
        for item in _mentioned_items(candidate):
            ticker = str(item.get("ticker") or "").upper().strip()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            output.append(
                {
                    "company_name": str(item.get("name") or ticker),
                    "tickers": [ticker],
                    "score": 0,
                    "status": f"{item.get('source_context') or 'readthrough'}_candidate",
                    "article": candidate.get("article") if isinstance(candidate.get("article"), dict) else {},
                }
            )
            if len(output) >= max_tickers:
                return output
    return output


def _mentioned_items(candidate: dict[str, object]) -> list[dict[str, object]]:
    items = []
    earnings = candidate.get("earnings_analysis") if isinstance(candidate.get("earnings_analysis"), dict) else {}
    technology = candidate.get("technology_intel") if isinstance(candidate.get("technology_intel"), dict) else {}
    for source_name, source in (("earnings_readthrough", earnings), ("technology_readthrough", technology)):
        for item in source.get("mentioned_companies", []) or []:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["source_context"] = row.get("source_context") or source_name
            items.append(row)
    return items


def _candidate_readthrough(candidate: dict[str, object], by_ticker: dict[str, dict[str, object]]) -> dict[str, object]:
    mentioned = _mentioned_items(candidate)
    if not mentioned:
        return {
            "status": "no_readthrough",
            "summary_zh": "财报或技术资料中暂未识别到可跟踪的二阶公司。",
            "items": [],
        }

    items = []
    for item in mentioned:
        ticker = str(item.get("ticker") or "").upper()
        row = by_ticker.get(ticker, {})
        financial = row.get("financial_snapshot") if isinstance(row.get("financial_snapshot"), dict) else {}
        market = row.get("market_confirmation") if isinstance(row.get("market_confirmation"), dict) else {}
        status = _item_status(financial, market)
        items.append(
            {
                "ticker": ticker,
                "name": item.get("name"),
                "matched_alias": item.get("matched_alias"),
                "themes": item.get("themes") or [],
                "source_context": item.get("source_context") or "readthrough",
                "reason_zh": item.get("reason_zh"),
                "financial_snapshot": financial,
                "market_confirmation": market,
                "status": status,
                "decision_zh": _decision_zh(status, financial, market),
            }
        )

    priority = sum(1 for item in items if item["status"] in {"confirmed_readthrough", "needs_model"})
    technology_count = sum(1 for item in items if str(item.get("source_context") or "").startswith("technology"))
    earnings_count = len(items) - technology_count
    return {
        "status": "active" if priority else "watching",
        "summary_zh": f"识别到 {len(items)} 个二阶 read-through 公司；财报线索 {earnings_count}，技术线索 {technology_count}，其中 {priority} 个需要优先检查。",
        "items": items,
        "rules_zh": [
            "被财报、技术博客、论文或研究报告点名的供应商/客户/合作方不是自动买入标的，只是二阶研究线索。",
            "优先看：是否属于主线产业、是否有价格/成交量确认、是否有收入基数和财务影响可建模。",
            "如果只有技术路线图，没有订单/财报/价格确认，只进入观察池，不进入买入结论。",
        ],
    }


def _item_status(financial: dict[str, object], market: dict[str, object]) -> str:
    market_status = str(market.get("status") or "")
    financial_status = str(financial.get("status") or "")
    if market_status in {"confirmed", "early_confirmation"} and financial_status in {"ok", "partial"}:
        return "confirmed_readthrough"
    if market_status in {"price_only_confirmation", "confirmed", "early_confirmation"}:
        return "needs_model"
    if market_status == "negative_reaction":
        return "conflicting"
    return "watch_only"


def _decision_zh(status: str, financial: dict[str, object], market: dict[str, object]) -> str:
    if status == "confirmed_readthrough":
        return "二阶线索有市场确认和基础财务事实，进入动态观察池候选。"
    if status == "needs_model":
        return "有价格反应但财务事实或成交量不足，先补模型。"
    if status == "conflicting":
        return "市场反应冲突，先解释分歧，不做埋伏结论。"
    return "仅观察；等待新闻重复、市场确认、财报披露或更明确财务影响。"
