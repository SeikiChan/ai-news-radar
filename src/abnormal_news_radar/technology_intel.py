from __future__ import annotations

import re
from urllib.request import Request, urlopen

from .feeds import strip_html
from .model import Company

FETCH_TIMEOUT_SECONDS = 8
USER_AGENT = "AI-News-Radar/0.1 technology-intelligence"
MAX_ARTICLE_TEXT_CHARS = 30000

TECHNOLOGY_TERMS: dict[str, tuple[str, ...]] = {
    "800v_hvdc_power": (
        "800 vdc",
        "800 v hvdc",
        "800v hvdc",
        "hvdc",
        "high-voltage direct current",
        "high voltage direct current",
        "1 mw rack",
        "megawatt rack",
        "power delivery",
        "power distribution",
    ),
    "ai_factory_rackscale": (
        "ai factory",
        "ai factories",
        "rack-scale",
        "rack scale",
        "kyber",
        "rubin ultra",
        "gb200",
        "gb300",
        "mgx",
        "nvl72",
    ),
    "optical_interconnect": (
        "co-packaged optics",
        "cpo",
        "silicon photonics",
        "optical interconnect",
        "1.6t",
        "6.4t",
        "800g",
        "linear pluggable optics",
    ),
    "accelerated_compute": (
        "gpu cluster",
        "training cluster",
        "inference cluster",
        "hbm",
        "nvlink",
        "cuda",
        "accelerated computing",
    ),
    "cooling_power_infrastructure": (
        "liquid cooling",
        "thermal management",
        "busway",
        "switchgear",
        "rectifier",
        "solid-state transformer",
        "energy storage",
    ),
}

TECH_SOURCE_HINTS = (
    "developer blog",
    "technical blog",
    "research",
    "arxiv",
    "open compute",
    "ocp",
    "semiconductor engineering",
)


def enrich_candidates_with_technology_intel(
    candidates: list[dict[str, object]],
    watchlist: list[Company],
    fetcher: object | None = None,
) -> list[dict[str, object]]:
    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["technology_intel"] = analyze_technology_candidate(row, watchlist=watchlist, fetcher=fetcher)
        enriched.append(row)
    return enriched


def analyze_technology_candidate(
    candidate: dict[str, object],
    watchlist: list[Company] | None = None,
    fetcher: object | None = None,
) -> dict[str, object]:
    article = candidate.get("article") if isinstance(candidate.get("article"), dict) else {}
    seed_text = _candidate_text(candidate)
    source = str(article.get("source") or "").lower()
    release = _article_text(article, seed_text, fetcher)
    text = release["text"]
    themes = _technology_themes(text)
    is_tech_source = any(hint in source for hint in TECH_SOURCE_HINTS)
    if not themes and not is_tech_source:
        return {
            "status": "not_technology_signal",
            "summary_zh": "该候选不是技术路线图/研究信号。",
            "themes": [],
            "mentioned_companies": [],
            "watch_points_zh": [],
        }

    mentioned = _mentioned_companies(text, watchlist or [], candidate)
    status = "technology_signal_detected" if themes else "technology_source_unclassified"
    strength = _signal_strength(themes, mentioned, release["read_depth"])
    return {
        "status": status,
        "summary_zh": _summary_zh(themes, mentioned, strength),
        "themes": themes,
        "mentioned_companies": mentioned,
        "read_through_zh": _read_through_zh(mentioned),
        "watch_points_zh": _watch_points(themes),
        "source_title": article.get("title") or "",
        "source_link": article.get("link") or "",
        "read_depth": release["read_depth"],
        "signal_strength": strength,
        "method": "technical_blog_paper_report_keyword_and_entity_pass",
        "limitations_zh": "技术博客、论文和研究报告通常早于财务确认，但也更容易停留在路线图或生态展示阶段；系统只把它作为早期线索，必须等待订单、财报、价格/成交量或重复证据确认。",
    }


def _technology_themes(text: str) -> list[dict[str, object]]:
    lower = f" {text.lower()} "
    output = []
    for theme, terms in TECHNOLOGY_TERMS.items():
        matched = []
        for term in terms:
            if _contains_term(lower, term):
                matched.append(term)
        if matched:
            output.append({"theme": theme, "matched_terms": matched[:8], "score": min(5, len(matched))})
    output.sort(key=lambda row: int(row["score"]), reverse=True)
    return output


def _mentioned_companies(text: str, watchlist: list[Company], candidate: dict[str, object]) -> list[dict[str, object]]:
    lower = f" {text.lower()} "
    own_tickers = {str(ticker).upper() for ticker in candidate.get("tickers", []) or []}
    output = []
    for company in watchlist:
        if company.ticker.upper() in own_tickers:
            continue
        matched_alias = ""
        for alias in company.aliases:
            alias_text = str(alias).lower().strip()
            if not alias_text or len(alias_text) < 3:
                continue
            if len(alias_text) <= 5:
                if re.search(rf"(?<![a-z0-9]){re.escape(alias_text)}(?![a-z0-9])", lower):
                    matched_alias = str(alias)
                    break
            elif alias_text in lower:
                matched_alias = str(alias)
                break
        if matched_alias:
            output.append(
                {
                    "ticker": company.ticker,
                    "name": company.name,
                    "matched_alias": matched_alias,
                    "themes": list(company.themes),
                    "source_context": "technology_intel",
                    "reason_zh": _mention_reason(company, matched_alias),
                }
            )
    return output[:16]


def _signal_strength(themes: list[dict[str, object]], mentioned: list[dict[str, object]], read_depth: str) -> int:
    score = 0
    score += min(3, len(themes))
    if mentioned:
        score += 1
    if len(mentioned) >= 3:
        score += 1
    if read_depth == "full_article_html":
        score += 1
    return min(score, 5)


def _summary_zh(themes: list[dict[str, object]], mentioned: list[dict[str, object]], strength: int) -> str:
    if not themes:
        return f"技术来源命中，但暂未识别明确技术主题；强度={strength}/5。"
    theme_names = ", ".join(str(item.get("theme")) for item in themes[:3])
    tickers = ", ".join(str(item.get("ticker")) for item in mentioned[:8]) or "暂无明确二阶公司"
    return f"识别到技术路线图/研究信号：{theme_names}；强度={strength}/5；二阶公司={tickers}。"


def _watch_points(themes: list[dict[str, object]]) -> list[str]:
    theme_names = {str(item.get("theme")) for item in themes}
    points = [
        "检查该技术路线是否由龙头公司、标准组织或客户生态推动，而不是单一供应商自我宣传。",
        "等待订单、量产、财报 capex/收入、价格/成交量或多来源重复确认。",
    ]
    if "800v_hvdc_power" in theme_names:
        points.insert(0, "800V/HVDC 线索优先映射到功率半导体、电源模块、配电、UPS、散热和数据中心电气系统。")
    if "optical_interconnect" in theme_names:
        points.insert(0, "光互连线索优先映射到 CPO、硅光、DSP、激光器、光模块和网络设备。")
    if "ai_factory_rackscale" in theme_names:
        points.insert(0, "rack-scale AI factory 线索优先映射到服务器、网络、电源、散热、内存和先进封装。")
    return points


def _read_through_zh(mentioned: list[dict[str, object]]) -> str:
    if not mentioned:
        return "技术资料中暂未识别到 watchlist 内的明确二阶公司。"
    tickers = ", ".join(str(item.get("ticker")) for item in mentioned[:8])
    return f"技术资料点名或暗示 {tickers}；系统会继续拉取这些公司的价格、财务事实和后续新闻，判断是否进入动态观察池。"


def _mention_reason(company: Company, alias: str) -> str:
    themes = ", ".join(company.themes[:3])
    return f"技术资料提到 {company.name} / {company.ticker} 相关词 {alias}；主题={themes or 'n/a'}，需要检查是否形成供应链 read-through。"


def _article_text(article: dict[str, object], seed_text: str, fetcher: object | None) -> dict[str, str]:
    link = str(article.get("link") or "")
    if not link.startswith(("http://", "https://")):
        return {"text": seed_text, "read_depth": "headline_summary"}
    fetch = fetcher or _fetch_text
    try:
        raw = str(fetch(link))
    except Exception:
        return {"text": seed_text, "read_depth": "headline_summary_fetch_failed"}
    body = strip_html(raw)
    if len(body) < 120:
        return {"text": seed_text, "read_depth": "headline_summary_short_body"}
    return {"text": f"{seed_text}\n{body[:MAX_ARTICLE_TEXT_CHARS]}", "read_depth": "full_article_html"}


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def _candidate_text(candidate: dict[str, object]) -> str:
    article = candidate.get("article") if isinstance(candidate.get("article"), dict) else {}
    values = [
        candidate.get("company_name"),
        article.get("title"),
        article.get("summary"),
        candidate.get("reason"),
        *(candidate.get("matched_terms") or []),
    ]
    return "\n".join(str(value) for value in values if value)


def _contains_term(text: str, term: str) -> bool:
    term = term.lower()
    if re.fullmatch(r"[a-z0-9 +./-]+", term):
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text
