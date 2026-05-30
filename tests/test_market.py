import json
import unittest

from src.abnormal_news_radar.market import assess_market_regime, collect_market_regime
from src.abnormal_news_radar.model import MarketSource


class MarketRegimeTests(unittest.TestCase):
    def test_assess_market_regime_scores_risk_on_when_growth_tape_is_supportive(self):
        metrics = {
            "spy": {"value": 110.0, "change_20d_pct": 4.0},
            "qqq": {"value": 120.0, "change_20d_pct": 5.0},
            "vix": {"value": 14.5, "change_5d": -1.0},
            "us10y": {"value": 4.2, "change_20d_bp": -30.0},
            "us2y": {"value": 4.0},
            "broad_dollar": {"value": 120.0, "change_20d_pct": -2.5},
        }

        regime = assess_market_regime(metrics, source_health=[], events=[])

        self.assertEqual(regime["status"], "connected")
        self.assertEqual(regime["regime"], "risk_on")
        self.assertGreaterEqual(regime["score"], 3)
        self.assertIn("yield_curve_2s10s", [row["key"] for row in regime["metrics"]])

    def test_collect_market_regime_reports_source_errors_without_fake_values(self):
        sources = [
            MarketSource(
                name="Yahoo SPY Chart API",
                group="equity_indices",
                type="api",
                url="https://example.com/spy",
                purpose="S&P 500 ETF daily price confirmation.",
            ),
            MarketSource(
                name="FRED DGS10 CSV",
                group="rates",
                type="csv",
                url="https://example.com/dgs10",
                purpose="10-year Treasury yield history.",
            ),
        ]
        payloads = {
            "https://example.com/spy": _yahoo_chart([100 + index for index in range(25)]),
        }

        def fetcher(url):
            if url not in payloads:
                raise TimeoutError("timed out")
            return payloads[url]

        regime = collect_market_regime(sources, fetcher=fetcher)

        self.assertEqual(regime["status"], "degraded")
        self.assertEqual(len(regime["metrics"]), 1)
        self.assertEqual(regime["source_health"][1]["status"], "error")
        self.assertIn("timed out", regime["source_health"][1]["message"])

    def test_collect_market_regime_parses_bls_yoy(self):
        sources = [
            MarketSource(
                name="BLS CPI Public API",
                group="inflation",
                type="api",
                url="https://example.com/cpi",
                purpose="Consumer inflation time series.",
            )
        ]

        regime = collect_market_regime(sources, fetcher=lambda _url: _bls_payload())
        cpi = next(row for row in regime["metrics"] if row["key"] == "cpi")

        self.assertEqual(cpi["as_of"], "2026-04")
        self.assertAlmostEqual(cpi["yoy_pct"], 3.81, places=2)

    def test_collect_market_regime_marks_bls_quota_as_limited(self):
        sources = [
            MarketSource(
                name="BLS PPI Final Demand Public API",
                group="inflation",
                type="api",
                url="https://example.com/ppi",
                purpose="Producer inflation time series.",
            )
        ]

        regime = collect_market_regime(sources, fetcher=lambda _url: _bls_limited_payload())

        self.assertEqual(regime["source_health"][0]["status"], "limited")
        self.assertEqual(regime["metrics"], [])

    def test_policy_feed_events_are_tagged_but_do_not_replace_market_score(self):
        sources = [
            MarketSource(
                name="White House Presidential Actions RSS",
                group="policy_event_feeds",
                type="rss",
                url="https://example.com/whitehouse",
                purpose="Policy monitoring.",
            )
        ]

        regime = collect_market_regime(sources, fetcher=lambda _url: _rss_payload())

        self.assertEqual(regime["status"], "not_connected")
        self.assertEqual(regime["score"], 0)
        self.assertEqual(regime["events"][0]["policy_importance"], 3)
        self.assertIn("semiconductors", regime["events"][0]["policy_topics"])
        self.assertIn("tariffs", regime["events"][0]["policy_topics"])
        self.assertIn("transparent_rules_engine", regime["methodology"]["type"])


def _yahoo_chart(closes):
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_700_000_000 + index * 86_400 for index in range(len(closes))],
                        "indicators": {"quote": [{"close": closes}]},
                    }
                ]
            }
        }
    )


def _bls_payload():
    return json.dumps(
        {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "data": [
                            {"year": "2026", "period": "M04", "value": "333.020"},
                            {"year": "2025", "period": "M04", "value": "320.795"},
                        ]
                    }
                ]
            }
        }
    )


def _bls_limited_payload():
    return json.dumps(
        {
            "status": "REQUEST_NOT_PROCESSED",
            "message": ["Request could not be serviced, as the daily threshold has been reached."],
            "Results": {},
        }
    )


def _rss_payload():
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Executive Order on Semiconductor Tariffs and Export Controls</title>
      <link>https://example.com/policy</link>
      <pubDate>Wed, 27 May 2026 12:00:00 +0000</pubDate>
      <description>Policy action involving chips, China, and national security.</description>
    </item>
  </channel>
</rss>"""


if __name__ == "__main__":
    unittest.main()
