import base64
import unittest

from src.abnormal_news_radar.model import Article
from src.abnormal_news_radar.web import (
    _article_payload,
    _is_local_host,
    _merge_candidate_rows,
    _source_counts,
    check_basic_auth,
)


def _basic(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


class AuthGateTests(unittest.TestCase):
    def test_auth_disabled_when_no_password(self):
        self.assertTrue(check_basic_auth("", "admin", ""))
        self.assertTrue(check_basic_auth("anything", "admin", ""))

    def test_correct_credentials_pass(self):
        self.assertTrue(check_basic_auth(_basic("admin", "s3cret"), "admin", "s3cret"))

    def test_wrong_password_rejected(self):
        self.assertFalse(check_basic_auth(_basic("admin", "nope"), "admin", "s3cret"))

    def test_wrong_user_rejected(self):
        self.assertFalse(check_basic_auth(_basic("root", "s3cret"), "admin", "s3cret"))

    def test_missing_and_malformed_header_rejected(self):
        self.assertFalse(check_basic_auth("", "admin", "s3cret"))
        self.assertFalse(check_basic_auth("Bearer xyz", "admin", "s3cret"))
        self.assertFalse(check_basic_auth("Basic !!!notbase64", "admin", "s3cret"))

    def test_localhost_detection(self):
        self.assertTrue(_is_local_host("127.0.0.1"))
        self.assertTrue(_is_local_host("localhost"))
        self.assertFalse(_is_local_host("0.0.0.0"))
        self.assertFalse(_is_local_host("203.0.113.5"))


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

    def test_merge_preserves_first_seen_for_undated_repeated_article(self):
        latest = [{"company_name": "IR Co", "score": 40,
                   "article": {"link": "https://example.com/ir", "fetched_at": "2026-10-15T12:00:00+00:00"}}]
        stored = [{"company_name": "IR Co", "score": 40,
                   "article": {"link": "https://example.com/ir", "fetched_at": "2026-09-01T12:00:00+00:00"}}]
        rows = _merge_candidate_rows(latest, stored, limit=10)
        self.assertEqual(rows[0]["first_seen_at"], "2026-09-01T12:00:00+00:00")
        self.assertEqual(rows[0]["article"]["fetched_at"], "2026-10-15T12:00:00+00:00")
        self.assertNotIn("first_seen_at", latest[0])


if __name__ == "__main__":
    unittest.main()
