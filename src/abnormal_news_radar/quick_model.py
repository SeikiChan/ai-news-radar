from __future__ import annotations


def enrich_candidates_with_quick_model(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["quick_model"] = build_quick_model(row)
        enriched.append(row)
    return enriched


def build_quick_model(candidate: dict[str, object]) -> dict[str, object]:
    impact = candidate.get("impact_assessment") if isinstance(candidate.get("impact_assessment"), dict) else {}
    impact_score = int(impact.get("impact_score") or 0)
    if impact_score < 4:
        return {
            "status": "not_queued",
            "summary_zh": "未进入 quick model：财务影响分不足 4/5。",
            "inputs": {},
            "missing_inputs": [],
            "scenarios": [],
        }

    amounts = impact.get("amount_mentions") if isinstance(impact.get("amount_mentions"), list) else []
    amount = _largest_amount(amounts)
    event_type = str(impact.get("event_type") or "news_signal")
    tickers = [str(ticker) for ticker in candidate.get("tickers", []) or []]
    primary_ticker = tickers[0] if tickers else ""
    financial = _primary_financial_snapshot(candidate)

    if amount is None:
        return _blocked_model(primary_ticker, event_type, impact, financial)

    base_revenue_increment = float(amount["value_millions_usd"])
    scenarios = _scenario_rows(base_revenue_increment, financial)
    return {
        "status": "ready_for_assumptions",
        "primary_ticker": primary_ticker,
        "event_type": event_type,
        "summary_zh": "已生成 quick model 骨架：披露金额可作为收入增量起点，但毛利率、收入基数、一致预期和估值倍数仍需补齐。",
        "known_inputs": {
            "disclosed_amount_musd": base_revenue_increment,
            "amount_source_text": amount.get("mention", ""),
            "latest_revenue_base_musd": financial.get("revenue_musd"),
            "gross_margin_assumption_pct": financial.get("gross_margin_pct"),
            "financial_source": financial.get("source"),
            "financial_period_end": financial.get("period_end"),
        },
        "missing_inputs": _missing_inputs(impact, has_amount=True, financial=financial),
        "formulas": [
            "revenue_materiality_pct = disclosed_or_estimated_revenue_increment / latest_revenue_base",
            "gross_profit_increment = revenue_increment * gross_margin_assumption",
            "implied_value_increment = revenue_increment * relevant_ev_sales_or_gp_multiple",
            "variant_perception = modeled_impact - consensus_embedded_expectation",
        ],
        "scenarios": scenarios,
        "analyst_instruction_zh": "先填收入基数和毛利率，再判断这条新闻是否足以改变未来 4 个季度预期；不要直接用新闻金额推目标价。",
    }


def _blocked_model(
    primary_ticker: str,
    event_type: str,
    impact: dict[str, object],
    financial: dict[str, object],
) -> dict[str, object]:
    return {
        "status": "blocked_missing_amount",
        "primary_ticker": primary_ticker,
        "event_type": event_type,
        "summary_zh": "进入建模队列，但缺少订单/收入金额，当前只能生成建模框架，不能做数字敏感性。",
        "known_inputs": {
            "latest_revenue_base_musd": financial.get("revenue_musd"),
            "gross_margin_assumption_pct": financial.get("gross_margin_pct"),
            "financial_source": financial.get("source"),
            "financial_period_end": financial.get("period_end"),
        },
        "missing_inputs": _missing_inputs(impact, has_amount=False, financial=financial),
        "formulas": [
            "revenue_increment = unit_volume * asp * recognition_probability",
            "revenue_materiality_pct = revenue_increment / latest_revenue_base",
            "gross_profit_increment = revenue_increment * gross_margin_assumption",
            "variant_perception = modeled_impact - consensus_embedded_expectation",
        ],
        "scenarios": [
            _empty_scenario("bear", "Low conversion / delayed ramp"),
            _empty_scenario("base", "Management case / normal ramp"),
            _empty_scenario("bull", "Fast conversion / stronger customer pull"),
        ],
        "analyst_instruction_zh": "先找金额、产量、ASP 或客户采购节奏；缺这些输入时不能把 production ramp 量化成 EPS。",
    }


def _scenario_rows(base_revenue_increment: float, financial: dict[str, object]) -> list[dict[str, object]]:
    return [
        _scenario("bear", "50% conversion of disclosed amount", base_revenue_increment * 0.5, financial),
        _scenario("base", "100% conversion of disclosed amount", base_revenue_increment, financial),
        _scenario("bull", "150% conversion of disclosed amount", base_revenue_increment * 1.5, financial),
    ]


def _scenario(name: str, assumption: str, revenue_increment: float, financial: dict[str, object]) -> dict[str, object]:
    revenue_base = _to_float(financial.get("revenue_musd"))
    gross_margin = _to_float(financial.get("gross_margin_pct"))
    revenue_materiality = None
    if revenue_base is not None and revenue_base != 0:
        revenue_materiality = round((revenue_increment / revenue_base) * 100, 2)
    gross_profit_increment = None
    if gross_margin is not None:
        gross_profit_increment = round(revenue_increment * (gross_margin / 100), 2)
    return {
        "case": name,
        "assumption": assumption,
        "revenue_increment_musd": round(revenue_increment, 2),
        "latest_revenue_base_musd": revenue_base,
        "revenue_materiality_pct": revenue_materiality,
        "gross_margin_assumption_pct": gross_margin,
        "gross_profit_increment_musd": gross_profit_increment,
        "valuation_multiple": None,
        "implied_value_increment_musd": None,
        "status": "needs_valuation_multiple" if revenue_base is not None and gross_margin is not None else "needs_inputs",
    }


def _empty_scenario(name: str, assumption: str) -> dict[str, object]:
    return {
        "case": name,
        "assumption": assumption,
        "revenue_increment_musd": None,
        "latest_revenue_base_musd": None,
        "revenue_materiality_pct": None,
        "gross_margin_assumption_pct": None,
        "gross_profit_increment_musd": None,
        "valuation_multiple": None,
        "implied_value_increment_musd": None,
        "status": "blocked_missing_revenue_increment",
    }


def _largest_amount(amounts: list[object]) -> dict[str, object] | None:
    valid = [row for row in amounts if isinstance(row, dict) and row.get("value_millions_usd") is not None]
    if not valid:
        return None
    return max(valid, key=lambda row: float(row.get("value_millions_usd") or 0))


def _missing_inputs(impact: dict[str, object], has_amount: bool, financial: dict[str, object]) -> list[str]:
    needed = [str(item) for item in impact.get("model_inputs_needed", []) or []]
    if has_amount:
        needed = [item for item in needed if item != "disclosed or estimated order / revenue value"]
    if financial.get("revenue_musd") is not None:
        needed = [item for item in needed if item != "latest revenue base"]
    if financial.get("gross_margin_pct") is not None:
        needed = [item for item in needed if item != "gross margin sensitivity"]
    return needed


def _primary_financial_snapshot(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("financial_snapshot")
    if not isinstance(value, dict):
        return {}
    snapshots = value.get("snapshots")
    if not isinstance(snapshots, list):
        return {}
    for snapshot in snapshots:
        if isinstance(snapshot, dict) and snapshot.get("revenue_musd") is not None:
            return snapshot
    return {}


def _to_float(value: object) -> float | None:
    try:
        if value in {None, "", ".", "-"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
