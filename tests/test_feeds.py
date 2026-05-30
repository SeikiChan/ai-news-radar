import unittest
import urllib.error
import xml.etree.ElementTree as ET
from unittest import mock

from src.abnormal_news_radar import feeds
from src.abnormal_news_radar.feeds import _parse_html_links, _parse_rss, fetch_all, fetch_feed, fetch_sources
from src.abnormal_news_radar.model import Article, Source


class HtmlFeedTests(unittest.TestCase):
    def test_html_link_parser_filters_press_release_links(self):
        source = Source(
            name="Example IR",
            type="html",
            url="https://example.com/news/",
            trust=0.9,
            include_patterns=("/press/", "production"),
            exclude_patterns=("privacy",),
        )
        document = """
        <html>
          <body>
            <a href="/press/production-order">Example wins production order</a>
            <a href="/privacy">Privacy Policy</a>
            <a href="/about">About Example</a>
          </body>
        </html>
        """

        articles = list(_parse_html_links(document, source))

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Example wins production order")
        self.assertEqual(articles[0].link, "https://example.com/press/production-order")

    def test_generic_read_more_title_uses_link_slug(self):
        source = Source(
            name="Example IR",
            type="html",
            url="https://example.com/news/",
            trust=0.9,
            include_patterns=("production-order",),
        )
        document = '<a href="/2026/04/example-receives-production-order/">Read More</a>'

        articles = list(_parse_html_links(document, source))

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "example receives production order")

    def test_rss_parser_applies_include_patterns(self):
        source = Source(
            name="Policy",
            type="rss",
            url="https://example.com/feed",
            trust=0.95,
            include_patterns=("tariff|semiconductor",),
        )
        root = ET.fromstring(
            """<rss><channel>
            <item><title>Sports message</title><link>https://example.com/a</link><description>no market term</description></item>
            <item><title>Semiconductor tariff action</title><link>https://example.com/b</link><description>chips</description></item>
            </channel></rss>"""
        )

        articles = list(_parse_rss(root, source))

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Semiconductor tariff action")

    def test_arxiv_429_is_retried_once(self):
        source = Source(
            name="arXiv",
            type="atom",
            url="https://export.arxiv.org/api/query?search_query=all:gpu",
        )
        calls = {"count": 0}

        def opener(_request, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.HTTPError(source.url, 429, "rate limited", {}, None)
            return _FakeResponse(
                b"""<?xml version="1.0" encoding="UTF-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom">
                  <entry>
                    <title>GPU cluster power paper</title>
                    <id>https://arxiv.org/abs/2601.00001</id>
                    <updated>2026-01-01T00:00:00Z</updated>
                    <summary>data center power</summary>
                    <link href="https://arxiv.org/abs/2601.00001"/>
                  </entry>
                </feed>"""
            )

        with mock.patch("src.abnormal_news_radar.feeds.urllib.request.urlopen", opener), mock.patch(
            "src.abnormal_news_radar.feeds.time.sleep", lambda _seconds: None
        ):
            articles = fetch_feed(source)

        self.assertEqual(calls["count"], 2)
        self.assertEqual(articles[0].title, "GPU cluster power paper")

    def test_arxiv_rate_exceeded_body_degrades_to_empty_feed(self):
        source = Source(
            name="arXiv",
            type="atom",
            url="https://export.arxiv.org/api/query?search_query=all:gpu",
        )

        with mock.patch(
            "src.abnormal_news_radar.feeds.urllib.request.urlopen",
            lambda _request, timeout: _FakeResponse(b"Rate exceeded."),
        ), mock.patch("src.abnormal_news_radar.feeds.time.sleep", lambda _seconds: None):
            articles = fetch_feed(source)

        self.assertEqual(articles, [])


class FetchAllTests(unittest.TestCase):
    def _sources(self):
        return [
            Source(name="A", type="rss", url="https://a"),
            Source(name="B", type="rss", url="https://b"),
            Source(name="C", type="rss", url="https://c"),
        ]

    def _fake_fetch_feed(self, source):
        if source.name == "B":
            raise RuntimeError("boom")
        return [Article(source=source.name, source_trust=0.8, title=f"{source.name} headline", link=f"https://{source.name}/1")]

    def test_fetch_sources_preserves_order_and_reports_health(self):
        with mock.patch.object(feeds, "fetch_feed", self._fake_fetch_feed):
            articles, health = fetch_sources(self._sources())

        # Order preserved despite concurrency (A then C; B failed).
        self.assertEqual([a.source for a in articles], ["A", "C"])
        statuses = {row["source"]: row["status"] for row in health}
        self.assertEqual(statuses, {"A": "ok", "B": "error", "C": "ok"})
        b_row = next(row for row in health if row["source"] == "B")
        self.assertIn("boom", b_row["error"])
        self.assertIn("latency_ms", b_row)

    def test_fetch_all_keeps_backward_compatible_shape(self):
        with mock.patch.object(feeds, "fetch_feed", self._fake_fetch_feed):
            articles, errors = fetch_all(self._sources())

        self.assertEqual(len(articles), 2)
        self.assertEqual(errors, ["B: boom"])

    def test_fetch_sources_empty_input(self):
        self.assertEqual(fetch_sources([]), ([], []))


class _FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


if __name__ == "__main__":
    unittest.main()
