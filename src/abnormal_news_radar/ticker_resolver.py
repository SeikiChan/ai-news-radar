from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

USER_AGENT = "AI-News-Radar/0.1 research-tool contact=local@example.com"
FETCH_TIMEOUT_SECONDS = 8
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_CORPORATE_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "plc",
    "sa",
    "nv",
    "ag",
    "holdings",
    "holding",
    "group",
}


def enrich_candidates_with_ticker_resolution(
    candidates: list[dict[str, object]],
    fetcher: object | None = None,
) -> list[dict[str, object]]:
    fetch = fetcher or _fetch_text
    try:
        companies = _load_sec_companies(fetch)
    except Exception as exc:  # noqa: BLE001 - resolver failure must not block the scan.
        return [_with_resolution_error(candidate, str(exc)) for candidate in candidates]

    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        tickers = [str(ticker).strip().upper() for ticker in row.get("tickers", []) or [] if str(ticker).strip()]
        if tickers:
            row["ticker_resolution"] = {
                "status": "already_present",
                "tickers": tickers,
                "resolver": "watchlist_or_source",
            }
            enriched.append(row)
            continue

        match = _resolve_company_name(str(row.get("company_name") or ""), companies)
        if match is None:
            row["ticker_resolution"] = {
                "status": "unresolved",
                "resolver": "sec_company_tickers_exact_name",
                "reason": "no high-confidence SEC company-name match",
            }
            enriched.append(row)
            continue

        row["tickers"] = [match["ticker"]]
        row["ticker_resolution"] = {
            "status": "resolved",
            "resolver": "sec_company_tickers_exact_name",
            "ticker": match["ticker"],
            "company_name": match["name"],
            "confidence": match["confidence"],
            "source_url": SEC_TICKERS_URL,
        }
        enriched.append(row)
    return enriched


def _resolve_company_name(company_name: str, companies: list[dict[str, object]]) -> dict[str, object] | None:
    needle = _normalize_company_name(company_name)
    if len(needle) < 3:
        return None

    exact_matches = [company for company in companies if company["normalized_name"] == needle]
    if len(exact_matches) == 1:
        return _match_payload(exact_matches[0], "high")

    prefix_matches = [
        company
        for company in companies
        if len(needle) >= 6
        and (
            str(company["normalized_name"]).startswith(f"{needle} ")
            or needle.startswith(f"{company['normalized_name']} ")
        )
    ]
    if len(prefix_matches) == 1:
        return _match_payload(prefix_matches[0], "medium")

    contained_matches = [
        company
        for company in companies
        if len(needle) >= 8 and f" {needle} " in f" {company['normalized_name']} "
    ]
    if len(contained_matches) == 1:
        return _match_payload(contained_matches[0], "medium")
    return None


def _match_payload(company: dict[str, object], confidence: str) -> dict[str, object]:
    return {
        "ticker": str(company["ticker"]),
        "name": str(company["name"]),
        "confidence": confidence,
    }


def _load_sec_companies(fetch: object) -> list[dict[str, object]]:
    payload = json.loads(fetch(SEC_TICKERS_URL))
    if isinstance(payload, dict):
        rows = payload.values()
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []

    companies = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        name = str(row.get("title") or "").strip()
        normalized_name = _normalize_company_name(name)
        if ticker and normalized_name:
            companies.append({"ticker": ticker, "name": name, "normalized_name": normalized_name})
    return companies


def _normalize_company_name(value: str) -> str:
    text = value.lower()
    text = re.sub(r"\b(class|common|ordinary|shares?|stock|adr|ads)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = [word for word in text.split() if word not in _CORPORATE_SUFFIXES]
    return " ".join(words).strip()


def _with_resolution_error(candidate: dict[str, object], reason: str) -> dict[str, object]:
    row = dict(candidate)
    if row.get("ticker_resolution"):
        return row
    row["ticker_resolution"] = {
        "status": "unavailable",
        "resolver": "sec_company_tickers_exact_name",
        "reason": reason,
    }
    return row


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")
