from __future__ import annotations

import json
import math
import time
from urllib.request import Request, urlopen

USER_AGENT = "AI-News-Radar/0.1 public-options-chain"
FETCH_TIMEOUT_SECONDS = 8
YAHOO_OPTIONS_URL = "https://query2.finance.yahoo.com/v7/finance/options/{ticker}"

MIN_VOLUME = 1000
MIN_PREMIUM_USD = 250_000
MIN_VOLUME_OI_RATIO = 1.0
MAX_DTE = 45


def enrich_candidates_with_options_chain_anomalies(
    candidates: list[dict[str, object]],
    fetcher: object | None = None,
    max_tickers: int = 8,
) -> list[dict[str, object]]:
    fetch = fetcher or _fetch_text
    tickers = _candidate_tickers(candidates)[:max_tickers]
    snapshots: dict[str, dict[str, object]] = {}
    for ticker in tickers:
        snapshots[ticker] = assess_public_options_chain(ticker, fetch)

    enriched = []
    for candidate in candidates:
        row = dict(candidate)
        ticker = _primary_ticker(row)
        chain = snapshots.get(ticker) if ticker else _no_chain("no_ticker", "candidate has no confirmed ticker")
        row["options_flow"] = _merge_options_flow(row.get("options_flow"), chain)
        enriched.append(row)
    return enriched


def assess_public_options_chain(ticker: str, fetcher: object | None = None) -> dict[str, object]:
    symbol = ticker.strip().upper()
    if not symbol:
        return _no_chain("no_ticker", "missing ticker")
    fetch = fetcher or _fetch_text
    source_url = YAHOO_OPTIONS_URL.format(ticker=symbol)
    try:
        payload = json.loads(fetch(source_url))
        result = (((payload.get("optionChain") or {}).get("result")) or [])[0]
    except Exception as exc:  # noqa: BLE001 - options chain should not break the scan.
        return _no_chain("unavailable", str(exc), symbol, source_url)

    quote = result.get("quote") if isinstance(result, dict) else {}
    price = _to_float((quote or {}).get("regularMarketPrice"))
    contracts = _contracts_from_result(result, price)
    anomalies = [contract for contract in contracts if _is_anomalous(contract)]
    anomalies.sort(key=lambda row: (int(row["score"]), float(row["premium_usd"])), reverse=True)
    if not anomalies:
        return {
            "status": "no_flow_evidence",
            "direction": "none",
            "score": 0,
            "summary_zh": f"{symbol} 公开期权链快照未发现达到阈值的异常成交。",
            "source_tier": "public_options_chain_snapshot",
            "source_policy_zh": "该层使用公开期权链快照，不是逐笔订单流；只能作为市场博弈线索，不能单独构成买入依据。",
            "evidence_zh": [],
            "rules_zh": _rules_zh(),
            "source_url": source_url,
        }

    calls = [row for row in anomalies if row["type"] == "call"]
    puts = [row for row in anomalies if row["type"] == "put"]
    call_premium = sum(float(row["premium_usd"]) for row in calls)
    put_premium = sum(float(row["premium_usd"]) for row in puts)
    if call_premium and put_premium and min(call_premium, put_premium) / max(call_premium, put_premium) >= 0.45:
        status = "mixed_flow"
        direction = "mixed"
    elif call_premium > put_premium:
        status = "supportive_flow"
        direction = "bullish"
    else:
        status = "bearish_flow"
        direction = "bearish"

    score = min(5, max(int(row["score"]) for row in anomalies))
    return {
        "status": status,
        "direction": direction,
        "score": score,
        "summary_zh": _summary_zh(symbol, anomalies, call_premium, put_premium),
        "source_tier": "public_options_chain_snapshot",
        "source_policy_zh": "该层来自公开期权链快照，参考开源 options-chain/flow 项目的思路；它不是 FlowAlgo/Unusual Whales 的逐笔 tape。",
        "evidence_zh": [_contract_evidence_zh(row) for row in anomalies[:5]],
        "rules_zh": _rules_zh(),
        "contracts": anomalies[:10],
        "source_url": source_url,
    }


def _contracts_from_result(result: dict[str, object], underlying_price: float | None) -> list[dict[str, object]]:
    options = result.get("options") if isinstance(result, dict) else []
    if not isinstance(options, list) or not options:
        return []
    rows = []
    now = int(time.time())
    for option_group in options[:1]:
        if not isinstance(option_group, dict):
            continue
        expiration = _to_int(option_group.get("expirationDate"))
        dte = max(0, round((expiration - now) / 86400)) if expiration else None
        for option_type in ("calls", "puts"):
            contracts = option_group.get(option_type)
            if not isinstance(contracts, list):
                continue
            for contract in contracts:
                if not isinstance(contract, dict):
                    continue
                row = _contract_row(contract, "call" if option_type == "calls" else "put", dte, underlying_price)
                if row is not None:
                    rows.append(row)
    return rows


def _contract_row(
    contract: dict[str, object],
    option_type: str,
    dte: int | None,
    underlying_price: float | None,
) -> dict[str, object] | None:
    volume = _to_float(contract.get("volume"))
    open_interest = _to_float(contract.get("openInterest"))
    strike = _to_float(contract.get("strike"))
    if volume is None or volume <= 0 or strike is None:
        return None
    last = _to_float(contract.get("lastPrice"))
    bid = _to_float(contract.get("bid"))
    ask = _to_float(contract.get("ask"))
    price = _contract_price(last, bid, ask)
    if price is None or price <= 0:
        return None
    premium = price * volume * 100
    oi = open_interest or 0.0
    volume_oi_ratio = volume / oi if oi > 0 else math.inf
    score = 0
    if volume >= MIN_VOLUME:
        score += 1
    if premium >= MIN_PREMIUM_USD:
        score += 1
    if volume_oi_ratio >= MIN_VOLUME_OI_RATIO:
        score += 1
    if dte is not None and dte <= MAX_DTE:
        score += 1
    if _is_near_money(option_type, strike, underlying_price):
        score += 1
    return {
        "contract_symbol": str(contract.get("contractSymbol") or ""),
        "type": option_type,
        "strike": strike,
        "dte": dte,
        "last_price": last,
        "bid": bid,
        "ask": ask,
        "used_price": round(price, 4),
        "volume": int(volume),
        "open_interest": int(oi),
        "volume_oi_ratio": round(volume_oi_ratio, 3) if math.isfinite(volume_oi_ratio) else "inf",
        "premium_usd": round(premium, 2),
        "score": score,
    }


def _is_anomalous(contract: dict[str, object]) -> bool:
    return (
        int(contract["score"]) >= 3
        and int(contract["volume"]) >= MIN_VOLUME
        and float(contract["premium_usd"]) >= MIN_PREMIUM_USD
    )


def _is_near_money(option_type: str, strike: float, underlying_price: float | None) -> bool:
    if underlying_price is None or underlying_price <= 0:
        return False
    distance = abs(strike - underlying_price) / underlying_price
    if option_type == "call":
        return strike >= underlying_price * 0.85 and distance <= 0.25
    return strike <= underlying_price * 1.15 and distance <= 0.25


def _contract_price(last: float | None, bid: float | None, ask: float | None) -> float | None:
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2
    return last


def _merge_options_flow(existing: object, chain: dict[str, object]) -> dict[str, object]:
    current = existing if isinstance(existing, dict) else {}
    if not current or current.get("status") in {"", None, "no_flow_evidence"}:
        return chain
    chain_status = str(chain.get("status") or "")
    current_status = str(current.get("status") or "")
    if chain_status == "no_flow_evidence":
        merged = dict(current)
        merged["public_chain_check"] = chain
        return merged
    if current_status == chain_status:
        merged = dict(current)
        merged["score"] = max(int(current.get("score") or 0), int(chain.get("score") or 0))
        merged["evidence_zh"] = [*(current.get("evidence_zh") or []), *(chain.get("evidence_zh") or [])][:8]
        merged["public_chain_check"] = chain
        return merged
    if {current_status, chain_status} & {"bearish_flow", "conflicting_flow", "mixed_flow"}:
        merged = dict(current)
        merged["status"] = "conflicting_flow"
        merged["direction"] = "conflicting"
        merged["summary_zh"] = f"{current.get('summary_zh') or ''} 公开期权链出现不同方向信号：{chain.get('summary_zh') or ''}".strip()
        merged["public_chain_check"] = chain
        return merged
    if chain_status == "supportive_flow" and int(chain.get("score") or 0) > int(current.get("score") or 0):
        return chain
    merged = dict(current)
    merged["public_chain_check"] = chain
    return merged


def _summary_zh(symbol: str, anomalies: list[dict[str, object]], call_premium: float, put_premium: float) -> str:
    top = anomalies[0]
    return (
        f"{symbol} 公开期权链发现 {len(anomalies)} 条异常合约；"
        f"call premium≈${call_premium/1_000_000:.2f}m，put premium≈${put_premium/1_000_000:.2f}m。"
        f"最大线索：{top['type']} strike={top['strike']}，volume={top['volume']}，premium≈${float(top['premium_usd'])/1_000_000:.2f}m。"
    )


def _contract_evidence_zh(contract: dict[str, object]) -> str:
    ratio = contract.get("volume_oi_ratio")
    return (
        f"{contract['type']} {contract['contract_symbol']} strike={contract['strike']} "
        f"dte={contract.get('dte') if contract.get('dte') is not None else 'n/a'} "
        f"vol={contract['volume']} OI={contract['open_interest']} vol/OI={ratio} "
        f"premium≈${float(contract['premium_usd'])/1_000_000:.2f}m"
    )


def _rules_zh() -> list[str]:
    return [
        f"成交量 >= {MIN_VOLUME}",
        f"估算权利金成交额 >= ${MIN_PREMIUM_USD:,}",
        f"volume/open interest >= {MIN_VOLUME_OI_RATIO} 或 OI 近似为 0",
        f"优先看 {MAX_DTE} 天内、接近现价的合约",
        "该方法只能证明期权链出现异常，不能证明买方/卖方身份，也不能替代逐笔订单流。",
    ]


def _candidate_tickers(candidates: list[dict[str, object]]) -> list[str]:
    output = []
    for candidate in candidates:
        ticker = _primary_ticker(candidate)
        if ticker and ticker not in output:
            output.append(ticker)
    return output


def _primary_ticker(candidate: dict[str, object]) -> str:
    for ticker in candidate.get("tickers", []) or []:
        text = str(ticker).upper().strip()
        if text and "." not in text and "-" not in text:
            return text
    return ""


def _no_chain(status: str, reason: str, ticker: str = "", source_url: str = "") -> dict[str, object]:
    return {
        "status": "no_flow_evidence",
        "direction": "none",
        "score": 0,
        "summary_zh": f"{ticker or '候选标的'} 公开期权链未形成可用异常信号：{reason}",
        "source_tier": "public_options_chain_snapshot",
        "source_policy_zh": "公开期权链快照不可用时，系统不会伪造异常期权流。",
        "evidence_zh": [],
        "rules_zh": _rules_zh(),
        "chain_status": status,
        "source_url": source_url,
    }


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def _to_float(value: object) -> float | None:
    try:
        if value in {None, "", ".", "-"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    try:
        if value in {None, "", ".", "-"}:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
