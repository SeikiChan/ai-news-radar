"""Drawdown attribution and momentum/trend state for one ticker.

The single most important question for a "wrongly punished" (错杀) thesis is
whether a drop is the stock's own or just sector beta. This module decomposes
the 20-day move into the sector-ETF part and the idiosyncratic residual
(beta≈1 simplification, stated honestly), and adds the standard trend reads:
RSI(14), 20/50/200-day moving-average structure, 52-week position, drawdown,
and a heavy-down-volume exhaustion check.

Sector mapping uses Yahoo ``assetProfile`` -> SPDR sector ETF, with SPY as the
benchmark and fallback. All fetchers are injectable for tests; any failure
degrades to ``unavailable`` instead of fabricating numbers.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import quote

from .net import fetch_text
from .yahoo import make_yahoo_fetcher, quote_summary_url

logger = logging.getLogger("ai_news_radar")

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
BENCHMARK = "SPY"

SECTOR_ETF = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

HEAVY_DOWN_DAY_PCT = -2.0
HEAVY_DOWN_VOLUME_RATIO = 1.5


def assess_relative_strength(
    ticker: str,
    fetcher: object | None = None,
    profile_fetcher: object | None = None,
    sector_etf: str = "",
) -> dict[str, object]:
    symbol = ticker.strip().upper()
    if not symbol:
        return _unavailable("", "missing ticker")
    fetch = fetcher or _fetch_text

    closes, volumes = _daily_series(symbol, fetch)
    if len(closes) < 60:
        return _unavailable(symbol, "历史价格不足 60 个交易日")

    etf = sector_etf.strip().upper() or _sector_etf(symbol, profile_fetcher)
    sector_closes, _ = _daily_series(etf, fetch) if etf else ([], [])
    spy_closes, _ = _daily_series(BENCHMARK, fetch)

    trend = _trend_state(closes, volumes)
    attribution = _attribution(symbol, closes, etf, sector_closes, spy_closes)
    return {
        "status": "ok",
        "ticker": symbol,
        "sector_etf": etf or None,
        "trend": trend,
        "attribution": attribution,
        "summary_zh": _summary_zh(symbol, trend, attribution),
        "source": "Yahoo chart API (1y daily)",
        "method_note_zh": "归因采用 beta≈1 的简化：个股跌幅 − 板块跌幅 = 自身残差。它是一阶估计，高贝塔股会低估板块贡献。",
    }


def _daily_series(symbol: str, fetch: object) -> tuple[list[float], list[float]]:
    if not symbol:
        return [], []
    url = CHART_URL.format(ticker=quote(symbol))
    try:
        payload = json.loads(fetch(url))  # type: ignore[operator]
        result = (payload.get("chart", {}).get("result") or [None])[0]
        quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
        raw_closes = quote_data.get("close") or []
        raw_volumes = quote_data.get("volume") or []
        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    except Exception as exc:  # noqa: BLE001 - one missing series degrades, not breaks.
        logger.warning("chart fetch failed for %s: %s", symbol, exc)
        return [], []
    closes, volumes = [], []
    for close, volume in zip(raw_closes, raw_volumes, strict=False):
        if close is None:
            continue
        closes.append(float(close))
        volumes.append(float(volume or 0))
    # Yahoo reports the in-progress session as close=null; the live price lives
    # in meta.regularMarketPrice. Without this the "latest" close is a day stale.
    if raw_closes and raw_closes[-1] is None:
        live = meta.get("regularMarketPrice")
        if isinstance(live, (int, float)) and float(live) > 0:
            closes.append(float(live))
            volumes.append(float(meta.get("regularMarketVolume") or 0))
    return closes, volumes


def _sector_etf(symbol: str, profile_fetcher: object | None) -> str:
    try:
        fetch = profile_fetcher or make_yahoo_fetcher()
        payload = json.loads(fetch(quote_summary_url(symbol, "assetProfile")))  # type: ignore[operator]
        result = (((payload.get("quoteSummary") or {}).get("result")) or [None])[0]
        sector = str(((result or {}).get("assetProfile") or {}).get("sector") or "")
        return SECTOR_ETF.get(sector, "")
    except Exception as exc:  # noqa: BLE001 - sector lookup is optional.
        logger.warning("sector lookup failed for %s: %s", symbol, exc)
        return ""


def _trend_state(closes: list[float], volumes: list[float]) -> dict[str, object]:
    price = closes[-1]
    high_52w = max(closes)
    low_52w = min(closes)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    stack = _stack_label(price, sma20, sma50, sma200)
    return {
        "price": round(price, 2),
        "rsi_14": _rsi(closes, 14),
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "ma_stack": stack,
        "pct_off_52w_high": round((price / high_52w - 1) * 100, 2),
        "pct_above_52w_low": round((price / low_52w - 1) * 100, 2),
        "return_5d_pct": _window_return(closes, 5),
        "return_20d_pct": _window_return(closes, 20),
        "return_60d_pct": _window_return(closes, 60),
        "heavy_down_days_10d": _heavy_down_days(closes, volumes, 10),
        "selling_exhaustion": _selling_exhaustion(closes, volumes),
    }


def _attribution(
    symbol: str,
    closes: list[float],
    etf: str,
    sector_closes: list[float],
    spy_closes: list[float],
) -> dict[str, object]:
    stock_20d = _window_return(closes, 20)
    sector_20d = _window_return(sector_closes, 20) if sector_closes else None
    spy_20d = _window_return(spy_closes, 20) if spy_closes else None
    benchmark_20d = sector_20d
    benchmark_is_proxy = False
    if benchmark_20d is None and spy_20d is not None:
        benchmark_20d = spy_20d
        benchmark_is_proxy = True
    row: dict[str, object] = {
        "stock_20d_pct": stock_20d,
        "sector_20d_pct": sector_20d,
        "spy_20d_pct": spy_20d,
        "excess_vs_spy_20d_pct": _diff(stock_20d, spy_20d),
        "excess_vs_sector_20d_pct": _diff(stock_20d, sector_20d),
        "benchmark_is_spy_proxy": benchmark_is_proxy,
    }
    if stock_20d is not None and benchmark_20d is not None:
        sector_20d = benchmark_20d
        idio = stock_20d - sector_20d
        row["idiosyncratic_20d_pct"] = round(idio, 2)
        if stock_20d < 0:
            sector_share = max(0.0, min(1.0, (sector_20d / stock_20d) if stock_20d != 0 else 0.0))
            row["sector_share_of_drop"] = round(sector_share, 2)
            row["verdict"] = (
                "sector_driven" if sector_share >= 0.6 else "idiosyncratic" if sector_share <= 0.3 else "mixed"
            )
        else:
            row["verdict"] = "not_in_drawdown_20d"
    else:
        row["verdict"] = "insufficient_data"
    row["sector_etf"] = etf or None
    return row


def _summary_zh(symbol: str, trend: dict[str, object], attribution: dict[str, object]) -> str:
    parts = [
        f"{symbol} 现价 {trend['price']}，距 52 周高点 {trend['pct_off_52w_high']}%，"
        f"RSI(14)={trend['rsi_14']}，均线结构={_stack_zh(str(trend['ma_stack']))}。"
    ]
    verdict = str(attribution.get("verdict") or "")
    proxy_zh = "（板块数据缺失，以 SPY 代理）" if attribution.get("benchmark_is_spy_proxy") else ""
    if verdict == "sector_driven":
        parts.append(
            f"近20日下跌主要由板块解释{proxy_zh}（板块贡献约 {float(attribution['sector_share_of_drop'])*100:.0f}%），属于「陪葬式」下跌，错杀概率较高。"
        )
    elif verdict == "idiosyncratic":
        parts.append("近20日下跌主要是个股自身原因（板块解释不足三成），必须先核对公司层面证据，不能假设错杀。")
    elif verdict == "mixed":
        parts.append("近20日下跌由板块与个股因素共同造成。")
    elif verdict == "not_in_drawdown_20d":
        parts.append("近20日并未下跌，错杀前提不成立。")
    exhaustion = trend.get("selling_exhaustion")
    if exhaustion == "exhausting":
        parts.append("下跌动能在缩量，卖压有衰竭迹象。")
    elif exhaustion == "active_selling":
        parts.append("仍在放量下跌，卖压未衰竭，左侧接刀风险高。")
    return " ".join(parts)


def _stack_label(price: float, sma20: float | None, sma50: float | None, sma200: float | None) -> str:
    if sma20 is None or sma50 is None:
        return "insufficient"
    if sma200 is None:
        return "above_all" if price > sma20 > sma50 else "mixed"
    if price > sma20 > sma50 > sma200:
        return "uptrend_stack"
    if price < sma20 < sma50 < sma200:
        return "downtrend_stack"
    if price < sma200:
        return "below_200dma"
    return "mixed"


def _stack_zh(stack: str) -> str:
    return {
        "uptrend_stack": "多头排列",
        "downtrend_stack": "空头排列",
        "below_200dma": "200日线下方",
        "mixed": "纠缠",
        "above_all": "短期偏多",
        "insufficient": "数据不足",
    }.get(stack, stack)


def _heavy_down_days(closes: list[float], volumes: list[float], window: int) -> int:
    if len(closes) < window + 61:
        baseline_start = max(1, len(closes) - window - 60)
    else:
        baseline_start = len(closes) - window - 60
    baseline = [v for v in volumes[baseline_start : len(closes) - window] if v > 0]
    if not baseline:
        return 0
    avg_volume = sum(baseline) / len(baseline)
    count = 0
    for index in range(len(closes) - window, len(closes)):
        if index < 1:
            continue
        change = (closes[index] / closes[index - 1] - 1) * 100
        if change <= HEAVY_DOWN_DAY_PCT and volumes[index] >= avg_volume * HEAVY_DOWN_VOLUME_RATIO:
            count += 1
    return count


def _selling_exhaustion(closes: list[float], volumes: list[float]) -> str:
    """Down move on shrinking volume = exhausting; on rising volume = active."""
    if len(closes) < 11:
        return "unknown"
    recent_return = _window_return(closes, 5)
    if recent_return is None or recent_return > -1:
        return "not_applicable"
    recent_volume = sum(volumes[-3:]) / 3
    prior_volume = sum(volumes[-10:-3]) / 7
    if prior_volume <= 0:
        return "unknown"
    ratio = recent_volume / prior_volume
    if ratio <= 0.75:
        return "exhausting"
    if ratio >= 1.15:
        return "active_selling"
    return "steady"


def _rsi(closes: list[float], period: int) -> float | None:
    if len(closes) <= period:
        return None
    gains, losses = [], []
    for index in range(len(closes) - period, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)


def _window_return(closes: list[float], lookback: int) -> float | None:
    if len(closes) <= lookback:
        return None
    previous = closes[-lookback - 1]
    if previous == 0:
        return None
    return round((closes[-1] / previous - 1) * 100, 2)


def _diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 2)


def _unavailable(symbol: str, reason: str) -> dict[str, object]:
    return {
        "status": "unavailable",
        "ticker": symbol,
        "reason": reason,
        "summary_zh": f"{symbol or 'ticker'} 相对强弱数据不可用：{reason}。",
        "source": "Yahoo chart API",
    }


def _fetch_text(url: str) -> str:
    return fetch_text(url, accept="application/json", timeout=15)
