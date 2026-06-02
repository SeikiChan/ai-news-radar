from datetime import datetime, timedelta, timezone
from unittest import mock

from src.abnormal_news_radar import feeds
from src.abnormal_news_radar.model import Article, Source
from src.abnormal_news_radar.timeliness import article_age_days, is_within_max_age

_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _article(published):
    return Article(source="T", source_trust=1.0, title="t", link="x", summary="", published=published)


def test_age_days_and_within_max_age():
    fresh = _article("Mon, 25 May 2026 12:00:00 GMT")
    old = _article("Mon, 01 Jan 2023 12:00:00 GMT")
    assert article_age_days(fresh, now=_NOW) < 10
    assert is_within_max_age(fresh, now=_NOW) is True
    assert is_within_max_age(old, now=_NOW) is False


def test_undated_is_kept():
    assert is_within_max_age(_article(""), now=_NOW) is True
    assert article_age_days(_article(""), now=_NOW) is None


def test_future_dated_is_kept():
    future = _article("Mon, 25 Dec 2026 12:00:00 GMT")
    assert is_within_max_age(future, now=_NOW) is True


def test_fetch_feed_drops_stale_articles():
    from email.utils import format_datetime

    source = Source(name="X", type="rss", url="https://x/feed")
    fresh_date = format_datetime(datetime.now(timezone.utc) - timedelta(days=5))
    old_date = format_datetime(datetime.now(timezone.utc) - timedelta(days=800))
    rss = f"""<rss><channel>
      <item><title>Fresh order</title><link>https://x/fresh</link><description>order</description>
        <pubDate>{fresh_date}</pubDate></item>
      <item><title>Ancient news</title><link>https://x/old</link><description>order</description>
        <pubDate>{old_date}</pubDate></item>
    </channel></rss>""".encode()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return rss

    with mock.patch("src.abnormal_news_radar.feeds.urllib.request.urlopen", lambda *a, **k: _Resp()):
        articles = feeds.fetch_feed(source)

    titles = [a.title for a in articles]
    assert "Fresh order" in titles
    assert "Ancient news" not in titles  # >1y old dropped
