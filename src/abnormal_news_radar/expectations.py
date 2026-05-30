from __future__ import annotations

POSITIVE_MARKET_STATUSES = {"confirmed", "early_confirmation", "price_only_confirmation"}
SERENITY_LENS_SOURCE = "yan-labs/serenity-aleabitoreddit methodology"


def enrich_candidates_with_expectation_check(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["expectation_check"] = assess_expectation_check(row)
        enriched.append(row)
    return enriched


def assess_expectation_check(candidate: dict[str, object]) -> dict[str, object]:
    market = _dict_value(candidate.get("market_confirmation"))
    impact = _dict_value(candidate.get("impact_assessment"))
    quick_model = _dict_value(candidate.get("quick_model"))
    options_flow = _dict_value(candidate.get("options_flow"))
    status = str(market.get("status") or "")
    rows = [row for row in market.get("confirmations", []) or [] if isinstance(row, dict)]
    lead = _lead_confirmation(rows)
    impact_score = int(impact.get("impact_score") or 0)
    event_type = str(impact.get("event_type") or "news_signal")
    quick_status = str(quick_model.get("status") or "")
    market_read = _market_read(lead)
    evidence: list[str] = []

    if lead:
        evidence.extend(_market_evidence(lead))
    if impact:
        evidence.append(f"impact_score={impact_score}/5, event_type={event_type}")
    if quick_status:
        evidence.append(f"quick_model={quick_status}")
    if options_flow.get("status") and options_flow.get("status") != "no_flow_evidence":
        evidence.append(f"options_flow={options_flow.get('status')}, direction={options_flow.get('direction')}, score={options_flow.get('score')}/5")

    lens_hits = _serenity_lens_hits(candidate, impact, quick_model, options_flow)
    evidence.extend(lens_hits[:4])

    if status in {"no_ticker", "unavailable"} or not lead:
        result = {
            "status": "no_market_data",
            "score": 1,
            "setup_zh": "还不能判断是否存在预期差。",
            "pre_positioning_zh": "先补 ticker、交易所和价格/成交量数据，不应只凭新闻标题进入研究结论。",
        }
    elif status == "negative_reaction":
        result = {
            "status": "negative_divergence",
            "score": 1,
            "setup_zh": "新闻表面偏正面，但市场反应为负，优先解释分歧原因。",
            "pre_positioning_zh": "暂停埋伏判断；先查是否存在估值过高、指引低于预期、稀释、客户质量或宏观冲击。",
        }
    elif _is_extended(lead, status):
        result = {
            "status": "likely_already_priced_in",
            "score": 2,
            "setup_zh": "价格已经明显提前反应，当前更像确认而不是早期预期差。",
            "pre_positioning_zh": "不追高；这更像已经 price-in。只有出现回撤后基本面证据仍成立，或新增订单/客户/金额披露，才重新进入模型。",
        }
    elif _is_early_variant(lead, status, impact_score, quick_status, lens_hits, options_flow):
        result = {
            "status": "variant_not_fully_priced",
            "score": 5,
            "setup_zh": "存在早期预期差：新闻有基本面含义，市场刚开始确认，但尚未出现明显提前透支。",
            "pre_positioning_zh": "进入重点研究和小仓位候选池；下一步必须完成订单金额、收入弹性、毛利率和估值敏感性。",
        }
    elif _needs_price_in_check(lead, status, impact_score, quick_status):
        result = {
            "status": "needs_price_in_check",
            "score": 3,
            "setup_zh": "新闻重要，但缺少足够金额或成交量证据，无法判断是否还有预期差。",
            "pre_positioning_zh": "先做信息补全：金额、客户、交付时间、收入确认节奏和同业对比；确认前不把它升级为买入结论。",
        }
    else:
        result = {
            "status": "watch_only",
            "score": 2,
            "setup_zh": "当前证据不足以证明市场存在明显认知滞后。",
            "pre_positioning_zh": "保留观察；等待重复证据、成交量确认或更明确的财务量化信息。",
        }

    result.update(
        {
            "method": "transparent_rules_engine",
            "not_claimed": "This is an analyst triage heuristic, not a backtested trading formula.",
            "source_lens": SERENITY_LENS_SOURCE,
            "market_read": market_read,
            "evidence_zh": evidence,
            "rules_zh": _rules_zh(),
        }
    )
    return result


def _lead_confirmation(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {}
    return max(rows, key=_confirmation_rank)


def _confirmation_rank(row: dict[str, object]) -> tuple[float, float, float]:
    status_rank = {
        "confirmed": 5,
        "early_confirmation": 4,
        "price_only_confirmation": 3,
        "already_extended": 2,
        "unconfirmed": 1,
        "negative_reaction": 0,
        "unavailable": -1,
    }
    return (
        float(status_rank.get(str(row.get("status") or ""), -1)),
        _number(row.get("change_5d_pct")),
        _number(row.get("volume_ratio_vs_20d")),
    )


def _market_read(row: dict[str, object]) -> dict[str, object]:
    if not row:
        return {}
    return {
        "ticker": row.get("ticker"),
        "change_1d_pct": row.get("change_1d_pct"),
        "change_5d_pct": row.get("change_5d_pct"),
        "change_20d_pct": row.get("change_20d_pct"),
        "volume_ratio_vs_20d": row.get("volume_ratio_vs_20d"),
    }


def _market_evidence(row: dict[str, object]) -> list[str]:
    return [
        f"{row.get('ticker')}: 1d={_fmt_pct(row.get('change_1d_pct'))}, 5d={_fmt_pct(row.get('change_5d_pct'))}, 20d={_fmt_pct(row.get('change_20d_pct'))}, volume={_fmt_x(row.get('volume_ratio_vs_20d'))}",
    ]


def _serenity_lens_hits(
    candidate: dict[str, object],
    impact: dict[str, object],
    quick_model: dict[str, object],
    options_flow: dict[str, object],
) -> list[str]:
    text = _candidate_text(candidate).lower()
    hits = []
    if any(term in text for term in ("ramp", "production", "qualification", "qualified", "design win", "foundry")):
        hits.append("Serenity lens: qualification/ramp evidence can matter before reported revenue.")
    if any(term in text for term in ("contract", "order", "take-or-pay", "multi-year", "customer")):
        hits.append("Serenity lens: signed demand and counterparty quality must be checked before conviction.")
    if any(term in text for term in ("optical", "photonics", "cpo", "inp", "substrate", "hbm", "memory", "power", "grid")):
        hits.append("Serenity lens: possible upstream bottleneck or AI infrastructure chain signal.")
    if quick_model.get("status") == "blocked_missing_amount":
        hits.append("Serenity lens: no disclosed amount means the thesis is not yet valuation-proven.")
    if str(impact.get("event_type") or "") in {"production_ramp", "design_win", "capacity_commitment"}:
        hits.append("Serenity lens: pre-volume evidence should be tracked, but current revenue is not enough.")
    if options_flow.get("status") == "supportive_flow":
        hits.append("Options-flow lens: bullish flow is supportive only because it aligns with other evidence.")
    elif options_flow.get("status") in {"bearish_flow", "conflicting_flow", "mixed_flow"}:
        hits.append("Options-flow lens: flow is conflicting or mixed, so do not treat it as bullish confirmation.")
    return hits


def _is_extended(lead: dict[str, object], status: str) -> bool:
    change_5d = _number(lead.get("change_5d_pct"))
    change_20d = _number(lead.get("change_20d_pct"))
    volume = _number(lead.get("volume_ratio_vs_20d"))
    if status == "already_extended":
        return True
    if change_20d >= 18 and change_5d < 4:
        return True
    if change_20d >= 15 and change_5d >= 8:
        return True
    if status == "price_only_confirmation" and change_20d >= 12 and volume < 1.1:
        return True
    return False


def _is_early_variant(
    lead: dict[str, object],
    status: str,
    impact_score: int,
    quick_status: str,
    lens_hits: list[str],
    options_flow: dict[str, object],
) -> bool:
    change_1d = _number(lead.get("change_1d_pct"))
    change_5d = _number(lead.get("change_5d_pct"))
    change_20d = _number(lead.get("change_20d_pct"))
    volume = _number(lead.get("volume_ratio_vs_20d"))
    market_confirming = status in POSITIVE_MARKET_STATUSES and (change_1d >= 1 or change_5d >= 2)
    not_chased = change_20d < 12
    supportive_flow = options_flow.get("status") == "supportive_flow" and int(options_flow.get("score") or 0) >= 3
    enough_signal = impact_score >= 4 or len(lens_hits) >= 2 or supportive_flow
    volume_support = status in {"confirmed", "early_confirmation"} or volume >= 1.2
    model_not_disqualifying = quick_status != "not_queued"
    return market_confirming and not_chased and enough_signal and volume_support and model_not_disqualifying


def _needs_price_in_check(lead: dict[str, object], status: str, impact_score: int, quick_status: str) -> bool:
    change_5d = _number(lead.get("change_5d_pct"))
    change_20d = _number(lead.get("change_20d_pct"))
    if impact_score >= 4 and status in POSITIVE_MARKET_STATUSES:
        return True
    if quick_status == "blocked_missing_amount" and (change_5d >= 2 or change_20d >= 8):
        return True
    return False


def _rules_zh() -> list[str]:
    return [
        "先看基本面事件强度：订单、量产、设计定点、产能、政策冲击优先于普通新闻。",
        "再看市场是否刚开始确认：1日/5日上涨且成交量放大，比单纯标题更有价值。",
        "如果20日涨幅已经很大而成交量没有同步放大，默认可能已经 price-in。",
        "没有披露金额时，只能进入研究队列，不能给出估值确定性。",
        "这套规则吸收了上游瓶颈、机构认知滞后、pre-ramp 证据等 Serenity lens，但不复制任何人的交易。",
    ]


def _candidate_text(candidate: dict[str, object]) -> str:
    article = candidate.get("article") if isinstance(candidate.get("article"), dict) else {}
    values = [
        candidate.get("company_name"),
        candidate.get("reason"),
        article.get("title"),
        article.get("summary"),
        *(candidate.get("matched_terms") or []),
    ]
    return " ".join(str(value) for value in values if value)


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_pct(value: object) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_x(value: object) -> str:
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return "n/a"
