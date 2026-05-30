import unittest

from src.abnormal_news_radar.expectations import assess_expectation_check, enrich_candidates_with_expectation_check


class ExpectationCheckTests(unittest.TestCase):
    def test_marks_early_variant_when_market_confirms_without_extended_move(self):
        candidate = {
            "company_name": "Example Photonics",
            "matched_terms": ["production ramp", "optical"],
            "article": {"title": "Example announces production ramp for optical engine"},
            "market_confirmation": {
                "status": "early_confirmation",
                "confirmations": [
                    {
                        "ticker": "EXPH",
                        "status": "early_confirmation",
                        "change_1d_pct": 2.1,
                        "change_5d_pct": 4.3,
                        "change_20d_pct": 6.0,
                        "volume_ratio_vs_20d": 1.35,
                    }
                ],
            },
            "impact_assessment": {"impact_score": 4, "event_type": "production_ramp"},
            "quick_model": {"status": "blocked_missing_amount"},
        }

        check = assess_expectation_check(candidate)

        self.assertEqual(check["status"], "variant_not_fully_priced")
        self.assertEqual(check["score"], 5)
        self.assertIn("Serenity lens", " ".join(check["evidence_zh"]))

    def test_marks_already_priced_when_twenty_day_move_is_extended(self):
        candidate = {
            "company_name": "Example Memory",
            "market_confirmation": {
                "status": "price_only_confirmation",
                "confirmations": [
                    {
                        "ticker": "EXM",
                        "status": "price_only_confirmation",
                        "change_1d_pct": 0.8,
                        "change_5d_pct": 9.2,
                        "change_20d_pct": 22.0,
                        "volume_ratio_vs_20d": 0.95,
                    }
                ],
            },
            "impact_assessment": {"impact_score": 5, "event_type": "order_contract"},
            "quick_model": {"status": "ready_for_assumptions"},
        }

        check = assess_expectation_check(candidate)

        self.assertEqual(check["status"], "likely_already_priced_in")
        self.assertIn("price-in", check["pre_positioning_zh"])

    def test_enrich_candidates_keeps_rows_and_adds_check(self):
        rows = enrich_candidates_with_expectation_check([{"company_name": "No Ticker"}])

        self.assertEqual(rows[0]["company_name"], "No Ticker")
        self.assertEqual(rows[0]["expectation_check"]["status"], "no_market_data")


if __name__ == "__main__":
    unittest.main()
