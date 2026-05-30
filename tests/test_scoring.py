import unittest

from src.abnormal_news_radar.model import Article, Company
from src.abnormal_news_radar.scoring import (
    analyze_evidence,
    band_for_score,
    score_article,
)


def _article(title: str, summary: str = "") -> Article:
    return Article(source="Test", source_trust=1.0, title=title, link="https://example.com/x", summary=summary)


def test_band_for_score_boundaries():
    assert band_for_score(35) == "hard alert"
    assert band_for_score(34.99) == "watch alert"
    assert band_for_score(20) == "watch alert"
    assert band_for_score(10) == "weak alert"
    assert band_for_score(9.99) == "ignore"


def test_hard_evidence_tier_and_high_confidence():
    profile = analyze_evidence(
        _article(
            "Acme receives $290M customer prepayment for mass production order",
            "Multi-year agreement covers data center demand.",
        )
    )
    assert profile["evidence_tier"] == "hard_evidence"
    assert profile["quantified_economics"] is True
    # tier1 (0.5) + corroboration (0.15) + quantified (0.25) -> capped near 1.0
    assert profile["confidence"] >= 0.85


def test_thematic_only_is_low_confidence_and_capped():
    # A wall of thematic buzzwords with no hard evidence must stay weak.
    profile = analyze_evidence(
        _article(
            "AI and artificial intelligence drive semiconductor and silicon photonics interest",
            "ai infrastructure, ai customer, co-packaged optics, hbm, nvlink everywhere.",
        )
    )
    assert profile["evidence_tier"] == "thematic"
    assert profile["confidence"] <= 0.2
    # Diminishing returns + cap keep the thematic pile from inflating the score.
    assert profile["raw_score"] <= 12


def test_penalty_reduces_confidence():
    clean = analyze_evidence(_article("Acme signs multi-year production order agreement"))
    penalized = analyze_evidence(
        _article("Acme signs multi-year production order agreement amid going concern warning")
    )
    assert penalized["confidence"] < clean["confidence"]


def test_score_article_exposes_confidence_and_tier():
    watchlist = [Company(ticker="NVDA", name="NVIDIA", aliases=("NVIDIA", "NVDA"), themes=("ai",))]
    signal = score_article(
        _article("NVIDIA receives $1 billion production order with capacity reservation"),
        watchlist,
    )
    assert signal is not None
    assert signal.evidence_tier == "hard_evidence"
    assert 0.0 < signal.confidence <= 1.0


class ScoringTests(unittest.TestCase):
    def test_hard_signal_scores_high_when_order_and_prepayment_match_watchlist(self):
        watchlist = [
            Company(
                ticker="TSEM",
                name="Tower Semiconductor",
                aliases=("TSEM", "Tower Semiconductor", "silicon photonics"),
                themes=("silicon_photonics",),
            )
        ]
        article = Article(
            source="Test",
            source_trust=1.0,
            title="Tower Semiconductor signs multi-year silicon photonics capacity agreement",
            link="https://example.com/tsem",
            summary="The company received a customer prepayment tied to 1.6T optical interconnect production order and data center demand.",
        )

        signal = score_article(article, watchlist)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.band, "hard alert")
        self.assertGreaterEqual(signal.score, 35)
        self.assertEqual(signal.tickers, ("TSEM",))

    def test_generic_ai_mention_without_watchlist_is_ignored(self):
        article = Article(
            source="Test",
            source_trust=1.0,
            title="Executives say AI remains important",
            link="https://example.com/noise",
            summary="The company discussed artificial intelligence in broad terms.",
        )

        signal = score_article(article, [])

        self.assertIsNone(signal)

    def test_rerating_evidence_scores_without_being_company_specific(self):
        watchlist = [
            Company(
                ticker="EXM",
                name="Example Photonics",
                aliases=("Example Photonics", "EXM"),
                themes=("ai_datacenter", "photonics"),
            )
        ]
        article = Article(
            source="Test",
            source_trust=1.0,
            title="Example Photonics and Jabil sign high-volume production agreement for 1.6T AI data center modules",
            link="https://example.com/exm",
            summary="The program covers production qualification, manufacturing readiness, and pre-production units for field trials.",
        )

        signal = score_article(article, watchlist)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.band, "hard alert")
        self.assertEqual(signal.tickers, ("EXM",))
        self.assertIn("high-volume production", signal.matched_terms)
        self.assertIn("counterparty:jabil", signal.matched_terms)

    def test_strategic_counterparty_without_evidence_does_not_create_alert(self):
        article = Article(
            source="Test",
            source_trust=1.0,
            title="Jabil executive discusses AI trends at industry conference",
            link="https://example.com/no-evidence",
            summary="The talk covered broad artificial intelligence themes and long-range technology roadmaps.",
        )

        signal = score_article(article, [])

        self.assertIsNone(signal)

    def test_generic_theme_alias_does_not_match_unrelated_company_ticker(self):
        watchlist = [
            Company(
                ticker="MRVL",
                name="Marvell",
                aliases=("Marvell", "silicon photonics"),
                themes=("custom_silicon",),
            ),
            Company(
                ticker="AEHR",
                name="Aehr Test Systems",
                aliases=("Aehr", "Aehr Test", "silicon photonics test"),
                themes=("test_equipment",),
            ),
        ]
        article = Article(
            source="Test",
            source_trust=1.0,
            title="Aehr wins silicon photonics customer order",
            link="https://example.com/aehr",
            summary="The article discusses optical interconnect production demand.",
        )

        signal = score_article(article, watchlist)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.tickers, ("AEHR",))


if __name__ == "__main__":
    unittest.main()
