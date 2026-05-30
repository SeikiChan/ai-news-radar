"""Signal -> forward-return feedback loop.

This is the module that answers the only question that matters for a research
radar: *do higher-scored signals actually precede higher forward excess return?*

For every stored signal/candidate it anchors on the emission date (when the
item was first recorded), then measures the forward price change at fixed
trading-day horizons and the excess over a benchmark (SPY). Results are
aggregated by the current alert bands so the 10/20/35 thresholds can be
calibrated against realized outcomes instead of guesswork.

Network access is injected (``fetcher``) so the whole evaluation is
deterministic and unit-testable without hitting Yahoo.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

from .net import user_agent
from .scoring import HARD_BAND, WATCH_BAND, WEAK_BAND

FETCH_TIMEOUT_SECONDS = 10
BENCHMARK = "SPY"

#: Forward horizons in *trading* days.
HORIZONS: tuple[int, ...] = (1, 5, 20)

#: Minimum matured outcomes per band before a calibration verdict is trusted.
#: Below this, small-sample noise would make the monotonicity check meaningless.
MIN_CALIBRATION_SAMPLE = 8

#: Alert bands, reusing scoring's centralized thresholds. (lower_inclusive, label).
BANDS: tuple[tuple[float, str], ...] = (
    (HARD_BAND, "hard"),
    (WATCH_BAND, "watch"),
    (WEAK_BAND, "weak"),
)


def band_for_score(score: float) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return "ignore"


# --------------------------------------------------------------------------- #
# Price series
# --------------------------------------------------------------------------- #
def _yahoo_chart_url(symbol: str, range_: str = "1y") -> str:
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range={range_}&interval=1d"


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": user_agent(), "Accept": "application/json"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def fetch_daily_closes(symbol: str, fetcher: object | None = None, range_: str = "1y") -> list[tuple[str, float]]:
    """Return sorted ``[(YYYY-MM-DD, close), ...]`` for ``symbol``.

    Returns an empty list on any failure; callers treat that as "no data".
    """
    symbol = symbol.strip().upper()
    if not symbol:
        return []
    fetch = fetcher or _fetch_text
    try:
        payload = json.loads(fetch(_yahoo_chart_url(symbol, range_)))
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not isinstance(result, dict):
            return []
        timestamps = result.get("timestamp") or []
        quote_block = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote_block.get("close") or []
        series: list[tuple[str, float]] = []
        for ts, close in zip(timestamps, closes, strict=False):
            if close is None:
                continue
            date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
            series.append((date, float(close)))
        series.sort(key=lambda item: item[0])
        return series
    except Exception:  # noqa: BLE001 - a missing/bad series must not break the report.
        return []


def _t0_index(series: list[tuple[str, float]], emission_date: str) -> int | None:
    """Index of the first trading day on/after ``emission_date``."""
    for index, (date, _close) in enumerate(series):
        if date >= emission_date:
            return index
    return None


def forward_returns(
    series: list[tuple[str, float]],
    emission_date: str,
    horizons: tuple[int, ...] = HORIZONS,
) -> dict[int, dict[str, object]]:
    """Per-horizon forward return anchored at the first trading day >= emission.

    Each value is ``{"return_pct": float|None, "matured": bool, "from": date,
    "to": date|None}``. ``matured`` is False when the horizon extends past the
    available series (not enough trading days have elapsed yet).
    """
    out: dict[int, dict[str, object]] = {}
    t0 = _t0_index(series, emission_date)
    for horizon in horizons:
        if t0 is None:
            out[horizon] = {"return_pct": None, "matured": False, "from": None, "to": None}
            continue
        base_date, base_close = series[t0]
        target = t0 + horizon
        if target >= len(series) or base_close == 0:
            out[horizon] = {"return_pct": None, "matured": False, "from": base_date, "to": None}
            continue
        end_date, end_close = series[target]
        out[horizon] = {
            "return_pct": round((end_close / base_close - 1) * 100, 3),
            "matured": True,
            "from": base_date,
            "to": end_date,
        }
    return out


def evaluate_outcome(
    ticker: str,
    emission_date: str,
    benchmark_series: list[tuple[str, float]],
    fetcher: object | None = None,
    horizons: tuple[int, ...] = HORIZONS,
) -> dict[str, object]:
    """Forward returns for ``ticker`` and excess over the benchmark by horizon."""
    series = fetch_daily_closes(ticker, fetcher)
    if not series:
        return {"ticker": ticker, "status": "no_price_data", "horizons": {}}
    ticker_fwd = forward_returns(series, emission_date, horizons)
    bench_fwd = forward_returns(benchmark_series, emission_date, horizons) if benchmark_series else {}
    horizon_rows: dict[str, object] = {}
    for horizon in horizons:
        t = ticker_fwd.get(horizon, {})
        b = bench_fwd.get(horizon, {})
        t_ret = t.get("return_pct")
        b_ret = b.get("return_pct")
        excess = None
        if isinstance(t_ret, (int, float)) and isinstance(b_ret, (int, float)):
            excess = round(t_ret - b_ret, 3)
        horizon_rows[str(horizon)] = {
            "matured": bool(t.get("matured")),
            "return_pct": t_ret,
            "benchmark_return_pct": b_ret,
            "excess_pct": excess,
            "from": t.get("from"),
            "to": t.get("to"),
        }
    return {"ticker": ticker, "status": "ok", "horizons": horizon_rows}


# --------------------------------------------------------------------------- #
# Aggregation over stored rows
# --------------------------------------------------------------------------- #
def _emission_date(row: dict[str, object]) -> str:
    article = row.get("article") if isinstance(row.get("article"), dict) else {}
    raw = str(article.get("fetched_at") or article.get("published") or "")
    return raw[:10] if len(raw) >= 10 else ""


def _row_tickers(row: dict[str, object]) -> list[str]:
    return [str(t).upper().strip() for t in (row.get("tickers") or []) if str(t).strip()]


def evaluate_rows(
    rows: list[dict[str, object]],
    fetcher: object | None = None,
    horizons: tuple[int, ...] = HORIZONS,
    benchmark: str = BENCHMARK,
) -> list[dict[str, object]]:
    """Evaluate one outcome per (ticker, emission-date) pair found in ``rows``.

    Deduplicates so the same ticker/day is only scored once, and caches each
    ticker's price series for the run.
    """
    benchmark_series = fetch_daily_closes(benchmark, fetcher)
    price_cache: dict[str, list[tuple[str, float]]] = {benchmark: benchmark_series}

    seen: set[tuple[str, str]] = set()
    outcomes: list[dict[str, object]] = []
    for row in rows:
        emission = _emission_date(row)
        if not emission:
            continue
        score = float(row.get("score", 0) or 0)
        for ticker in _row_tickers(row):
            key = (ticker, emission)
            if key in seen:
                continue
            seen.add(key)
            if ticker not in price_cache:
                price_cache[ticker] = fetch_daily_closes(ticker, fetcher)
            outcome = evaluate_outcome(ticker, emission, benchmark_series, fetcher, horizons)
            outcome["emission_date"] = emission
            outcome["score"] = score
            outcome["band"] = band_for_score(score)
            outcome["title"] = str((row.get("article") or {}).get("title") or "") if isinstance(row.get("article"), dict) else ""
            outcomes.append(outcome)
    return outcomes


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 3)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 3)


def summarize_outcomes(
    outcomes: list[dict[str, object]],
    horizons: tuple[int, ...] = HORIZONS,
) -> dict[str, object]:
    """Aggregate matured outcomes by band and horizon.

    For each band/horizon: matured sample size, hit rate (share with positive
    excess), mean and median excess, and mean raw return.
    """
    band_order = ["hard", "watch", "weak", "ignore"]
    by_band: dict[str, dict[str, object]] = {}
    for band in band_order:
        band_rows = [o for o in outcomes if o.get("band") == band]
        horizon_stats: dict[str, object] = {}
        for horizon in horizons:
            cells = [
                o["horizons"][str(horizon)]
                for o in band_rows
                if isinstance(o.get("horizons"), dict) and str(horizon) in o["horizons"]
            ]
            excess = [c["excess_pct"] for c in cells if c.get("matured") and isinstance(c.get("excess_pct"), (int, float))]
            raw = [c["return_pct"] for c in cells if c.get("matured") and isinstance(c.get("return_pct"), (int, float))]
            wins = sum(1 for value in excess if value > 0)
            horizon_stats[str(horizon)] = {
                "matured_n": len(excess),
                "hit_rate": round(wins / len(excess), 3) if excess else None,
                "mean_excess_pct": _mean(excess),
                "median_excess_pct": _median(excess),
                "mean_return_pct": _mean(raw),
            }
        by_band[band] = {
            "total_n": len(band_rows),
            "horizons": horizon_stats,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": BENCHMARK,
        "horizons": list(horizons),
        "total_outcomes": len(outcomes),
        "by_band": by_band,
        "calibration": _calibration_verdict(by_band, horizons),
    }


def _calibration_verdict(by_band: dict[str, dict[str, object]], horizons: tuple[int, ...]) -> dict[str, object]:
    """Check whether mean excess is monotonic across hard >= watch >= weak.

    A useful score model should rank: hard-band mean excess should exceed
    watch, which should exceed weak. Reports per-horizon monotonicity plus the
    longest-horizon spread (hard minus weak) as the headline edge estimate.
    """
    def cell_for(band: str, horizon: int) -> dict[str, object]:
        return by_band.get(band, {}).get("horizons", {}).get(str(horizon), {})

    verdict: dict[str, object] = {}
    for horizon in horizons:
        hard_c, watch_c, weak_c = cell_for("hard", horizon), cell_for("watch", horizon), cell_for("weak", horizon)
        hard, watch, weak = hard_c.get("mean_excess_pct"), watch_c.get("mean_excess_pct"), weak_c.get("mean_excess_pct")
        samples = [int(c.get("matured_n") or 0) for c in (hard_c, watch_c, weak_c)]
        # Need each scored band to have a usable sample before judging the rank.
        scored = [n for n in samples if n > 0]
        sufficient = bool(scored) and all(n >= MIN_CALIBRATION_SAMPLE for n in scored)

        ordered = [v for v in (hard, watch, weak) if v is not None]
        monotonic = None
        if sufficient and len(ordered) >= 2:
            monotonic = all(ordered[i] >= ordered[i + 1] for i in range(len(ordered) - 1))
        spread = None
        if hard is not None and weak is not None:
            spread = round(hard - weak, 3)
        verdict[str(horizon)] = {
            "monotonic_rank": monotonic,
            "hard_minus_weak_excess_pct": spread,
            "sufficient_sample": sufficient,
            "min_sample_required": MIN_CALIBRATION_SAMPLE,
        }
    return verdict


def build_performance_report(
    rows: list[dict[str, object]],
    fetcher: object | None = None,
    horizons: tuple[int, ...] = HORIZONS,
) -> dict[str, object]:
    outcomes = evaluate_rows(rows, fetcher, horizons)
    report = summarize_outcomes(outcomes, horizons)
    report["outcomes"] = outcomes
    return report
