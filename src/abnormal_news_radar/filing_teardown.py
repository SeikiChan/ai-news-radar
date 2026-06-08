"""Deep teardown of an actual SEC 10-Q / 10-K filing.

Once the authoritative filing document is located (financials.fetch_recent_filings),
this module downloads it, strips it to text, and extracts the narrative an analyst
cares about that structured XBRL does not give:

* named companies the filer acquired / invested in / partners with / lists as a
  customer or supplier — resolved to their US ticker via the SEC name index;
* large orders / contracts / purchase commitments (with dollar amounts);
* customer-concentration disclosures ("one customer represented X% of revenue").

Capital-allocation amounts ("where the money went": R&D, capex, buybacks,
dividends, M&A) come from structured companyfacts (financials.py), not from this
text parse, so those numbers stay exact. Entity extraction here is rule-based
and best-effort: it only emits companies that resolve to a real ticker, and it
is gated to sentences carrying an investment/customer/order context to keep
precision high. Failures degrade to a status flag.
"""

from __future__ import annotations

import re

from .feeds import strip_html
from .model import Company
from .net import fetch_text

MAX_BYTES = 8_000_000
MAX_CHARS = 320_000
MAX_NAMED = 16
MAX_ORDERS = 10
MIN_ORDER_MUSD = 50.0

_RELATIONS = (
    ("acquisition", ("acquisition", "acquired", "acquire ", "acquiring", "business combination")),
    ("investment", ("investment in", "invested in", "equity interest", "minority interest", "strategic investment", "ownership interest")),
    ("partnership", ("partnership", "collaborat", "joint venture", "strategic alliance")),
    ("customer", ("customer", "end customer", "largest customer")),
    ("supplier", ("supplier", "foundry", "contract manufacturer", "manufactured by", "fabricat")),
    ("order", ("purchase commitment", "purchase order", "supply agreement", "backlog", "committed to purchase")),
)
# Purpose classification for dollar amounts ("where the money goes"), in Chinese.
# Ordered most-specific first; the first matching rule wins.
_PURPOSE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("收购", ("acquisition", "acquired", "acquire ", "business combination", "purchase consideration")),
    ("股票回购", ("repurchase", "buyback", "repurchased")),
    ("现金分红", ("dividend",)),
    ("资本开支", ("property and equipment", "capital expenditure", "construction in progress", "data center build")),
    ("采购承诺 / 供应", ("purchase commitment", "purchase obligation", "supply agreement", "committed to purchase", "inventory purchase", "capacity reservation", "manufacturing capacity")),
    ("债务 / 票据", ("senior notes", "notes due", "borrowings", "credit facility", "term loan", "commercial paper")),
    ("合同 / 未确认收入", ("remaining performance obligation", "deferred revenue", "backlog", "contract with customer")),
    ("投资 / 证券组合", ("available-for-sale", "marketable securities", "equity securities", "debt securities", "investment in", "invested in", "fair value of", "cash equivalents and marketable")),
    ("租赁", ("operating lease", "finance lease", "lease obligation")),
    ("税务", ("income tax", "deferred tax", "unrecognized tax")),
)
_PORTFOLIO_LABEL = "投资 / 证券组合"
#: Display priority: actionable capital deployment first, treasury portfolio last.
_PURPOSE_PRIORITY: dict[str, int] = {
    "收购": 0,
    "采购承诺 / 供应": 1,
    "资本开支": 2,
    "股票回购": 3,
    "现金分红": 4,
    "合同 / 未确认收入": 5,
    "债务 / 票据": 6,
    "租赁": 7,
    "税务": 8,
    _PORTFOLIO_LABEL: 9,
}

# Capitalized multi-token proper-noun phrases (company-name candidates).
_PHRASE_RE = re.compile(r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+(?:[A-Z][A-Za-z0-9&.\-]*|and|of|for))*[A-Za-z0-9])")
_AMOUNT_RE = re.compile(r"\$\s?([0-9][0-9.,]*)\s?(billion|bn|million|m)?\b", re.IGNORECASE)
# Strict customer-concentration pattern: "<n>% of [total/net] revenue|sales".
_CONCENTRATION_RE = re.compile(
    r"([0-9]{1,2}(?:\.[0-9]+)?)\s?%\s+of\s+(?:our\s+|the\s+|its\s+)?(?:total\s+|net\s+|consolidated\s+)*"
    r"(?:revenue|revenues|net revenue|sales|accounts receivable)",
    re.IGNORECASE,
)
_CONCENTRATION_VERBS = ("accounted for", "represented", "comprised", "made up", "accounting for")
# Strip ONLY true legal-entity suffixes. Distinctive name words like
# "Semiconductor"/"Technology" must be kept — stripping them collapsed
# "Taiwan Semiconductor" to "taiwan", which then false-matched the region.
_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|plc|llc|lp|holdings?|group|the)\b",
    re.IGNORECASE,
)
_TABLE_MARKERS = ("geographic", "(in millions)", "months ended", "year ended", "table of contents", "headquarters location")
_GENERIC_NAMES = {
    "the company", "common stock", "united states", "u s", "north america", "europe", "asia", "china",
    "form", "note", "item", "annual report", "quarterly report", "board", "committee", "exchange commission",
    "generally accepted", "fair value", "cash flow", "balance sheet", "income statement", "risk factors",
}


def build_name_index(cik_map: dict[str, dict[str, object]], watchlist: list[Company] | None = None) -> dict[str, dict[str, str]]:
    """Normalized-company-name -> {ticker, name}, for resolving filing mentions."""
    index: dict[str, dict[str, str]] = {}
    for ticker, info in cik_map.items():
        name = str(info.get("name") or "")
        key = _normalize(name)
        if len(key) >= 4 and key not in _GENERIC_NAMES:
            index.setdefault(key, {"ticker": str(ticker), "name": name})
    for company in watchlist or []:
        index[_normalize(company.name)] = {"ticker": company.ticker, "name": company.name}
        for alias in company.aliases:
            key = _normalize(alias)
            if len(key) >= 4 and key not in _GENERIC_NAMES:
                index.setdefault(key, {"ticker": company.ticker, "name": company.name})
    return index


def teardown_filing(
    doc_url: str,
    name_index: dict[str, dict[str, str]],
    fetcher: object | None = None,
    self_ticker: str = "",
) -> dict[str, object]:
    fetch = fetcher or (lambda url: fetch_text(url, accept="text/html", timeout=25, max_bytes=MAX_BYTES))
    try:
        html = fetch(doc_url)  # type: ignore[operator]
    except Exception as exc:  # noqa: BLE001 - degrade cleanly.
        return {"status": "unavailable", "source_url": doc_url, "reason": str(exc)[:160]}
    text = strip_html(html)[:MAX_CHARS]
    if not text.strip():
        return {"status": "empty", "source_url": doc_url}

    sentences = _sentences(text)
    named = _named_companies(sentences, name_index, self_ticker)
    money_flows = _money_flows(sentences, name_index, self_ticker)
    concentration = _customer_concentration(sentences)
    return {
        "status": "ok",
        "source_url": doc_url,
        "char_count": len(text),
        "named_companies": named,
        "money_flows": money_flows,
        "customer_concentration": concentration,
        "summary_zh": _summary_zh(named, money_flows, concentration),
    }


def _resolve_companies(sentence: str, name_index: dict[str, dict[str, str]], exclude: set[str]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _PHRASE_RE.finditer(sentence):
        key = _normalize(match.group(1))
        if len(key) < 4 or key in _GENERIC_NAMES:
            continue
        hit = name_index.get(key)
        if not hit or hit["ticker"] in exclude or hit["ticker"] in seen:
            continue
        seen.add(hit["ticker"])
        hits.append(hit)
    return hits


def _named_companies(sentences: list[str], name_index: dict[str, dict[str, str]], self_ticker: str = "") -> list[dict[str, object]]:
    exclude: set[str] = {self_ticker.upper()} if self_ticker else set()
    out: list[dict[str, object]] = []
    for sentence in sentences:
        low = sentence.lower()
        if any(marker in low for marker in _TABLE_MARKERS):
            continue
        relation = _relation(low)
        if not relation:
            continue
        for hit in _resolve_companies(sentence, name_index, exclude):
            exclude.add(hit["ticker"])
            out.append({"name": hit["name"], "ticker": hit["ticker"], "relation": relation, "context": _clip(sentence)})
            if len(out) >= MAX_NAMED:
                return out
    return out


def _money_flows(sentences: list[str], name_index: dict[str, dict[str, str]], self_ticker: str = "") -> list[dict[str, object]]:
    """Classify each large dollar amount by *purpose* (Chinese), and attach the
    target company when one is named — so each line reads "金额 · 用途 → 公司"."""
    exclude: set[str] = {self_ticker.upper()} if self_ticker else set()
    collected: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    for sentence in sentences:
        purpose = _purpose_zh(sentence.lower())
        if not purpose:
            continue
        match = _AMOUNT_RE.search(sentence)
        if not match:
            continue
        musd = _to_musd(match.group(1), match.group(2))
        if musd is None or musd < MIN_ORDER_MUSD:
            continue
        dedupe = (purpose, int(musd))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        target = _resolve_companies(sentence, name_index, exclude)
        company = target[0] if target else None
        collected.append({
            "amount_musd": musd,
            "purpose_zh": purpose,
            "target_ticker": company["ticker"] if company else "",
            "target_name": company["name"] if company else "",
            "context": _clip(sentence),
        })
        if len(collected) >= 60:
            break

    # The treasury/securities portfolio repeats many times and is the least
    # "spending decision" — keep only its largest couple of lines.
    portfolio = sorted(
        (f for f in collected if f["purpose_zh"] == _PORTFOLIO_LABEL),
        key=lambda f: -float(f["amount_musd"]),
    )[:2]
    others = [f for f in collected if f["purpose_zh"] != _PORTFOLIO_LABEL]
    ranked = others + portfolio
    # Surface the actionable, company-targeted spending first.
    ranked.sort(key=lambda f: (
        0 if f["target_ticker"] else 1,
        _PURPOSE_PRIORITY.get(str(f["purpose_zh"]), 9),
        -float(f["amount_musd"]),
    ))
    return ranked[:MAX_ORDERS]


def _purpose_zh(low: str) -> str:
    for label, keywords in _PURPOSE_RULES:
        if any(kw in low for kw in keywords):
            return label
    return ""


def _customer_concentration(sentences: list[str]) -> list[dict[str, object]]:
    """Only genuine "<customer> accounted for N% of revenue" disclosures.

    Deliberately strict: a bare "%" near the word "customer" is not enough
    (that produced misleading numbers), so it must match the canonical
    "N% of [total/net] revenue|sales" pattern with a disclosure verb.
    """
    out: list[dict[str, object]] = []
    seen: set[float] = set()
    for sentence in sentences:
        low = sentence.lower()
        if "customer" not in low:
            continue
        # Skip statement/table fragments that merely happen to contain a % and
        # the word "customer" (geographic revenue tables, etc.).
        if any(marker in low for marker in ("geographic", "(in millions)", "months ended", "year ended", "table of contents")):
            continue
        if not any(verb in low for verb in _CONCENTRATION_VERBS):
            continue
        match = _CONCENTRATION_RE.search(sentence)
        if not match:
            continue
        pct = float(match.group(1))
        if pct in seen:
            continue
        seen.add(pct)
        # Keep the verbatim disclosure sentence — it carries the real, often
        # multi-customer breakdown ("30%, 18% and 16%"); a single synthesized
        # number would misrepresent it.
        out.append({"pct": pct, "context": _clip(sentence)})
        if len(out) >= 4:
            break
    return out


def _summary_zh(named: list, money_flows: list, concentration: list) -> str:
    parts = []
    if named:
        tickers = "、".join(f"{n['ticker']}" for n in named[:6])
        parts.append(f"正文识别到 {len(named)} 家可解析公司（{tickers}…）")
    else:
        parts.append("正文未解析到明确的关联公司")
    if money_flows:
        parts.append(f"{len(money_flows)} 条大额资金去向（按用途分类）")
    if concentration:
        parts.append(f"{len(concentration)} 条客户集中度披露")
    return "；".join(parts) + "。来源：SEC 10-Q/10-K 正文（规则抽取，需人工复核）。"


def _relation(low: str) -> str:
    for label, keywords in _RELATIONS:
        if any(kw in low for kw in keywords):
            return label
    return ""


def _sentences(text: str) -> list[str]:
    collapsed = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+", collapsed) if 12 <= len(s.strip()) <= 600]


def _clip(sentence: str, limit: int = 220) -> str:
    sentence = sentence.strip()
    return sentence if len(sentence) <= limit else sentence[:limit].rsplit(" ", 1)[0] + "…"


def _normalize(name: str) -> str:
    lowered = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    without_suffix = _SUFFIX_RE.sub(" ", lowered)
    return re.sub(r"\s+", " ", without_suffix).strip()


def _to_musd(number: str, unit: str | None) -> float | None:
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit in {"billion", "bn"}:
        return round(value * 1000, 2)
    if unit in {"million", "m"}:
        return round(value, 2)
    # Bare "$X" in a 10-Q is usually already in millions (statements are in $M).
    return round(value, 2)
