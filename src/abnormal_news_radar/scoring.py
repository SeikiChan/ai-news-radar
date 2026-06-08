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
    # --- AI full-chain deepening (upstream materials/EDA/packaging → mid memory/
    #     interconnect → downstream compute/agents). Thematic boosters, not
    #     stand-alone triggers; hard-evidence terms above still carry the score.
    "advanced packaging": 10,
    "cowos": 12,
    "chiplet": 10,
    "chiplets": 10,
    "glass substrate": 12,
    "hybrid bonding": 12,
    "high bandwidth memory": 8,
    "ai inference": 8,
    "ai training": 8,
    "training cluster": 10,
    "gpu cluster": 10,
    "agentic ai": 8,
    "frontier model": 8,
    "optical transceiver": 8,
    "linear pluggable optics": 10,
    "neocloud": 10,
    # --- Robotics full-chain (sensing → actuation → platform → application).
    "humanoid robot": 14,
    "humanoid robots": 14,
    "humanoid": 10,
    "embodied ai": 12,
    "harmonic reducer": 12,
    "harmonic drive": 12,
    "planetary roller screw": 12,
    "robot actuator": 12,
    "servo motor": 8,
    "force-torque sensor": 10,
    "tactile sensor": 10,
    "machine vision": 8,
    "lidar": 8,
    "autonomous mobile robot": 10,
    "warehouse automation": 10,
    "industrial robot": 8,
    "industrial robots": 8,
    "collaborative robot": 8,
    "cobot": 8,
    "robotic arm": 8,
    "factory automation": 8,
    "autonomous driving": 8,
    "full self-driving": 10,
    # --- Energy transition (storage/battery → nuclear → renewables → grid).
    #     An off-take agreement is a binding multi-year purchase = hard evidence.
    "offtake agreement": 18,
    "offtake": 12,
    "power purchase agreement": 14,
    "solid-state battery": 14,
    "solid state battery": 14,
    "gigafactory": 14,
    "battery energy storage": 12,
    "grid storage": 10,
    "small modular reactor": 14,
    "advanced nuclear": 12,
    "nuclear reactor": 10,
    "electrolyzer": 12,
    "green hydrogen": 10,
    "photovoltaic": 8,
    "solar module": 8,
    "wind turbine": 8,
    "grid interconnection": 10,
    "cathode": 8,
    "anode": 8,
    "lithium": 6,
    "ev charging": 6,
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


# --------------------------------------------------------------------------- #
# Alert bands and evidence tiers
#
# Single source of truth for the score thresholds. When the `report` command
# accumulates enough matured forward-return outcomes, calibrate these here.
# --------------------------------------------------------------------------- #
HARD_BAND = 35.0
WATCH_BAND = 20.0
WEAK_BAND = 10.0

#: Minimum raw evidence score for an article to seed a discovered candidate.
DISCOVERY_MIN_RAW = 16

#: Aliases this short are treated as ticker/symbol-like and matched
#: case-sensitively, so a symbol such as "ON" (onsemi) is not triggered by the
#: English word "on". Longer company-name aliases stay case-insensitive.
TICKER_MATCH_MAX_LEN = 5

#: Common English words that also appear as tickers ("ON", "CAT") or as the
#: leading word of a company name ("On Semiconductor", "ARM Holdings"). They are
#: dangerous because they collide with ordinary prose ("...transistors on
#: semiconductor substrates...", "robotic arm"). Aliases that ARE one of these
#: short words require an explicit ticker context ($ON / (ON) / NASDAQ: ON);
#: longer aliases that START with one require the match to carry real
#: capitalization (rejecting all-lowercase coincidental phrases). The company
#: still matches via its distinctive aliases ("onsemi", "Caterpillar").
_AMBIGUOUS_WORD_ALIASES: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "big", "by", "can", "core", "do",
    "for", "go", "high", "id", "if", "in", "is", "it", "key", "low", "new",
    "next", "no", "now", "of", "ok", "on", "one", "open", "or", "real", "so",
    "the", "to", "two", "up", "us", "we", "arm", "cat", "hon", "ten",
    # Short symbols that collide with common words/abbreviations: only count
    # inside an explicit ticker context.
    "emr", "nee", "path", "pwr", "smr",
})

#: Exchange prefixes that unambiguously introduce a ticker symbol.
_TICKER_CONTEXT_RE_CACHE: dict[str, re.Pattern[str]] = {}

#: Evidence tiers derived from a term's weight. Hard-evidence terms describe a
#: change in real economics (orders, prepayments, production, guidance); thematic
#: terms are narrative ("AI", "semiconductor") and must not dominate a score.
TIER1_MIN_WEIGHT = 18
TIER2_MIN_WEIGHT = 10

#: Thematic (tier-3) terms get diminishing returns and a hard cap so a wall of
#: buzzwords without hard evidence cannot inflate the score.
TIER3_FULL_COUNT = 1
TIER3_DECAY = 0.5
TIER3_MAX_CONTRIBUTION = 12.0

#: Quantified economics (dollar amounts, magnitudes, capacity/unit counts) are a
#: strong tell that a headline carries real numbers rather than narrative.
_QUANTIFIED_ECONOMICS_RE = re.compile(
    r"(\$\s?\d[\d,.]*"
    r"|\b\d[\d,.]*\s?(?:million|billion|thousand|m|bn)\b"
    r"|\b\d[\d,.]*\s?%"
    r"|\b\d[\d,.]*\s?(?:mw|gw|kw|kwh|mwh|units|wafers|systems|racks)\b)",
    re.IGNORECASE,
)


def band_for_score(score: float) -> str:
    if score >= HARD_BAND:
        return "hard alert"
    if score >= WATCH_BAND:
        return "watch alert"
    if score >= WEAK_BAND:
        return "weak alert"
    return "ignore"


def _tier_for_weight(weight: int) -> str:
    if weight >= TIER1_MIN_WEIGHT:
        return "tier1_hard"
    if weight >= TIER2_MIN_WEIGHT:
        return "tier2_material"
    return "tier3_thematic"


def analyze_evidence(article: Article) -> dict[str, object]:
    """Structured, explainable evidence profile for an article.

    Returns the raw score (with thematic diminishing returns applied), the flat
    matched-term list (order preserved for backward compatibility), the terms
    grouped by tier, whether quantified economics were detected, and a derived
    evidence tier + confidence in [0, 1].
    """
    text = f" {article.text.lower()} "
    matched_terms: list[str] = []
    by_tier: dict[str, list[tuple[str, int]]] = {
        "tier1_hard": [],
        "tier2_material": [],
        "tier3_thematic": [],
        "penalty": [],
        "counterparty": [],
    }

    for term, weight in TERM_WEIGHTS.items():
        if _contains_term(text, term):
            matched_terms.append(term.strip())
            by_tier[_tier_for_weight(weight)].append((term.strip(), weight))

    for term, weight in PENALTY_WEIGHTS.items():
        if _contains_term(text, term):
            matched_terms.append(term.strip())
            by_tier["penalty"].append((term.strip(), weight))

    if _has_evidence_context(text, matched_terms):
        for term, weight in STRATEGIC_COUNTERPARTIES.items():
            if _contains_term(text, term):
                matched_terms.append(f"counterparty:{term.strip()}")
                by_tier["counterparty"].append((term.strip(), weight))

    raw_score = _score_from_tiers(by_tier)
    quantified = bool(_QUANTIFIED_ECONOMICS_RE.search(article.text))
    evidence_tier, confidence = _grade_confidence(by_tier, quantified)

    return {
        "raw_score": raw_score,
        "matched_terms": tuple(dict.fromkeys(matched_terms)),
        "by_tier": by_tier,
        "quantified_economics": quantified,
        "evidence_tier": evidence_tier,
        "confidence": confidence,
    }


def _score_from_tiers(by_tier: dict[str, list[tuple[str, int]]]) -> int:
    score = 0.0
    score += sum(weight for _term, weight in by_tier["tier1_hard"])
    score += sum(weight for _term, weight in by_tier["tier2_material"])

    thematic = sorted((weight for _term, weight in by_tier["tier3_thematic"]), reverse=True)
    thematic_contribution = 0.0
    for index, weight in enumerate(thematic):
        factor = 1.0 if index < TIER3_FULL_COUNT else TIER3_DECAY
        thematic_contribution += weight * factor
    score += min(thematic_contribution, TIER3_MAX_CONTRIBUTION)

    score += sum(weight for _term, weight in by_tier["penalty"])
    score += sum(weight for _term, weight in by_tier["counterparty"])
    return round(score)


def _grade_confidence(by_tier: dict[str, list[tuple[str, int]]], quantified: bool) -> tuple[str, float]:
    tier1 = by_tier["tier1_hard"]
    tier2 = by_tier["tier2_material"]
    tier3 = by_tier["tier3_thematic"]
    penalty = by_tier["penalty"]

    if tier1:
        evidence_tier, confidence = "hard_evidence", 0.5
    elif tier2:
        evidence_tier, confidence = "material", 0.3
    elif tier3:
        evidence_tier, confidence = "thematic", 0.1
    else:
        return "none", 0.0

    if len(tier1) + len(tier2) >= 2:
        confidence += 0.15
    if quantified:
        confidence += 0.25
    if penalty:
        confidence -= 0.25

    return evidence_tier, max(0.0, min(round(confidence, 2), 1.0))


def score_article(article: Article, watchlist: list[Company]) -> Signal | None:
    # Company matching needs the original casing so short uppercase tickers can
    # be told apart from same-spelled English words. Evidence scoring (below)
    # lower-cases internally.
    matched_companies = _match_companies(f" {article.text} ", watchlist)
    profile = analyze_evidence(article)
    raw_score = int(profile["raw_score"])
    matched_terms = tuple(profile["matched_terms"])

    if not matched_companies and raw_score < WATCH_BAND:
        return None

    tickers = tuple(company.ticker for company in matched_companies)
    themes = tuple(dict.fromkeys(theme for company in matched_companies for theme in company.themes))
    freshness = article_timeliness(article)
    adjusted = round(raw_score * article.source_trust * float(freshness.get("score_multiplier") or 1.0), 2)
    band = band_for_score(adjusted)

    if adjusted < WEAK_BAND and not tickers:
        return None

    return Signal(
        article=article,
        tickers=tickers,
        themes=themes,
        score=adjusted,
        raw_score=raw_score,
        matched_terms=matched_terms,
        band=band,
        confidence=float(profile["confidence"]),
        evidence_tier=str(profile["evidence_tier"]),
    )


def _match_companies(text: str, watchlist: list[Company]) -> list[Company]:
    """Match watchlist companies in the (original-case) article ``text``.

    Matching is deliberately conservative to avoid false attributions:

    * short ticker aliases that spell an English word ("ON", "CAT") need an
      explicit ticker context ("$ON", "(ON)", "NASDAQ: ON");
    * other short aliases use case-sensitive word-boundary matching ("AMD");
    * company-name aliases use word-boundary matching, and if the name *starts*
      with an English word ("On Semiconductor") an all-lowercase coincidental
      phrase ("...on semiconductor substrates...") is rejected.
    """
    matched: list[Company] = []
    for company in watchlist:
        for alias in company.aliases:
            alias_clean = alias.strip()
            if not alias_clean or alias_clean.lower() in GENERIC_COMPANY_ALIASES:
                continue
            if _alias_in_text(alias_clean, text):
                matched.append(company)
                break
    return matched


def _alias_in_text(alias: str, text: str) -> bool:
    alias_lower = alias.lower()
    leading_word = alias_lower.split(" ", 1)[0]
    ambiguous = leading_word in _AMBIGUOUS_WORD_ALIASES

    if len(alias) <= TICKER_MATCH_MAX_LEN:
        if ambiguous:
            # A bare English-word symbol only counts inside a ticker context.
            return _ticker_context_match(alias, text)
        # Distinctive short symbol (AMD, NVDA): case-sensitive word boundary.
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text) is not None

    boundary = rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"
    if not ambiguous:
        return re.search(boundary, text, re.IGNORECASE) is not None
    # Name starts with an English word: accept only when that leading word is
    # itself capitalized, so "On Semiconductor"/"ON Semiconductor" (the company)
    # match, but neither the lowercase phrase "on semiconductor substrates" nor
    # the preposition in "...appeared first on Semiconductor Engineering" does.
    for match in re.finditer(boundary, text, re.IGNORECASE):
        if match.group(0)[:1].isupper():
            return True
    return False


def _ticker_context_match(alias: str, text: str) -> bool:
    """True when ``alias`` appears as an explicit ticker, e.g. ``$ON``, ``(ON)``,
    ``ON:`` or ``NASDAQ: ON`` — never as a bare prose word."""
    pattern = _TICKER_CONTEXT_RE_CACHE.get(alias)
    if pattern is None:
        symbol = re.escape(alias)
        pattern = re.compile(
            rf"(?:[$(]|(?:NYSE|NASDAQ|Nasdaq|NMS|OTC|AMEX|CBOE)\s*:\s*){symbol}(?![A-Za-z0-9])"
            rf"|(?<![A-Za-z0-9]){symbol}[):]"
        )
        _TICKER_CONTEXT_RE_CACHE[alias] = pattern
    return pattern.search(text) is not None


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
