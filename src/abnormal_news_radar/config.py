from __future__ import annotations

import json
from pathlib import Path

from .model import Company, MarketSource, Source


def load_sources(path: Path) -> list[Source]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        Source(
            name=item["name"],
            type=item.get("type", "rss"),
            url=item["url"],
            trust=float(item.get("trust", 0.75)),
            group=item.get("group", "ungrouped"),
            include_patterns=tuple(item.get("include_patterns", [])),
            exclude_patterns=tuple(item.get("exclude_patterns", [])),
        )
        for item in payload.get("sources", [])
    ]


def load_market_sources(path: Path) -> list[MarketSource]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        MarketSource(
            name=item["name"],
            group=item.get("group", "market"),
            type=item.get("type", "api"),
            url=item["url"],
            purpose=item.get("purpose", ""),
            status=item.get("status", "configured"),
        )
        for item in payload.get("market_sources", [])
    ]


def load_watchlist(path: Path) -> list[Company]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    companies: list[Company] = []
    for item in payload.get("companies", []):
        aliases = tuple(dict.fromkeys([item["ticker"], item["name"], *item.get("aliases", [])]))
        companies.append(
            Company(
                ticker=item["ticker"].upper(),
                name=item["name"],
                aliases=aliases,
                themes=tuple(item.get("themes", [])),
            )
        )
    return companies
