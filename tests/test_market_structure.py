import json
from datetime import datetime, timezone

from src.abnormal_news_radar.market_structure import assess_market_structure

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _chain_payload(spot=100.0):
    # Heavy call OI well below spot -> cumulative net GEX flips positive far
    # under the current price = positive-gamma regime at spot.
    options = [
        {"option": "SPY260612P00070000", "gamma": 0.02, "open_interest": 100, "volume": 50, "iv": 0.20},
        {"option": "SPY260612C00080000", "gamma": 0.05, "open_interest": 4000, "volume": 800, "iv": 0.18},
        {"option": "SPY260717C00100000", "gamma": 0.03, "open_interest": 1000, "volume": 100, "iv": 0.17},
        {"option": "SPY260717P00100000", "gamma": 0.03, "open_interest": 900, "volume": 100, "iv": 0.17},
    ]
    return json.dumps({"data": {"symbol": "SPY", "current_price": spot, "iv30": 15.0,
                                "last_trade_time": "2026-06-10T16:00:00", "options": options}})


def _bearish_chain_payload(spot=100.0):
    options = [
        {"option": "SPY260612P00095000", "gamma": 0.06, "open_interest": 9000, "volume": 2000, "iv": 0.35},
        {"option": "SPY260612C00110000", "gamma": 0.01, "open_interest": 200, "volume": 50, "iv": 0.33},
    ]
    return json.dumps({"data": {"symbol": "SPY", "current_price": spot, "iv30": 30.0,
                                "last_trade_time": "2026-06-10T16:00:00", "options": options}})


def _finra(ratio_recent, ratio_prior):
    from datetime import timedelta

    days = []
    day = NOW.date()
    while len(days) < 10:
        if day.weekday() < 5:
            days.append(day.strftime("%Y%m%d"))
        day -= timedelta(days=1)

    def fetch(url):
        import urllib.error

        date = url.rsplit("CNMSshvol", 1)[1].split(".")[0]
        if date not in days:
            raise urllib.error.HTTPError(url, 404, "nf", None, None)
        ratio = ratio_recent if days.index(date) < 4 else ratio_prior
        header = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"
        return f"{header}\n{date}|AAA|{int(ratio * 1000)}|0|1000|B,Q,N\n{date}|BBB|{int(ratio * 500)}|0|500|B,Q,N\n"

    return fetch


def _vix_chart(level):
    def fetch(_url):
        return json.dumps({"chart": {"result": [{"meta": {}, "indicators": {"quote": [{"close": [level] * 60, "volume": [0] * 60}]}}]}})

    return fetch


def test_friendly_posture(tmp_path):
    result = assess_market_structure(
        cboe_fetcher=lambda _url: _chain_payload(),
        finra_fetcher=_finra(0.40, 0.60),  # falling = covering
        chart_fetcher=_vix_chart(14.0),
        data_dir=tmp_path,
        now=NOW,
    )
    assert result["status"] == "ok"
    assert result["posture"] == "friendly"
    assert "友好" in result["posture_zh"]
    assert result["spy"]["status"] == "ok"
    # SPX rides along as the full-notional "biggest bets" view (relabeled from _SPX).
    assert result["spx"]["status"] == "ok"
    assert result["spx"]["ticker"] == "SPX"
    assert "SPX GEX 集中位" in result["summary_zh"]
    assert result["dark_pool"]["trend"] == "falling"


def test_hostile_posture(tmp_path):
    result = assess_market_structure(
        cboe_fetcher=lambda _url: _bearish_chain_payload(),
        finra_fetcher=_finra(0.62, 0.45),  # rising = pressing
        chart_fetcher=_vix_chart(30.0),
        data_dir=tmp_path,
        now=NOW,
    )
    assert result["posture"] == "hostile"
    assert "偏谨慎" in result["posture_zh"]


def test_everything_unavailable_is_unknown(tmp_path):
    def boom(_url):
        raise RuntimeError("offline")

    result = assess_market_structure(
        cboe_fetcher=boom, finra_fetcher=boom, chart_fetcher=boom, data_dir=tmp_path, now=NOW
    )
    assert result["posture"] == "unknown"
