"""Daily short-volume positioning — the free "dark pool sentiment" proxy.

FINRA publishes consolidated daily short sale volume per symbol
(``cdn.finra.org/equity/regsho/daily/CNMSshvol{yyyymmdd}.txt``). The short
volume ratio (short volume / total volume) is the standard free proxy for
off-exchange/dark-pool sentiment: a high and *rising* ratio means shorts are
still pressing; a high ratio that *rolls over* is the classic early sign of
covering. It is a positioning clue, not a directional guarantee.

Files are one ~500KB pipe-delimited text file per trading day. They are cached
under ``data/finra_short_volume/`` so a diagnosis re-run does not re-download.
Non-trading days simply 404 and are skipped. Every failure degrades to
``unavailable``; the module never fabricates a reading.
"""

from __future__ import annotations

import logging
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

from .net import MARKET_TZ, fetch_text

logger = logging.getLogger("ai_news_radar")

FINRA_DAILY_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date}.txt"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "finra_short_volume"

#: Trading days of history to assemble for the trend read.
DEFAULT_LOOKBACK_DAYS = 20
#: Calendar days to walk back while collecting trading-day files.
MAX_CALENDAR_LOOKBACK = 45

#: Above this ratio the short-side pressure is considered heavy.
HIGH_RATIO = 0.55
ELEVATED_RATIO = 0.45


def assess_positioning(
    ticker: str,
    fetcher: object | None = None,
    cache_dir: Path | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> dict[str, object]:
    """Return the short-volume-ratio positioning read for one ticker."""
    symbol = ticker.strip().upper()
    if not symbol:
        return _unavailable("", "missing ticker")
    series = fetch_short_volume_series(
        symbol, fetcher=fetcher, cache_dir=cache_dir, lookback_days=lookback_days, now=now
    )
    if not series:
        return _unavailable(symbol, "FINRA 日度卖空数据不可用或该 symbol 无记录")
    return _assess(symbol, series)


def fetch_short_volume_series(
    ticker: str,
    fetcher: object | None = None,
    cache_dir: Path | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Collect up to ``lookback_days`` trading-day readings, oldest first."""
    symbol = ticker.strip().upper()
    fetch = fetcher or _fetch_text
    cache = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    moment = (now or datetime.now(MARKET_TZ)).astimezone(MARKET_TZ)

    series: list[dict[str, object]] = []
    day = moment.date()
    for _ in range(MAX_CALENDAR_LOOKBACK):
        if len(series) >= lookback_days:
            break
        if day.weekday() < 5:  # weekends never publish; holidays just 404.
            raw = _day_file(day.strftime("%Y%m%d"), fetch, cache)
            if raw is not None:
                row = _symbol_row(raw, symbol, day.strftime("%Y-%m-%d"))
                if row is not None:
                    series.append(row)
        day -= timedelta(days=1)
    series.reverse()
    return series


def _day_file(yyyymmdd: str, fetch: object, cache: Path) -> str | None:
    cached = cache / f"CNMSshvol{yyyymmdd}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="replace")
    url = FINRA_DAILY_URL.format(date=yyyymmdd)
    try:
        raw = fetch(url)  # type: ignore[operator]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # non-trading day or not yet published
            return None
        logger.warning("FINRA short volume fetch failed for %s: %s", yyyymmdd, exc)
        return None
    except Exception as exc:  # noqa: BLE001 - positioning must not break a diagnosis.
        logger.warning("FINRA short volume fetch failed for %s: %s", yyyymmdd, exc)
        return None
    if not raw or "Date|Symbol" not in raw[:200]:
        return None
    try:
        cache.mkdir(parents=True, exist_ok=True)
        cached.write_text(raw, encoding="utf-8")
    except OSError as exc:
        logger.warning("FINRA cache write failed for %s: %s", yyyymmdd, exc)
    return raw


def _symbol_row(raw: str, symbol: str, date_iso: str) -> dict[str, object] | None:
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) < 5 or parts[1] != symbol:
            continue
        short_volume = _to_float(parts[2])
        total_volume = _to_float(parts[4])
        if short_volume is None or total_volume is None or total_volume <= 0:
            return None
        return {
            "date": date_iso,
            "short_volume": round(short_volume),
            "total_volume": round(total_volume),
            "ratio": round(short_volume / total_volume, 4),
        }
    return None


def _assess(symbol: str, series: list[dict[str, object]]) -> dict[str, object]:
    ratios = [float(row["ratio"]) for row in series]
    latest = ratios[-1]
    avg_5d = _mean(ratios[-5:])
    avg_20d = _mean(ratios)
    trend = _trend(ratios)
    level = "high" if latest >= HIGH_RATIO else "elevated" if latest >= ELEVATED_RATIO else "normal"
    return {
        "status": "ok",
        "ticker": symbol,
        "latest_ratio": latest,
        "latest_date": series[-1]["date"],
        "avg_5d": avg_5d,
        "avg_20d": avg_20d,
        "trend": trend,
        "level": level,
        "observations": len(series),
        "series": series,
        "summary_zh": _summary_zh(symbol, latest, avg_20d, trend, level),
        "source": "FINRA Reg SHO daily short sale volume",
        "source_policy_zh": (
            "卖空成交占比是免费可得的暗盘情绪代理指标：它统计当日卖空成交（多发生在场外/做市商内部化），"
            "不是逐笔暗盘方向数据；只能与其他证据共同使用。"
        ),
    }


def _trend(ratios: list[float]) -> str:
    if len(ratios) < 8:
        return "insufficient_history"
    recent = _mean(ratios[-4:])
    prior = _mean(ratios[-8:-4])
    if recent is None or prior is None:
        return "insufficient_history"
    if recent - prior >= 0.03:
        return "rising"
    if prior - recent >= 0.03:
        return "falling"
    return "flat"


def _summary_zh(symbol: str, latest: float, avg_20d: float | None, trend: str, level: str) -> str:
    pct = f"{latest * 100:.1f}%"
    avg = f"{avg_20d * 100:.1f}%" if avg_20d is not None else "n/a"
    trend_zh = {
        "rising": "且仍在上升（空头继续施压）",
        "falling": "但正在回落（可能开始回补）",
        "flat": "且基本持平",
        "insufficient_history": "（历史不足，趋势未知）",
    }[trend]
    level_zh = {"high": "高", "elevated": "偏高", "normal": "正常"}[level]
    return f"{symbol} 最新卖空成交占比 {pct}（{level_zh}，20日均值 {avg}）{trend_zh}。"


def _unavailable(symbol: str, reason: str) -> dict[str, object]:
    return {
        "status": "unavailable",
        "ticker": symbol,
        "reason": reason,
        "summary_zh": f"{symbol or 'ticker'} 卖空占比数据不可用：{reason}。不基于缺失数据下结论。",
        "source": "FINRA Reg SHO daily short sale volume",
    }


def _mean(values: list[float]) -> float | None:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return round(sum(cleaned) / len(cleaned), 4)


def _to_float(value: object) -> float | None:
    try:
        if value in {None, "", ".", "-"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_text(url: str) -> str:
    return fetch_text(url, accept="text/plain", timeout=15, retries=0)
