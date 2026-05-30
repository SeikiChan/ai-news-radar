import json
import unittest

from src.abnormal_news_radar.financials import enrich_candidates_with_financial_snapshots, fetch_financial_snapshot


class FinancialSnapshotTests(unittest.TestCase):
    def test_fetch_financial_snapshot_extracts_revenue_and_gross_margin_from_sec_facts(self):
        cik_map = {"AMD": {"cik": 2488, "name": "Advanced Micro Devices, Inc."}}

        snapshot = fetch_financial_snapshot("AMD", cik_map=cik_map, fetcher=lambda _url: _companyfacts_payload())

        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["revenue_musd"], 25785.0)
        self.assertEqual(snapshot["gross_profit_musd"], 12500.0)
        self.assertAlmostEqual(snapshot["gross_margin_pct"], 48.48, places=2)
        self.assertEqual(snapshot["revenue_concept"], "RevenueFromContractWithCustomerExcludingAssessedTax")

    def test_enrich_candidates_does_not_guess_when_ticker_is_missing(self):
        enriched = enrich_candidates_with_financial_snapshots([{"company_name": "Unknown", "tickers": []}])

        self.assertEqual(enriched[0]["financial_snapshot"]["status"], "no_ticker")

    def test_missing_revenue_is_reported_as_missing(self):
        cik_map = {"ABC": {"cik": 123, "name": "ABC Corp"}}

        snapshot = fetch_financial_snapshot("ABC", cik_map=cik_map, fetcher=lambda _url: json.dumps({"facts": {"us-gaap": {}}}))

        self.assertEqual(snapshot["status"], "missing")
        self.assertIn("annual revenue", snapshot["missing_fields"])


def _companyfacts_payload():
    return json.dumps(
        {
            "entityName": "Advanced Micro Devices, Inc.",
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {
                            "USD": [
                                {"fy": 2024, "fp": "FY", "form": "10-K", "end": "2024-12-28", "filed": "2025-02-05", "val": 25785000000}
                            ]
                        }
                    },
                    "GrossProfit": {
                        "units": {
                            "USD": [
                                {"fy": 2024, "fp": "FY", "form": "10-K", "end": "2024-12-28", "filed": "2025-02-05", "val": 12500000000}
                            ]
                        }
                    },
                }
            },
        }
    )


if __name__ == "__main__":
    unittest.main()
