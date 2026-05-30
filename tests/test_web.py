import unittest

from src.abnormal_news_radar.model import Article
from src.abnormal_news_radar.web import _article_payload, _merge_candidate_rows, _source_counts


class WebPayloadTests(unittest.TestCase):
    def test_article_payload_exposes_scan_trail_fields(self):
        article = Article(
            source="Example Source",
            source_trust=0.8,
            title="Example announces production qualification",
            link="https://example.com/news",
            published="Mon, 01 Jan 2026 00:00:00 GMT",
            summary="A short summary.",
        )

        payload = _article_payload(article)

        self.assertEqual(payload["source"], "Example Source")
        self.assertEqual(payload["title"], "Example announces production qualification")
        self.assertEqual(payload["link"], "https://example.com/news")
        self.assertEqual(payload["source_trust"], 0.8)

    def test_source_counts_groups_last_scan_articles(self):
        articles = [
            Article(source="A", source_trust=1.0, title="One", link="https://example.com/1"),
            Article(source="A", source_trust=1.0, title="Two", link="https://example.com/2"),
            Article(source="B", source_trust=1.0, title="Three", link="https://example.com/3"),
        ]

        self.assertEqual(_source_counts(articles), {"A": 2, "B": 1})

    def test_merge_candidate_rows_keeps_stored_earnings_context_after_latest_scan(self):
        latest = [
            {"company_name": "Advanced Micro Devices", "score": 20, "article": {"link": "https://example.com/amd"}},
        ]
        stored = [
            {"company_name": "Snowflake", "score": 35, "article": {"link": "https://example.com/snow"}},
            {"company_name": "Advanced Micro Devices", "score": 20, "article": {"link": "https://example.com/amd"}},
        ]

        rows = _merge_candidate_rows(latest, stored, limit=10)

        self.assertEqual([row["company_name"] for row in rows], ["Snowflake", "Advanced Micro Devices"])


if __name__ == "__main__":
    unittest.main()
