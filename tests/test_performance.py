import json
from datetime import datetime, timezone

from src.abnormal_news_radar.performance import (
    band_for_score,
    build_performance_report,
    evaluate_outcome,
    fetch_daily_closes,
    forward_returns,
    summarize_outcomes,
)


def _unix(date: str) -> int:
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())


def _chart_payload(dates_closes: list[tuple[str, float]]) -> str:
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": [_unix(d) for d, _c in dates_closes],
                        "indicators": {"quote": [{"close": [c for _d, c in dates_closes]}]},
                    }
                ]
            }
        }
    )


def _make_fetcher(series_by_symbol: dict[str, list[tuple[str, float]]]):
    def fetcher(url: str) -> str:
        symbol = url.split("/chart/")[1].split("?")[0]
        return _chart_payload(series_by_symbol.get(symbol, []))

    return fetcher


def test_band_for_score_boundaries():
    assert band_for_score(35) == "hard"
    assert band_for_score(34.9) == "watch"
    assert band_for_score(20) == "watch"
    assert band_for_score(10) == "weak"
    assert band_for_score(9.9) == "ignore"


def test_forward_returns_anchors_on_first_trading_day():
    series = [("2026-01-05", 100.0), ("2026-01-06", 110.0), ("2026-01-07", 121.0)]
    out = forward_returns(series, "2026-01-05", horizons=(1, 2))
    assert out[1]["return_pct"] == 10.0
    assert out[1]["matured"] is True
    assert out[2]["return_pct"] == 21.0
    # Emission falls on a weekend/holiday -> anchor on the next available day.
    out2 = forward_returns(series, "2026-01-04", horizons=(1,))
    assert out2[1]["from"] == "2026-01-05"
    assert out2[1]["return_pct"] == 10.0


def test_forward_returns_marks_unmatured_when_window_exceeds_series():
    series = [("2026-01-05", 100.0), ("2026-01-06", 110.0)]
    out = forward_returns(series, "2026-01-05", horizons=(5,))
    assert out[5]["matured"] is False
    assert out[5]["return_pct"] is None


def test_evaluate_outcome_computes_excess_over_benchmark():
    fetcher = _make_fetcher(
        {
            "AAA": [("2026-01-05", 100.0), ("2026-01-06", 110.0)],
            "SPY": [("2026-01-05", 100.0), ("2026-01-06", 102.0)],
        }
    )
    bench = fetch_daily_closes("SPY", fetcher)
    out = evaluate_outcome("AAA", "2026-01-05", bench, fetcher, horizons=(1,))
    cell = out["horizons"]["1"]
    assert cell["return_pct"] == 10.0
    assert cell["benchmark_return_pct"] == 2.0
    assert cell["excess_pct"] == 8.0


def test_evaluate_outcome_handles_missing_price_data():
    fetcher = _make_fetcher({"SPY": [("2026-01-05", 100.0)]})
    out = evaluate_outcome("ZZZ", "2026-01-05", [], fetcher, horizons=(1,))
    assert out["status"] == "no_price_data"


def test_build_report_aggregates_and_calibrates():
    # hard-band winner beats SPY, weak-band loser lags SPY -> monotonic edge.
    fetcher = _make_fetcher(
        {
            "WIN": [("2026-01-05", 100.0), ("2026-01-06", 120.0)],
            "LOSE": [("2026-01-05", 100.0), ("2026-01-06", 95.0)],
            "SPY": [("2026-01-05", 100.0), ("2026-01-06", 100.0)],
        }
    )
    rows = [
        {"score": 40.0, "tickers": ["WIN"], "article": {"fetched_at": "2026-01-05T12:00:00+00:00", "title": "win"}},
        {"score": 12.0, "tickers": ["LOSE"], "article": {"fetched_at": "2026-01-05T12:00:00+00:00", "title": "lose"}},
    ]
    report = build_performance_report(rows, fetcher=fetcher, horizons=(1,))
    assert report["total_outcomes"] == 2
    hard = report["by_band"]["hard"]["horizons"]["1"]
    weak = report["by_band"]["weak"]["horizons"]["1"]
    assert hard["mean_excess_pct"] == 20.0
    assert hard["hit_rate"] == 1.0
    assert weak["mean_excess_pct"] == -5.0
    assert weak["hit_rate"] == 0.0
    cal = report["calibration"]["1"]
    # One sample per band is below MIN_CALIBRATION_SAMPLE, so no rank verdict yet.
    assert cal["sufficient_sample"] is False
    assert cal["monotonic_rank"] is None
    # The headline spread is still reported regardless of sample size.
    assert cal["hard_minus_weak_excess_pct"] == 25.0


def test_calibration_rank_when_sample_sufficient(monkeypatch):
    from src.abnormal_news_radar import performance

    monkeypatch.setattr(performance, "MIN_CALIBRATION_SAMPLE", 1)
    fetcher = _make_fetcher(
        {
            "WIN": [("2026-01-05", 100.0), ("2026-01-06", 120.0)],
            "LOSE": [("2026-01-05", 100.0), ("2026-01-06", 95.0)],
            "SPY": [("2026-01-05", 100.0), ("2026-01-06", 100.0)],
        }
    )
    rows = [
        {"score": 40.0, "tickers": ["WIN"], "article": {"fetched_at": "2026-01-05T12:00:00+00:00"}},
        {"score": 12.0, "tickers": ["LOSE"], "article": {"fetched_at": "2026-01-05T12:00:00+00:00"}},
    ]
    report = performance.build_performance_report(rows, fetcher=fetcher, horizons=(1,))
    cal = report["calibration"]["1"]
    assert cal["sufficient_sample"] is True
    assert cal["monotonic_rank"] is True


def test_evaluate_rows_dedupes_ticker_day():
    fetcher = _make_fetcher(
        {
            "AAA": [("2026-01-05", 100.0), ("2026-01-06", 110.0)],
            "SPY": [("2026-01-05", 100.0), ("2026-01-06", 100.0)],
        }
    )
    rows = [
        {"score": 40.0, "tickers": ["AAA"], "article": {"fetched_at": "2026-01-05T01:00:00+00:00"}},
        {"score": 22.0, "tickers": ["AAA"], "article": {"fetched_at": "2026-01-05T09:00:00+00:00"}},
    ]
    report = build_performance_report(rows, fetcher=fetcher, horizons=(1,))
    assert report["total_outcomes"] == 1


def test_summarize_handles_empty():
    summary = summarize_outcomes([], horizons=(1, 5))
    assert summary["total_outcomes"] == 0
    assert summary["by_band"]["hard"]["total_n"] == 0
