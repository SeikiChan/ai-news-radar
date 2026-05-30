from __future__ import annotations

import re

from .model import Article, Company, Signal
from .timeliness import article_timeliness

TERM_WEIGHTS: dict[str, int] = {
    "mass production": 30,
    "high-volume production": 28,
    "volume production": 24,
    "lifecycle revenue": 24,
    "lifetime revenue": 24,
    "design win": 22,
    "prepayment": 25,
    "advance payment": 25,
    "capacity reservation": 22,
    "capacity commitment": 22,
    "production order": 22,
    "purchase order": 22,
    "manufacturing readiness": 20,
    "production qualification": 20,
    "multi-year agreement": 18,
    "long-term agreement": 18,
    "book-to-bill": 18,
    "backlog": 18,
    "follow-up order": 18,
    "follow-up orders": 18,
    "ramp production": 18,
    "customer ramps": 18,
    "pre-production units": 16,
    "demand exceeds capacity": 16,
    "supply constrained": 16,
    "capacity constrained": 16,
    "field trial": 14,
    "field trials": 14,
    "hyperscale customer": 14,
    "hyperscaler": 14,
    "strategic customer": 14,
    "qualification to production": 14,
    "external light source": 12,
    "els": 10,
    "1.6t": 10,
    "6.4t": 10,
    "data center demand": 10,
    "datacenter demand": 10,
    "ai datacenter": 10,
    "ai data center": 10,
    "ai customer": 8,
    "ai infrastructure": 8,
    "ai factory": 12,
    "ai factories": 12,
    "rack-scale": 12,
    "rack scale": 12,
    "800 vdc": 24,
    "800 v hvdc": 24,
    "800v hvdc": 24,
    "hvdc": 14,
    "high-voltage direct current": 20,
    "high voltage direct current": 20,
    "1 mw rack": 18,
    "megawatt rack": 18,
    "power delivery": 12,
    "power distribution": 12,
    "rubin ultra": 12,
    "kyber": 12,
    "large-scale ai workloads": 8,
    "silicon photonics": 8,
    "co-packaged optics": 8,
    "cpo": 8,
    "dfb laser": 8,
    "laser arrays": 8,
    "optical interconnect": 8,
    "liquid cooling": 8,
    "thermal management": 8,
    "hbm": 8,
    "nvlink": 8,
    "accelerated computing": 8,
    "new product ramp": 8,
    "ramp": 6,
    "analyst upgrade": 4,
    "price target": 4,
    "reports financial results": 22,
    "reported financial results": 22,
    "quarter results": 18,
    "earnings": 14,
    "guidance": 14,
    "raises guidance": 24,
    "raised guidance": 24,
    "increases outlook": 22,
    "increased outlook": 22,
    "product revenue": 16,
    "remaining performance obligations": 16,
    "rpo": 10,
    "net revenue retention": 14,
    "executive order": 16,
    "presidential memorandum": 14,
    "tariff": 14,
    "tariffs": 14,
    "export control": 16,
    "export controls": 16,
    "sanctions": 14,
    "critical minerals": 12,
    "rare earth": 12,
    "data center infrastructure": 16,
    "federal contracting": 12,
    "procurement": 12,
    "defense production": 18,
    "national security": 10,
    "semiconductor": 6,
    "semiconductors": 6,
    "chips": 6,
    "artificial intelligence": 2,
    " ai ": 2,
}

PENALTY_WEIGHTS: dict[str, int] = {
    "common stock offering": -18,
    "at-the-market": -18,
    "atm offering": -18,
    "dilution": -18,
    "going concern": -25,
    "liquidity warning": -25,
    "guidance cut": -16,
    "revenue miss": -16,
    "lawsuit": -12,
    "investigation": -12,
    "sponsored": -8,
}

STRATEGIC_COUNTERPARTIES: dict[str, int] = {
    "jabil": 10,
    "celestica": 10,
    "foxconn": 10,
    "poet technologies": 8,
    "enablence": 8,
    "o-net": 8,
    "nvidia": 10,
    "analog devices": 8,
    "infineon": 8,
    "monolithic power": 8,
    "navitas": 8,
    "onsemi": 8,
    "renesas": 8,
    "rohm": 8,
    "stmicroelectronics": 8,
    "texas instruments": 8,
    "delta electronics": 8,
    "flex power": 8,
    "liteon": 8,
    "lite-on": 8,
    "schneider electric": 8,
    "vertiv": 8,
    "amazon": 8,
    " aws ": 8,
    "microsoft": 8,
    "azure": 8,
    "google": 8,
    "meta": 8,
    "oracle": 8,
    "broadcom": 10,
    "marvell": 10,
    "amd": 8,
    "tsmc": 8,
    "asml": 8,
    "department of defense": 10,
    "pentagon": 10,
    "white house": 8,
    "president trump": 8,
    "fortune 100": 8,
    "tier 1": 8,
    "tier-one": 8,
}

EVIDENCE_TERMS: tuple[str, ...] = (
    "agreement",
    "contract",
    "order",
    "prepayment",
    "advance payment",
    "production",
    "technology roadmap",
    "technical blog",
    "architecture",
    "ecosystem",
    "partner ecosystem",
    "qualification",
    "manufacturing readiness",
    "field trial",
    "field trials",
    "revenue",
    "backlog",
    "capacity",
    "design win",
    "ramp",
    "earnings",
    "financial results",
    "guidance",
    "outlook",
    "product revenue",
    "remaining performance obligations",
)

GENERIC_COMPANY_ALIASES: set[str] = {
    "accelerated storage",
    "ai-ran",
    "6g",
    "open ran",
    "custom silicon",
    "silicon photonics",
    "silicon photonics foundry",
    "1.6t optical",
    "photodiode",
    "laser driver",
    "data center optical",
    "burn-in",
    "wafer-level test",
    "silicon photonics test",
    "indium phosphide",
    "inp substrate",
    "cw dfb",
    "dfb laser",
    "laser arrays",
    "optical interposer",
    "optical engine",
    "electro-optic polymer",
    "eo polymer",
    "edge ai",
    "automotive radar",
    "drone",
}


def score_article(article: Article, watchlist: list[Company]) -> Signal | None:
    text = f" {article.text.lower()} "
    matched_companies = _match_companies(text, watchlist)
    raw_score, matched_terms = score_evidence(article)

    if not matched_companies and raw_score < 20:
        return None

    tickers = tuple(company.ticker for company in matched_companies)
    themes = tuple(dict.fromkeys(theme for company in matched_companies for theme in company.themes))
    freshness = article_timeliness(article)
    adjusted = round(raw_score * article.source_trust * float(freshness.get("score_multiplier") or 1.0), 2)

    if adjusted >= 35:
        band = "hard alert"
    elif adjusted >= 20:
        band = "watch alert"
    elif adjusted >= 10:
        band = "weak alert"
    else:
        band = "ignore"

    if adjusted < 10 and not tickers:
        return None

    return Signal(
        article=article,
        tickers=tickers,
        themes=themes,
        score=adjusted,
        raw_score=raw_score,
        matched_terms=tuple(dict.fromkeys(matched_terms)),
        band=band,
    )


def score_evidence(article: Article) -> tuple[int, tuple[str, ...]]:
    text = f" {article.text.lower()} "
    matched_terms: list[str] = []
    raw_score = 0

    for term, weight in TERM_WEIGHTS.items():
        if _contains_term(text, term):
            matched_terms.append(term.strip())
            raw_score += weight

    for term, weight in PENALTY_WEIGHTS.items():
        if _contains_term(text, term):
            matched_terms.append(term.strip())
            raw_score += weight

    if _has_evidence_context(text, matched_terms):
        for term, weight in STRATEGIC_COUNTERPARTIES.items():
            if _contains_term(text, term):
                matched_terms.append(f"counterparty:{term.strip()}")
                raw_score += weight

    return raw_score, tuple(dict.fromkeys(matched_terms))


def _match_companies(text: str, watchlist: list[Company]) -> list[Company]:
    matched: list[Company] = []
    for company in watchlist:
        for alias in company.aliases:
            alias_clean = alias.lower().strip()
            if not alias_clean:
                continue
            if alias_clean in GENERIC_COMPANY_ALIASES:
                continue
            if len(alias_clean) <= 5:
                pattern = rf"(?<![a-z0-9]){re.escape(alias_clean)}(?![a-z0-9])"
                if re.search(pattern, text):
                    matched.append(company)
                    break
            elif alias_clean in text:
                matched.append(company)
                break
    return matched


def _contains_term(text: str, term: str) -> bool:
    term = term.lower()
    if term.strip() != term or len(term.strip()) <= 4:
        return term in text
    if re.fullmatch(r"[a-z0-9 -]+", term):
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def _has_evidence_context(text: str, matched_terms: list[str]) -> bool:
    if any(term in EVIDENCE_TERMS for term in matched_terms):
        return True
    return any(_contains_term(text, term) for term in EVIDENCE_TERMS)
