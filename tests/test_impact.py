import unittest

from src.abnormal_news_radar.impact import assess_candidate_impact


class ImpactAssessmentTests(unittest.TestCase):
    def test_production_ramp_with_market_reaction_enters_model_queue(self):
        candidate = {
            "company_name": "Advanced Micro Devices",
            "tickers": ["AMD", "TSM"],
            "score": 20.24,
            "matched_terms": ["ramp", "counterparty:amd", "counterparty:tsmc"],
            "article": {
                "title": "AMD Announces Production Ramp of Next-Generation AMD EPYC Processor Venice on TSMC 2nm Process Technology",
                "summary": "",
            },
            "market_confirmation": {"status": "price_only_confirmation"},
        }

        impact = assess_candidate_impact(candidate)

        self.assertEqual(impact["event_type"], "production_ramp")
        self.assertGreaterEqual(impact["impact_score"], 4)
        self.assertIn("建模", impact["action_zh"])
        self.assertIn("ramp timing", impact["model_inputs_needed"])

    def test_order_amount_is_extracted_without_claiming_materiality_to_revenue(self):
        candidate = {
            "company_name": "Example Systems",
            "tickers": ["EXM"],
            "score": 36.0,
            "matched_terms": ["production order"],
            "article": {
                "title": "Example receives $41 million production order from hyperscale customer",
                "summary": "",
            },
            "market_confirmation": {"status": "confirmed"},
        }

        impact = assess_candidate_impact(candidate)

        self.assertEqual(impact["event_type"], "order_contract")
        self.assertEqual(impact["amount_mentions"][0]["value_millions_usd"], 41.0)
        self.assertIn("latest revenue base", impact["model_inputs_needed"])


if __name__ == "__main__":
    unittest.main()
