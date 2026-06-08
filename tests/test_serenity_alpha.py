import json
import unittest

from src.abnormal_news_radar.model import Company
from src.abnormal_news_radar.serenity_alpha import enrich_candidates_with_serenity_alpha


def _profile(market_cap, analysts, revenue=None):
    return json.dumps({
        "quoteSummary": {"result": [{
            "price": {"marketCap": {"raw": market_cap}},
            "financialData": {
                "numberOfAnalystOpinions": {"raw": analysts},
                "totalRevenue": {"raw": revenue},
            },
        }]}
    })


def _fake_fetch(url):
    if "SMALL" in url:
        return _profile(1_500_000_000, 2, 300_000_000)
    if "MEGA" in url:
        return _profile(1_500_000_000_000, 50, 60_000_000_000)
    if "BOOM" in url:
        raise RuntimeError("rate limited")
    return _profile(None, None)


def _row(**over):
    base = {
        "tickers": ["SMALL"],
        "company_name": "SmallCo",
        "evidence_tier": "hard_evidence",
        "confidence": 0.9,
        "status": "known_watchlist",
        "matched_terms": ["purchase order", "mass production"],
        "financial_snapshot": {"revenue_base_musd": 300},
        "impact": {"materiality": "high", "amount_mentions": [{"value_millions_usd": 200}]},
        "institutional_flow": {"institutions_pct_held": 0.4},
    }
    base.update(over)
    return base


class SerenityAlphaTests(unittest.TestCase):
    def test_small_pure_misclassified_beneficiary_scores_high_and_qualifies(self):
        rows = enrich_candidates_with_serenity_alpha([_row()], fetcher=_fake_fetch)
        sa = rows[0]["serenity_alpha"]
        self.assertEqual(sa["status"], "ok")
        self.assertEqual(sa["verdict"], "qualified")
        self.assertEqual(sa["excluded_filters"], [])
        self.assertGreater(sa["alpha_score"], 60)
        # high elasticity: a $200M order vs a $1.5B cap is material
        elasticity = next(d["value"] for d in sa["dimensions"] if d["key"] == "market_cap_elasticity")
        self.assertGreaterEqual(elasticity, 0.9)
        self.assertTrue(sa["verification_chain"]["cashflow_demand"])  # order -> backlog hooks

    def test_mega_cap_is_excluded_with_low_elasticity(self):
        rows = enrich_candidates_with_serenity_alpha(
            [_row(tickers=["MEGA"], company_name="MegaCorp", financial_snapshot={"revenue_base_musd": 50000})],
            fetcher=_fake_fetch,
        )
        sa = rows[0]["serenity_alpha"]
        self.assertEqual(sa["verdict"], "excluded")
        keys = {f["key"] for f in sa["excluded_filters"]}
        self.assertIn("large_cap", keys)
        self.assertIn("high_consensus", keys)  # 50 analysts
        self.assertLess(sa["alpha_score"], 20)

    def test_narrative_only_is_excluded(self):
        rows = enrich_candidates_with_serenity_alpha(
            [_row(
                tickers=["SMALL"],
                evidence_tier="thematic",
                confidence=0.1,
                matched_terms=["artificial intelligence"],
                impact={"materiality": "low", "amount_mentions": []},
                financial_snapshot={},
            )],
            fetcher=_fake_fetch,
        )
        sa = rows[0]["serenity_alpha"]
        self.assertEqual(sa["verdict"], "excluded")
        self.assertIn("narrative_only", {f["key"] for f in sa["excluded_filters"]})

    def test_fetch_failure_degrades_without_crashing(self):
        rows = enrich_candidates_with_serenity_alpha([_row(tickers=["BOOM"])], fetcher=_fake_fetch)
        sa = rows[0]["serenity_alpha"]
        self.assertEqual(sa["status"], "partial")
        self.assertIsInstance(sa["alpha_score"], float)
        self.assertEqual(sa["market_cap_display"], "n/a")

    def test_no_ticker_still_returns_a_hypothesis(self):
        rows = enrich_candidates_with_serenity_alpha([_row(tickers=[], status="discovered", confidence=0.2)], fetcher=_fake_fetch)
        sa = rows[0]["serenity_alpha"]
        self.assertIn("distant_transmission", {f["key"] for f in sa["excluded_filters"]})

    def test_business_purity_uses_watchlist_when_known(self):
        watchlist = [Company(ticker="SMALL", name="SmallCo", aliases=("SmallCo",), themes=("robotics",))]
        rows = enrich_candidates_with_serenity_alpha([_row()], fetcher=_fake_fetch, watchlist=watchlist)
        sa = rows[0]["serenity_alpha"]
        self.assertIn("robotics", sa["relabel_zh"])


if __name__ == "__main__":
    unittest.main()
