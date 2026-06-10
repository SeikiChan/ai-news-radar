import urllib.error
from datetime import datetime, timezone

from src.abnormal_news_radar.positioning import (
    assess_positioning,
    fetch_short_volume_series,
)

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _finra_file(date_yyyymmdd, rows):
    lines = ["Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"]
    for symbol, short, total in rows:
        lines.append(f"{date_yyyymmdd}|{symbol}|{short}|0|{total}|B,Q,N")
    return "\n".join(lines) + "\n"


def _fetcher(ratio_by_date, symbol="CRDO"):
    """ratio_by_date: yyyymmdd -> short ratio; other dates 404 like FINRA."""

    def fetch(url):
        date = url.rsplit("CNMSshvol", 1)[1].split(".")[0]
        if date not in ratio_by_date:
            raise urllib.error.HTTPError(url, 404, "not found", None, None)
        ratio = ratio_by_date[date]
        return _finra_file(date, [(symbol, int(ratio * 1000), 1000)])

    return fetch


def _trading_days_back(count):
    """Weekday yyyymmdd strings walking back from NOW, newest first."""
    from datetime import timedelta

    days = []
    day = NOW.date()
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day.strftime("%Y%m%d"))
        day -= timedelta(days=1)
    return days


def test_series_parses_ratio_and_caches(tmp_path):
    days = _trading_days_back(3)
    fetcher = _fetcher({d: 0.5 for d in days})
    series = fetch_short_volume_series("CRDO", fetcher=fetcher, cache_dir=tmp_path, lookback_days=3, now=NOW)
    assert len(series) == 3
    assert series[-1]["ratio"] == 0.5
    assert series[0]["date"] < series[-1]["date"]
    assert (tmp_path / f"CNMSshvol{days[0]}.txt").exists()


def test_cached_file_is_not_refetched(tmp_path):
    days = _trading_days_back(1)
    calls = []

    def fetch(url):
        calls.append(url)
        return _finra_file(days[0], [("CRDO", 400, 1000)])

    fetch_short_volume_series("CRDO", fetcher=fetch, cache_dir=tmp_path, lookback_days=1, now=NOW)
    fetch_short_volume_series("CRDO", fetcher=fetch, cache_dir=tmp_path, lookback_days=1, now=NOW)
    assert len(calls) == 1


def test_falling_trend_reads_as_covering(tmp_path):
    days = _trading_days_back(10)
    ratios = {}
    for index, day in enumerate(days):  # newest first: recent low, prior high
        ratios[day] = 0.40 if index < 4 else 0.60
    result = assess_positioning("CRDO", fetcher=_fetcher(ratios), cache_dir=tmp_path, lookback_days=10, now=NOW)
    assert result["status"] == "ok"
    assert result["trend"] == "falling"
    assert "回落" in result["summary_zh"]


def test_rising_trend_reads_as_pressing(tmp_path):
    days = _trading_days_back(10)
    ratios = {}
    for index, day in enumerate(days):
        ratios[day] = 0.62 if index < 4 else 0.45
    result = assess_positioning("CRDO", fetcher=_fetcher(ratios), cache_dir=tmp_path, lookback_days=10, now=NOW)
    assert result["trend"] == "rising"
    assert result["level"] == "high"


def test_all_missing_degrades_to_unavailable(tmp_path):
    result = assess_positioning("CRDO", fetcher=_fetcher({}), cache_dir=tmp_path, lookback_days=5, now=NOW)
    assert result["status"] == "unavailable"
    assert "不可用" in result["summary_zh"]


def test_symbol_absent_from_files_is_unavailable(tmp_path):
    days = _trading_days_back(3)
    fetcher = _fetcher({d: 0.5 for d in days}, symbol="OTHR")
    result = assess_positioning("CRDO", fetcher=fetcher, cache_dir=tmp_path, lookback_days=3, now=NOW)
    assert result["status"] == "unavailable"
