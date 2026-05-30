import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from src.abnormal_news_radar.net import (
    MARKET_TZ,
    expand_url_template,
    fetch_bytes,
    user_agent,
)


class _FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def _opener_sequence(*outcomes):
    """Build a fake opener that yields each outcome (response or exception) in turn."""
    calls = {"n": 0}

    def opener(_request, timeout):
        outcome = outcomes[calls["n"]]
        calls["n"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)

    return opener, calls


def test_user_agent_default_has_contact():
    agent = user_agent()
    assert "ai-news-radar" in agent
    assert "contact=" in agent


def test_user_agent_env_override(monkeypatch):
    monkeypatch.setenv("AI_NEWS_RADAR_USER_AGENT", "custom-agent/1.0 contact=me@example.com")
    assert user_agent() == "custom-agent/1.0 contact=me@example.com"


def test_expand_url_template_substitutes_date_tokens():
    moment = datetime(2026, 5, 30, 12, 0, tzinfo=MARKET_TZ)
    url = "https://x/api?year={yyyy}&month={yyyymm}&day={yyyymmdd}"
    assert expand_url_template(url, now=moment) == "https://x/api?year=2026&month=202605&day=20260530"


def test_expand_url_template_noop_without_tokens():
    url = "https://x/api?static=1"
    assert expand_url_template(url) == url


def test_expand_url_template_resolves_to_market_timezone():
    # 02:00 UTC on 2026-06-01 is still 2026-05-31 in America/New_York.
    moment = datetime(2026, 6, 1, 2, 0, tzinfo=ZoneInfo("UTC"))
    assert expand_url_template("d={yyyymmdd}", now=moment) == "d=20260531"


def test_fetch_bytes_returns_body_on_first_success():
    opener, calls = _opener_sequence(b"hello")
    result = fetch_bytes("https://x/api", opener=opener, sleep=lambda _s: None)
    assert result == b"hello"
    assert calls["n"] == 1


def test_fetch_bytes_retries_transient_timeout_then_succeeds():
    opener, calls = _opener_sequence(TimeoutError("slow"), b"ok")
    result = fetch_bytes("https://x/api", opener=opener, sleep=lambda _s: None)
    assert result == b"ok"
    assert calls["n"] == 2


def test_fetch_bytes_retries_retryable_http_status():
    err = urllib.error.HTTPError("https://x/api", 503, "unavailable", {}, None)
    opener, calls = _opener_sequence(err, b"recovered")
    result = fetch_bytes("https://x/api", opener=opener, sleep=lambda _s: None)
    assert result == b"recovered"
    assert calls["n"] == 2


def test_fetch_bytes_does_not_retry_non_retryable_status():
    err = urllib.error.HTTPError("https://x/api", 404, "not found", {}, None)
    opener, calls = _opener_sequence(err, b"never")
    with pytest.raises(urllib.error.HTTPError):
        fetch_bytes("https://x/api", opener=opener, sleep=lambda _s: None)
    assert calls["n"] == 1


def test_fetch_bytes_exhausts_retries_then_raises():
    opener, calls = _opener_sequence(TimeoutError("1"), TimeoutError("2"), TimeoutError("3"))
    with pytest.raises(TimeoutError):
        fetch_bytes("https://x/api", retries=2, opener=opener, sleep=lambda _s: None)
    assert calls["n"] == 3
