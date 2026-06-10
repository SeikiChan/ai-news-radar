"""Options structure from the CBOE delayed full chain: GEX, walls, IV, P/C.

CBOE publishes a free delayed-quote JSON for every listed underlying
(``cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json``) that already
includes per-contract greeks (delta/gamma/vega), IV, volume, and open
interest — so dealer-gamma exposure (GEX) can be aggregated directly without a
Black-Scholes reimplementation.

Honesty note baked into every result: GEX uses the standard open-interest
heuristic (dealers long calls / short puts). Nobody outside the dealers knows
true positioning; SpotGamma/SqueezeMetrics style products estimate from the
same OI data. This is a structure estimate, never order-flow truth.

Per-contract dollar gamma per 1% move: ``gamma * OI * 100 * spot^2 * 0.01``,
calls positive / puts negative. The gamma flip is approximated by the zero
crossing of the cumulative net-GEX profile across strikes.

Each successful read appends one daily snapshot per ticker to
``data/options_structure_history.jsonl`` so IV rank becomes computable once
enough local history accumulates (the free chain has no IV history API).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .net import fetch_text

logger = logging.getLogger("ai_news_radar")

CBOE_CHAIN_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json"
DEFAULT_HISTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "options_structure_history.jsonl"

OCC_RE = re.compile(r"^(?P<root>[A-Z0-9.]{1,6})(?P<date>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")

#: Strikes further than this from spot are noise for the wall/flip profile.
PROFILE_STRIKE_BAND = 0.40
#: Minimum local snapshots before an IV rank is reported.
IV_RANK_MIN_HISTORY = 20
#: Front ATM IV above back ATM IV by this factor counts as an inverted term structure.
TERM_INVERSION_FACTOR = 1.05


def assess_options_structure(
    ticker: str,
    fetcher: object | None = None,
    history_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Fetch the full chain and return GEX / walls / IV / P-C structure."""
    symbol = ticker.strip().upper()
    if not symbol:
        return _unavailable("", "missing ticker")
    fetch = fetcher or _fetch_text
    url = CBOE_CHAIN_URL.format(ticker=symbol)
    try:
        payload = json.loads(fetch(url))  # type: ignore[operator]
        data = payload.get("data") or {}
        spot = _to_float(data.get("current_price"))
        contracts = _parse_contracts(data.get("options") or [], now=now)
    except Exception as exc:  # noqa: BLE001 - chain trouble must not break a diagnosis.
        return _unavailable(symbol, str(exc)[:200], url)
    if not spot or spot <= 0 or not contracts:
        return _unavailable(symbol, "链数据为空或缺少现价", url)

    profile = _gex_profile(contracts, spot)
    pc = _put_call_ratios(contracts)
    term = _atm_term_structure(contracts, spot)
    result = {
        "status": "ok",
        "ticker": symbol,
        "as_of": str(data.get("last_trade_time") or ""),
        "spot": spot,
        "iv30": _to_float(data.get("iv30")),
        "gex": profile,
        "put_call": pc,
        "iv_term": term,
        "summary_zh": _summary_zh(symbol, spot, profile, pc, term),
        "source": "CBOE delayed quotes (full chain, greeks included)",
        "source_url": url,
        "source_policy_zh": (
            "GEX 基于持仓量(OI)与「做市商多 call 空 put」的行业惯例假设推算，"
            "与 SpotGamma 类产品方法论同源；它是结构估计，不是真实做市商持仓，也不是逐笔订单流。"
        ),
    }
    history = _record_snapshot(result, history_path or DEFAULT_HISTORY_PATH)
    iv_rank = _iv_rank(result, history)
    result["iv_rank"] = iv_rank
    if iv_rank.get("status") == "ok":
        result["summary_zh"] += f" IV Rank≈{iv_rank['rank_pct']:.0f}%（基于本地 {iv_rank['history_n']} 个快照）。"
    return result


def _parse_contracts(rows: list[object], now: datetime | None = None) -> list[dict[str, object]]:
    moment = now or datetime.now(timezone.utc)
    contracts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        meta = parse_occ_symbol(str(row.get("option") or ""))
        if meta is None:
            continue
        gamma = _to_float(row.get("gamma"))
        oi = _to_float(row.get("open_interest"))
        iv = _to_float(row.get("iv"))
        dte = max(0, (meta["expiry"] - moment.date()).days)
        contracts.append(
            {
                "type": meta["cp"],
                "strike": meta["strike"],
                "expiry": meta["expiry"].isoformat(),
                "dte": dte,
                "gamma": gamma or 0.0,
                "open_interest": oi or 0.0,
                "volume": _to_float(row.get("volume")) or 0.0,
                "iv": iv,
            }
        )
    return contracts


def parse_occ_symbol(symbol: str) -> dict[str, object] | None:
    """``AAPL260821C00410000`` -> ``{cp, strike, expiry}`` (shared with options_chain)."""
    match = OCC_RE.match(symbol.strip().upper())
    if not match:
        return None
    raw_date = match.group("date")
    try:
        expiry = datetime.strptime(raw_date, "%y%m%d").date()
    except ValueError:
        return None
    return {
        "cp": "call" if match.group("cp") == "C" else "put",
        "strike": int(match.group("strike")) / 1000.0,
        "expiry": expiry,
    }


def _gex_profile(contracts: list[dict[str, object]], spot: float) -> dict[str, object]:
    by_strike: dict[float, dict[str, float]] = {}
    lo, hi = spot * (1 - PROFILE_STRIKE_BAND), spot * (1 + PROFILE_STRIKE_BAND)
    for contract in contracts:
        strike = float(contract["strike"])
        if not lo <= strike <= hi:
            continue
        gex = float(contract["gamma"]) * float(contract["open_interest"]) * 100 * spot * spot * 0.01
        bucket = by_strike.setdefault(strike, {"call": 0.0, "put": 0.0})
        bucket[str(contract["type"])] += gex

    if not by_strike:
        return {"status": "unavailable", "reason": "现价±40%内没有有效持仓"}

    strikes = sorted(by_strike)
    net_total = sum(b["call"] - b["put"] for b in by_strike.values())
    call_wall = max(strikes, key=lambda s: by_strike[s]["call"])
    put_wall = max(strikes, key=lambda s: by_strike[s]["put"])
    flip = _flip_level(strikes, by_strike)
    regime = _regime(spot, flip, net_total)
    top = sorted(strikes, key=lambda s: abs(by_strike[s]["call"] - by_strike[s]["put"]), reverse=True)[:8]
    return {
        "status": "ok",
        "net_gex_usd": round(net_total),
        "regime": regime,
        "flip_level": flip,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "top_strikes": [
            {
                "strike": s,
                "net_gex_usd": round(by_strike[s]["call"] - by_strike[s]["put"]),
                "call_oi_gex_usd": round(by_strike[s]["call"]),
                "put_oi_gex_usd": round(by_strike[s]["put"]),
            }
            for s in sorted(top)
        ],
    }


def _flip_level(strikes: list[float], by_strike: dict[float, dict[str, float]]) -> float | None:
    """Zero crossing of the cumulative net-GEX profile (estimate)."""
    cumulative = 0.0
    previous_strike: float | None = None
    previous_cumulative = 0.0
    for strike in strikes:
        cumulative += by_strike[strike]["call"] - by_strike[strike]["put"]
        if previous_strike is not None and previous_cumulative < 0 <= cumulative:
            span = cumulative - previous_cumulative
            if span > 0:
                fraction = -previous_cumulative / span
                return round(previous_strike + fraction * (strike - previous_strike), 2)
            return round(strike, 2)
        previous_strike = strike
        previous_cumulative = cumulative
    return None


def _regime(spot: float, flip: float | None, net_total: float) -> str:
    if flip is None:
        return "positive_gamma" if net_total >= 0 else "negative_gamma"
    return "positive_gamma" if spot >= flip else "negative_gamma"


def _put_call_ratios(contracts: list[dict[str, object]]) -> dict[str, object]:
    call_oi = sum(float(c["open_interest"]) for c in contracts if c["type"] == "call")
    put_oi = sum(float(c["open_interest"]) for c in contracts if c["type"] == "put")
    call_vol = sum(float(c["volume"]) for c in contracts if c["type"] == "call")
    put_vol = sum(float(c["volume"]) for c in contracts if c["type"] == "put")
    return {
        "oi_ratio": round(put_oi / call_oi, 3) if call_oi > 0 else None,
        "volume_ratio": round(put_vol / call_vol, 3) if call_vol > 0 else None,
        "call_oi": round(call_oi),
        "put_oi": round(put_oi),
        "call_volume": round(call_vol),
        "put_volume": round(put_vol),
    }


def _atm_term_structure(contracts: list[dict[str, object]], spot: float) -> dict[str, object]:
    by_expiry: dict[str, list[dict[str, object]]] = {}
    for contract in contracts:
        if contract.get("iv") and int(contract["dte"]) >= 1:
            by_expiry.setdefault(str(contract["expiry"]), []).append(contract)
    points = []
    for expiry in sorted(by_expiry):
        rows = sorted(by_expiry[expiry], key=lambda c: abs(float(c["strike"]) - spot))
        atm = [float(c["iv"]) for c in rows[:4] if c.get("iv")]
        if atm:
            points.append({"expiry": expiry, "dte": int(rows[0]["dte"]), "atm_iv": round(sum(atm) / len(atm), 4)})
    if len(points) < 2:
        return {"status": "unavailable", "points": points}
    front = points[0]
    back = next((p for p in points if int(p["dte"]) >= 25), points[-1])
    inverted = bool(front["atm_iv"] > back["atm_iv"] * TERM_INVERSION_FACTOR and front["expiry"] != back["expiry"])
    return {
        "status": "ok",
        "front": front,
        "back": back,
        "inverted": inverted,
        "points": points[:8],
    }


def _record_snapshot(result: dict[str, object], path: Path) -> list[dict[str, object]]:
    """Append today's structure snapshot (dedup by ticker+date); return history."""
    snapshot_date = str(result.get("as_of") or "")[:10] or datetime.now(timezone.utc).date().isoformat()
    ticker = str(result.get("ticker") or "")
    history: list[dict[str, object]] = []
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("ticker") == ticker:
                    history.append(row)
        if any(row.get("date") == snapshot_date for row in history):
            return history
        gex = result.get("gex") if isinstance(result.get("gex"), dict) else {}
        pc = result.get("put_call") if isinstance(result.get("put_call"), dict) else {}
        row = {
            "ticker": ticker,
            "date": snapshot_date,
            "spot": result.get("spot"),
            "iv30": result.get("iv30"),
            "net_gex_usd": gex.get("net_gex_usd"),
            "flip_level": gex.get("flip_level"),
            "pc_oi_ratio": pc.get("oi_ratio"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        history.append(row)
    except OSError as exc:
        logger.warning("options structure history write failed: %s", exc)
    return history


def _iv_rank(result: dict[str, object], history: list[dict[str, object]]) -> dict[str, object]:
    current = _to_float(result.get("iv30"))
    values = [v for v in (_to_float(row.get("iv30")) for row in history) if v is not None]
    if current is None:
        return {"status": "unavailable", "reason": "no iv30"}
    if len(values) < IV_RANK_MIN_HISTORY:
        return {
            "status": "accumulating",
            "history_n": len(values),
            "needed": IV_RANK_MIN_HISTORY,
            "note_zh": f"IV Rank 需要本地累计 {IV_RANK_MIN_HISTORY} 个交易日快照，当前 {len(values)} 个；先用 IV 期限结构判断恐慌。",
        }
    below = sum(1 for v in values if v <= current)
    return {"status": "ok", "rank_pct": round(below / len(values) * 100, 1), "history_n": len(values)}


def _summary_zh(
    symbol: str,
    spot: float,
    profile: dict[str, object],
    pc: dict[str, object],
    term: dict[str, object],
) -> str:
    parts = []
    if profile.get("status") == "ok":
        regime_zh = "正gamma区（做市商对冲压制波动）" if profile["regime"] == "positive_gamma" else "负gamma区（对冲放大波动，易超跌/超涨）"
        flip = profile.get("flip_level")
        flip_zh = f"，gamma 翻转位≈{flip}" if flip is not None else ""
        parts.append(
            f"{symbol} 现价 {spot} 处于{regime_zh}{flip_zh}；call wall={profile['call_wall']}，put wall={profile['put_wall']}。"
        )
    oi_ratio = pc.get("oi_ratio")
    if oi_ratio is not None:
        bias = "put 堆积偏重（对冲/看空仓位多）" if oi_ratio > 1.1 else "call 堆积偏重（看多仓位多）" if oi_ratio < 0.7 else "多空持仓大致均衡"
        parts.append(f"P/C 持仓比={oi_ratio}，{bias}。")
    if term.get("status") == "ok" and term.get("inverted"):
        front = term["front"]
        parts.append(f"近月 ATM IV {float(front['atm_iv'])*100:.0f}% 高于远月，期限结构倒挂：市场在为短期恐慌定价。")
    return " ".join(parts) if parts else f"{symbol} 期权结构数据不足。"


def _unavailable(symbol: str, reason: str, url: str = "") -> dict[str, object]:
    return {
        "status": "unavailable",
        "ticker": symbol,
        "reason": reason,
        "summary_zh": f"{symbol or 'ticker'} 期权链不可用：{reason}。不在缺数据时伪造 gamma 结构。",
        "source": "CBOE delayed quotes",
        "source_url": url,
    }


def _to_float(value: object) -> float | None:
    try:
        if value in {None, "", ".", "-"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_text(url: str) -> str:
    return fetch_text(url, accept="application/json", timeout=15)
