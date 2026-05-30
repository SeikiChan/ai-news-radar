from __future__ import annotations

import re

from .model import Article, Candidate, Company
from .scoring import DISCOVERY_MIN_RAW, analyze_evidence, score_article
from .timeliness import article_timeliness

DISCOVERY_VERBS = (
    "announces",
    "receives",
    "reports",
    "signs",
    "partners",
    "wins",
    "awarded",
    "secures",
    "launches",
    "introduces",
    "publishes",
    "demonstrates",
    "collaborates",
    "develops",
    "enters",
    "raises",
    "begins",
    "starts",
    "expands",
    "completes",
)

GENERIC_COMPANY_NAMES = {
    "press release",
    "technology",
    "manufacturing news",
    "financial reports",
    "share repurchase programme",
}


def discover_candidate(
    article: Article,
    watchlist: list[Company],
    min_raw_score: int = DISCOVERY_MIN_RAW,
) -> Candidate | None:
    profile = analyze_evidence(article)
    raw_score = int(profile["raw_score"])
    matched_terms = tuple(profile["matched_terms"])
    if raw_score < min_raw_score:
        return None

    signal = score_article(article, watchlist)
    tickers = signal.tickers if signal is not None else ()
    company_name = _known_company_name(tickers, watchlist) or _extract_company_name(article)
    if not company_name:
        return None

    freshness = article_timeliness(article)
    adjusted = round(raw_score * article.source_trust * float(freshness.get("score_multiplier") or 1.0), 2)
    status = "known_watchlist" if tickers else "discovered"
    reason = _reason(matched_terms, tickers)
    return Candidate(
        article=article,
        company_name=company_name,
        tickers=tickers,
        score=adjusted,
        raw_score=raw_score,
        matched_terms=matched_terms,
        status=status,
        reason=reason,
        confidence=float(profile["confidence"]),
        evidence_tier=str(profile["evidence_tier"]),
    )


def _known_company_name(tickers: tuple[str, ...], watchlist: list[Company]) -> str:
    if not tickers:
        return ""
    by_ticker = {company.ticker: company.name for company in watchlist}
    return by_ticker.get(tickers[0], "")


def _extract_company_name(article: Article) -> str:
    title = article.title.strip()
    if not title:
        return ""

    prefix = title.split(":", 1)[0].strip()
    if 2 <= len(prefix) <= 60 and not _is_generic(prefix):
        return _clean_company_name(prefix)

    verb_pattern = "|".join(re.escape(verb) for verb in DISCOVERY_VERBS)
    match = re.match(rf"^(.{{2,80}}?)\s+(?:{verb_pattern})\b", title, flags=re.IGNORECASE)
    if match:
        return _clean_company_name(match.group(1))

    return ""


def _clean_company_name(value: str) -> str:
    value = re.sub(r"^\W+", "", value)
    value = re.sub(r"\s+", " ", value).strip(" -:|")
    value = re.sub(r"\s+\([A-Z0-9.: -]{1,16}\)$", "", value)
    if _is_generic(value):
        return ""
    return value


def _is_generic(value: str) -> bool:
    normalized = value.lower().strip()
    return normalized in GENERIC_COMPANY_NAMES or len(normalized) < 2


def _reason(matched_terms: tuple[str, ...], tickers: tuple[str, ...]) -> str:
    evidence = ", ".join(matched_terms[:5]) if matched_terms else "evidence terms"
    if tickers:
        return f"Known company matched watchlist; evidence: {evidence}."
    return f"Company inferred from hard-evidence article; evidence: {evidence}."
