"""Options structure from the CBOE delayed full chain: GEX proxy, IV, P/C.

CBOE publishes a free delayed-quote JSON for every listed underlying
(``cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json``) that already
includes per-contract greeks (delta/gamma/vega), IV, volume, and open
interest. This lets us calculate a signed GEX proxy without recalculating
Greeks, but it does not reveal actual dealer exposure.

Honesty note baked into every result: OI does not identify who is long or
short. The signed GEX proxy uses one explicit convention (calls positive,
puts negative); it is a scenario estimate, never observed dealer positioning.

Per-contract dollar gamma per 1% move: ``gamma * OI * 100 * spot^2 * 0.01``,
calls positive / puts negative. A gamma flip is intentionally not reported:
the chain's current Greeks cannot be summed across strikes to obtain the
hypothetical spot at which total GEX crosses zero.

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

#: Strikes further than this from spot are excluded from the peak profile.
PROFILE_STRIKE_BAND = 0.40
#: Tighter band + cap for the per-strike chart (readability over completeness).
CHART_STRIKE_BAND = 0.12
MAX_CHART_STRIKES = 40
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
    """Fetch the full chain and return a signed GEX proxy / IV / P-C structure."""
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
    strike_map = _strike_map(contracts, spot)
    strike_chart = _strike_gamma_chart(contracts, spot, profile)
    result = {
        "status": "ok",
        "ticker": symbol,
        "as_of": str(data.get("last_trade_time") or ""),
        "spot": spot,
        "iv30": _to_float(data.get("iv30")),
        "gex": profile,
        "put_call": pc,
        "iv_term": term,
        "strike_map": strike_map,
        "strike_chart": strike_chart,
        "summary_zh": _summary_zh(symbol, spot, profile, pc, term),
        "source": "CBOE delayed quotes (full chain, greeks included)",
        "source_url": url,
        "source_policy_zh": (
            "数据来自 CBOE 延迟期权链；OI 是未平仓合约数，不显示哪一方买入或卖出。"
            "净 GEX 采用 calls 正、puts 负的简化符号假设，只是现价下的结构估算，"
            "不代表真实做市商仓位或逐笔订单流；OI 更新节奏也不等同于行情时间戳。"
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
    regime = _regime(net_total)
    top = sorted(strikes, key=lambda s: abs(by_strike[s]["call"] - by_strike[s]["put"]), reverse=True)[:8]
    return {
        "status": "ok",
        "net_gex_usd": round(net_total),
        "regime": regime,
        "flip_level": None,
        "flip_status": "not_estimated",
        "flip_reason_zh": "当前只估算现价下的净 GEX；翻转位需要在一系列假设价格下重估整条期权链，不能用按 strike 累加的零点代替。",
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


def _strike_gamma_chart(
    contracts: list[dict[str, object]],
    spot: float,
    profile: dict[str, object],
) -> dict[str, object]:
    """Per-strike chart data: call/put/net GEX + call/put OI + volume.

    This is the "gamma by strike" ladder the UI draws: one row per strike in a
    tight band around spot, with the signed GEX proxy under the stated OI
    convention plus raw open interest and volume. It is not dealer positioning.
    """
    rows: dict[float, dict[str, float]] = {}
    lo, hi = spot * (1 - CHART_STRIKE_BAND), spot * (1 + CHART_STRIKE_BAND)
    for contract in contracts:
        strike = float(contract["strike"])
        if not lo <= strike <= hi:
            continue
        oi = float(contract["open_interest"])
        volume = float(contract["volume"])
        gex = float(contract["gamma"]) * oi * 100 * spot * spot * 0.01
        row = rows.setdefault(
            strike,
            {"call_gex": 0.0, "put_gex": 0.0, "call_oi": 0.0, "put_oi": 0.0, "call_volume": 0.0, "put_volume": 0.0},
        )
        if contract["type"] == "call":
            row["call_gex"] += gex
            row["call_oi"] += oi
            row["call_volume"] += volume
        else:
            row["put_gex"] += gex
            row["put_oi"] += oi
            row["put_volume"] += volume

    if not rows:
        return {"status": "unavailable"}

    # Keep the strikes nearest spot when there are more than the cap.
    selected = sorted(rows, key=lambda s: abs(s - spot))[:MAX_CHART_STRIKES]
    strikes = sorted(selected)
    bars = [
        {
            "strike": strike,
            "call_gex_usd": round(rows[strike]["call_gex"]),
            "put_gex_usd": round(rows[strike]["put_gex"]),
            "net_gex_usd": round(rows[strike]["call_gex"] - rows[strike]["put_gex"]),
            "call_oi": round(rows[strike]["call_oi"]),
            "put_oi": round(rows[strike]["put_oi"]),
            "call_volume": round(rows[strike]["call_volume"]),
            "put_volume": round(rows[strike]["put_volume"]),
        }
        for strike in strikes
    ]
    gex = profile if isinstance(profile, dict) else {}
    return {
        "status": "ok",
        "spot": spot,
        "flip_level": gex.get("flip_level"),
        "call_wall": gex.get("call_wall"),
        "put_wall": gex.get("put_wall"),
        "net_gex_usd": gex.get("net_gex_usd"),
        "regime": gex.get("regime"),
        "bars": bars,
    }


def _regime(net_total: float) -> str:
    """Classify only the current-spot signed GEX proxy, not dealer positioning."""
    return "positive_gamma" if net_total >= 0 else "negative_gamma"


def _strike_map(contracts: list[dict[str, object]], spot: float) -> dict[str, object]:
    """Where the open interest sits and where today's volume went, by strike.

    Reports where open interest and daily volume are largest. Neither measure
    reveals trade direction, so these strikes are not support/resistance or a
    map of where buyers are active.
    """
    by_strike: dict[float, dict[str, float]] = {}
    lo, hi = spot * (1 - PROFILE_STRIKE_BAND), spot * (1 + PROFILE_STRIKE_BAND)
    for contract in contracts:
        strike = float(contract["strike"])
        if not lo <= strike <= hi:
            continue
        bucket = by_strike.setdefault(strike, {"call_oi": 0.0, "put_oi": 0.0, "call_volume": 0.0, "put_volume": 0.0})
        prefix = "call" if contract["type"] == "call" else "put"
        bucket[f"{prefix}_oi"] += float(contract["open_interest"])
        bucket[f"{prefix}_volume"] += float(contract["volume"])

    if not by_strike:
        return {"status": "unavailable"}

    def row(strike: float) -> dict[str, object]:
        b = by_strike[strike]
        return {
            "strike": strike,
            "call_oi": round(b["call_oi"]),
            "put_oi": round(b["put_oi"]),
            "call_volume": round(b["call_volume"]),
            "put_volume": round(b["put_volume"]),
        }

    strikes = list(by_strike)
    top_oi = sorted(strikes, key=lambda s: by_strike[s]["call_oi"] + by_strike[s]["put_oi"], reverse=True)[:7]
    top_volume = sorted(strikes, key=lambda s: by_strike[s]["call_volume"] + by_strike[s]["put_volume"], reverse=True)[:5]
    max_call_oi = max(strikes, key=lambda s: by_strike[s]["call_oi"])
    max_put_oi = max(strikes, key=lambda s: by_strike[s]["put_oi"])
    max_volume = max(strikes, key=lambda s: by_strike[s]["call_volume"] + by_strike[s]["put_volume"])
    return {
        "status": "ok",
        "top_oi": [row(s) for s in sorted(top_oi)],
        "top_volume": [row(s) for s in sorted(top_volume)],
        "max_call_oi_strike": max_call_oi,
        "max_put_oi_strike": max_put_oi,
        "max_volume_strike": max_volume,
        "summary_zh": (
            f"未平仓量最高的 strike：call ${max_call_oi} / put ${max_put_oi}；"
            f"当日成交量最高的 strike：${max_volume}。OI 与成交量都不区分买卖方向，不能单独当作支撑/阻力。"
        ),
    }


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
        regime_zh = "假设口径下净 GEX 为正" if profile["regime"] == "positive_gamma" else "假设口径下净 GEX 为负"
        parts.append(
            f"{symbol} 现价 {spot}：{regime_zh}；call GEX 峰值=${profile['call_wall']}，put GEX 峰值=${profile['put_wall']}。"
        )
    oi_ratio = pc.get("oi_ratio")
    if oi_ratio is not None:
        bias = "put 合约未平仓量较多" if oi_ratio > 1.1 else "call 合约未平仓量较多" if oi_ratio < 0.7 else "put/call 未平仓量接近"
        parts.append(f"P/C OI={oi_ratio}，{bias}；OI 不显示持仓方向。")
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
