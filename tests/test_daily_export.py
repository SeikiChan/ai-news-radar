import json
import tempfile
import unittest
from pathlib import Path

from src.abnormal_news_radar.daily_report import export_daily_report, render_daily_report

BRIEF = {
    "counts": {"articles_reviewed": 120, "report_items": 2, "urgent_items": 1, "discoveries": 9},
    "market_regime": {"regime": "risk_on", "score": 62},
    "market_conclusion_zh": {"title": "偏进攻", "summary": "广度健康", "action": "可加仓"},
    "analyst_report": [
        {
            "tickers": ["SMALLCO"], "company_name": "SmallCo", "action": "research_now",
            "score": 41.2, "confidence": 0.8, "matched_terms": ["purchase order", "humanoid robot"],
            "decision": "进入观察",
            "article": {"source": "GlobeNewswire", "title": "SmallCo wins humanoid robot order", "link": "http://x"},
            "serenity_alpha": {
                "status": "ok", "alpha_score": 82.9, "verdict": "qualified", "weakest_zh": "市场忽视度",
                "market_cap_display": "$1.50B", "market_cap_usd": 1.5e9, "analyst_count": 2,
                "posture_zh": "小额试探仓", "excluded_filters": [],
            },
        },
        {
            "tickers": ["MEGA"], "company_name": "MegaCorp", "action": "monitor",
            "score": 38.0, "confidence": 0.7, "matched_terms": ["purchase order"],
            "article": {"source": "PRNewswire", "title": "MegaCorp order", "link": "http://y"},
            "serenity_alpha": {
                "status": "ok", "alpha_score": 7.1, "verdict": "excluded", "weakest_zh": "市值弹性",
                "market_cap_display": "$1.50T", "market_cap_usd": 1.5e12, "analyst_count": 50,
                "excluded_filters": [{"key": "large_cap", "reason_zh": "市值过大"}],
            },
        },
    ],
    "dynamic_watchlist": [],
    "earnings_calendar": {"items": [], "summary_zh": "窗口内无标的"},
    "data_gaps_zh": ["X 源未取到"],
}


class DailyExportTests(unittest.TestCase):
    def test_serenity_section_rendered_and_sorted(self):
        md = render_daily_report(BRIEF)
        self.assertIn("Serenity Alpha", md)
        self.assertIn("通过筛 1", md)
        self.assertIn("被排除 1", md)
        # qualified beneficiary appears before the excluded mega-cap
        self.assertLess(md.index("SMALLCO"), md.index("MEGA"))

    def test_export_writes_markdown_dated_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            paths = export_daily_report(BRIEF, d)
            self.assertTrue(Path(paths["markdown"]).exists())
            self.assertTrue(Path(paths["dated"]).exists())
            self.assertTrue(Path(paths["markdown"]).name == "latest-daily-report.md")
            payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertEqual(len(payload["top_calls"]), 2)
            self.assertEqual(payload["top_calls"][0]["serenity_alpha"]["verdict"], "qualified")
            self.assertIn("NOT investment advice", payload["purpose"])

    def test_export_handles_empty_brief(self):
        with tempfile.TemporaryDirectory() as d:
            paths = export_daily_report({}, d)
            self.assertTrue(Path(paths["markdown"]).exists())


if __name__ == "__main__":
    unittest.main()
