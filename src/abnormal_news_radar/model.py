from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Source:
    name: str
    type: str
    url: str
    trust: float = 0.75
    group: str = "ungrouped"
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketSource:
    name: str
    group: str
    type: str
    url: str
    purpose: str
    status: str = "configured"


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    aliases: tuple[str, ...]
    themes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Article:
    source: str
    source_trust: float
    title: str
    link: str
    summary: str = ""
    published: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.summary}".strip()


@dataclass(frozen=True)
class Signal:
    article: Article
    tickers: tuple[str, ...]
    themes: tuple[str, ...]
    score: float
    raw_score: int
    matched_terms: tuple[str, ...]
    band: str


@dataclass(frozen=True)
class Candidate:
    article: Article
    company_name: str
    tickers: tuple[str, ...]
    score: float
    raw_score: int
    matched_terms: tuple[str, ...]
    status: str
    reason: str
