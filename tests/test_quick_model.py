import unittest

from src.abnormal_news_radar.quick_model import build_quick_model


class QuickModelTests(unittest.TestCase):
    def test_builds_sensitivity_rows_only_when_amount_is_disclosed(self):
        model = build_quick_model(
            {
                "tickers": ["EXM"],
                "financial_snapshot": {
                    "snapshots": [
                        {
                            "ticker": "EXM",
                            "revenue_musd": 1000.0,
                            "gross_margin_pct": 40.0,
                            "source": "SEC companyfacts",
                            "period_end": "2025-12-31",
                        }
                    ]
                },
                "impact_assessment": {
                    "impact_score": 5,
                    "event_type": "order_contract",
                    "amount_mentions": [{"mention": "$100 million", "value_millions_usd": 100.0}],
                    "model_inputs_needed": ["latest revenue base", "gross margin sensitivity"],
                },
            }
        )

        self.assertEqual(model["status"], "ready_for_assumptions")
        self.assertEqual(model["known_inputs"]["disclosed_amount_musd"], 100.0)
        self.assertEqual(model["scenarios"][0]["revenue_increment_musd"], 50.0)
        self.assertEqual(model["scenarios"][0]["latest_revenue_base_musd"], 1000.0)
        self.assertEqual(model["scenarios"][0]["gross_margin_assumption_pct"], 40.0)
        self.assertEqual(model["scenarios"][0]["revenue_materiality_pct"], 5.0)
        self.assertEqual(model["scenarios"][0]["gross_profit_increment_musd"], 20.0)

    def test_blocks_numeric_model_when_amount_is_missing(self):
        model = build_quick_model(
            {
                "tickers": ["AMD"],
                "impact_assessment": {
                    "impact_score": 4,
                    "event_type": "production_ramp",
                    "amount_mentions": [],
                    "model_inputs_needed": ["disclosed or estimated order / revenue value", "ramp timing"],
                },
            }
        )

        self.assertEqual(model["status"], "blocked_missing_amount")
        self.assertIsNone(model["scenarios"][0]["revenue_increment_musd"])
        self.assertIn("disclosed or estimated order / revenue value", model["missing_inputs"])

    def test_low_impact_candidate_is_not_queued(self):
        model = build_quick_model({"impact_assessment": {"impact_score": 2}})

        self.assertEqual(model["status"], "not_queued")


if __name__ == "__main__":
    unittest.main()
