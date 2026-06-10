"""Render the daily brief into a one-page institutional morning report (Markdown).

This is the PM-desk deliverable: a scannable one-pager that leads with market
posture, then the ranked TOP CALLS (each carrying its evidence line, financial
health veto, and short-squeeze alert), the dynamic watchlist, upcoming
earnings, and the honest data gaps. It is a research triage memo, not an
investment recommendation, and it says so.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")

_ACTION_ZH = {
    "research_now": "立即研究",
    "track": "跟踪",
    "identify_then_monitor": "待识别",
    "monitor": "观察",
}
_MARKET_ZH = {
    "confirmed": "确认", "early_confirmation": "早期确认", "price_only_confirmation": "仅价格",
    "already_extended": "已延伸", "unconfirmed": "未确认", "negative_reaction": "负向反应",
    "no_ticker": "无ticker", "unavailable": "无数据",
}


def render_daily_report(brief: dict[str, object], top_n: int = 5, watchlist_n: int = 8) -> str:
    counts = _dict(brief.get("counts"))
    regime = _dict(brief.get("market_regime"))
    conclusion = _dict(brief.get("market_conclusion_zh"))
    report_items = _list(brief.get("analyst_report"))
    watchlist = _list(brief.get("dynamic_watchlist"))
    earnings = _dict(brief.get("earnings_calendar"))
    gaps = _list(brief.get("data_gaps_zh")) or _list(brief.get("data_gaps"))

    today = datetime.now(MARKET_TZ).strftime("%Y-%m-%d %a")
    lines: list[str] = []
    lines.append(f"# AI News Radar — 每日投研简报 · {today}")
    lines.append("_自动生成 · 研究分流与选题用途，非投资建议 · 仓位与估值判断仍需人工_")
    lines.append("")

    # --- posture -----------------------------------------------------------
    lines.append("## 一、市场姿态")
    posture = _regime_zh(str(regime.get("regime") or "unknown"))
    score = regime.get("score")
    score_txt = f"（分数 {score}）" if score not in (None, "") and regime.get("regime") not in (None, "unknown") else ""
    lines.append(f"- **{conclusion.get('title') or posture}** {score_txt}")
    if conclusion.get("summary"):
        lines.append(f"- {conclusion.get('summary')}")
    if conclusion.get("action"):
        lines.append(f"- 操作基调：{conclusion.get('action')}")
    lines.append("")

    # --- top calls ---------------------------------------------------------
    urgent = counts.get("urgent_items", 0)
    lines.append(f"## 二、TOP CALLS · 今日最该看（urgent {urgent}）")
    if not report_items:
        lines.append("- 本轮无达到阈值的机会。")
    for index, item in enumerate(report_items[:top_n], start=1):
        lines.extend(_render_call(index, _dict(item)))
    lines.append("")

    # --- serenity alpha ----------------------------------------------------
    lines.append("## 三、Serenity Alpha · 小而纯受益者（选股第二视角）")
    lines.extend(_render_serenity_section(report_items))

    # --- watchlist ---------------------------------------------------------
    lines.append("## 四、动态观察池")
    if not watchlist:
        lines.append("- 观察池暂无足够证据。")
    for row in watchlist[:watchlist_n]:
        row = _dict(row)
        tickers = ", ".join(str(t) for t in _list(row.get("tickers"))) or "待确认"
        flag = _risk_flag(row)
        lines.append(
            f"- **{tickers}** {row.get('company_name') or ''} · 信念 {row.get('conviction', 0)}/5{flag} — {row.get('decision_zh') or ''}"
        )
    lines.append("")

    # --- earnings ----------------------------------------------------------
    lines.append("## 五、未来财报窗口")
    items = _list(earnings.get("items"))
    if items:
        lines.append(f"- {earnings.get('summary_zh') or ''}")
        for row in items[:10]:
            row = _dict(row)
            lines.append(
                f"  - {row.get('date')} · **{row.get('ticker')}** {row.get('name') or ''} · {_time_zh(str(row.get('time') or ''))} · EPS预期 {row.get('eps_forecast') or 'n/a'}"
            )
    else:
        lines.append(f"- {earnings.get('summary_zh') or '财报日历未连接或窗口内无观察标的。'}")
    lines.append("")

    # --- gaps --------------------------------------------------------------
    lines.append("## 六、证据缺口（系统下一轮要补，不是你的待办）")
    if gaps:
        for gap in gaps[:8]:
            lines.append(f"- {gap}")
    else:
        lines.append("- 当前无关键缺口。")
    lines.append("")

    # --- method ------------------------------------------------------------
    lines.append("---")
    lines.append(
        f"方法学：扫描公开源 → 硬证据分层打分 → 多维富化（价量/SEC财务/财务体检/空头轧空/预期差）→ 合成。"
        f"本轮文章 {counts.get('articles_reviewed', 0)}，候选 {counts.get('discoveries', 0)}，报告项 {counts.get('report_items', 0)}。"
        f" 评分确定性可解释；高分仅代表证据密度，alpha 需反馈闭环成熟后才能确认。"
    )
    return "\n".join(lines)


_VERDICT_ZH = {"qualified": "通过筛", "exploratory": "探索级", "excluded": "被排除"}


def _render_serenity_section(report_items: list[object], top_n: int = 6) -> list[str]:
    rows = [(_dict(item), _dict(_dict(item).get("serenity_alpha"))) for item in report_items]
    rows = [(item, sa) for item, sa in rows if sa.get("status")]
    if not rows:
        return ["- 本轮候选暂无 Serenity Alpha 评估（缺确认 ticker 或市值/覆盖数据未取到）。", ""]
    order = {"qualified": 0, "exploratory": 1, "excluded": 2}
    rows.sort(key=lambda r: (order.get(str(r[1].get("verdict")), 3), -_num(r[1].get("alpha_score"))))
    counts: dict[str, int] = {}
    for _item, sa in rows:
        verdict = str(sa.get("verdict"))
        counts[verdict] = counts.get(verdict, 0) + 1
    lines = [
        f"- 通过筛 {counts.get('qualified', 0)} · 探索级 {counts.get('exploratory', 0)} · 被排除 {counts.get('excluded', 0)}"
        "（找小而纯、被错分类、对该需求高弹性的受益者；五维乘法分，任一维近 0 即归零）"
    ]
    for item, sa in rows[:top_n]:
        tickers = ", ".join(str(t) for t in _list(item.get("tickers"))) or str(item.get("company_name") or "待确认")
        verdict = _VERDICT_ZH.get(str(sa.get("verdict")), str(sa.get("verdict")))
        head = f"- **[{verdict} · alpha {_num(sa.get('alpha_score')):.0f}] {tickers}** {item.get('company_name') or ''} — 最弱环节:{sa.get('weakest_zh') or '—'}"
        cap = sa.get("market_cap_display")
        if cap and cap != "n/a":
            head += f" · 市值 {cap}"
        lines.append(head)
        if sa.get("posture_zh"):
            lines.append(f"   - 仓位姿态：{sa.get('posture_zh')}")
        filters = _list(sa.get("excluded_filters"))
        if filters:
            reasons = "；".join(str(_dict(f).get("reason_zh")) for f in filters[:2])
            lines.append(f"   - 排除原因：{reasons}")
    lines.append("")
    return lines


def export_daily_report(brief: dict[str, object], reports_dir: str | Path, top_n: int = 5, watchlist_n: int = 8) -> dict[str, str]:
    """Write the daily report to a stable location for scheduled external readers
    (e.g. a Claude Desktop scheduled task): ``latest-daily-report.md`` (always
    current), a dated archive under ``daily/``, and a structured JSON companion
    so skills can parse exact tickers/scores. Returns the written paths."""
    base = Path(reports_dir)
    (base / "daily").mkdir(parents=True, exist_ok=True)
    markdown = render_daily_report(brief, top_n=top_n, watchlist_n=watchlist_n)
    today = datetime.now(MARKET_TZ).strftime("%Y-%m-%d")
    latest_md = base / "latest-daily-report.md"
    dated_md = base / "daily" / f"{today}.md"
    latest_json = base / "latest-daily-report.json"
    latest_md.write_text(markdown, encoding="utf-8")
    dated_md.write_text(markdown, encoding="utf-8")
    latest_json.write_text(json.dumps(_structured_payload(brief, today), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"markdown": str(latest_md), "dated": str(dated_md), "json": str(latest_json)}


def _structured_payload(brief: dict[str, object], today: str) -> dict[str, object]:
    counts = _dict(brief.get("counts"))
    regime = _dict(brief.get("market_regime"))
    items = _list(brief.get("analyst_report"))

    def _call(item: object) -> dict[str, object]:
        item = _dict(item)
        article = _dict(item.get("article"))
        sa = _dict(item.get("serenity_alpha"))
        return {
            "tickers": _list(item.get("tickers")),
            "company": item.get("company_name"),
            "action": item.get("action"),
            "score": _num(item.get("score")),
            "confidence": _num(item.get("confidence")),
            "evidence_terms": [str(t) for t in _list(item.get("matched_terms"))[:8]],
            "catalyst": {
                "source": article.get("source"),
                "title": article.get("title"),
                "link": article.get("link"),
                "published": article.get("published"),
            },
            "serenity_alpha": {
                "alpha_score": sa.get("alpha_score"),
                "verdict": sa.get("verdict"),
                "weakest": sa.get("weakest_zh"),
                "market_cap_usd": sa.get("market_cap_usd"),
                "analyst_count": sa.get("analyst_count"),
                "excluded_filters": [str(_dict(f).get("key")) for f in _list(sa.get("excluded_filters"))],
            } if sa.get("status") else None,
        }

    return {
        "date": today,
        "generated_at": datetime.now(MARKET_TZ).isoformat(),
        "purpose": ("AI News Radar daily export for a Claude Desktop scheduled task. "
                    "Research triage / idea sourcing only — NOT investment advice. "
                    "Analyze with serenity-alpha and other relevant skills."),
        "market_regime": {"regime": regime.get("regime"), "score": regime.get("score")},
        "counts": {
            "articles_reviewed": counts.get("articles_reviewed"),
            "report_items": counts.get("report_items"),
            "urgent_items": counts.get("urgent_items"),
        },
        "top_calls": [_call(item) for item in items[:15]],
        "earnings": [_dict(row) for row in _list(_dict(brief.get("earnings_calendar")).get("items"))[:15]],
        "data_gaps": [str(g) for g in (_list(brief.get("data_gaps_zh")) or _list(brief.get("data_gaps")))[:8]],
    }


def _render_call(index: int, item: dict[str, object]) -> list[str]:
    article = _dict(item.get("article"))
    action = _ACTION_ZH.get(str(item.get("action") or ""), str(item.get("action") or "观察"))
    tickers = ", ".join(str(t) for t in _list(item.get("tickers"))) or "待确认"
    score = _num(item.get("score"))
    conf = _num(item.get("confidence"))
    conf_txt = f" · 置信 {conf:.2f}" if conf else ""
    head = f"{index}. **[{action}] {tickers}** {item.get('company_name') or ''} · 评分 {score:.1f}{conf_txt}"

    quality = _dict(item.get("quality_screen"))
    squeeze = _dict(item.get("short_squeeze"))
    flow = _dict(item.get("institutional_flow"))
    flags = []
    if quality.get("veto"):
        flags.append("🛑 " + (_first_label(quality) or "[高风险归零股]"))
    elif "[流血中标]" in _list(quality.get("labels")):
        flags.append("⚠ [流血中标]")
    if squeeze.get("alert") and not quality.get("veto"):
        flags.append("🚀 " + (str(squeeze.get("label")) or "[空头轧空潜力]"))
    if flow.get("flow") == "accumulation":
        flags.append("🏦 机构吸筹")
    elif flow.get("flow") == "distribution":
        flags.append("🏦 机构派发")
    if flags:
        head += "  " + " ".join(flags)

    lines = [head]
    if item.get("decision"):
        lines.append(f"   - 决策：{item.get('decision')}")
    lines.append(f"   - 证据：{_evidence_line(item)}")
    el = _dict(quality.get("revenue_elasticity"))
    if el.get("band") in {"transformational", "immaterial"}:
        lines.append(f"   - 营收弹性：{el.get('zh')}")
    if squeeze.get("status") == "ok" and squeeze.get("potential") in {"high", "elevated"}:
        lines.append(f"   - 空头：{squeeze.get('summary_zh')}")
    if flow.get("flow") in {"accumulation", "distribution"}:
        lines.append(f"   - 机构：{flow.get('summary_zh')}")
    title = str(article.get("title") or "")
    link = str(article.get("link") or "")
    source = str(article.get("source") or "")
    lines.append(f"   - 催化剂：{source} · {title}" + (f"  <{link}>" if link else ""))
    return lines


def _evidence_line(item: dict[str, object]) -> str:
    market = _MARKET_ZH.get(str(_dict(item.get("market_confirmation")).get("status") or ""), "—")
    impact = _dict(item.get("impact_assessment")).get("impact_score")
    sec = str(_dict(item.get("financial_snapshot")).get("status") or "—")
    flow = str(_dict(item.get("options_flow")).get("status") or "—")
    exp = str(_dict(item.get("expectation_check")).get("status") or "—")
    return f"市场={market} · 影响={impact if impact is not None else '—'}/5 · SEC={sec} · 期权={flow} · 预期={exp}"


def _risk_flag(row: dict[str, object]) -> str:
    quality = _dict(row.get("quality_screen"))
    squeeze = _dict(row.get("short_squeeze"))
    flow = _dict(row.get("institutional_flow"))
    parts = []
    if quality.get("veto"):
        parts.append(" 🛑高风险")
    if squeeze.get("alert"):
        parts.append(" 🚀轧空")
    if flow.get("flow") == "accumulation":
        parts.append(" 🏦吸筹")
    elif flow.get("flow") == "distribution":
        parts.append(" 🏦派发")
    return "".join(parts)


def _first_label(screen: dict[str, object]) -> str:
    labels = _list(screen.get("labels"))
    return str(labels[0]) if labels else ""


def _regime_zh(regime: str) -> str:
    return {"risk_on": "风险偏好（偏进攻）", "risk_off": "风险防御", "neutral": "中性"}.get(regime, "未连接")


def _time_zh(value: str) -> str:
    low = value.lower()
    if "before" in low:
        return "盘前"
    if "after" in low:
        return "盘后"
    if "during" in low:
        return "盘中"
    return "时间待定"


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
