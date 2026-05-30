import unittest
from datetime import datetime, timezone

from src.abnormal_news_radar.model import Article
from src.abnormal_news_radar.timeliness import article_timeliness


class TimelinessTests(unittest.TestCase):
    def test_same_day_article_keeps_full_weight(self):
        article = Article(
            source="Wire",
            source_trust=1.0,
            title="News",
            link="https://example.com",
            published="Wed, 27 May 2026 16:00:00 UT",
        )

        result = article_timeliness(article, now=datetime(2026, 5, 27, 20, 0, tzinfo=timezone.utc))

        self.assertEqual(result["status"], "breaking")
        self.assertEqual(result["score_multiplier"], 1.10)

    def test_old_article_is_heavily_discounted(self):
        article = Article(
            source="Wire",
            source_trust=1.0,
            title="News",
            link="https://example.com",
            published="Mon, 18 May 2026 00:00:00 GMT",
        )

        result = article_timeliness(article, now=datetime(2026, 5, 27, 20, 0, tzinfo=timezone.utc))

        self.assertEqual(result["status"], "old")
        self.assertEqual(result["score_multiplier"], 0.25)

    def test_missing_published_time_is_marked_unknown(self):
        article = Article(source="HTML", source_trust=1.0, title="News", link="https://example.com")

        result = article_timeliness(article, now=datetime(2026, 5, 27, 20, 0, tzinfo=timezone.utc))

        self.assertEqual(result["status"], "published_unknown")
        self.assertEqual(result["score_multiplier"], 0.85)


if __name__ == "__main__":
    unittest.main()
