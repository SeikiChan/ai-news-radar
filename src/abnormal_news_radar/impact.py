from __future__ import annotations

import re

HARD_EVENT_TYPES: tuple[str, ...] = (
    "production_ramp",
    "order_contract",
    "design_win",
    "capacity_commitment",
    "policy_shock",
)


def enrich_candidates_with_impact_assessment(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["impact_assessment"] = assess_candidate_impact(row)
        enriched.append(row)
    return enriched


def assess_candidate_impact(candidate: dict[str, object]) -> dict[str, object]:
    article = candidate.get("article") if isinstance(candidate.get("article"), dict) else {}
    text = _candidate_text(candidate, article)
    event_type = _event_type(text, candidate.get("matched_terms"))
    amounts = _amount_mentions(text)
    market_status = _market_status(candidate)
    has_ticker = bool(candidate.get("tickers"))
    evidence_score = float(candidate.get("score", 0) or 0)
    impact_score = _impact_score(event_type, amounts, market_status, has_ticker, evidence_score)
    materiality = _materiality(event_type, amounts, impact_score)

    return {
        "event_type": event_type,
        "impact_score": impact_score,
        "materiality": materiality,
        "amount_mentions": amounts,
        "market_status": market_status,
        "action_zh": _action_zh(impact_score, market_status),
        "summary_zh": _summary_zh(event_type, materiality, amounts, market_status),
        "variant_perception_zh": _variant_perception_zh(event_type, amounts, market_status),
        "model_inputs_needed": _model_inputs_needed(event_type, amounts, has_ticker),
        "workplan_zh": _workplan_zh(event_type, impact_score, market_status),
        "limitations_zh": "这是基于公开新闻文本的一阶影响判断；未接入公司收入基数、市场一致预期和正式估值模型前，不能作为买入建议。",
    }


def _impact_score(
    event_type: str,
    amounts: list[dict[str, object]],
    market_status: str,
    has_ticker: bool,
    evidence_score: float,
) -> int:
    score = 0
    if event_type in HARD_EVENT_TYPES:
        score += 2
    elif event_type in {"earnings_update", "product_launch"}:
        score += 1
    if amounts:
        score += 1
    if has_ticker:
        score += 1
    if evidence_score >= 35:
        score += 1
    if market_status in {"confirmed", "early_confirmation", "price_only_confirmation"}:
        score += 1
    elif market_status == "negative_reaction":
        score -= 1
    return max(0, min(score, 5))


def _event_type(text: str, matched_terms: object) -> str:
    terms = " ".join(str(term).lower() for term in matched_terms or [])
    combined = f"{text} {terms}"
    if _has_any(combined, ("executive order", "tariff", "tariffs", "export control", "sanctions", "white house", "president trump")):
        return "policy_shock"
    if _has_any(combined, ("production ramp", "ramp production", "mass production", "high-volume production", "volume production")):
        return "production_ramp"
    if _has_any(combined, ("purchase order", "production order", "contract", "agreement", "awarded", "booking", "bookings")):
        return "order_contract"
    if _has_any(combined, ("design win", "qualification", "qualified", "customer win")):
        return "design_win"
    if _has_any(combined, ("capacity reservation", "capacity commitment", "prepayment", "advance payment")):
        return "capacity_commitment"
    if _has_any(combined, ("reports first quarter", "reports second quarter", "financial results", "earnings")):
        return "earnings_update"
    if _has_any(combined, ("launches", "introduces", "unveils", "new product")):
        return "product_launch"
    return "news_signal"


def _amount_mentions(text: str) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    patterns = [
        re.compile(r"(?i)(?:\$|us\$)\s*([0-9]+(?:\.[0-9]+)?)(?:\s*)(billion|bn|million|m)?"),
        re.compile(r"(?i)\b([0-9]+(?:\.[0-9]+)?)\s*(billion|bn|million)\s+(?:production order|order|contract|bookings|revenue|backlog)"),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = float(match.group(1))
            unit = (match.group(2) or "").lower()
            value_millions = _to_millions(value, unit)
            mention = match.group(0).strip()
            row = {
                "mention": mention,
                "value_millions_usd": value_millions,
            }
            if row not in output:
                output.append(row)
    return output[:5]


def _to_millions(value: float, unit: str) -> float:
    if unit in {"billion", "bn"}:
        return round(value * 1000, 2)
    return round(value, 2)


def _materiality(event_type: str, amounts: list[dict[str, object]], impact_score: int) -> str:
    largest = max((float(row.get("value_millions_usd", 0) or 0) for row in amounts), default=0.0)
    if largest >= 500:
        return "high_disclosed_amount"
    if largest >= 100:
        return "medium_disclosed_amount"
    if largest > 0:
        return "small_disclosed_amount"
    if event_type in {"production_ramp", "capacity_commitment"} and impact_score >= 3:
        return "potentially_material_no_amount"
    if event_type == "policy_shock":
        return "scenario_dependent"
    return "undetermined"


def _action_zh(impact_score: int, market_status: str) -> str:
    if impact_score >= 4 and market_status in {"confirmed", "early_confirmation", "price_only_confirmation"}:
        return "进入建模队列：先做收入/毛利/估值敏感性，不直接买入。"
    if impact_score >= 3:
        return "进入研究队列：补收入基数、客户/产品暴露和预期差。"
    if market_status == "negative_reaction":
        return "先解释市场为什么卖，不要只看新闻标题。"
    return "保持观察：证据还不足以占用深度建模时间。"


def _summary_zh(event_type: str, materiality: str, amounts: list[dict[str, object]], market_status: str) -> str:
    amount_text = "；".join(
        f"{row.get('mention')}≈{float(row.get('value_millions_usd', 0)):.1f}百万美元"
        for row in amounts
    )
    if not amount_text:
        amount_text = "未披露可量化金额"
    return f"事件类型={event_type}；重要性={materiality}；金额线索={amount_text}；市场确认={market_status or 'unknown'}。"


def _variant_perception_zh(event_type: str, amounts: list[dict[str, object]], market_status: str) -> str:
    if market_status == "confirmed":
        return "市场已经用价格和成交量确认，核心问题变成：确认幅度是否仍低估财务影响。"
    if market_status == "price_only_confirmation":
        return "价格有反应但成交量不足，可能是预期提前反映或流动性不足；需要确认是否真的形成增量买盘。"
    if market_status == "negative_reaction":
        return "市场反应与新闻表面方向相反，优先查是否存在毛利、产能、竞争或估值担忧。"
    if amounts:
        return "新闻披露了金额线索，但缺少公司收入基数和市场一致预期，暂不能判断是否超预期。"
    if event_type in {"production_ramp", "design_win", "capacity_commitment"}:
        return "事件性质偏硬，但缺少金额、客户占比和 ramp 时间表，预期差仍未闭环。"
    return "当前信息还不足以形成差异化观点。"


def _model_inputs_needed(event_type: str, amounts: list[dict[str, object]], has_ticker: bool) -> list[str]:
    inputs = ["latest revenue base", "gross margin sensitivity", "consensus expectations", "valuation multiple / peer comp"]
    if not has_ticker:
        inputs.insert(0, "confirmed ticker and exchange")
    if not amounts:
        inputs.insert(0, "disclosed or estimated order / revenue value")
    if event_type == "policy_shock":
        inputs.extend(["policy effective date", "country / product exposure", "tariff or sanction pass-through assumptions"])
    if event_type == "production_ramp":
        inputs.extend(["ramp timing", "customer identity", "capacity allocation"])
    return inputs


def _workplan_zh(event_type: str, impact_score: int, market_status: str) -> list[str]:
    plan = []
    if impact_score >= 4:
        plan.append("今天优先做一页 quick model：收入增量、毛利影响、估值敏感性。")
    else:
        plan.append("先收集缺失输入，避免在信息不足时过度建模。")
    if market_status in {"confirmed", "early_confirmation", "price_only_confirmation"}:
        plan.append("检查新闻发布时间前后的价格路径，判断是否已提前 price in。")
    if event_type in {"production_ramp", "order_contract"}:
        plan.append("把订单/生产节奏映射到未来 4 个季度收入，而不是只看标题。")
    if event_type == "policy_shock":
        plan.append("建立受益/受损行业清单，区分一阶冲击和二阶供应链传导。")
    return plan


def _candidate_text(candidate: dict[str, object], article: dict[str, object]) -> str:
    parts = [
        str(candidate.get("company_name") or ""),
        str(article.get("title") or ""),
        str(article.get("summary") or ""),
        str(candidate.get("reason") or ""),
    ]
    return " ".join(parts).lower()


def _market_status(candidate: dict[str, object]) -> str:
    market = candidate.get("market_confirmation")
    if isinstance(market, dict):
        return str(market.get("status") or "")
    return ""


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
