import json
import time
import unittest

from src.abnormal_news_radar.options_chain import assess_public_options_chain, enrich_candidates_with_options_chain_anomalies


class OptionsChainTests(unittest.TestCase):
    def test_bullish_public_chain_anomaly_becomes_supportive_flow(self):
        flow = assess_public_options_chain("AMD", fetcher=lambda _url: _payload(call_volume=2500, put_volume=100))

        self.assertEqual(flow["status"], "supportive_flow")
        self.assertEqual(flow["direction"], "bullish")
        self.assertEqual(flow["source_tier"], "public_options_chain_snapshot")
        self.assertGreaterEqual(flow["score"], 3)

    def test_no_large_contract_keeps_no_flow_evidence(self):
        flow = assess_public_options_chain("AMD", fetcher=lambda _url: _payload(call_volume=10, put_volume=5))

        self.assertEqual(flow["status"], "no_flow_evidence")

    def test_enrich_merges_public_chain_into_candidate_options_flow(self):
        rows = enrich_candidates_with_options_chain_anomalies(
            [{"company_name": "Advanced Micro Devices", "tickers": ["AMD"], "options_flow": {"status": "no_flow_evidence"}}],
            fetcher=lambda _url: _payload(call_volume=2500, put_volume=100),
        )

        self.assertEqual(rows[0]["options_flow"]["status"], "supportive_flow")


def _payload(call_volume: int, put_volume: int) -> str:
    expiration = int(time.time()) + 14 * 86400
    return json.dumps(
        {
            "optionChain": {
                "result": [
                    {
                        "quote": {"regularMarketPrice": 100.0},
                        "options": [
                            {
                                "expirationDate": expiration,
                                "calls": [
                                    {
                                        "contractSymbol": "AMD260612C00100000",
                                        "strike": 100.0,
                                        "lastPrice": 2.1,
                                        "bid": 2.0,
                                        "ask": 2.2,
                                        "volume": call_volume,
                                        "openInterest": 800,
                                    }
                                ],
                                "puts": [
                                    {
                                        "contractSymbol": "AMD260612P00095000",
                                        "strike": 95.0,
                                        "lastPrice": 1.0,
                                        "bid": 0.9,
                                        "ask": 1.1,
                                        "volume": put_volume,
                                        "openInterest": 1000,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )


if __name__ == "__main__":
    unittest.main()
