import unittest

from src.abnormal_news_radar.options_flow import assess_options_flow, enrich_candidates_with_options_flow


class OptionsFlowTests(unittest.TestCase):
    def test_supportive_flow_when_bullish_flow_matches_candidate(self):
        candidate = {
            "company_name": "Advanced Micro Devices",
            "tickers": ["AMD"],
            "market_confirmation": {"status": "price_only_confirmation"},
            "impact_assessment": {"impact_score": 4},
        }
        articles = [
            {
                "source": "Flow God X Options Flow",
                "title": "$AMD unusual call sweeps $2.4M premium",
                "summary": "FL0WG0D flags bullish calls",
                "link": "https://x.com/FL0WG0D/status/1",
            }
        ]

        enriched = enrich_candidates_with_options_flow([candidate], articles)
        flow = enriched[0]["options_flow"]

        self.assertEqual(flow["status"], "supportive_flow")
        self.assertEqual(flow["direction"], "bullish_call_flow")
        self.assertGreaterEqual(flow["score"], 3)

    def test_bearish_put_flow_is_not_treated_as_supportive(self):
        candidate = {
            "company_name": "NVIDIA",
            "tickers": ["NVDA"],
            "market_confirmation": {"status": "confirmed"},
            "impact_assessment": {"impact_score": 5},
        }
        flow = assess_options_flow(
            candidate,
            [
                {
                    "source": "Flow God X Options Flow",
                    "title": "$NVDA unusual put sweeps $1.2M premium",
                    "tickers": ["NVDA"],
                    "direction": "bearish_put_flow",
                    "premium_musd": 1.2,
                    "source_tier": "social_options_flow",
                }
            ],
        )

        self.assertEqual(flow["status"], "bearish_flow")

    def test_no_matching_flow_keeps_no_evidence_status(self):
        enriched = enrich_candidates_with_options_flow([{"company_name": "Unknown", "tickers": ["ABC"]}], [])

        self.assertEqual(enriched[0]["options_flow"]["status"], "no_flow_evidence")

    def test_regular_company_news_does_not_match_oi_inside_words(self):
        candidate = {"company_name": "Vertiv", "tickers": ["VRT"]}
        articles = [
            {
                "source": "Business Wire",
                "title": "Company appoints new chief executive officer",
                "summary": "The board member will be appointed chief executive officer.",
            }
        ]

        enriched = enrich_candidates_with_options_flow([candidate], articles)

        self.assertEqual(enriched[0]["options_flow"]["status"], "no_flow_evidence")


if __name__ == "__main__":
    unittest.main()
