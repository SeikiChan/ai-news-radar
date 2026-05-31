"""Quantitative quality / safety screen — the "health check & fraud filter".

This runs in the enrichment layer, AFTER a candidate has already passed the
hard-evidence scoring, never before. Its job is to catch the two classic US
small-cap traps that a pure event-driven radar walks into:

1. Penny-stock pump-and-dump: a tiny, cash-burning, negative-margin company
   posts an impressive-sounding order on a newswire. The SEC ``companyfacts``
   data exposes a balance sheet that cannot survive six months -> ``[高风险归零股]``.
2. The base illusion: a disclosed order amount is meaningless without the
   revenue base. $10M is transformational for a $5M-revenue company and noise
   for a $5B one. Revenue elasticity makes the difference explicit.

Three deterministic, zero-cost factors (all from data the SEC snapshot already
fetched): revenue elasticity, gross-margin trend, and survival runway.
"""

from __future__ import annotations

#: Order amount as a share of the trailing revenue base.
ELASTICITY_TRANSFORMATIONAL_PCT = 10.0
ELASTICITY_IMMATERIAL_PCT = 1.0

#: A company that cannot fund this many months of operations is a veto.
RUNWAY_VETO_MONTHS = 6.0
RUNWAY_CAUTION_MONTHS = 12.0

#: Minimum cumulative gross-margin erosion (percentage points) to flag.
MARGIN_EROSION_PP = 2.0


def enrich_candidates_with_quality_screen(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["quality_screen"] = screen_candidate(row)
        enriched.append(row)
    return enriched


def screen_candidate(candidate: dict[str, object]) -> dict[str, object]:
    if not candidate.get("tickers"):
        return {
            "status": "no_ticker",
            "grade": "unknown",
            "labels": [],
            "veto": False,
            "summary_zh": "尚无确认 ticker，无法做财务体检。",
        }
    snapshot = _primary_snapshot(candidate)
    if not snapshot:
        return {
            "status": "insufficient_data",
            "grade": "unknown",
            "labels": ["[财务数据不足]"],
            "veto": False,
            "summary_zh": "已识别 ticker，但 SEC 财务事实不足，无法体检；小市值股尤其要当心。",
        }

    elasticity = _revenue_elasticity(candidate, snapshot)
    margin = _margin_health(snapshot)
    runway = _survival_runway(snapshot)

    labels: list[str] = []
    veto = bool(runway.get("veto"))
    if veto:
        labels.append("[高风险归零股]")
    if margin.get("declining"):
        labels.append("[流血中标]")
    if elasticity.get("band") == "transformational":
        labels.append("[基数惊天逆转]")
    elif elasticity.get("band") == "immaterial":
        labels.append("[非核心财务催化剂]")

    grade = _grade(veto, margin, runway, elasticity)
    return {
        "status": "screened",
        "ticker": snapshot.get("ticker"),
        "grade": grade,
        "veto": veto,
        "labels": labels,
        "revenue_elasticity": elasticity,
        "margin": margin,
        "runway": runway,
        "summary_zh": _summary_zh(grade, elasticity, margin, runway),
    }


def _grade(veto: bool, margin: dict[str, object], runway: dict[str, object], elasticity: dict[str, object]) -> str:
    if veto:
        return "high_risk"
    months = runway.get("months")
    if margin.get("declining"):
        return "caution"
    if isinstance(months, (int, float)) and months < RUNWAY_CAUTION_MONTHS:
        return "caution"
    if elasticity.get("band") == "immaterial":
        return "caution"
    return "ok"


def _revenue_elasticity(candidate: dict[str, object], snapshot: dict[str, object]) -> dict[str, object]:
    order = _disclosed_order_musd(candidate)
    base = _number(snapshot.get("revenue_base_musd"))
    if order is None or base is None or base <= 0:
        return {
            "band": "unknown",
            "ratio_pct": None,
            "order_musd": order,
            "revenue_base_musd": base,
            "zh": "缺少披露金额或收入基数，无法判断订单弹性（避免基数幻觉）。",
        }
    ratio = round(order / base * 100, 2)
    if ratio >= ELASTICITY_TRANSFORMATIONAL_PCT:
        band, zh = "transformational", f"订单≈营收基数的 {ratio:.1f}%，相对体量极大，可能是惊天逆转，优先建模。"
    elif ratio >= ELASTICITY_IMMATERIAL_PCT:
        band, zh = "material", f"订单≈营收基数的 {ratio:.1f}%，对收入有实际影响。"
    else:
        band, zh = "immaterial", f"订单≈营收基数的 {ratio:.2f}%，对整体收入几乎无影响（毛毛雨），别因标题追高。"
    return {"band": band, "ratio_pct": ratio, "order_musd": order, "revenue_base_musd": base, "zh": zh}


def _margin_health(snapshot: dict[str, object]) -> dict[str, object]:
    trend = [float(x) for x in (snapshot.get("gross_margin_trend_pct") or []) if isinstance(x, (int, float))]
    if len(trend) < 3:
        return {"declining": False, "trend_pct": trend, "zh": "毛利率季度序列不足，无法判断趋势。"}
    declining = trend[-1] < trend[-2] < trend[-3] and (trend[-3] - trend[-1]) >= MARGIN_EROSION_PP
    if declining:
        zh = f"毛利率连续两季下滑（{trend[-3]:.1f}%→{trend[-2]:.1f}%→{trend[-1]:.1f}%），即便拿到订单也可能是流血中标。"
    else:
        zh = f"毛利率近季 {trend[-1]:.1f}%，未见连续恶化。"
    return {"declining": declining, "trend_pct": trend, "zh": zh}


def _survival_runway(snapshot: dict[str, object]) -> dict[str, object]:
    cash = _number(snapshot.get("cash_musd"))
    ocf = _number(snapshot.get("quarterly_operating_cash_flow_musd"))
    if cash is None or ocf is None:
        return {"months": None, "veto": False, "cash_musd": cash, "quarterly_ocf_musd": ocf,
                "zh": "缺少现金或经营现金流数据，无法计算生存跑道。"}
    if ocf >= 0:
        return {"months": None, "veto": False, "cash_musd": cash, "quarterly_ocf_musd": ocf,
                "zh": f"经营现金流为正（季度 {ocf:.1f} 百万美元），无即时生存风险。"}
    monthly_burn = abs(ocf) / 3.0
    months = round(cash / monthly_burn, 1) if monthly_burn > 0 else None
    veto = months is not None and months < RUNWAY_VETO_MONTHS
    if veto:
        zh = f"现金 {cash:.1f} 百万美元，季度净流出 {abs(ocf):.1f} 百万，仅够 ~{months:.1f} 个月，存在归零风险，一票否决。"
    else:
        zh = f"现金 {cash:.1f} 百万美元，按当前烧钱速度可支撑 ~{months:.1f} 个月。" if months else "现金充足。"
    return {"months": months, "veto": veto, "cash_musd": cash, "quarterly_ocf_musd": ocf, "zh": zh}


def _summary_zh(grade: str, elasticity: dict[str, object], margin: dict[str, object], runway: dict[str, object]) -> str:
    head = {"high_risk": "财务体检：高风险", "caution": "财务体检：需谨慎", "ok": "财务体检：通过", "unknown": "财务体检：数据不足"}.get(grade, "财务体检")
    return f"{head}。{elasticity.get('zh', '')} {margin.get('zh', '')} {runway.get('zh', '')}".strip()


def _primary_snapshot(candidate: dict[str, object]) -> dict[str, object]:
    financial = candidate.get("financial_snapshot")
    if not isinstance(financial, dict):
        return {}
    snapshots = financial.get("snapshots")
    if not isinstance(snapshots, list):
        return {}
    for snapshot in snapshots:
        if isinstance(snapshot, dict) and snapshot.get("revenue_base_musd") is not None:
            return snapshot
    return snapshots[0] if snapshots and isinstance(snapshots[0], dict) else {}


def _disclosed_order_musd(candidate: dict[str, object]) -> float | None:
    impact = candidate.get("impact_assessment")
    if not isinstance(impact, dict):
        return None
    amounts = impact.get("amount_mentions")
    if not isinstance(amounts, list):
        return None
    values = [
        float(amount.get("value_millions_usd"))
        for amount in amounts
        if isinstance(amount, dict) and isinstance(amount.get("value_millions_usd"), (int, float))
    ]
    return max(values) if values else None


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
