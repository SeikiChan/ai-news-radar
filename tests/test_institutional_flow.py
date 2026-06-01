import json

from src.abnormal_news_radar.institutional_flow import (
    enrich_candidates_with_institutional_flow,
    fetch_institutional_flow,
)


def _summary(holders, pct_held=0.7, count=2500):
    return json.dumps({
        "quoteSummary": {"result": [{
            "majorHoldersBreakdown": {
                "institutionsPercentHeld": {"raw": pct_held},
                "institutionsCount": {"raw": count},
            },
            "institutionOwnership": {
                "ownershipList": [
                    {"organization": h[0], "position": {"raw": h[1]}, "pctChange": {"raw": h[2]},
                     "pctHeld": {"raw": 0.05}}
                    for h in holders
                ]
            },
        }]}
    })


def _fetcher(holders_by_symbol):
    def fetch(url):
        symbol = url.split("/quoteSummary/")[1].split("?")[0]
        if symbol not in holders_by_symbol:
            raise RuntimeError("429 Too Many Requests")
        return _summary(holders_by_symbol[symbol])
    return fetch


def _candidate(ticker):
    return {"tickers": [ticker], "score": 40.0}


def test_fetch_parses_holders_and_breakdown():
    reading = fetch_institutional_flow("NVDA", _fetcher({"NVDA": [("Vanguard", 1000, 0.10)]}))
    assert reading["status"] == "ok"
    assert reading["institutions_pct_held"] == 0.7
    assert reading["holders"][0]["pct_change"] == 0.10


def test_accumulation_detected():
    holders = [("A", 1000, 0.20), ("B", 800, 0.10), ("C", 500, 0.05)]
    rows = enrich_candidates_with_institutional_flow([_candidate("AAA")], fetcher=_fetcher({"AAA": holders}))
    flow = rows[0]["institutional_flow"]
    assert flow["flow"] == "accumulation"
    assert flow["accumulators"] == 3
    assert flow["reducers"] == 0


def test_distribution_detected():
    holders = [("A", 1000, -0.20), ("B", 800, -0.15), ("C", 500, -0.05)]
    rows = enrich_candidates_with_institutional_flow([_candidate("BBB")], fetcher=_fetcher({"BBB": holders}))
    flow = rows[0]["institutional_flow"]
    assert flow["flow"] == "distribution"
    assert flow["reducers"] == 3


def test_mixed_when_offsetting():
    # Equal position with offsetting +/-10% changes -> net share delta within the
    # neutral band -> mixed (one accumulator, one reducer).
    holders = [("A", 1000, 0.10), ("B", 1000, -0.10)]
    rows = enrich_candidates_with_institutional_flow([_candidate("CCC")], fetcher=_fetcher({"CCC": holders}))
    assert rows[0]["institutional_flow"]["flow"] == "mixed"


def test_unavailable_degrades():
    rows = enrich_candidates_with_institutional_flow([_candidate("ZZZ")], fetcher=_fetcher({}))
    assert rows[0]["institutional_flow"]["status"] == "unavailable"
    assert rows[0]["institutional_flow"]["flow"] == "unknown"


def test_no_ticker():
    rows = enrich_candidates_with_institutional_flow([{"tickers": [], "score": 40.0}], fetcher=_fetcher({}))
    assert rows[0]["institutional_flow"]["status"] == "no_ticker"
