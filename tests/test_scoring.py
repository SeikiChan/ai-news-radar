import unittest

from src.abnormal_news_radar.model import Article, Company
from src.abnormal_news_radar.scoring import score_article


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
