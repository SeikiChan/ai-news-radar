"""Shared networking helpers: a single User-Agent policy and URL templating.

Runtime stays on the Python standard library on purpose. This module centralizes
the few cross-cutting HTTP concerns so every fetcher behaves consistently:

* one configurable ``User-Agent`` (SEC EDGAR rejects generic/empty agents and
  asks for a contact string), and
* date-templated source URLs so feeds that require a current year/month/day in
  the query string never silently break at a calendar boundary.
"""

from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

#: Market clock used to resolve URL date templates. Public market/government
#: data is published on the U.S. Eastern calendar, so resolve templates there.
MARKET_TZ = ZoneInfo("America/New_York")

_DEFAULT_USER_AGENT = "ai-news-radar/0.2 research-tool contact=local@example.com"

logger = logging.getLogger("ai_news_radar")

#: Conservative defaults for free public endpoints, several of which are slow.
DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.5
#: HTTP statuses worth retrying (rate limit + transient server/gateway errors).
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once for CLI/web entry points.

    Level can be overridden with the ``AI_NEWS_RADAR_LOG_LEVEL`` environment
    variable (e.g. ``DEBUG``, ``WARNING``).
    """
    env_level = os.environ.get("AI_NEWS_RADAR_LOG_LEVEL")
    if env_level:
        level = getattr(logging, env_level.upper(), level)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def user_agent() -> str:
    """Return the User-Agent used for every outbound request.

    Override with the ``AI_NEWS_RADAR_USER_AGENT`` environment variable. SEC
    EDGAR in particular expects a descriptive agent with a contact address.
    """
    return os.environ.get("AI_NEWS_RADAR_USER_AGENT", _DEFAULT_USER_AGENT)


def expand_url_template(url: str, now: datetime | None = None) -> str:
    """Substitute ``{yyyy}``, ``{yyyymm}``, and ``{yyyymmdd}`` in ``url``.

    Resolved against the current U.S. Eastern date so date-scoped public feeds
    (e.g. the Treasury daily yield curve) always request a live window instead
    of a value hard-coded into the config file.
    """
    if "{" not in url:
        return url
    moment = (now or datetime.now(MARKET_TZ)).astimezone(MARKET_TZ)
    replacements = {
        "{yyyy}": moment.strftime("%Y"),
        "{yyyymm}": moment.strftime("%Y%m"),
        "{yyyymmdd}": moment.strftime("%Y%m%d"),
    }
    for token, value in replacements.items():
        url = url.replace(token, value)
    return url


def fetch_bytes(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    accept: str = "*/*",
    headers: dict[str, str] | None = None,
    opener: object | None = None,
    sleep: object | None = None,
    max_bytes: int = 0,
) -> bytes:
    """Fetch ``url`` with a shared User-Agent, date templating, and retries.

    Retries transient failures (timeouts, connection errors, and retryable HTTP
    statuses) with exponential backoff. ``opener``/``sleep`` are injectable for
    deterministic tests. ``max_bytes`` (>0) caps the read so a runaway download
    (e.g. a huge PDF) cannot exhaust memory.
    """
    resolved = expand_url_template(url)
    do_open = opener or urllib.request.urlopen
    do_sleep = sleep or time.sleep
    request_headers = {"User-Agent": user_agent(), "Accept": accept}
    if headers:
        request_headers.update(headers)

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(resolved, headers=request_headers)
            with do_open(request, timeout=timeout) as response:
                return response.read(max_bytes) if max_bytes > 0 else response.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in RETRYABLE_STATUS or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            if attempt == retries:
                raise
        backoff = RETRY_BACKOFF_SECONDS * (2**attempt)
        logger.warning(
            "fetch retry %d/%d for %s after %s; backing off %.1fs",
            attempt + 1,
            retries,
            resolved,
            last_exc,
            backoff,
        )
        do_sleep(backoff)

    # Defensive: the loop either returns or raises on the final attempt.
    raise last_exc if last_exc else RuntimeError(f"fetch failed: {resolved}")


def fetch_text(url: str, *, encoding: str = "utf-8", **kwargs: object) -> str:
    """``fetch_bytes`` decoded as text (errors replaced)."""
    return fetch_bytes(url, **kwargs).decode(encoding, errors="replace")
