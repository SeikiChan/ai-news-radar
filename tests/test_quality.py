from src.abnormal_news_radar.quality import enrich_candidates_with_quality_screen, screen_candidate


def _candidate(snapshot=None, order_musd=None, tickers=("XYZ",)):
    candidate = {"tickers": list(tickers)}
    if snapshot is not None:
        candidate["financial_snapshot"] = {"status": "ok", "snapshots": [snapshot]}
    if order_musd is not None:
        candidate["impact_assessment"] = {"amount_mentions": [{"mention": f"${order_musd}M", "value_millions_usd": order_musd}]}
    return candidate


def _snap(**kw):
    base = {"ticker": "XYZ", "revenue_base_musd": 100.0, "gross_margin_trend_pct": [40, 41, 42],
            "cash_musd": 500.0, "quarterly_operating_cash_flow_musd": 30.0}
    base.update(kw)
    return base


def test_no_ticker_is_not_screened():
    screen = screen_candidate({"tickers": []})
    assert screen["status"] == "no_ticker"
    assert screen["veto"] is False


def test_insufficient_data_when_no_snapshot():
    screen = screen_candidate({"tickers": ["XYZ"]})
    assert screen["status"] == "insufficient_data"
    assert screen["veto"] is False


def test_going_concern_veto_flags_high_risk():
    # $20M cash, burning $60M/quarter -> ~1 month runway -> veto.
    snap = _snap(cash_musd=20.0, quarterly_operating_cash_flow_musd=-60.0)
    screen = screen_candidate(_candidate(snap))
    assert screen["veto"] is True
    assert screen["grade"] == "high_risk"
    assert "[高风险归零股]" in screen["labels"]


def test_healthy_cash_flow_no_veto():
    screen = screen_candidate(_candidate(_snap(cash_musd=500.0, quarterly_operating_cash_flow_musd=30.0)))
    assert screen["veto"] is False
    assert screen["runway"]["months"] is None  # cash-generative


def test_revenue_elasticity_transformational():
    # $25M order on a $100M revenue base -> 25% -> transformational.
    screen = screen_candidate(_candidate(_snap(revenue_base_musd=100.0), order_musd=25.0))
    el = screen["revenue_elasticity"]
    assert el["band"] == "transformational"
    assert el["ratio_pct"] == 25.0
    assert "[基数惊天逆转]" in screen["labels"]


def test_revenue_elasticity_immaterial():
    # $10M order on a $5B revenue base -> 0.2% -> immaterial (base illusion).
    screen = screen_candidate(_candidate(_snap(revenue_base_musd=5000.0), order_musd=10.0))
    el = screen["revenue_elasticity"]
    assert el["band"] == "immaterial"
    assert "[非核心财务催化剂]" in screen["labels"]
    assert screen["grade"] == "caution"


def test_elasticity_unknown_without_order_or_base():
    screen = screen_candidate(_candidate(_snap(), order_musd=None))
    assert screen["revenue_elasticity"]["band"] == "unknown"


def test_margin_decline_flags_bleeding_deal():
    snap = _snap(gross_margin_trend_pct=[30, 20, 10], cash_musd=500.0, quarterly_operating_cash_flow_musd=30.0)
    screen = screen_candidate(_candidate(snap, order_musd=25.0))
    assert screen["margin"]["declining"] is True
    assert "[流血中标]" in screen["labels"]


def test_enrich_attaches_quality_screen():
    rows = enrich_candidates_with_quality_screen([_candidate(_snap(), order_musd=25.0)])
    assert "quality_screen" in rows[0]
    assert rows[0]["quality_screen"]["status"] == "screened"
