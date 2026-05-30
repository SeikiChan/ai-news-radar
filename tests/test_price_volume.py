import json
import unittest

from src.abnormal_news_radar.price_volume import enrich_candidates_with_market_confirmation


class PriceVolumeConfirmationTests(unittest.TestCase):
    def test_enrich_candidates_marks_confirmed_when_price_and_volume_break_out(self):
        candidates = [
            {
                "company_name": "Advanced Micro Devices",
                "tickers": ["AMD"],
                "score": 24.0,
            }
        ]

        enriched = enrich_candidates_with_market_confirmation(
            candidates,
            fetcher=lambda _url: _chart_payload(
                closes=[100.0] * 20 + [102.0, 106.0],
                volumes=[1_000_000] * 21 + [2_500_000],
            ),
        )

        confirmation = enriched[0]["market_confirmation"]
        self.assertEqual(confirmation["status"], "confirmed")
        self.assertEqual(confirmation["primary_ticker"], "AMD")
        self.assertGreaterEqual(confirmation["confirmations"][0]["volume_ratio_vs_20d"], 1.5)

    def test_enrich_candidates_handles_missing_ticker_without_guessing(self):
        enriched = enrich_candidates_with_market_confirmation([{"company_name": "Unknown", "tickers": []}])

        self.assertEqual(enriched[0]["market_confirmation"]["status"], "no_ticker")


def _chart_payload(closes, volumes):
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_700_000_000 + index * 86_400 for index in range(len(closes))],
                        "indicators": {"quote": [{"close": closes, "volume": volumes}]},
                    }
                ]
            }
        }
    )


if __name__ == "__main__":
    unittest.main()
