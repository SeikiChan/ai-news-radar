"""Shared Yahoo Finance quoteSummary access (standard library only).

Yahoo's ``quoteSummary`` endpoint (short interest, institutional ownership, key
statistics) requires a cookie + crumb handshake. This module performs that once
and hands back a ``fetch(url) -> text`` callable, so the short-interest and
institutional-flow factors share a single authenticated session instead of each
re-negotiating a crumb. Every consumer injects this fetcher (or a fake one in
tests) and degrades cleanly when Yahoo rate-limits.
"""

from __future__ import annotations

import http.cookiejar
import urllib.parse
import urllib.request

from .net import user_agent

FETCH_TIMEOUT_SECONDS = 12
_BASE = "https://query2.finance.yahoo.com/v10/finance/quoteSummary"


def quote_summary_url(symbol: str, modules: str) -> str:
    return f"{_BASE}/{urllib.parse.quote(symbol)}?modules={urllib.parse.quote(modules)}"


def make_yahoo_fetcher() -> object:
    """Return ``fetch(url) -> text`` that performs the cookie+crumb handshake once
    and appends the crumb to each quoteSummary request."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    state: dict[str, str | None] = {"crumb": None}

    def _open(url: str, accept: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept": accept})
        with opener.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")

    def _ensure_crumb() -> str:
        if state["crumb"]:
            return str(state["crumb"])
        try:
            _open("https://fc.yahoo.com", "text/html")  # seeds the session cookie
        except Exception:  # noqa: BLE001 - 404 is fine; the cookie is still set.
            pass
        crumb = _open("https://query2.finance.yahoo.com/v1/test/getcrumb", "text/plain").strip()
        state["crumb"] = crumb
        return crumb

    def fetch(url: str) -> str:
        crumb = _ensure_crumb()
        separator = "&" if "?" in url else "?"
        return _open(f"{url}{separator}crumb={urllib.parse.quote(crumb)}", "application/json")

    return fetch


def raw(node: object) -> object:
    """Yahoo wraps numbers as ``{"raw": <value>, "fmt": "..."}``; unwrap to raw."""
    if isinstance(node, dict):
        return node.get("raw")
    return node
