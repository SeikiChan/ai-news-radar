import json
import unittest

from src.abnormal_news_radar.ticker_resolver import SEC_TICKERS_URL, enrich_candidates_with_ticker_resolution


class TickerResolverTests(unittest.TestCase):
    def test_resolves_exact_sec_company_name_when_candidate_has_no_ticker(self):
        rows = enrich_candidates_with_ticker_resolution(
            [{"company_name": "Snowflake", "tickers": []}],
            fetcher=_fake_sec_fetcher,
        )

        self.assertEqual(rows[0]["tickers"], ["SNOW"])
        self.assertEqual(rows[0]["ticker_resolution"]["status"], "resolved")
        self.assertEqual(rows[0]["ticker_resolution"]["confidence"], "high")

    def test_preserves_existing_ticker(self):
        rows = enrich_candidates_with_ticker_resolution(
            [{"company_name": "Snowflake", "tickers": ["SNOW"]}],
            fetcher=_fake_sec_fetcher,
        )

        self.assertEqual(rows[0]["tickers"], ["SNOW"])
        self.assertEqual(rows[0]["ticker_resolution"]["status"], "already_present")

    def test_ambiguous_or_unknown_company_stays_unresolved(self):
        rows = enrich_candidates_with_ticker_resolution(
            [{"company_name": "Acme", "tickers": []}],
            fetcher=_fake_sec_fetcher,
        )

        self.assertEqual(rows[0].get("tickers"), [])
        self.assertEqual(rows[0]["ticker_resolution"]["status"], "unresolved")


def _fake_sec_fetcher(url: str) -> str:
    if url != SEC_TICKERS_URL:
        raise AssertionError(f"unexpected URL: {url}")
    return json.dumps(
        {
            "0": {"cik_str": 1640147, "ticker": "SNOW", "title": "Snowflake Inc."},
            "1": {"cik_str": 1730168, "ticker": "AVGO", "title": "Broadcom Inc."},
        }
    )


if __name__ == "__main__":
    unittest.main()
