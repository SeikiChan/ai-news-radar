import unittest

from src.abnormal_news_radar.discovery import discover_candidate
from src.abnormal_news_radar.model import Article, Company


class DiscoveryTests(unittest.TestCase):
    def test_discovers_candidate_without_watchlist_match(self):
        article = Article(
            source="Industry News",
            source_trust=1.0,
            title="Example Photonics receives production order from hyperscale AI customer",
            link="https://example.com/news",
            summary="The program includes production qualification and manufacturing readiness.",
        )

        candidate = discover_candidate(article, [])

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.company_name, "Example Photonics")
        self.assertEqual(candidate.status, "discovered")
        self.assertEqual(candidate.tickers, ())
        self.assertGreaterEqual(candidate.raw_score, 16)

    def test_known_watchlist_candidate_keeps_ticker(self):
        article = Article(
            source="Company IR",
            source_trust=1.0,
            title="Aehr receives production order from lead hyperscale AI customer",
            link="https://example.com/aehr",
        )
        watchlist = [
            Company(
                ticker="AEHR",
                name="Aehr Test Systems",
                aliases=("Aehr", "Aehr Test"),
                themes=("test_equipment",),
            )
        ]

        candidate = discover_candidate(article, watchlist)

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.company_name, "Aehr Test Systems")
        self.assertEqual(candidate.status, "known_watchlist")
        self.assertEqual(candidate.tickers, ("AEHR",))


if __name__ == "__main__":
    unittest.main()
