"""Market-level structure: index gamma, market-wide dark-pool flow, VIX.

A single-stock "wrongly punished" trade lives or dies in market context — the
same setup that works in a positive-gamma, short-covering tape gets run over
in a negative-gamma tape. This module composes three free reads into one
market posture:

* **SPY / QQQ signed GEX proxy** (CBOE option-chain Greeks × OI, using the
  calls-positive / puts-negative convention in ``gamma.py``). OI does not
  reveal dealer positioning, so this is not an observed hedging regime.
* **Market-wide short volume ratio** (every symbol in the FINRA daily file
  summed): the free dark-pool sentiment gauge at tape level.
* **VIX level vs its 3-month average** for the fear backdrop.

Output ends with a one-line verdict used by ``diagnose`` to tighten or relax
its triggers: ``friendly`` / ``neutral`` / ``hostile`` for dip-buying.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .gamma import assess_options_structure
from .net import fetch_text
from .positioning import assess_market_positioning

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIX_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3mo&interval=1d"


def assess_market_structure(
    cboe_fetcher: object | None = None,
    finra_fetcher: object | None = None,
    chart_fetcher: object | None = None,
    data_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    data = Path(data_dir) if data_dir else PROJECT_ROOT / "data"
    history = data / "options_structure_history.jsonl"

    spy = assess_options_structure("SPY", fetcher=cboe_fetcher, history_path=history, now=now)
    qqq = assess_options_structure("QQQ", fetcher=cboe_fetcher, history_path=history, now=now)
    # The CBOE ``_SPX`` chain carries SPX monthlies and SPXW weeklys/0DTE.
    # Include it as another reference series; OI peaks are not confirmed bets.
    spx = assess_options_structure("_SPX", fetcher=cboe_fetcher, history_path=history, now=now)
    dark_pool = assess_market_positioning(
        fetcher=finra_fetcher, cache_dir=data / "finra_short_volume", now=now
    )
    vix = vix_context(chart_fetcher)

    # SPX tracks SPY almost identically, so it does not get its own posture vote
    # (that would double-count the S&P gamma signal) — it rides along as the
    # full-notional "where are the big bets" view instead.
    posture, posture_zh = _posture(spy, qqq, dark_pool, vix)
    return {
        "status": "ok" if any(part.get("status") == "ok" for part in (spy, qqq, spx, dark_pool, vix)) else "unavailable",
        "fetched_at": (now or datetime.now().astimezone()).isoformat(),
        "posture": posture,
        "posture_zh": posture_zh,
        "summary_zh": _summary_zh(posture_zh, spy, qqq, spx, dark_pool, vix),
        "spy": _index_brief(spy),
        "qqq": _index_brief(qqq),
        "spx": _index_brief(spx, label="SPX"),
        "dark_pool": dark_pool,
        "vix": vix,
        "source_policy_zh": (
            "期权链来自 CBOE 延迟报价；净 GEX 用 calls 正、puts 负的简化符号假设，"
            "而 OI 不显示买卖方，因此不是实际做市商仓位。SPX 使用 CBOE 指数链（含 SPXW 周/0DTE）；"
            "墙位只表示模型下的 GEX 集中 strike，不等于支撑/阻力。FINRA 数值是全市场卖空成交占比，"
            "也不等于暗池净买卖方向。"
        ),
    }


def vix_context(chart_fetcher: object | None = None) -> dict[str, object]:
    fetch = chart_fetcher or _fetch_text
    url = VIX_CHART_URL.format(symbol=quote("^VIX"))
    try:
        payload = json.loads(fetch(url))  # type: ignore[operator]
        result = (payload.get("chart", {}).get("result") or [None])[0]
        closes = [float(v) for v in (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [] if v]
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(exc)[:160]}
    if len(closes) < 20:
        return {"status": "unavailable", "reason": "VIX 历史不足"}
    latest = closes[-1]
    avg_3mo = sum(closes) / len(closes)
    regime = "fear" if latest >= 25 else "elevated" if latest >= 20 else "calm"
    regime_zh = {"fear": "恐慌", "elevated": "偏紧", "calm": "平静"}[regime]
    return {
        "status": "ok",
        "vix": round(latest, 2),
        "avg_3mo": round(avg_3mo, 2),
        "regime": regime,
        "summary_zh": f"VIX={latest:.1f}（3个月均值 {avg_3mo:.1f}），市场恐惧状态：{regime_zh}。",
    }


def _index_brief(structure: dict[str, object], label: str | None = None) -> dict[str, object]:
    if structure.get("status") != "ok":
        return {"status": "unavailable", "ticker": label or structure.get("ticker")}
    gex = structure.get("gex") if isinstance(structure.get("gex"), dict) else {}
    term = structure.get("iv_term") if isinstance(structure.get("iv_term"), dict) else {}
    return {
        "status": "ok",
        "ticker": label or structure.get("ticker"),
        "as_of": structure.get("as_of"),
        "source": structure.get("source"),
        "spot": structure.get("spot"),
        "regime": gex.get("regime"),
        "flip_level": gex.get("flip_level"),
        "flip_status": gex.get("flip_status"),
        "flip_reason_zh": gex.get("flip_reason_zh"),
        "call_wall": gex.get("call_wall"),
        "put_wall": gex.get("put_wall"),
        "net_gex_usd": gex.get("net_gex_usd"),
        "iv30": structure.get("iv30"),
        "term_inverted": bool(term.get("inverted")),
        "strike_chart": structure.get("strike_chart") if isinstance(structure.get("strike_chart"), dict) else None,
    }


def _posture(
    spy: dict[str, object],
    qqq: dict[str, object],
    dark_pool: dict[str, object],
    vix: dict[str, object],
) -> tuple[str, str]:
    points = 0
    known = 0
    spy_regime = _regime_of(spy)
    qqq_regime = _regime_of(qqq)
    if spy_regime:
        known += 1
        points += 1 if spy_regime == "positive_gamma" else -1
    if qqq_regime:
        known += 1
        points += 1 if qqq_regime == "positive_gamma" else -1
    dark_trend = str(dark_pool.get("trend") or "") if dark_pool.get("status") == "ok" else ""
    if dark_trend in {"rising", "falling", "flat"}:
        known += 1
        points += 1 if dark_trend == "falling" else -1 if dark_trend == "rising" else 0
    vix_regime = str(vix.get("regime") or "") if vix.get("status") == "ok" else ""
    if vix_regime:
        known += 1
        points += 1 if vix_regime == "calm" else -1 if vix_regime == "fear" else 0

    if known == 0:
        return "unknown", "大盘环境数据不可用，按中性处理。"
    if points >= 2:
        return "friendly", "结构代理指标偏友好：OI 符号模型下净 GEX 偏正，且全市场卖空占比回落；这不是实际做市商仓位。"
    if points <= -2:
        return "hostile", "结构代理指标偏谨慎：OI 符号模型下净 GEX 偏负或全市场卖空占比上升；这不是实际做市商仓位。"
    return "neutral", "大盘环境中性：信号混杂，按标准触发条件执行。"


def _regime_of(structure: dict[str, object]) -> str:
    if structure.get("status") != "ok":
        return ""
    gex = structure.get("gex") if isinstance(structure.get("gex"), dict) else {}
    return str(gex.get("regime") or "")


def _summary_zh(
    posture_zh: str,
    spy: dict[str, object],
    qqq: dict[str, object],
    spx: dict[str, object],
    dark_pool: dict[str, object],
    vix: dict[str, object],
) -> str:
    parts = [posture_zh]
    for structure, label in ((spy, None), (qqq, None)):
        brief = _index_brief(structure, label=label)
        if brief.get("status") == "ok":
            regime_zh = "净 GEX 估算为正" if brief["regime"] == "positive_gamma" else "净 GEX 估算为负"
            flip = brief.get("flip_level")
            parts.append(
                f"{brief['ticker']} {regime_zh}"
                + (f"（翻转位 {flip}，现价 {brief['spot']}）" if flip is not None else "")
            )
    spx_brief = _index_brief(spx, label="SPX")
    if spx_brief.get("status") == "ok":
        call_wall = spx_brief.get("call_wall")
        put_wall = spx_brief.get("put_wall")
        if call_wall is not None and put_wall is not None:
            parts.append(
                f"SPX GEX 集中位：call ${call_wall} / put ${put_wall}"
                + (f"（现价 {spx_brief['spot']}）" if spx_brief.get("spot") is not None else "")
                + "；这是 OI 符号假设下的 GEX 峰值，不是已确认的支撑/阻力。"
            )
    if dark_pool.get("status") == "ok":
        parts.append(str(dark_pool.get("summary_zh") or ""))
    if vix.get("status") == "ok":
        parts.append(str(vix.get("summary_zh") or ""))
    return " ".join(part for part in parts if part)


def _fetch_text(url: str) -> str:
    return fetch_text(url, accept="application/json", timeout=15)
