from __future__ import annotations

import re

FLOW_SOURCE_HINTS = ("fl0wg0d", "flow god", "unusual whales", "optionstrat", "flowalgo", "options flow")
FLOW_KEYWORD_PATTERNS = (
    r"\bunusual options\b",
    r"\boptions flow\b",
    r"\boption flow\b",
    r"\bask sweeps?\b",
    r"\bcall sweeps?\b",
    r"\bput sweeps?\b",
    r"\bcalls?\b",
    r"\bputs?\b",
    r"\bpremium\b",
    r"\boi\b",
    r"\bopen interest\b",
)
CALL_TERMS = (" call", " calls", "bullish", "ask sweep", "call sweep", "call sweeps")
PUT_TERMS = (" put", " puts", "bearish", "put sweep", "put sweeps")
PREMIUM_RE = re.compile(r"\$?\s*(\d+(?:\.\d+)?)\s*(m|mm|million|k|thousand)\b", re.IGNORECASE)
CASHTAG_RE = re.compile(r"(?<![A-Z0-9])\$([A-Z]{1,5})(?![A-Z0-9])")


def enrich_candidates_with_options_flow(
    candidates: list[dict[str, object]],
    articles: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    flow_events = _extract_flow_events(articles or [])
    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["options_flow"] = assess_options_flow(row, flow_events)
        enriched.append(row)
    return enriched


def assess_options_flow(candidate: dict[str, object], flow_events: list[dict[str, object]] | None = None) -> dict[str, object]:
    candidate_events = _candidate_flow_events(candidate, flow_events or [])
    inline_event = _inline_candidate_event(candidate)
    if inline_event:
        candidate_events.insert(0, inline_event)

    if not candidate_events:
        return {
            "status": "no_flow_evidence",
            "score": 0,
            "direction": "none",
            "summary_zh": "暂未发现与该候选标的匹配的异常期权流证据。",
            "evidence_zh": [],
            "source_policy_zh": _source_policy_zh(),
            "method": "transparent_rules_engine",
        }

    direction = _dominant_direction(candidate_events)
    score = _flow_score(candidate_events, direction)
    market_status = str(_dict_value(candidate.get("market_confirmation")).get("status") or "")
    impact_score = int(_dict_value(candidate.get("impact_assessment")).get("impact_score") or 0)
    status = _flow_status(direction, score, market_status, impact_score)

    return {
        "status": status,
        "score": score,
        "direction": direction,
        "summary_zh": _summary_zh(status, direction, score),
        "evidence_zh": [_event_summary(event) for event in candidate_events[:5]],
        "events": candidate_events[:10],
        "source_policy_zh": _source_policy_zh(),
        "method": "transparent_rules_engine",
        "rules_zh": [
            "异常期权流只能作为资金行为旁证，不能替代新闻、财务影响和价格/成交量确认。",
            "Call sweep / 大额 call premium 与正面新闻同向时，提升研究优先级。",
            "Put flow、混合 flow 或股价负反馈会被标为冲突证据，不能强行看多。",
            "未连接 X/API 时不生成虚假的 Flow God 数据。",
        ],
    }


def _extract_flow_events(articles: list[dict[str, object]]) -> list[dict[str, object]]:
    events = []
    for article in articles:
        text = _article_text(article)
        lower = text.lower()
        if not _looks_like_flow(lower):
            continue
        tickers = _article_tickers(text)
        if not tickers:
            continue
        events.append(
            {
                "source": str(article.get("source") or "unknown"),
                "title": str(article.get("title") or ""),
                "link": str(article.get("link") or ""),
                "published": str(article.get("published") or ""),
                "tickers": tickers,
                "direction": _direction_from_text(lower),
                "premium_musd": _premium_musd(lower),
                "source_tier": _source_tier(article, lower),
                "raw_excerpt": text[:500],
            }
        )
    return events


def _candidate_flow_events(candidate: dict[str, object], events: list[dict[str, object]]) -> list[dict[str, object]]:
    tickers = {str(ticker).upper() for ticker in candidate.get("tickers", []) or [] if str(ticker).strip()}
    if not tickers:
        return []
    matches = []
    for event in events:
        event_tickers = {str(ticker).upper() for ticker in event.get("tickers", []) or []}
        if tickers & event_tickers:
            matches.append(event)
    matches.sort(key=lambda event: (_event_rank(event), str(event.get("published") or "")), reverse=True)
    return matches


def _inline_candidate_event(candidate: dict[str, object]) -> dict[str, object] | None:
    article = _dict_value(candidate.get("article"))
    text = _article_text(article)
    lower = text.lower()
    if not _looks_like_flow(lower):
        return None
    tickers = [str(ticker).upper() for ticker in candidate.get("tickers", []) or [] if str(ticker).strip()]
    if not tickers:
        tickers = _article_tickers(text)
    if not tickers:
        return None
    return {
        "source": str(article.get("source") or "candidate_article"),
        "title": str(article.get("title") or ""),
        "link": str(article.get("link") or ""),
        "published": str(article.get("published") or ""),
        "tickers": tickers,
        "direction": _direction_from_text(lower),
        "premium_musd": _premium_musd(lower),
        "source_tier": _source_tier(article, lower),
        "raw_excerpt": text[:500],
    }


def _looks_like_flow(lower_text: str) -> bool:
    return any(hint in lower_text for hint in FLOW_SOURCE_HINTS) or any(
        re.search(pattern, lower_text, re.IGNORECASE) for pattern in FLOW_KEYWORD_PATTERNS
    )


def _article_tickers(text: str) -> list[str]:
    tickers = []
    for match in CASHTAG_RE.finditer(text.upper()):
        ticker = match.group(1)
        if ticker not in tickers:
            tickers.append(ticker)
    return tickers[:12]


def _direction_from_text(lower_text: str) -> str:
    call_score = sum(1 for term in CALL_TERMS if term in lower_text)
    put_score = sum(1 for term in PUT_TERMS if term in lower_text)
    if call_score > put_score:
        return "bullish_call_flow"
    if put_score > call_score:
        return "bearish_put_flow"
    if call_score and put_score:
        return "mixed"
    return "unknown"


def _premium_musd(lower_text: str) -> float | None:
    values = []
    for match in PREMIUM_RE.finditer(lower_text):
        number = float(match.group(1))
        unit = match.group(2).lower()
        multiplier = 1.0 if unit in {"m", "mm", "million"} else 0.001
        values.append(number * multiplier)
    if not values:
        return None
    return round(max(values), 3)


def _source_tier(article: dict[str, object], lower_text: str) -> str:
    source = f"{article.get('source', '')} {article.get('link', '')} {lower_text}".lower()
    if "fl0wg0d" in source or "flow god" in source:
        return "social_options_flow"
    if any(name in source for name in ("optionstrat", "flowalgo", "unusual whales", "benzinga")):
        return "flow_platform_or_wire"
    return "unverified_flow_mention"


def _dominant_direction(events: list[dict[str, object]]) -> str:
    bullish = sum(_event_rank(event) for event in events if event.get("direction") == "bullish_call_flow")
    bearish = sum(_event_rank(event) for event in events if event.get("direction") == "bearish_put_flow")
    if bullish > bearish:
        return "bullish_call_flow"
    if bearish > bullish:
        return "bearish_put_flow"
    if bullish or bearish:
        return "mixed"
    return "unknown"


def _flow_score(events: list[dict[str, object]], direction: str) -> int:
    if direction == "unknown":
        return 1
    score = min(3, len(events))
    if any(float(event.get("premium_musd") or 0) >= 1.0 for event in events):
        score += 1
    if any(event.get("source_tier") == "flow_platform_or_wire" for event in events):
        score += 1
    elif any(event.get("source_tier") == "social_options_flow" for event in events):
        score += 1
    return max(1, min(score, 5))


def _flow_status(direction: str, score: int, market_status: str, impact_score: int) -> str:
    if direction == "mixed":
        return "mixed_flow"
    if direction == "bearish_put_flow":
        return "bearish_flow"
    if direction == "bullish_call_flow":
        if market_status == "negative_reaction":
            return "conflicting_flow"
        if impact_score >= 3 or market_status in {"confirmed", "early_confirmation", "price_only_confirmation"}:
            return "supportive_flow"
        return "unverified_bullish_flow"
    return "unverified_flow"


def _summary_zh(status: str, direction: str, score: int) -> str:
    labels = {
        "supportive_flow": "发现同向异常期权流，可作为资金行为旁证。",
        "unverified_bullish_flow": "发现偏多期权流，但基本面或市场确认不足。",
        "bearish_flow": "发现偏空 put flow，必须解释风险，不应强行看多。",
        "conflicting_flow": "期权流与股价反馈冲突，先解释分歧。",
        "mixed_flow": "Call/put flow 混杂，不能作为方向证据。",
        "unverified_flow": "发现期权流提及，但方向不清晰。",
    }
    return f"{labels.get(status, '期权流状态未知')} direction={direction}, score={score}/5。"


def _event_summary(event: dict[str, object]) -> str:
    premium = event.get("premium_musd")
    premium_text = "premium=n/a" if premium is None else f"premium≈${float(premium):.3f}m"
    tickers = ",".join(str(ticker) for ticker in event.get("tickers", [])[:4])
    return (
        f"{event.get('source', 'unknown')} {tickers} "
        f"{event.get('direction', 'unknown')} {premium_text} tier={event.get('source_tier', 'unknown')}"
    )


def _event_rank(event: dict[str, object]) -> int:
    rank = 1
    if float(event.get("premium_musd") or 0) >= 1.0:
        rank += 2
    if event.get("source_tier") == "flow_platform_or_wire":
        rank += 2
    elif event.get("source_tier") == "social_options_flow":
        rank += 1
    return rank


def _source_policy_zh() -> str:
    return "Flow God / X / flow 平台属于市场行为线索；它证明有人在期权上博弈，不证明新闻为真，也不证明方向一定正确。"


def _article_text(article: dict[str, object]) -> str:
    return "\n".join(str(article.get(key) or "") for key in ("source", "title", "summary", "link"))


def _dict_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
