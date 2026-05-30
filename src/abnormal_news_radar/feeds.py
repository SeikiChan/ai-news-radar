from __future__ import annotations

import html
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from .model import Article, Source

TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    clean = TAG_RE.sub(" ", value or "")
    clean = html.unescape(clean)
    return " ".join(clean.split())


def fetch_feed(source: Source, timeout: int = 20) -> list[Article]:
    user_agent = os.environ.get(
        "AI_NEWS_RADAR_USER_AGENT",
        "ai-news-radar/0.1 research-tool contact=local@example.com",
    )
    request = urllib.request.Request(source.url, headers={"User-Agent": user_agent})
    is_arxiv = "export.arxiv.org" in source.url
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 429 or not is_arxiv:
            raise
        time.sleep(3.5)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except Exception:
            return []
    except TimeoutError:
        if not is_arxiv:
            raise
        return []

    if is_arxiv and raw.strip().lower().startswith(b"rate exceeded"):
        time.sleep(3.5)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except Exception:
            return []
        if raw.strip().lower().startswith(b"rate exceeded"):
            return []

    if source.type == "html":
        return list(_parse_html_links(raw.decode("utf-8", errors="replace"), source))

    root = ET.fromstring(raw)
    if root.tag.endswith("rss"):
        return list(_parse_rss(root, source))
    return list(_parse_atom(root, source))


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return strip_html(node.text)


def _parse_rss(root: ET.Element, source: Source) -> Iterable[Article]:
    channel = root.find("channel")
    if channel is None:
        return
    for item in channel.findall("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        summary = _text(item.find("description"))
        published = _text(item.find("pubDate"))
        if title:
            article = Article(
                source=source.name,
                source_trust=source.trust,
                title=title,
                link=link,
                summary=summary,
                published=published,
            )
            if _article_allowed(article, source):
                yield article


def _parse_atom(root: ET.Element, source: Source) -> Iterable[Article]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    if not entries:
        entries = root.findall("entry")

    for entry in entries:
        title = _text(_first_node(entry.find("atom:title", ns), entry.find("title")))
        summary = _text(
            _first_node(
                entry.find("atom:summary", ns),
                entry.find("summary"),
                entry.find("atom:content", ns),
                entry.find("content"),
            )
        )
        published = _text(_first_node(entry.find("atom:updated", ns), entry.find("updated")))
        link_node = _first_node(entry.find("atom:link", ns), entry.find("link"))
        link = ""
        if link_node is not None:
            link = link_node.attrib.get("href", "") or _text(link_node)
        if title:
            article = Article(
                source=source.name,
                source_trust=source.trust,
                title=title,
                link=link,
                summary=summary,
                published=published,
            )
            if _article_allowed(article, source):
                yield article


def _first_node(*nodes: ET.Element | None) -> ET.Element | None:
    for node in nodes:
        if node is not None:
            return node
    return None


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self._href = href
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        title = strip_html(" ".join(self._parts))
        if title:
            self.anchors.append((self._href, title))
        self._href = None
        self._parts = []


def _parse_html_links(document: str, source: Source) -> Iterable[Article]:
    parser = _AnchorParser()
    parser.feed(document)

    for href, title in parser.anchors:
        link = urljoin(source.url, href)
        title = _normalize_link_title(title, link)
        candidate = f"{link}\n{title}"
        if source.include_patterns and not _matches_any(candidate, source.include_patterns):
            continue
        if source.exclude_patterns and _matches_any(candidate, source.exclude_patterns):
            continue
        yield Article(
            source=source.name,
            source_trust=source.trust,
            title=title,
            link=link,
        )


def _normalize_link_title(title: str, link: str) -> str:
    title = strip_html(title)
    if title.lower() not in {"read more", "learn more", "more", "press releases"}:
        return title

    slug = Path(unquote(urlparse(link).path)).name
    if not slug:
        return title
    return " ".join(slug.replace("-", " ").replace("_", " ").split())


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def _article_allowed(article: Article, source: Source) -> bool:
    candidate = f"{article.link}\n{article.title}\n{article.summary}"
    if source.include_patterns and not _matches_any(candidate, source.include_patterns):
        return False
    if source.exclude_patterns and _matches_any(candidate, source.exclude_patterns):
        return False
    return True


def fetch_all(sources: list[Source], limit_per_source: int = 50) -> tuple[list[Article], list[str]]:
    articles: list[Article] = []
    errors: list[str] = []

    for source in sources:
        try:
            fetched = fetch_feed(source)
            articles.extend(fetched[:limit_per_source])
        except Exception as exc:  # noqa: BLE001 - capture source failures without killing the scan.
            errors.append(f"{source.name}: {exc}")

    return dedupe_articles(articles), errors


def dedupe_articles(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    output: list[Article] = []
    for article in articles:
        key = article.link or f"{article.source}:{article.title}"
        if key in seen:
            continue
        seen.add(key)
        output.append(article)
    return output
