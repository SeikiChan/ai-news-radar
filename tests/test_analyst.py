import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.abnormal_news_radar.analyst import build_daily_brief, next_automated_run, select_digest_items


class AnalystBriefTests(unittest.TestCase):
    def test_digest_spreads_companies_and_retains_other_article_links(self):
        rows = [
            {"company_name": "A", "tickers": ["AAA"], "score": 50, "article": {"title": "A order", "link": "https://a/1"}},
            {"company_name": "A", "tickers": ["AAA"], "score": 48, "article": {"title": "A filing", "source": "SEC", "link": "https://a/2"}},
            {"company_name": "B", "tickers": ["BBB"], "score": 40, "article": {"title": "B order"}},
        ]
        digest = select_digest_items(rows, limit=2)
        self.assertEqual([row["company_name"] for row in digest], ["A", "B"])
        self.assertEqual(digest[0]["related_update_count"], 1)
        self.assertEqual(digest[0]["related_updates"][0]["link"], "https://a/2")
        self.assertNotIn("related_updates", rows[0])

    def test_old_candidates_do_not_reappear_as_today_ideas(self):
        old = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
        candidate = {"company_name": "Old Co", "score": 50, "status": "discovered",
                     "article": {"title": "Old order", "published": old, "fetched_at": old}}
        brief = build_daily_brief([], [candidate], {}, 1, 0)
        self.assertEqual(brief["analyst_report"], [])
        self.assertEqual(brief["digest_items"], [])
        self.assertEqual(brief["counts"]["urgent_items"], 0)

    def test_undated_candidate_uses_first_retrieval_age(self):
        old = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
        candidate = {"company_name": "Old IR Page", "score": 50, "status": "discovered",
                     "first_seen_at": old,
                     "article": {"title": "Undated order", "fetched_at": datetime.now(timezone.utc).isoformat()}}
        brief = build_daily_brief([], [candidate], {}, 1, 0)
        self.assertEqual(brief["digest_items"], [])

    def test_vetoed_high_score_does_not_outrank_actionable_idea(self):
        candidates = [
            {"company_name": "Risky", "score": 70, "status": "discovered",
             "quality_screen": {"veto": True}, "article": {"title": "Risky order"}},
            {"company_name": "Actionable", "score": 40, "status": "discovered",
             "article": {"title": "Actionable order"}},
        ]
        brief = build_daily_brief([], candidates, {}, 1, 0)
        self.assertEqual(brief["analyst_report"][0]["company_name"], "Actionable")
        self.assertEqual(brief["digest_items"][0]["company_name"], "Actionable")

    def test_brief_routes_high_score_candidate_to_review_queue(self):
        candidates = [
            {
                "company_name": "Example Photonics",
                "score": 28.0,
                "status": "discovered",
                "article": {"title": "Example receives production order"},
            }
        ]

        brief = build_daily_brief(
            signals=[],
            candidates=candidates,
            last_scan={"fetched_count": 42},
            source_count=9,
            watchlist_count=16,
            market_source_count=8,
        )

        self.assertEqual(brief["counts"]["articles_reviewed"], 42)
        self.assertEqual(brief["counts"]["market_sources"], 8)
        self.assertEqual(brief["counts"]["dynamic_watchlist"], 1)
        self.assertEqual(brief["counts"]["review_items"], 1)
        self.assertEqual(brief["analyst_report"][0]["action"], "track")
        self.assertEqual(brief["analyst_report"][0]["decision"], "Track, do not buy yet")
        self.assertEqual(brief["dynamic_watchlist"][0]["company_name"], "Example Photonics")
        self.assertIn("进入", brief["dynamic_watchlist"][0]["decision_zh"])
        self.assertIn("price/volume confirmation", brief["analyst_report"][0]["missing_confirmations"])
        self.assertIn("price/volume", " ".join(brief["data_gaps"]))

    def test_brief_excludes_reviewed_candidates_from_review_queue(self):
        candidates = [
            {
                "company_name": "Example Photonics",
                "score": 28.0,
                "status": "discovered",
                "review_status": "reviewed",
                "article": {"title": "Example receives production order"},
            }
        ]

        brief = build_daily_brief(
            signals=[],
            candidates=candidates,
            last_scan={"fetched_count": 42},
            source_count=9,
            watchlist_count=16,
        )

        self.assertEqual(brief["counts"]["review_items"], 0)

    def test_brief_excludes_promoted_candidates_from_daily_report_queue(self):
        candidates = [
            {
                "company_name": "Example Photonics",
                "score": 28.0,
                "status": "discovered",
                "review_status": "promoted",
                "article": {"title": "Example receives production order"},
            }
        ]

        brief = build_daily_brief(
            signals=[],
            candidates=candidates,
            last_scan={"fetched_count": 42},
            source_count=9,
            watchlist_count=16,
        )

        self.assertEqual(brief["counts"]["report_items"], 0)

    def test_dynamic_watchlist_aggregates_repeated_news_by_company(self):
        candidates = [
            {
                "company_name": "Example Robotics",
                "score": 22.0,
                "status": "discovered",
                "matched_terms": ["contract"],
                "article": {"title": "Example wins contract", "source": "Wire A", "link": "https://a.example"},
            },
            {
                "company_name": "Example Robotics",
                "score": 18.0,
                "status": "discovered",
                "matched_terms": ["production order"],
                "article": {"title": "Example receives order", "source": "Wire B", "link": "https://b.example"},
            },
        ]

        brief = build_daily_brief(
            signals=[],
            candidates=candidates,
            last_scan={"fetched_count": 2},
            source_count=9,
            watchlist_count=16,
            market_regime={"status": "connected", "regime": "risk_on", "score": 3, "summary": "ok"},
        )

        self.assertEqual(brief["counts"]["dynamic_watchlist"], 1)
        item = brief["dynamic_watchlist"][0]
        self.assertEqual(item["evidence_count"], 2)
        self.assertEqual(item["sources"], ["Wire A", "Wire B"])
        self.assertEqual(item["origin"], "news_discovered")

    def test_next_automated_run_uses_five_minute_market_window(self):
        now = datetime(2026, 5, 27, 13, 2, tzinfo=ZoneInfo("America/New_York"))

        next_run = next_automated_run(now)

        self.assertEqual(next_run.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M"), "13:05")

    def test_next_automated_run_slows_down_on_weekend(self):
        now = datetime(2026, 5, 30, 13, 2, tzinfo=ZoneInfo("America/New_York"))

        next_run = next_automated_run(now)

        self.assertEqual(next_run.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M"), "14:00")


if __name__ == "__main__":
    unittest.main()
