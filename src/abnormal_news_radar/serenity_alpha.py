"""Serenity Alpha — translate news into an investable alpha *hypothesis*.

This absorbs the haskaomni/serenity-skill "news-to-alpha" stock-picking
philosophy. The radar's default ranking is "which name has the hardest
evidence", which structurally favours mega-caps (a $500M order is noise to
NVIDIA). Serenity asks the opposite, sharper question:

    *Who is the SMALL, PURE, MIS-CLASSIFIED beneficiary whose REPORTED numbers
    this already-observable demand change could actually move — and can it be
    verified within 1-4 quarters?*

Five multiplicative dimensions (any near-zero kills the idea — you must satisfy
all five, not average them):

    demand_certainty x transmission_clarity x business_purity
      x market_cap_elasticity x market_neglect  ->  alpha_score (0..100)

Plus the five Serenity exclusion filters (narrative-only / distant transmission
/ large-cap / high-consensus / unverifiable) and a four-bucket verification
chain (income statement, cash-flow & demand, operating leverage, market
validation) with a 1-4 quarter falsification window.

READ-ONLY: this enrichment only *attaches* ``serenity_alpha`` to each candidate
for display. It deliberately does NOT change the candidate's score, action, or
ranking — it is a second lens, surfaced beside the evidence score.

Inputs are reused from signals already on the candidate (evidence tier /
confidence, the impact module's quantified amounts, the SEC financial snapshot,
the institutional-ownership reading). The only new fetch is market cap +
analyst-coverage count from Yahoo (``price`` + ``financialData`` modules) via
the shared cookie/crumb session. Every failure degrades to a status flag — it
never fabricates a dimension it could not measure.
"""

from __future__ import annotations

import json

from .model import Company
from .yahoo import make_yahoo_fetcher, quote_summary_url
from .yahoo import raw as _raw

#: A demand shock cannot meaningfully move a company this large — Serenity's
#: "large-cap" exclusion. (USD market cap.)
MEGA_CAP_USD = 200_000_000_000.0
#: Coverage above this many sell-side analysts ≈ already-consensus.
CONSENSUS_ANALYST_COUNT = 25
#: Institutional ownership above this share ≈ crowded / fully discovered.
CROWDED_INSTITUTION_PCT = 0.90

_TIER_BASE = {"hard_evidence": 1.0, "material": 0.6, "thematic": 0.3, "none": 0.15}

_DIM_LABELS_ZH = {
    "demand_certainty": "需求确定性",
    "transmission_clarity": "财务传导清晰度",
    "business_purity": "业务纯度",
    "market_cap_elasticity": "市值弹性",
    "market_neglect": "市场忽视度",
}

_DEMAND_TERMS = (
    "order", "purchase order", "production order", "backlog", "book-to-bill",
    "capacity", "prepayment", "advance payment", "mass production", "volume production",
    "ramp", "design win", "offtake",
)
_CAPACITY_TERMS = ("capacity", "production", "ramp", "mass production", "volume production", "capex", "gigafactory")


def enrich_candidates_with_serenity_alpha(
    candidates: list[dict[str, object]],
    fetcher: object | None = None,
    watchlist: list[Company] | None = None,
    max_tickers: int = 20,
) -> list[dict[str, object]]:
    """Attach a ``serenity_alpha`` hypothesis to each candidate (read-only)."""
    themes_by_ticker = _themes_by_ticker(watchlist or [])
    tickers = _candidate_tickers(candidates)[:max_tickers]
    market: dict[str, dict[str, object]] = {}
    if tickers:
        fetch = fetcher or make_yahoo_fetcher()
        for ticker in tickers:
            market[ticker] = fetch_market_profile(ticker, fetch)

    enriched: list[dict[str, object]] = []
    for candidate in candidates:
        row = dict(candidate)
        row["serenity_alpha"] = _assess_candidate(row, market, themes_by_ticker)
        enriched.append(row)
    return enriched


def fetch_market_profile(ticker: str, fetch: object) -> dict[str, object]:
    """Market cap + sell-side coverage from Yahoo ``price`` + ``financialData``."""
    symbol = ticker.strip().upper()
    if not symbol:
        return {"status": "no_ticker"}
    url = quote_summary_url(symbol, "price,financialData")
    try:
        payload = json.loads(fetch(url))  # type: ignore[operator]
        result = (((payload.get("quoteSummary") or {}).get("result")) or [None])[0]
        if not isinstance(result, dict):
            return {"status": "unavailable", "ticker": symbol, "reason": "no result"}
        price = result.get("price") if isinstance(result.get("price"), dict) else {}
        fin = result.get("financialData") if isinstance(result.get("financialData"), dict) else {}
        return {
            "status": "ok",
            "ticker": symbol,
            "market_cap_usd": _num(_raw(price.get("marketCap"))),
            "analyst_count": _num(_raw(fin.get("numberOfAnalystOpinions"))),
            "total_revenue_usd": _num(_raw(fin.get("totalRevenue"))),
            "source": "Yahoo price+financialData",
        }
    except Exception as exc:  # noqa: BLE001 - degrade cleanly; never break the scan.
        return {"status": "unavailable", "ticker": symbol, "reason": str(exc)[:160]}


def _assess_candidate(
    candidate: dict[str, object],
    market: dict[str, dict[str, object]],
    themes_by_ticker: dict[str, tuple[str, ...]],
) -> dict[str, object]:
    tickers = [str(t).upper() for t in (candidate.get("tickers") or []) if str(t).strip()]
    company = str(candidate.get("company_name") or "该公司")

    profile = next((market[t] for t in tickers if market.get(t, {}).get("status") == "ok"), {})
    market_cap = _num(profile.get("market_cap_usd"))
    analyst_count = _num(profile.get("analyst_count"))

    tier = str(candidate.get("evidence_tier") or "none")
    confidence = float(candidate.get("confidence") or 0.0)
    status = str(candidate.get("status") or "")
    terms = {str(t).lower() for t in (candidate.get("matched_terms") or [])}
    revenue_base_musd = _snapshot_revenue_musd(candidate)
    amount_usd = _largest_amount_usd(candidate)
    materiality = _dict_get(candidate, "impact", "materiality")
    inst_pct = _num(_dict_get(candidate, "institutional_flow", "institutions_pct_held"))
    themes = next((themes_by_ticker[t] for t in tickers if t in themes_by_ticker), ())

    # --- five multiplicative dimensions (each 0..1) ---------------------------
    has_amount = amount_usd is not None
    demand = round(_TIER_BASE.get(tier, 0.3) * (0.7 + 0.3 * min(confidence, 1.0)), 3)
    transmission = _transmission(tier, has_amount, materiality, revenue_base_musd is not None)
    purity = _purity(market_cap)
    elasticity = _elasticity(market_cap, amount_usd)
    neglect = _neglect(analyst_count, inst_pct)

    dims = {
        "demand_certainty": demand,
        "transmission_clarity": transmission,
        "business_purity": purity,
        "market_cap_elasticity": elasticity,
        "market_neglect": neglect,
    }
    alpha = round(demand * transmission * purity * elasticity * neglect * 100.0, 1)
    weakest_key = min(dims, key=lambda k: dims[k])

    # --- exclusion filters ---------------------------------------------------
    triggered: list[dict[str, str]] = []
    if market_cap is not None and market_cap > MEGA_CAP_USD:
        triggered.append({"key": "large_cap", "reason_zh": f"市值约 {_fmt_usd(market_cap)}，需求冲击难以撼动其报表（仅利好巨头）。"})
    if tier in ("thematic", "none") and not has_amount:
        triggered.append({"key": "narrative_only", "reason_zh": "仅叙事/主题，需求尚不可观测（无具名金额或硬证据）。"})
    if status == "discovered" and confidence < 0.4:
        triggered.append({"key": "distant_transmission", "reason_zh": "归属/传导链偏弱，需求难在 1–2 步内落到这家具名公司。"})
    if (analyst_count is not None and analyst_count > CONSENSUS_ANALYST_COUNT) or (inst_pct is not None and inst_pct > CROWDED_INSTITUTION_PCT):
        triggered.append({"key": "high_consensus", "reason_zh": "覆盖/持仓已高度拥挤，多半已被price in。"})

    chain = _verification_chain(terms)
    if not chain["cashflow_demand"] and not chain["income_statement_hooked"]:
        triggered.append({"key": "unverifiable", "reason_zh": "缺少近端可量化检查点，1–4 季内难以证实/证伪。"})

    keys = {f["key"] for f in triggered}
    structural = keys & {"large_cap", "narrative_only", "distant_transmission"}
    if structural:
        verdict = "excluded"
    elif keys & {"high_consensus", "unverifiable"}:
        verdict = "exploratory"
    else:
        verdict = "qualified"

    return {
        "status": "ok" if (market_cap is not None or analyst_count is not None) else "partial",
        "alpha_score": alpha,
        "verdict": verdict,
        "dimensions": [
            {"key": k, "label_zh": _DIM_LABELS_ZH[k], "value": round(dims[k], 3)} for k in _DIM_LABELS_ZH
        ],
        "weakest_zh": _DIM_LABELS_ZH[weakest_key],
        "excluded_filters": triggered,
        "verification_chain": {
            "income_statement": chain["income_statement"],
            "cashflow_demand": chain["cashflow_demand"],
            "operating_leverage": chain["operating_leverage"],
            "market_validation": chain["market_validation"],
            "timeline_zh": "1–4 个季度内通过季报与电话会确认或证伪；关键假设被证伪即从观察池剔除。",
        },
        "posture_zh": _posture(verdict, keys, transmission),
        "relabel_zh": _relabel(company, themes),
        "market_cap_usd": market_cap,
        "market_cap_display": _fmt_usd(market_cap) if market_cap is not None else "n/a",
        "analyst_count": analyst_count,
        "revenue_base_musd": revenue_base_musd,
        "summary_zh": _summary_zh(alpha, verdict, _DIM_LABELS_ZH[weakest_key], dims[weakest_key], triggered),
        "source": "Yahoo price+financialData + 雷达内已有证据/财务/机构信号（只读叠加层）",
    }


# --------------------------------------------------------------------------- #
# dimension helpers
# --------------------------------------------------------------------------- #
def _transmission(tier: str, has_amount: bool, materiality: object, has_revenue: bool) -> float:
    if has_amount and has_revenue:
        return 1.0
    if str(materiality) == "high":
        return 0.85
    if has_amount or tier == "hard_evidence":
        return 0.7
    if tier == "material":
        return 0.55
    return 0.4


def _purity(market_cap: float | None) -> float:
    """Size proxy for purity: a mega-cap's reported numbers are diluted across
    many lines; smaller pure-plays are more directly exposed. (Honest proxy —
    we have no per-segment data for discovered names.)"""
    if market_cap is None:
        return 0.6
    b = market_cap / 1e9
    if b < 2:
        return 0.95
    if b < 10:
        return 0.9
    if b < 50:
        return 0.78
    if b < 200:
        return 0.62
    return 0.45


def _elasticity(market_cap: float | None, amount_usd: float | None) -> float:
    if market_cap is None:
        return 0.5
    b = market_cap / 1e9
    if b < 2:
        base = 1.0
    elif b < 10:
        base = 0.8
    elif b < 50:
        base = 0.45
    elif b < 200:
        base = 0.22
    else:
        base = 0.08
    # incremental demand / current scale = alpha potential
    if amount_usd and market_cap > 0:
        ratio = amount_usd / market_cap
        if ratio >= 0.10:
            base = max(base, 0.9)
        elif ratio >= 0.03:
            base = max(base, 0.6)
    return round(base, 3)


def _neglect(analyst_count: float | None, inst_pct: float | None) -> float:
    if analyst_count is None:
        neglect = 0.5
    elif analyst_count <= 3:
        neglect = 1.0
    elif analyst_count <= 8:
        neglect = 0.7
    elif analyst_count <= 20:
        neglect = 0.45
    else:
        neglect = 0.25
    if inst_pct is not None and inst_pct > 0.85:
        neglect *= 0.8
    return round(neglect, 3)


def _verification_chain(terms: set[str]) -> dict[str, object]:
    income = [
        "下一季营收同比/环比增速是否抬升",
        "管理层是否上调指引(guidance)",
        "毛利率 / 产品组合(mix)是否改善",
    ]
    demand_hit = any(any(t in term for t in _DEMAND_TERMS) for term in terms)
    capacity_hit = any(any(t in term for t in _CAPACITY_TERMS) for term in terms)
    cashflow = []
    if demand_hit:
        cashflow = ["在手订单 backlog / 出货比 book-to-bill", "交期 lead time 与订单评论", "存货周转"]
    opslev = []
    if capacity_hit:
        opslev = ["产能利用率 / 扩产 capex", "固定成本摊薄(operating leverage)"]
    market_validation = ["管理层电话会是否『主动』提及该需求", "竞争对手 / 供应商 / 客户的侧面印证"]
    return {
        "income_statement": income,
        "income_statement_hooked": demand_hit or capacity_hit,
        "cashflow_demand": cashflow,
        "operating_leverage": opslev,
        "market_validation": market_validation,
    }


def _posture(verdict: str, keys: set[str], transmission: float) -> str:
    if "narrative_only" in keys:
        return "需求未坐实——仅观察，至多极小试探仓。"
    if "large_cap" in keys:
        return "需求难以撼动其报表（市值过大）——非本策略首选标的，可作主题参考。"
    if "distant_transmission" in keys:
        return "归属/传导链不清——先确认是哪家具名公司直接受益，再谈仓位。"
    if "high_consensus" in keys:
        return "已是高共识 / 估值或已拉伸——降低收益预期，只做交易性参与。"
    if transmission < 0.6:
        return "需求或已出现但传导不清——观察，极小试探仓。"
    return "需求与传导较清晰、市场关注仍低——可小额试探仓，按 1–4 季验证链加减。"


def _relabel(company: str, themes: tuple[str, ...]) -> str:
    if themes:
        theme = themes[0].replace("_", " ")
        return (
            f"市场当前或仍按『{theme}』给 {company} 定价；若该需求持续兑现，"
            f"其角色有望被重估为该需求链上的直接受益方——以下方验证链确认，而非凭叙事。"
        )
    return (
        f"先问：市场现在把 {company} 当成什么？若需求持续，它可能正在变成什么？"
        "差距是否大到、且足够接近报表，能形成错误定价——用验证链确认。"
    )


def _summary_zh(alpha: float, verdict: str, weakest_label: str, weakest_value: float, triggered: list[dict[str, str]]) -> str:
    verdict_zh = {"qualified": "通过 Serenity 筛", "exploratory": "仅探索级", "excluded": "被排除"}.get(verdict, verdict)
    head = f"Serenity 五维 alpha={alpha}（满分100，乘法制）；结论：{verdict_zh}。最弱环节：{weakest_label}（{weakest_value:.2f}）。"
    if triggered:
        head += " 触发排除：" + "、".join(f["reason_zh"] for f in triggered[:2])
    return head


# --------------------------------------------------------------------------- #
# input extraction
# --------------------------------------------------------------------------- #
def _snapshot_revenue_musd(candidate: dict[str, object]) -> float | None:
    snap = candidate.get("financial_snapshot")
    if not isinstance(snap, dict):
        return None
    return _num(snap.get("revenue_base_musd")) or _num(snap.get("ttm_revenue_musd")) or _num(snap.get("revenue_musd"))


def _largest_amount_usd(candidate: dict[str, object]) -> float | None:
    impact = candidate.get("impact")
    if not isinstance(impact, dict):
        return None
    mentions = impact.get("amount_mentions")
    if not isinstance(mentions, list):
        return None
    values = [_num(m.get("value_millions_usd")) for m in mentions if isinstance(m, dict)]
    values = [v for v in values if v is not None]
    return max(values) * 1_000_000 if values else None


def _dict_get(candidate: dict[str, object], key: str, field: str) -> object:
    node = candidate.get(key)
    return node.get(field) if isinstance(node, dict) else None


def _themes_by_ticker(watchlist: list[Company]) -> dict[str, tuple[str, ...]]:
    return {c.ticker.upper(): tuple(c.themes) for c in watchlist if getattr(c, "ticker", "")}


def _candidate_tickers(candidates: list[dict[str, object]]) -> list[str]:
    output: list[str] = []
    for candidate in candidates:
        for ticker in candidate.get("tickers", []) or []:
            text = str(ticker).upper().strip()
            if text and text not in output:
                output.append(text)
    return output


def _num(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _fmt_usd(value: object) -> str:
    v = _num(value)
    if v is None:
        return "n/a"
    if abs(v) >= 1e12:
        return f"${v / 1e12:.2f}T"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:.0f}"
