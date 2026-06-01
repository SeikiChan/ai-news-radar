import json
import unittest

from src.abnormal_news_radar.financials import (
    _gross_margin_trend,
    _latest_instant_musd,
    _latest_quarterly_musd,
    _ttm_revenue_musd,
    enrich_candidates_with_financial_snapshots,
    fetch_financial_snapshot,
    fetch_recent_filings,
)


class RecentFilingsTests(unittest.TestCase):
    def _submissions(self):
        return json.dumps({
            "filings": {"recent": {
                "form": ["10-Q", "8-K", "4", "10-K"],
                "filingDate": ["2026-05-20", "2026-05-20", "2026-05-01", "2026-02-20"],
                "reportDate": ["2026-04-26", "", "", "2026-01-28"],
                "accessionNumber": ["0001045810-26-000052", "0001045810-26-000051", "x", "0001045810-26-000010"],
                "primaryDocument": ["nvda-20260426.htm", "nvda-8k.htm", "form4.xml", "nvda-10k.htm"],
                "primaryDocDescription": ["10-Q", "8-K", "FORM 4", "10-K"],
            }}
        })

    def test_recent_filings_builds_edgar_urls_and_filters_forms(self):
        filings = fetch_recent_filings(1045810, fetcher=lambda _url: self._submissions())
        forms = [f["form"] for f in filings]
        self.assertEqual(forms, ["10-Q", "8-K", "10-K"])  # Form 4 filtered out
        self.assertEqual(
            filings[0]["doc_url"],
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000052/nvda-20260426.htm",
        )

    def test_recent_filings_degrades_on_error(self):
        def boom(_url):
            raise RuntimeError("429")
        self.assertEqual(fetch_recent_filings(123, fetcher=boom), [])


def _q(start, end, val):
    return {"start": start, "end": end, "val": val, "filed": end, "form": "10-Q", "fp": "Q1"}


class FinancialSeriesTests(unittest.TestCase):
    def _facts(self):
        return {
            "Revenues": {"units": {"USD": [
                _q("2025-01-01", "2025-03-31", 100_000_000),
                _q("2025-04-01", "2025-06-30", 110_000_000),
                _q("2025-07-01", "2025-09-30", 120_000_000),
                _q("2025-10-01", "2025-12-31", 130_000_000),
            ]}},
            "GrossProfit": {"units": {"USD": [
                _q("2025-01-01", "2025-03-31", 40_000_000),
                _q("2025-04-01", "2025-06-30", 33_000_000),
                _q("2025-07-01", "2025-09-30", 24_000_000),
            ]}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                {"end": "2025-09-30", "val": 250_000_000, "filed": "2025-10-30"},
                {"end": "2025-12-31", "val": 200_000_000, "filed": "2026-01-30"},
            ]}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
                _q("2025-10-01", "2025-12-31", -30_000_000),
            ]}},
        }

    def test_ttm_revenue_sums_last_four_quarters(self):
        self.assertEqual(_ttm_revenue_musd(self._facts()), 460.0)

    def test_gross_margin_trend_is_declining(self):
        trend = _gross_margin_trend(self._facts())
        self.assertEqual(trend, [40.0, 30.0, 20.0])

    def test_latest_instant_cash_picks_newest(self):
        self.assertEqual(_latest_instant_musd(self._facts(), ("CashAndCashEquivalentsAtCarryingValue",)), 200.0)

    def test_latest_quarterly_ocf(self):
        self.assertEqual(
            _latest_quarterly_musd(self._facts(), ("NetCashProvidedByUsedInOperatingActivities",)), -30.0
        )


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
