import json
import unittest
from datetime import datetime, timedelta, timezone

from src.abnormal_news_radar.options_chain import (
    assess_public_options_chain,
    enrich_candidates_with_options_chain_anomalies,
)

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _occ(root, expiry, cp, strike):
    return f"{root}{expiry.strftime('%y%m%d')}{cp}{int(strike * 1000):08d}"


def _contract(symbol, volume, open_interest, bid, ask, last):
    return {
        "option": symbol,
        "volume": volume,
        "open_interest": open_interest,
        "bid": bid,
        "ask": ask,
        "last_trade_price": last,
    }


def _payload(options, spot=100.0):
    return json.dumps({"data": {"symbol": "AMD", "current_price": spot, "options": options}})


def _near_expiry():
    return (NOW + timedelta(days=14)).date()


def _far_expiry():
    return (NOW + timedelta(days=30)).date()


class OptionsChainTests(unittest.TestCase):
    def test_bullish_public_chain_anomaly_becomes_supportive_flow(self):
        options = [
            _contract(_occ("AMD", _near_expiry(), "C", 100.0), 2500, 800, 2.0, 2.2, 2.1),
            _contract(_occ("AMD", _near_expiry(), "P", 95.0), 100, 1000, 0.9, 1.1, 1.0),
        ]
        flow = assess_public_options_chain("AMD", fetcher=lambda _url: _payload(options), now=NOW)

        self.assertEqual(flow["status"], "supportive_flow")
        self.assertEqual(flow["direction"], "bullish")
        self.assertEqual(flow["source_tier"], "public_options_chain_snapshot")
        self.assertGreaterEqual(flow["score"], 3)

    def test_no_large_contract_keeps_no_flow_evidence(self):
        options = [
            _contract(_occ("AMD", _near_expiry(), "C", 100.0), 10, 800, 2.0, 2.2, 2.1),
            _contract(_occ("AMD", _near_expiry(), "P", 95.0), 5, 1000, 0.9, 1.1, 1.0),
        ]
        flow = assess_public_options_chain("AMD", fetcher=lambda _url: _payload(options), now=NOW)

        self.assertEqual(flow["status"], "no_flow_evidence")

    def test_anomaly_beyond_nearest_expiry_is_scanned(self):
        # The old Yahoo source only saw the first expiration; the whole point
        # of the CBOE migration is that a later-expiry block trade is caught.
        options = [
            _contract(_occ("AMD", _near_expiry(), "C", 100.0), 10, 800, 2.0, 2.2, 2.1),
            _contract(_occ("AMD", _far_expiry(), "C", 105.0), 3000, 500, 3.0, 3.2, 3.1),
        ]
        flow = assess_public_options_chain("AMD", fetcher=lambda _url: _payload(options), now=NOW)

        self.assertEqual(flow["status"], "supportive_flow")
        self.assertEqual(flow["contracts"][0]["dte"], 30)

    def test_bearish_put_premium_dominates(self):
        options = [
            _contract(_occ("AMD", _near_expiry(), "P", 95.0), 4000, 1000, 4.0, 4.2, 4.1),
            _contract(_occ("AMD", _near_expiry(), "C", 100.0), 1100, 5000, 2.4, 2.6, 2.5),
        ]
        flow = assess_public_options_chain("AMD", fetcher=lambda _url: _payload(options), now=NOW)

        self.assertEqual(flow["status"], "bearish_flow")
        self.assertEqual(flow["direction"], "bearish")

    def test_fetch_failure_degrades_to_no_flow_evidence(self):
        def boom(_url):
            raise RuntimeError("offline")

        flow = assess_public_options_chain("AMD", fetcher=boom, now=NOW)

        self.assertEqual(flow["status"], "no_flow_evidence")
        self.assertEqual(flow["chain_status"], "unavailable")

    def test_enrich_merges_public_chain_into_candidate_options_flow(self):
        options = [
            _contract(_occ("AMD", _near_expiry(), "C", 100.0), 2500, 800, 2.0, 2.2, 2.1),
        ]
        rows = enrich_candidates_with_options_chain_anomalies(
            [{"company_name": "Advanced Micro Devices", "tickers": ["AMD"], "options_flow": {"status": "no_flow_evidence"}}],
            fetcher=lambda _url: _payload(options),
        )

        self.assertEqual(rows[0]["options_flow"]["status"], "supportive_flow")


if __name__ == "__main__":
    unittest.main()
