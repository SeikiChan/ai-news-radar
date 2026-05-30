from __future__ import annotations

import re
from urllib.request import Request, urlopen

from .feeds import strip_html
from .model import Company

FETCH_TIMEOUT_SECONDS = 8
USER_AGENT = "AI-News-Radar/0.1 earnings-release-reader"
MAX_RELEASE_TEXT_CHARS = 25000


EARNINGS_TERMS = (
    "reports financial results",
    "reported financial results",
    "earnings",
    "quarter results",
    "fiscal results",
    "guidance",
)
METRIC_PATTERNS = {
    "revenue": re.compile(r"(?:revenue|total revenue)\D{0,40}\$?([0-9]+(?:\.[0-9]+)?)\s*(billion|million)", re.IGNORECASE),
    "product_revenue": re.compile(r"product revenue\D{0,40}\$?([0-9]+(?:\.[0-9]+)?)\s*(billion|million)", re.IGNORECASE),
    "eps": re.compile(r"(?:eps|earnings per share)\D{0,40}\$?(-?[0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "rpo": re.compile(r"(?:remaining performance obligations|rpo)\D{0,40}\$?([0-9]+(?:\.[0-9]+)?)\s*(billion|million)", re.IGNORECASE),
    "net_revenue_retention": re.compile(r"(?:net revenue retention|nrr)\D{0,30}([0-9]+(?:\.[0-9]+)?)%", re.IGNORECASE),
    "capex": re.compile(r"(?:capital expenditures|capex|capital expenditure)\D{0,50}\$?([0-9]+(?:\.[0-9]+)?)\s*(billion|million)", re.IGNORECASE),
    "research_development": re.compile(r"(?:research and development|r&d)\D{0,50}\$?([0-9]+(?:\.[0-9]+)?)\s*(billion|million)", re.IGNORECASE),
    "free_cash_flow": re.compile(r"(?:free cash flow)\D{0,50}\$?(-?[0-9]+(?:\.[0-9]+)?)\s*(billion|million)", re.IGNORECASE),
}
SPEND_PATTERNS = {
    "ai_infrastructure": r"\b(ai infrastructure|gpu|accelerated computing|training cluster|inference|ai data center)\b",
    "data_center": r"\b(data center|datacenter|cloud infrastructure|capacity expansion)\b",
    "research_development": r"\b(research and development|r&d|engineering investment|product development)\b",
    "sales_marketing": r"\b(sales and marketing|go-to-market|customer acquisition)\b",
    "capex": r"\b(capex|capital expenditure|capital expenditures|capital investment)\b",
    "acquisition": r"\b(acquisition|acquire|merger|strategic investment|minority investment)\b",
    "share_repurchase": r"\b(share repurchase|stock repurchase|buyback)\b",
}


def enrich_candidates_with_earnings_analysis(
    candidates: list[dict[str, object]],
    watchlist: list[Company] | None = None,
    fetcher: object | None = None,
) -> list[dict[str, object]]:
    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        row["earnings_analysis"] = analyze_earnings_candidate(row, watchlist=watchlist or [], fetcher=fetcher)
        enriched.append(row)
    return enriched


def analyze_earnings_candidate(
    candidate: dict[str, object],
    watchlist: list[Company] | None = None,
    fetcher: object | None = None,
) -> dict[str, object]:
    article = candidate.get("article") if isinstance(candidate.get("article"), dict) else {}
    seed_text = _candidate_text(candidate)
    release = _release_text(article, seed_text, fetcher)
    text = release["text"]
    lower = text.lower()
    if not any(term in lower for term in EARNINGS_TERMS):
        return {
            "status": "not_earnings",
            "summary_zh": "该候选不是财报事件。",
            "metrics": [],
            "watch_points_zh": [],
        }

    metrics = _extract_metrics(text)
    guidance_terms = _guidance_terms(lower)
    spend = _spend_allocation(text)
    mentioned = _mentioned_companies(text, watchlist or [], candidate)
    status = "earnings_release_detected" if metrics or guidance_terms else "earnings_headline_only"
    return {
        "status": status,
        "summary_zh": _summary_zh(metrics, guidance_terms),
        "metrics": metrics,
        "spend_allocation": spend,
        "mentioned_companies": mentioned,
        "read_through_zh": _read_through_zh(mentioned),
        "watch_points_zh": _watch_points(metrics, guidance_terms),
        "source_title": article.get("title") or "",
        "source_link": article.get("link") or "",
        "read_depth": release["read_depth"],
        "method": "full_release_regex_first_pass_no_consensus",
        "limitations_zh": "已尽量读取可访问的财报原文 HTML；没有付费 consensus/FactSet 时，beat/miss 只能在公开预期可得时确认。PDF、登录墙或脚本渲染页面会被标为原文读取受限。",
    }


def _extract_metrics(text: str) -> list[dict[str, object]]:
    metrics = []
    for key, pattern in METRIC_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        if key in {"eps", "net_revenue_retention"}:
            value = float(match.group(1))
            unit = "usd" if key == "eps" else "pct"
        else:
            value = float(match.group(1))
            unit_text = match.group(2).lower()
            unit = "musd"
            if unit_text == "billion":
                value *= 1000
        metrics.append({"metric": key, "value": round(value, 3), "unit": unit})
    return metrics


def _spend_allocation(text: str) -> list[dict[str, object]]:
    lower = text.lower()
    output = []
    for category, pattern in SPEND_PATTERNS.items():
        match = re.search(pattern, lower, re.IGNORECASE)
        if not match:
            continue
        output.append(
            {
                "category": category,
                "evidence": _snippet(text, match.start(), match.end()),
                "interpretation_zh": _spend_interpretation(category),
            }
        )
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
                    "reason_zh": _mention_reason(company),
                }
            )
    return output[:10]


def _guidance_terms(lower: str) -> list[str]:
    output = []
    for term in ("raises guidance", "raised guidance", "increases outlook", "increased outlook", "guidance", "outlook"):
        if term in lower and term not in output:
            output.append(term)
    return output[:5]


def _summary_zh(metrics: list[dict[str, object]], guidance_terms: list[str]) -> str:
    if metrics:
        names = ", ".join(str(metric.get("metric")) for metric in metrics[:4])
        return f"检测到财报 release，并抽取到核心指标：{names}。"
    if guidance_terms:
        return "检测到财报/指引相关语言，但 RSS 摘要中缺少足够数字，需打开原文或 8-K。"
    return "检测到财报标题，但摘要信息不足，等待原文/8-K/电话会材料。"


def _watch_points(metrics: list[dict[str, object]], guidance_terms: list[str]) -> list[str]:
    points = ["对比 consensus EPS/revenue，确认 beat/miss 幅度。", "检查盘后/次日价格与成交量，判断市场是否接受指引。"]
    metric_names = {str(metric.get("metric")) for metric in metrics}
    if "product_revenue" in metric_names:
        points.insert(0, "SaaS/AI 软件公司优先看 product revenue，而不是只看总收入。")
    if "rpo" in metric_names:
        points.insert(0, "RPO/订单能见度是未来增长质量的核心指标。")
    if guidance_terms:
        points.insert(0, "指引变化比历史季度 beat 更重要，优先拆 forward outlook。")
    return points


def _release_text(article: dict[str, object], seed_text: str, fetcher: object | None) -> dict[str, str]:
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
    return {"text": f"{seed_text}\n{body[:MAX_RELEASE_TEXT_CHARS]}", "read_depth": "full_release_html"}


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
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


def _snippet(text: str, start: int, end: int, radius: int = 120) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return " ".join(text[left:right].split())


def _spend_interpretation(category: str) -> str:
    labels = {
        "ai_infrastructure": "资金/资源投向 AI 基础设施，优先寻找 GPU、网络、光模块、电力和数据中心 read-through。",
        "data_center": "数据中心容量相关支出，可能利好电力、散热、服务器、网络和地产容量链。",
        "research_development": "R&D 投入上升通常代表产品周期或 AI 功能投入，需看是否压利润率。",
        "sales_marketing": "销售投入增加可能是增长抢跑，也可能压 FCF，需看回款和 NRR。",
        "capex": "资本开支变化会影响自由现金流，也可能形成上游供应链订单。",
        "acquisition": "并购/战略投资可能指向新产业布局，需要跟踪被投公司和可比公司。",
        "share_repurchase": "回购是资本配置选择，但不应替代增长质量判断。",
    }
    return labels.get(category, "需要人工复核该资金用途。")


def _mention_reason(company: Company) -> str:
    themes = ", ".join(company.themes[:3])
    return f"财报原文提到 {company.name} / {company.ticker} 相关词；主题={themes or 'n/a'}，需要检查是否形成二阶 read-through。"


def _read_through_zh(mentioned: list[dict[str, object]]) -> str:
    if not mentioned:
        return "财报中暂未识别到 watchlist 内的明确二阶公司。"
    tickers = ", ".join(str(item.get("ticker")) for item in mentioned[:6])
    return f"识别到二阶 read-through 公司：{tickers}。系统会继续拉取这些公司的 SEC 财务事实和价格确认，判断是否值得进入动态观察池。"
