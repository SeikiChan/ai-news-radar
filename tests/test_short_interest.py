import json

from src.abnormal_news_radar.short_interest import (
    ALERT_LABEL,
    enrich_candidates_with_short_interest,
    fetch_short_percent_of_float,
)


def _summary(spf):
    stats = {}
    if spf is not None:
        stats["shortPercentOfFloat"] = {"raw": spf}
        stats["sharesShort"] = {"raw": 1_000_000}
        stats["shortRatio"] = {"raw": 5.0}
    return json.dumps({"quoteSummary": {"result": [{"defaultKeyStatistics": stats}]}})


def _fetcher(spf_by_symbol):
    def fetch(url):
        symbol = url.split("/quoteSummary/")[1].split("?")[0]
        if symbol not in spf_by_symbol:
            raise RuntimeError("429 Too Many Requests")
        return _summary(spf_by_symbol[symbol])

    return fetch


def _candidate(ticker, score):
    return {"tickers": [ticker], "score": score}


def test_fetch_parses_short_percent_of_float():
    reading = fetch_short_percent_of_float("GME", _fetcher({"GME": 0.22}))
    assert reading["status"] == "ok"
    assert reading["short_percent_of_float"] == 0.22


def test_high_short_plus_hard_catalyst_fires_alert():
    rows = enrich_candidates_with_short_interest([_candidate("GME", 45.0)], fetcher=_fetcher({"GME": 0.22}))
    sq = rows[0]["short_squeeze"]
    assert sq["alert"] is True
    assert sq["potential"] == "high"
    assert sq["label"] == ALERT_LABEL


def test_high_short_but_weak_catalyst_no_alert():
    rows = enrich_candidates_with_short_interest([_candidate("GME", 18.0)], fetcher=_fetcher({"GME": 0.22}))
    sq = rows[0]["short_squeeze"]
    assert sq["alert"] is False
    assert sq["potential"] == "high"  # still flagged as squeeze-prone


def test_low_short_no_alert():
    rows = enrich_candidates_with_short_interest([_candidate("NVDA", 60.0)], fetcher=_fetcher({"NVDA": 0.012}))
    sq = rows[0]["short_squeeze"]
    assert sq["alert"] is False
    assert sq["potential"] == "low"


def test_unavailable_data_degrades_without_alert():
    # Fetcher raises (simulating Yahoo 429) -> unavailable, never a false alert.
    rows = enrich_candidates_with_short_interest([_candidate("ZZZ", 90.0)], fetcher=_fetcher({}))
    sq = rows[0]["short_squeeze"]
    assert sq["status"] == "unavailable"
    assert sq["alert"] is False


def test_no_ticker():
    rows = enrich_candidates_with_short_interest([{"tickers": [], "score": 90.0}], fetcher=_fetcher({}))
    assert rows[0]["short_squeeze"]["status"] == "no_ticker"


def test_no_network_calls_when_no_tickers():
    def exploding_fetcher(_url):
        raise AssertionError("should not fetch when there are no tickers")

    rows = enrich_candidates_with_short_interest([{"tickers": [], "score": 90.0}], fetcher=exploding_fetcher)
    assert rows[0]["short_squeeze"]["status"] == "no_ticker"
