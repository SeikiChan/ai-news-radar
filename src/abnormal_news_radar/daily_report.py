"""Render the daily brief into a one-page institutional morning report (Markdown).

This is the PM-desk deliverable: a scannable one-pager that leads with market
posture, then the ranked TOP CALLS (each carrying its evidence line, financial
health veto, and short-squeeze alert), the dynamic watchlist, upcoming
earnings, and the honest data gaps. It is a research triage memo, not an
investment recommendation, and it says so.
"""

from __future__ import annotations

from datetime import datetime
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

    # --- watchlist ---------------------------------------------------------
    lines.append("## 三、动态观察池")
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
    lines.append("## 四、未来财报窗口")
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
    lines.append("## 五、证据缺口（系统下一轮要补，不是你的待办）")
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
    flags = []
    if quality.get("veto"):
        flags.append("🛑 " + (_first_label(quality) or "[高风险归零股]"))
    elif "[流血中标]" in _list(quality.get("labels")):
        flags.append("⚠ [流血中标]")
    if squeeze.get("alert") and not quality.get("veto"):
        flags.append("🚀 " + (str(squeeze.get("label")) or "[空头轧空潜力]"))
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
    if quality.get("veto"):
        return " 🛑高风险"
    if squeeze.get("alert"):
        return " 🚀轧空"
    return ""


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
