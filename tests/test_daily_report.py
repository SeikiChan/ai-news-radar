from src.abnormal_news_radar.daily_report import render_daily_report


def _brief():
    return {
        "counts": {"urgent_items": 1, "articles_reviewed": 200, "discoveries": 9, "report_items": 3},
        "market_regime": {"regime": "risk_on", "score": 5},
        "market_conclusion_zh": {"title": "宏观偏进攻", "summary": "成长股有配合。", "action": "可积极跟踪硬证据标的。"},
        "analyst_report": [
            {
                "action": "research_now", "tickers": ["NVDA"], "company_name": "NVIDIA",
                "score": 61.6, "confidence": 0.75, "decision": "Research now; wait for confirmation",
                "article": {"source": "BusinessWire", "title": "NVIDIA $1B order", "link": "https://x/1"},
                "market_confirmation": {"status": "unconfirmed"},
                "impact_assessment": {"impact_score": 4},
                "financial_snapshot": {"status": "ok"},
                "options_flow": {"status": "no_flow_evidence"},
                "expectation_check": {"status": "watch_only"},
                "quality_screen": {"veto": False, "labels": ["[基数惊天逆转]"],
                                   "revenue_elasticity": {"band": "transformational", "zh": "订单≈营收 25%"}},
                "short_squeeze": {"status": "ok", "alert": True, "potential": "high",
                                  "label": "[警告：极高空头轧空爆发潜力]", "summary_zh": "空头占流通盘 22.0%（高）"},
            },
            {
                "action": "monitor", "tickers": ["ZZZ"], "company_name": "Penny Co",
                "score": 40.0, "decision": "高风险归零股",
                "article": {"source": "PRNewswire", "title": "Penny gets big order", "link": "https://x/2"},
                "quality_screen": {"veto": True, "labels": ["[高风险归零股]"]},
                "short_squeeze": {"status": "ok", "alert": True, "potential": "high", "label": "[x]"},
            },
        ],
        "dynamic_watchlist": [
            {"tickers": ["VRT", "CEG"], "company_name": "Vertiv", "conviction": 4, "decision_zh": "进入重点观察",
             "quality_screen": {}, "short_squeeze": {}},
        ],
        "earnings_calendar": {"summary_zh": "窗口内 2 个财报。", "items": [
            {"date": "2026-06-03", "ticker": "AVGO", "name": "Broadcom", "time": "time-after-hours", "eps_forecast": "$1.20"},
        ]},
        "data_gaps_zh": ["缺口A", "缺口B"],
    }


def test_report_has_all_sections():
    md = render_daily_report(_brief())
    for heading in ["每日投研简报", "市场姿态", "TOP CALLS", "动态观察池", "未来财报窗口", "证据缺口"]:
        assert heading in md


def test_top_call_renders_with_evidence_and_catalyst():
    md = render_daily_report(_brief())
    assert "NVDA" in md
    assert "评分 61.6" in md
    assert "市场=未确认" in md
    assert "https://x/1" in md


def test_squeeze_alert_shown_for_healthy_name():
    md = render_daily_report(_brief())
    assert "🚀" in md
    assert "空头轧空" in md


def test_veto_shown_and_suppresses_squeeze_amplifier():
    md = render_daily_report(_brief())
    # Penny Co is vetoed -> shows stop flag, and the squeeze rocket must NOT be
    # attached to a going-concern name.
    assert "🛑" in md
    assert "[高风险归零股]" in md
    penny_line = [line for line in md.splitlines() if "Penny Co" in line][0]
    assert "🚀" not in penny_line


def test_disclaimer_present():
    md = render_daily_report(_brief())
    assert "非投资建议" in md


def test_handles_empty_brief():
    md = render_daily_report({})
    assert "每日投研简报" in md
    assert "本轮无达到阈值的机会" in md
