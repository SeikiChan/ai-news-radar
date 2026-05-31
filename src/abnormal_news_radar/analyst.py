from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_MIN_SCORE = 10.0
DEFAULT_LIMIT_PER_SOURCE = 40
DEFAULT_SIGNAL_LIMIT = 40

ANALYST_SCAN_POLICY = {
    "min_score": DEFAULT_MIN_SCORE,
    "limit_per_source": DEFAULT_LIMIT_PER_SOURCE,
    "signal_limit": DEFAULT_SIGNAL_LIMIT,
    "description": "Balanced public-source scan: enough depth to catch hard-evidence items without turning the terminal into a noisy news firehose.",
    "schedule": [
        "Every 5 minutes during 08:00-20:00 America/New_York on weekdays for news, earnings, and price confirmation.",
        "Every 15 minutes during 04:00-08:00 and 20:00-22:00 America/New_York on weekdays.",
        "Every 60 minutes overnight and weekends.",
    ],
    "why_not_every_minute": "A full public-source scan every minute is noisy and can overload free sources. Use sub-minute polling only for a small hot list such as imminent earnings releases or explicit breaking events.",
}

MARKET_TZ = ZoneInfo("America/New_York")


def build_daily_brief(
    signals: list[dict[str, object]],
    candidates: list[dict[str, object]],
    last_scan: dict[str, object],
    source_count: int,
    watchlist_count: int,
    market_source_count: int = 0,
    market_regime: dict[str, object] | None = None,
    earnings_calendar: dict[str, object] | None = None,
) -> dict[str, object]:
    report_items = _analyst_report_items(candidates)
    urgent = [item for item in report_items if item.get("action") == "research_now"]
    regime = market_regime or _disconnected_market_regime()
    earnings = earnings_calendar or _disconnected_earnings_calendar()
    dynamic_watchlist = _dynamic_watchlist_items(candidates, regime)
    data_gaps = _data_gaps(report_items, earnings, regime)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": _headline(len(signals), len(candidates), len(urgent)),
        "headline_zh": _headline_zh(len(signals), len(candidates), len(urgent)),
        "counts": {
            "sources": source_count,
            "market_sources": market_source_count,
            "seed_watchlist": watchlist_count,
            "dynamic_watchlist": len(dynamic_watchlist),
            "articles_reviewed": int(last_scan.get("fetched_count", 0) or 0),
            "signals": len(signals),
            "discoveries": len(candidates),
            "review_items": len(report_items),
            "report_items": len(report_items),
            "urgent_items": len(urgent),
        },
        "scan_policy": ANALYST_SCAN_POLICY,
        "automation": _automation_state(last_scan),
        "morning_checklist": [
            _check_item("宏观状态", str(regime.get("status") or "unknown"), str(regime.get("summary") or "")),
            _check_item("财报日历", str(earnings.get("status") or "unknown"), str(earnings.get("summary_zh") or "")),
            _check_item("新闻发现", "active", "系统正在扫描公开新闻线、IR 页面、SEC feed 和行业垂直媒体。"),
            _check_item("公司证据", "active", "硬证据关键词会被打分，并保留原文链接。"),
            _check_item("价格/成交量确认", _market_confirmation_check_status(report_items), _market_confirmation_check_detail(report_items)),
            _check_item("财务影响初判", _impact_check_status(report_items), _impact_check_detail(report_items)),
            _check_item("SEC 财务事实", _financial_check_status(report_items), _financial_check_detail(report_items)),
            _check_item("Quick Model", _quick_model_check_status(report_items), _quick_model_check_detail(report_items)),
            _check_item("财报快拆", _earnings_analysis_check_status(report_items), _earnings_analysis_check_detail(report_items)),
            _check_item("二阶公司线索", _readthrough_check_status(report_items), _readthrough_check_detail(report_items)),
            _check_item("异常期权流", _options_flow_check_status(report_items), _options_flow_check_detail(report_items)),
            _check_item("预期差/埋伏判断", _expectation_check_status(report_items), _expectation_check_detail(report_items)),
            _check_item("分析员合成", "active", "高证据候选会被转换成带证据、缺口和下一步动作的分析报告。"),
        ],
        "review_queue": report_items,
        "analyst_report": report_items,
        "dynamic_watchlist": dynamic_watchlist,
        "market_regime": regime,
        "earnings_calendar": earnings,
        "market_conclusion_zh": _market_conclusion_zh(regime),
        "data_gaps": data_gaps,
        "data_gaps_zh": _data_gaps_zh(data_gaps),
        "top_evidence": report_items[:5],
    }


def _headline(signal_count: int, candidate_count: int, urgent_count: int) -> str:
    if urgent_count:
        return f"{urgent_count} urgent review item(s), {candidate_count} total candidate(s), {signal_count} watchlist signal(s)."
    if candidate_count:
        return f"{candidate_count} candidate(s) detected; none marked urgent by current threshold."
    return "No hard-evidence candidates detected in the latest stored scan."


def _headline_zh(signal_count: int, candidate_count: int, urgent_count: int) -> str:
    if urgent_count:
        return f"今日有 {urgent_count} 个需要立即研究的高优先级机会，共 {candidate_count} 个候选标的，{signal_count} 个种子名单信号。"
    if candidate_count:
        return f"今日发现 {candidate_count} 个候选标的；当前阈值下暂无立即买入级别信号。"
    return "最新扫描没有发现足够硬的公司证据。"


def _automation_state(last_scan: dict[str, object]) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    last_run = str(last_scan.get("completed_at") or "")
    next_run = next_automated_run(now)
    return {
        "mode": "automatic",
        "last_run": last_run or "not yet run in this server session",
        "next_run": next_run.isoformat(),
        "timezone": "UTC",
    }


def next_automated_run(now: datetime | None = None) -> datetime:
    if now is None:
        now = datetime.now(timezone.utc)
    local = now.astimezone(MARKET_TZ)
    interval = _scan_interval_minutes(local)
    rounded = local.replace(second=0, microsecond=0) + timedelta(minutes=1)
    minute_offset = rounded.minute % interval
    if minute_offset:
        rounded += timedelta(minutes=interval - minute_offset)
    return rounded.astimezone(timezone.utc)


def _scan_interval_minutes(local: datetime) -> int:
    if local.weekday() >= 5:
        return 60
    current = local.time()
    if time(8, 0) <= current < time(20, 0):
        return 5
    if time(4, 0) <= current < time(8, 0) or time(20, 0) <= current < time(22, 0):
        return 15
    return 60


def _analyst_report_items(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for candidate in candidates:
        if candidate.get("review_status") in {"reviewed", "dismissed", "promoted"}:
            continue
        score = float(candidate.get("score", 0) or 0)
        if score < 10:
            continue
        row = dict(candidate)
        row["action"] = _action(score, str(candidate.get("status") or ""))
        # A failed financial health check (going-concern risk) vetoes urgency:
        # a cash-burning penny stock must never be promoted to "research now".
        if _quality_screen(row).get("veto") and row["action"] in {"research_now", "track"}:
            row["action"] = "monitor"
        row["decision"] = _decision(row)
        row["missing_confirmations"] = _missing_confirmations(row)
        row["analyst_take"] = _analyst_take(row)
        rows.append(row)
    rows.sort(key=lambda item: (float(item.get("score", 0)), str(item.get("status") == "discovered")), reverse=True)
    return rows


def _action(score: float, status: str) -> str:
    if score >= 35:
        return "research_now"
    if score >= 20:
        return "track"
    if status == "discovered":
        return "identify_then_monitor"
    return "monitor"


def _analyst_take(candidate: dict[str, object]) -> str:
    action = candidate.get("action")
    terms = ", ".join(_sequence(candidate.get("matched_terms"))[:4])
    market = _market_confirmation(candidate)
    market_summary = str(market.get("summary_zh") or "")
    impact = _impact_assessment(candidate)
    impact_summary = str(impact.get("summary_zh") or "")
    quick_model = _quick_model(candidate)
    quick_summary = str(quick_model.get("summary_zh") or "")
    earnings = _earnings_analysis(candidate)
    earnings_summary = str(earnings.get("summary_zh") or "")
    readthrough = _readthrough_analysis(candidate)
    readthrough_summary = str(readthrough.get("summary_zh") or "")
    options_flow = _options_flow(candidate)
    flow_summary = str(options_flow.get("summary_zh") or "")
    expectation = _expectation_check(candidate)
    expectation_summary = str(expectation.get("setup_zh") or "")
    if action == "research_now":
        return f"High-evidence item. Evidence is strong enough for immediate research, but not a buy decision until confirmations clear. Market: {market_summary} Impact: {impact_summary} Quick model: {quick_summary} Earnings: {earnings_summary} Read-through: {readthrough_summary} Options flow: {flow_summary} Expectations: {expectation_summary} Evidence: {terms}."
    if action == "track":
        return f"Material evidence. Track for market confirmation and financial impact. Market: {market_summary} Impact: {impact_summary} Quick model: {quick_summary} Earnings: {earnings_summary} Read-through: {readthrough_summary} Options flow: {flow_summary} Expectations: {expectation_summary} Evidence: {terms}."
    if action == "identify_then_monitor":
        return f"Potential new candidate. Resolve ticker/exchange before any investment work. Evidence: {terms}."
    return f"Monitor only unless repeated or market confirms. Market: {market_summary} Impact: {impact_summary} Quick model: {quick_summary} Earnings: {earnings_summary} Read-through: {readthrough_summary} Options flow: {flow_summary} Expectations: {expectation_summary} Evidence: {terms}."


def _decision(candidate: dict[str, object]) -> str:
    quality = _quality_screen(candidate)
    if quality.get("veto"):
        return "高风险归零股，一票否决：先解释生存能力，不投入研究"
    if "[流血中标]" in (quality.get("labels") or []):
        return "毛利率连续恶化，警惕流血中标：先确认订单是否真的赚钱"
    score = float(candidate.get("score", 0) or 0)
    status = str(candidate.get("status") or "")
    market_status = str(_market_confirmation(candidate).get("status") or "")
    impact_score = int(_impact_assessment(candidate).get("impact_score") or 0)
    expectation_status = str(_expectation_check(candidate).get("status") or "")
    flow_status = str(_options_flow(candidate).get("status") or "")
    if flow_status in {"bearish_flow", "conflicting_flow"}:
        return "Explain options-flow conflict first"
    if expectation_status == "variant_not_fully_priced":
        return "Research now; possible variant perception"
    if expectation_status == "likely_already_priced_in":
        return "Do not chase; likely priced in"
    if expectation_status == "negative_divergence":
        return "Explain negative divergence first"
    if score >= 20 and impact_score >= 4 and market_status in {"confirmed", "early_confirmation", "price_only_confirmation"}:
        return "Build quick model; not a buy yet"
    if score >= 35:
        if market_status in {"confirmed", "early_confirmation", "price_only_confirmation"}:
            return "Research now; market is confirming"
        return "Research now; wait for market confirmation"
    if score >= 20:
        if market_status == "confirmed":
            return "Track urgently; market confirmed"
        if market_status == "negative_reaction":
            return "Track cautiously; market reaction is negative"
        return "Track, do not buy yet"
    if status == "discovered":
        return "Identify company, then monitor"
    return "Monitor only"


def _missing_confirmations(candidate: dict[str, object]) -> list[str]:
    missing = []
    quality = _quality_screen(candidate)
    if quality.get("veto"):
        missing.append("生存能力存疑（现金跑道 < 6 个月）")
    elasticity = quality.get("revenue_elasticity") if isinstance(quality.get("revenue_elasticity"), dict) else {}
    if elasticity.get("band") == "unknown" and candidate.get("tickers"):
        missing.append("订单金额 vs 收入基数（弹性）未知")
    impact = _impact_assessment(candidate)
    if not impact:
        missing.append("financial impact estimate")
    else:
        needed = impact.get("model_inputs_needed") if isinstance(impact.get("model_inputs_needed"), list) else []
        if needed:
            missing.extend(str(item) for item in needed[:3])
    quick_model = _quick_model(candidate)
    if quick_model and quick_model.get("status") == "blocked_missing_amount":
        missing.insert(0, "quick model blocked: missing revenue/order amount")
    market_status = str(_market_confirmation(candidate).get("status") or "")
    if market_status in {"", "no_ticker", "unavailable", "unconfirmed"}:
        missing.insert(0, "price/volume confirmation")
    elif market_status == "price_only_confirmation":
        missing.insert(0, "volume confirmation")
    elif market_status == "already_extended":
        missing.insert(0, "expectations/priced-in check")
    elif market_status == "negative_reaction":
        missing.insert(0, "explain negative market reaction")
    expectation_status = str(_expectation_check(candidate).get("status") or "")
    if expectation_status == "needs_price_in_check":
        missing.insert(0, "price-in/variant perception check")
    elif expectation_status == "likely_already_priced_in":
        missing.insert(0, "new catalyst after likely priced-in move")
    elif expectation_status == "negative_divergence":
        missing.insert(0, "negative divergence explanation")
    flow_status = str(_options_flow(candidate).get("status") or "")
    if flow_status in {"bearish_flow", "conflicting_flow", "mixed_flow"}:
        missing.insert(0, "options-flow conflict explanation")
    if not candidate.get("tickers"):
        missing.insert(0, "ticker/exchange confirmation")
    if float(candidate.get("score", 0) or 0) < 35:
        missing.append("repeat evidence or stronger hard signal")
    return missing


def _check_item(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _dynamic_watchlist_items(
    candidates: list[dict[str, object]],
    market_regime: dict[str, object],
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        score = float(candidate.get("score", 0) or 0)
        if score < 10:
            continue
        article = candidate.get("article") if isinstance(candidate.get("article"), dict) else {}
        company_name = str(candidate.get("company_name") or "").strip()
        if not company_name:
            continue
        key = "|".join(str(ticker) for ticker in candidate.get("tickers", []) or []) or company_name.lower()
        row = grouped.setdefault(
            key,
            {
                "company_name": company_name,
                "tickers": candidate.get("tickers", []) or [],
                "status": candidate.get("status") or "discovered",
                "evidence_count": 0,
                "max_score": 0.0,
                "total_score": 0.0,
                "sources": [],
                "matched_terms": [],
                "latest_article": {},
                "origin": "news_discovered" if candidate.get("status") == "discovered" else "seed_confirmed_by_news",
            },
        )
        row["evidence_count"] = int(row["evidence_count"]) + 1
        row["max_score"] = max(float(row["max_score"]), score)
        row["total_score"] = round(float(row["total_score"]) + score, 2)
        row["sources"] = _append_unique(row.get("sources", []), str(article.get("source") or "unknown"))
        row["matched_terms"] = _append_many_unique(row.get("matched_terms", []), candidate.get("matched_terms", []) or [])
        row["market_confirmation"] = _merge_market_confirmation(
            row.get("market_confirmation"),
            candidate.get("market_confirmation"),
        )
        row["impact_assessment"] = _merge_impact_assessment(
            row.get("impact_assessment"),
            candidate.get("impact_assessment"),
        )
        row["financial_snapshot"] = _merge_financial_snapshot(
            row.get("financial_snapshot"),
            candidate.get("financial_snapshot"),
        )
        row["quick_model"] = _merge_quick_model(
            row.get("quick_model"),
            candidate.get("quick_model"),
        )
        row["earnings_analysis"] = _merge_earnings_analysis(
            row.get("earnings_analysis"),
            candidate.get("earnings_analysis"),
        )
        row["readthrough_analysis"] = _merge_readthrough_analysis(
            row.get("readthrough_analysis"),
            candidate.get("readthrough_analysis"),
        )
        row["options_flow"] = _merge_options_flow(
            row.get("options_flow"),
            candidate.get("options_flow"),
        )
        row["expectation_check"] = _merge_expectation_check(
            row.get("expectation_check"),
            candidate.get("expectation_check"),
        )
        row["quality_screen"] = _merge_quality_screen(
            row.get("quality_screen"),
            candidate.get("quality_screen"),
        )
        if _article_time(article) >= _article_time(row.get("latest_article", {})):
            row["latest_article"] = article

    rows = []
    for row in grouped.values():
        conviction = _watchlist_conviction(
            float(row["max_score"]),
            int(row["evidence_count"]),
            str(row["origin"]),
            str(_market_confirmation(row).get("status") or ""),
            str(_expectation_check(row).get("status") or ""),
            str(_options_flow(row).get("status") or ""),
        )
        # A failed financial health check overrides conviction entirely.
        if _quality_screen(row).get("veto"):
            conviction = 0
        item = dict(row)
        item["conviction"] = conviction
        item["decision_zh"] = _watchlist_decision_zh(conviction, market_regime)
        item["why_zh"] = _watchlist_why_zh(item)
        item["next_steps_zh"] = _watchlist_next_steps_zh(item, market_regime)
        rows.append(item)
    rows.sort(key=lambda item: (item["conviction"], float(item["max_score"]), int(item["evidence_count"])), reverse=True)
    return rows


def _watchlist_conviction(
    max_score: float,
    evidence_count: int,
    origin: str,
    market_status: str = "",
    expectation_status: str = "",
    flow_status: str = "",
) -> int:
    conviction = 0
    if max_score >= 35:
        conviction += 3
    elif max_score >= 20:
        conviction += 2
    elif max_score >= 10:
        conviction += 1
    if evidence_count >= 3:
        conviction += 2
    elif evidence_count >= 2:
        conviction += 1
    if origin == "seed_confirmed_by_news":
        conviction += 1
    if market_status == "confirmed":
        conviction += 1
    elif market_status == "negative_reaction":
        conviction -= 1
    if expectation_status == "variant_not_fully_priced":
        conviction += 1
    elif expectation_status in {"likely_already_priced_in", "negative_divergence"}:
        conviction -= 1
    if flow_status == "supportive_flow":
        conviction += 1
    elif flow_status in {"bearish_flow", "conflicting_flow", "mixed_flow"}:
        conviction -= 1
    return max(0, min(conviction, 5))


def _watchlist_decision_zh(conviction: int, market_regime: dict[str, object]) -> str:
    regime = str(market_regime.get("regime") or "neutral")
    if conviction >= 4 and regime == "risk_on":
        return "进入重点观察：允许更积极跟踪，但仍需价格/成交量确认。"
    if conviction >= 4:
        return "进入重点观察：公司证据足够强，但宏观环境不支持追高。"
    if conviction >= 2:
        return "进入普通观察：等待重复证据或市场确认。"
    return "临时观察：单条证据不足，不应上升为投资结论。"


def _watchlist_why_zh(item: dict[str, object]) -> str:
    terms = ", ".join(str(term) for term in (item.get("matched_terms") or [])[:4])
    sources = ", ".join(str(source) for source in (item.get("sources") or [])[:3])
    market = _market_confirmation(item)
    impact = _impact_assessment(item)
    quick_model = _quick_model(item)
    options_flow = _options_flow(item)
    expectation = _expectation_check(item)
    return f"进入原因：新闻证据 {int(item.get('evidence_count', 0))} 条，最高分 {float(item.get('max_score', 0)):.1f}，来源 {sources or 'unknown'}，关键词 {terms or 'n/a'}。市场确认：{market.get('summary_zh') or 'n/a'} 财务初判：{impact.get('summary_zh') or 'n/a'} Quick Model：{quick_model.get('summary_zh') or 'n/a'} 期权流：{options_flow.get('summary_zh') or 'n/a'} 预期差：{expectation.get('setup_zh') or 'n/a'}"


def _watchlist_next_steps_zh(item: dict[str, object], market_regime: dict[str, object]) -> list[str]:
    market_status = str(_market_confirmation(item).get("status") or "")
    expectation_status = str(_expectation_check(item).get("status") or "")
    steps = ["确认 ticker / 交易所 / 流动性。", "估算新闻对收入、订单、毛利或融资风险的实际影响。"]
    if expectation_status == "variant_not_fully_priced":
        steps.insert(1, "优先做预期差模型：验证是否仍未完全 price-in。")
    elif expectation_status == "likely_already_priced_in":
        steps.insert(1, "不要追高；等待新催化或回撤后重新验证。")
    elif expectation_status == "negative_divergence":
        steps.insert(1, "先解释负面分歧，确认是否有被标题掩盖的风险。")
    if market_status in {"", "no_ticker", "unavailable", "unconfirmed"}:
        steps.insert(1, "补价格与成交量异动，判断市场是否已经重估。")
    elif market_status == "confirmed":
        steps.insert(1, "市场已确认，优先检查是否已 price in 以及估值空间。")
    elif market_status == "negative_reaction":
        steps.insert(1, "先解释负面市场反应，不要因为新闻标题好看而强行看多。")
    if str(market_regime.get("regime") or "") == "risk_off":
        steps.append("宏观偏防守时，提高证据门槛，避免只因题材热度追入。")
    return steps


def _market_confirmation(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("market_confirmation")
    return value if isinstance(value, dict) else {}


def _impact_assessment(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("impact_assessment")
    return value if isinstance(value, dict) else {}


def _financial_snapshot(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("financial_snapshot")
    return value if isinstance(value, dict) else {}


def _quick_model(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("quick_model")
    return value if isinstance(value, dict) else {}


def _earnings_analysis(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("earnings_analysis")
    return value if isinstance(value, dict) else {}


def _readthrough_analysis(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("readthrough_analysis")
    return value if isinstance(value, dict) else {}


def _options_flow(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("options_flow")
    return value if isinstance(value, dict) else {}


def _expectation_check(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("expectation_check")
    return value if isinstance(value, dict) else {}


def _quality_screen(candidate: dict[str, object]) -> dict[str, object]:
    value = candidate.get("quality_screen")
    return value if isinstance(value, dict) else {}


def _market_confirmation_check_status(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "waiting"
    statuses = [str(_market_confirmation(item).get("status") or "") for item in report_items]
    if any(status in {"confirmed", "early_confirmation", "price_only_confirmation"} for status in statuses):
        return "active"
    if any(status in {"no_ticker", "unavailable"} for status in statuses):
        return "partial"
    return "watching"


def _market_confirmation_check_detail(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "暂无候选标的，等待下一次扫描。"
    confirmed = sum(
        1
        for item in report_items
        if str(_market_confirmation(item).get("status") or "") in {"confirmed", "early_confirmation", "price_only_confirmation"}
    )
    unavailable = sum(
        1
        for item in report_items
        if str(_market_confirmation(item).get("status") or "") in {"no_ticker", "unavailable"}
    )
    return f"已对候选 ticker 做 Yahoo chart 价格/成交量确认；确认={confirmed}，待补={unavailable}。"


def _market_confirmation_gaps(report_items: list[dict[str, object]]) -> list[str]:
    if not report_items:
        return ["No price/volume confirmation because there are no candidates yet."]
    if any(str(_market_confirmation(item).get("status") or "") in {"confirmed", "early_confirmation", "price_only_confirmation"} for item in report_items):
        return []
    return ["No candidate has positive price/volume confirmation yet."]


def _impact_check_status(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "waiting"
    if any(int(_impact_assessment(item).get("impact_score") or 0) >= 4 for item in report_items):
        return "model_queue"
    if any(_impact_assessment(item) for item in report_items):
        return "active"
    return "pending"


def _impact_check_detail(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "暂无候选标的，等待下一次扫描。"
    model_queue = sum(1 for item in report_items if int(_impact_assessment(item).get("impact_score") or 0) >= 4)
    assessed = sum(1 for item in report_items if _impact_assessment(item))
    return f"已对 {assessed} 个候选做一阶财务影响初判；建模队列={model_queue}。"


def _impact_gaps(report_items: list[dict[str, object]]) -> list[str]:
    if not report_items:
        return ["No financial impact estimate because there are no candidates yet."]
    if any(int(_impact_assessment(item).get("impact_score") or 0) >= 4 for item in report_items):
        return []
    return ["No candidate is strong enough for quick-model queue yet."]


def _financial_check_status(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "waiting"
    statuses = [str(_financial_snapshot(item).get("status") or "") for item in report_items]
    if any(status == "ok" for status in statuses):
        return "active"
    if any(status in {"partial", "missing", "unavailable"} for status in statuses):
        return "partial"
    return "waiting"


def _financial_check_detail(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "暂无候选标的，等待下一次扫描。"
    ok = sum(1 for item in report_items if str(_financial_snapshot(item).get("status") or "") == "ok")
    partial = sum(1 for item in report_items if str(_financial_snapshot(item).get("status") or "") in {"partial", "missing", "unavailable"})
    return f"已用 SEC companyfacts 拉取收入基数/毛利率；ok={ok}，partial_or_missing={partial}。"


def _financial_gaps(report_items: list[dict[str, object]]) -> list[str]:
    if not report_items:
        return ["No SEC financial snapshot because there are no candidates yet."]
    if any(str(_financial_snapshot(item).get("status") or "") == "ok" for item in report_items):
        return []
    return ["No candidate has complete SEC revenue and gross-margin snapshot yet."]


def _quick_model_check_status(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "waiting"
    statuses = [str(_quick_model(item).get("status") or "") for item in report_items]
    if any(status == "ready_for_assumptions" for status in statuses):
        return "ready"
    if any(status == "blocked_missing_amount" for status in statuses):
        return "blocked"
    return "waiting"


def _quick_model_check_detail(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "暂无候选标的，等待下一次扫描。"
    ready = sum(1 for item in report_items if str(_quick_model(item).get("status") or "") == "ready_for_assumptions")
    blocked = sum(1 for item in report_items if str(_quick_model(item).get("status") or "") == "blocked_missing_amount")
    return f"Quick model ready={ready}，blocked_missing_amount={blocked}；只在披露金额存在时填数字敏感性。"


def _quick_model_gaps(report_items: list[dict[str, object]]) -> list[str]:
    if not report_items:
        return ["No quick model because there are no candidates yet."]
    if any(str(_quick_model(item).get("status") or "") == "ready_for_assumptions" for item in report_items):
        return []
    if any(str(_quick_model(item).get("status") or "") == "blocked_missing_amount" for item in report_items):
        return ["Quick model is blocked for at least one candidate because disclosed revenue/order amount is missing."]
    return ["No candidate has entered quick-model workflow yet."]


def _earnings_analysis_check_status(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "waiting"
    statuses = [str(_earnings_analysis(item).get("status") or "") for item in report_items]
    if any(status == "earnings_release_detected" for status in statuses):
        return "active"
    if any(status == "earnings_headline_only" for status in statuses):
        return "needs_source"
    return "waiting"


def _earnings_analysis_check_detail(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "暂无候选标的，等待下一次扫描。"
    detected = sum(1 for item in report_items if str(_earnings_analysis(item).get("status") or "") == "earnings_release_detected")
    headline = sum(1 for item in report_items if str(_earnings_analysis(item).get("status") or "") == "earnings_headline_only")
    return f"财报 release 已拆解={detected}，标题命中但需打开原文/8-K={headline}。"


def _readthrough_check_status(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "waiting"
    statuses = [str(_readthrough_analysis(item).get("status") or "") for item in report_items]
    if any(status == "active" for status in statuses):
        return "active"
    if any(status == "watching" for status in statuses):
        return "watching"
    return "waiting"


def _readthrough_check_detail(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "暂无候选标的，等待下一次扫描。"
    active_items = 0
    total_items = 0
    for item in report_items:
        readthrough = _readthrough_analysis(item)
        rows = readthrough.get("items") if isinstance(readthrough.get("items"), list) else []
        total_items += len(rows)
        active_items += sum(1 for row in rows if isinstance(row, dict) and row.get("status") in {"confirmed_readthrough", "needs_model"})
    return f"二阶公司线索={total_items}，其中需优先检查={active_items}。"


def _options_flow_check_status(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "waiting"
    statuses = [str(_options_flow(item).get("status") or "") for item in report_items]
    if any(status == "supportive_flow" for status in statuses):
        return "active"
    if any(status in {"bearish_flow", "conflicting_flow", "mixed_flow"} for status in statuses):
        return "caution"
    if any(status.startswith("unverified") for status in statuses):
        return "watching"
    return "not_connected"


def _options_flow_check_detail(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "暂无候选标的，等待下一次扫描。"
    supportive = sum(1 for item in report_items if str(_options_flow(item).get("status") or "") == "supportive_flow")
    conflict = sum(1 for item in report_items if str(_options_flow(item).get("status") or "") in {"bearish_flow", "conflicting_flow", "mixed_flow"})
    none = sum(1 for item in report_items if str(_options_flow(item).get("status") or "") == "no_flow_evidence")
    public_chain = sum(
        1
        for item in report_items
        if str(_options_flow(item).get("source_tier") or "") == "public_options_chain_snapshot"
        or isinstance(_options_flow(item).get("public_chain_check"), dict)
    )
    return f"异常期权流：同向旁证={supportive}，冲突/混合={conflict}，未发现={none}，公开期权链检查={public_chain}。未连接 X/API 时不会伪造 Flow God 数据。"


def _options_flow_gaps(report_items: list[dict[str, object]]) -> list[str]:
    if not report_items:
        return ["No options-flow check because there are no candidates yet."]
    if any(str(_options_flow(item).get("status") or "") == "supportive_flow" for item in report_items):
        return []
    if any(
        str(_options_flow(item).get("source_tier") or "") == "public_options_chain_snapshot"
        or isinstance(_options_flow(item).get("public_chain_check"), dict)
        for item in report_items
    ):
        return ["No public options-chain anomaly or connected social/options-flow source has confirmed any candidate yet."]
    return ["No options-flow evidence has confirmed any candidate yet."]


def _expectation_check_status(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "waiting"
    statuses = [str(_expectation_check(item).get("status") or "") for item in report_items]
    if any(status == "variant_not_fully_priced" for status in statuses):
        return "active"
    if any(status in {"needs_price_in_check", "likely_already_priced_in"} for status in statuses):
        return "watching"
    if any(status == "negative_divergence" for status in statuses):
        return "caution"
    return "waiting"


def _expectation_check_detail(report_items: list[dict[str, object]]) -> str:
    if not report_items:
        return "暂无候选标的，等待下一次扫描。"
    early = sum(1 for item in report_items if str(_expectation_check(item).get("status") or "") == "variant_not_fully_priced")
    priced = sum(1 for item in report_items if str(_expectation_check(item).get("status") or "") == "likely_already_priced_in")
    needs = sum(1 for item in report_items if str(_expectation_check(item).get("status") or "") == "needs_price_in_check")
    return f"预期差判断：可能未完全 price-in={early}，可能已提前反应={priced}，仍需补证据={needs}。"


def _expectation_gaps(report_items: list[dict[str, object]]) -> list[str]:
    if not report_items:
        return ["No expectation/price-in check because there are no candidates yet."]
    if any(str(_expectation_check(item).get("status") or "") == "variant_not_fully_priced" for item in report_items):
        return []
    return ["No candidate currently passes the early variant perception screen."]


def _data_gaps(
    report_items: list[dict[str, object]],
    earnings: dict[str, object],
    regime: dict[str, object],
) -> list[str]:
    gaps = [
        *_market_confirmation_gaps(report_items),
        *_impact_gaps(report_items),
        *_financial_gaps(report_items),
        *_quick_model_gaps(report_items),
        *_options_flow_gaps(report_items),
        *_expectation_gaps(report_items),
    ]
    if _has_unresolved_ticker_candidate(report_items):
        gaps.append("Some discovered companies still need ticker/exchange confirmation after SEC name matching.")
    gaps.extend(_calendar_connectivity_gaps(earnings, regime))
    gaps.append("Optional: OpenAI entity enrichment is not connected; current extraction uses deterministic rules.")
    return _dedupe_strings(gaps)


def _has_unresolved_ticker_candidate(report_items: list[dict[str, object]]) -> bool:
    for item in report_items:
        tickers = item.get("tickers")
        if isinstance(tickers, (list, tuple)) and any(str(ticker).strip() for ticker in tickers):
            continue
        return True
    return False


def _calendar_connectivity_gaps(earnings: dict[str, object], regime: dict[str, object]) -> list[str]:
    gaps = []
    if str(earnings.get("status") or "") not in {"connected"}:
        gaps.append("Earnings calendar is degraded or unavailable; upcoming-report monitoring may be incomplete.")
    if str(regime.get("status") or "") != "connected":
        gaps.append("Macro regime feed is degraded or unavailable; market-context scoring may be incomplete.")
    return gaps


def _dedupe_strings(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _data_gaps_zh(gaps: list[str]) -> list[str]:
    translations = {
        "No price/volume confirmation because there are no candidates yet.": "暂无候选标的，因此还没有价格/成交量确认。",
        "No candidate has positive price/volume confirmation yet.": "目前没有候选标的获得正向价格/成交量确认。",
        "No financial impact estimate because there are no candidates yet.": "暂无候选标的，因此还没有财务影响初判。",
        "No candidate is strong enough for quick-model queue yet.": "目前没有候选标的强到进入快速建模队列。",
        "No SEC financial snapshot because there are no candidates yet.": "暂无候选标的，因此还没有 SEC 财务快照。",
        "No candidate has complete SEC revenue and gross-margin snapshot yet.": "目前没有候选标的拿到完整的 SEC 收入和毛利率快照。",
        "No quick model because there are no candidates yet.": "暂无候选标的，因此还没有 Quick Model。",
        "Quick model is blocked for at least one candidate because disclosed revenue/order amount is missing.": "至少一个候选标的缺少披露的收入/订单金额，Quick Model 只能给定性判断，不能硬填数字。",
        "No candidate has entered quick-model workflow yet.": "目前没有候选标的进入 Quick Model 工作流。",
        "No options-flow check because there are no candidates yet.": "暂无候选标的，因此还没有异常期权流检查。",
        "No connected unusual-options-flow source has confirmed any candidate yet.": "目前没有已连接的异常期权流来源确认任何候选标的。",
        "No public options-chain anomaly or connected social/options-flow source has confirmed any candidate yet.": "公开期权链和已连接的社媒/期权流来源目前都没有确认任何候选标的。",
        "No options-flow evidence has confirmed any candidate yet.": "目前没有期权流证据确认任何候选标的。",
        "No expectation/price-in check because there are no candidates yet.": "暂无候选标的，因此还没有预期差/price-in 检查。",
        "No candidate currently passes the early variant perception screen.": "目前没有候选标的通过“早期预期差”筛选。",
        "Some discovered companies still need ticker/exchange confirmation after SEC name matching.": "部分新闻发现的公司在 SEC 名称匹配后仍未确认 ticker/交易所。",
        "Earnings calendar is degraded or unavailable; upcoming-report monitoring may be incomplete.": "财报日历当前降级或不可用，未来财报监控可能不完整。",
        "Macro regime feed is degraded or unavailable; market-context scoring may be incomplete.": "宏观状态源当前降级或不可用，市场背景评分可能不完整。",
        "Optional: OpenAI entity enrichment is not connected; current extraction uses deterministic rules.": "可选增强：OpenAI 实体抽取层尚未接入；当前使用确定性规则，优点是可解释，缺点是复杂新闻可能漏识别。",
    }
    return [translations.get(gap, gap) for gap in gaps]


def _merge_market_confirmation(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    statuses = [str(current.get("status") or ""), str(incoming.get("status") or "")]
    status = _best_market_status(statuses)
    confirmations = []
    for source in (current, incoming):
        for row in source.get("confirmations", []) or []:
            if isinstance(row, dict):
                confirmations.append(row)
    return {
        "status": status,
        "primary_ticker": current.get("primary_ticker") or incoming.get("primary_ticker"),
        "summary_zh": current.get("summary_zh") or incoming.get("summary_zh") or "",
        "confirmations": confirmations,
    }


def _best_market_status(statuses: list[str]) -> str:
    rank = {
        "confirmed": 5,
        "early_confirmation": 4,
        "price_only_confirmation": 3,
        "already_extended": 2,
        "unconfirmed": 1,
        "negative_reaction": 0,
        "unavailable": -1,
        "no_ticker": -2,
        "": -3,
    }
    return max(statuses, key=lambda status: rank.get(status, -3))


def _merge_impact_assessment(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    current_score = int(current.get("impact_score") or 0)
    incoming_score = int(incoming.get("impact_score") or 0)
    return incoming if incoming_score > current_score else current


def _merge_financial_snapshot(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    rank = {"ok": 4, "partial": 3, "missing": 2, "unavailable": 1, "no_ticker": 0}
    return incoming if rank.get(str(incoming.get("status") or ""), -1) > rank.get(str(current.get("status") or ""), -1) else current


def _merge_quick_model(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    rank = {"ready_for_assumptions": 3, "blocked_missing_amount": 2, "not_queued": 1}
    return incoming if rank.get(str(incoming.get("status") or ""), 0) > rank.get(str(current.get("status") or ""), 0) else current


def _merge_earnings_analysis(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    rank = {"earnings_release_detected": 3, "earnings_headline_only": 2, "not_earnings": 1}
    return incoming if rank.get(str(incoming.get("status") or ""), 0) > rank.get(str(current.get("status") or ""), 0) else current


def _merge_readthrough_analysis(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    rank = {"active": 3, "watching": 2, "no_readthrough": 1}
    return incoming if rank.get(str(incoming.get("status") or ""), 0) > rank.get(str(current.get("status") or ""), 0) else current


def _merge_options_flow(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    rank = {
        "supportive_flow": 5,
        "conflicting_flow": 4,
        "bearish_flow": 4,
        "mixed_flow": 3,
        "unverified_bullish_flow": 2,
        "unverified_flow": 1,
        "no_flow_evidence": 0,
    }
    return incoming if rank.get(str(incoming.get("status") or ""), -1) > rank.get(str(current.get("status") or ""), -1) else current


def _merge_quality_screen(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    # Keep the most cautious screen (high_risk > caution > ok > unknown).
    rank = {"high_risk": 3, "caution": 2, "ok": 1, "unknown": 0}
    return incoming if rank.get(str(incoming.get("grade")), 0) > rank.get(str(current.get("grade")), 0) else current


def _merge_expectation_check(existing: object, new_value: object) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    incoming = new_value if isinstance(new_value, dict) else {}
    if not current:
        return incoming
    if not incoming:
        return current
    rank = {
        "variant_not_fully_priced": 5,
        "needs_price_in_check": 4,
        "likely_already_priced_in": 3,
        "negative_divergence": 2,
        "watch_only": 1,
        "no_market_data": 0,
    }
    return incoming if rank.get(str(incoming.get("status") or ""), -1) > rank.get(str(current.get("status") or ""), -1) else current


def _market_conclusion_zh(regime: dict[str, object]) -> dict[str, object]:
    status = str(regime.get("status") or "not_connected")
    label = str(regime.get("regime") or "unknown")
    score = int(regime.get("score") or 0)
    if status == "not_connected":
        return {
            "title": "宏观模块未连接",
            "summary": "当前不能用宏观数据辅助机会筛选。",
            "action": "先修复数据源，再做投资判断。",
        }
    if label == "risk_on":
        return {
            "title": "宏观环境偏风险偏好",
            "summary": f"当前分数 {score}，成长股和高 beta 主题更容易获得市场配合。",
            "action": "可以更积极跟踪 AI、半导体、国防、机器人等硬证据标的，但仍必须等待价格/成交量确认。",
        }
    if label == "risk_off":
        return {
            "title": "宏观环境偏防守",
            "summary": f"当前分数 {score}，市场对高估值和小盘投机容忍度下降。",
            "action": "只提升合同、订单、收入可见度强且流动性足够的标的；弱新闻直接过滤。",
        }
    return {
        "title": "宏观环境中性",
        "summary": f"当前分数 {score}，宏观本身不给明显方向。",
        "action": "维持默认证据门槛，重点看公司新闻是否足够硬、是否被市场确认。",
    }


def _append_unique(values: object, value: str) -> list[str]:
    output = [str(item) for item in values] if isinstance(values, list) else []
    if value and value not in output:
        output.append(value)
    return output


def _append_many_unique(values: object, new_values: object) -> list[str]:
    output = [str(item) for item in values] if isinstance(values, list) else []
    if not isinstance(new_values, (list, tuple)):
        return output
    for value in new_values:
        text = str(value)
        if text and text not in output:
            output.append(text)
    return output


def _sequence(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


def _article_time(article: object) -> str:
    if not isinstance(article, dict):
        return ""
    return str(article.get("published") or article.get("fetched_at") or "")


def _disconnected_market_regime() -> dict[str, object]:
    return {
        "status": "not_connected",
        "regime": "unknown",
        "score": 0,
        "summary": "Macro regime module is not connected to public data feeds.",
        "needed_feeds": [
            "10Y Treasury yield",
            "2Y Treasury yield",
            "VIX",
            "SPY price",
            "QQQ price",
            "CPI",
            "Unemployment rate",
        ],
        "metrics": [],
        "source_health": [],
        "events": [],
        "implications": [],
    }


def _disconnected_earnings_calendar() -> dict[str, object]:
    return {
        "status": "not_connected",
        "generated_at": "",
        "items": [],
        "summary_zh": "财报日历尚未连接。",
        "errors": [],
    }
