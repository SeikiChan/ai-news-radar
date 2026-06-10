import json

from src.abnormal_news_radar.relative_strength import assess_relative_strength


def _chart_payload(closes, live=None, volumes=None):
    volume_list = volumes if volumes is not None else [1_000_000] * len(closes)
    meta = {}
    if live is not None:
        meta = {"regularMarketPrice": live, "regularMarketVolume": 2_000_000, "regularMarketTime": 1781035201}
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": meta,
                        "indicators": {"quote": [{"close": closes, "volume": volume_list}]},
                    }
                ]
            }
        }
    )


def _series(start, end, points=260):
    step = (end - start) / (points - 1)
    return [round(start + step * index, 4) for index in range(points)]


def _fetcher(by_symbol):
    def fetch(url):
        symbol = url.split("/chart/")[1].split("?")[0]
        if symbol not in by_symbol:
            raise RuntimeError(f"no fake series for {symbol}")
        return by_symbol[symbol]

    return fetch


def _flat(level, points=260):
    return [level] * points


def test_sector_driven_drop_detected():
    # Stock -20% over last 20 days, sector ETF -15%, SPY flat.
    stock = _flat(100.0, 240) + _series(100.0, 80.0, 21)[1:]
    sector = _flat(50.0, 240) + _series(50.0, 42.5, 21)[1:]
    spy = _flat(400.0)
    fetcher = _fetcher({"CRDO": _chart_payload(stock), "XLK": _chart_payload(sector), "SPY": _chart_payload(spy)})
    result = assess_relative_strength("CRDO", fetcher=fetcher, sector_etf="XLK")
    assert result["status"] == "ok"
    attribution = result["attribution"]
    assert attribution["verdict"] == "sector_driven"
    assert attribution["sector_share_of_drop"] >= 0.6
    assert "陪葬" in result["summary_zh"]


def test_idiosyncratic_drop_detected():
    stock = _flat(100.0, 240) + _series(100.0, 75.0, 21)[1:]
    sector = _flat(50.0)
    spy = _flat(400.0)
    fetcher = _fetcher({"CRDO": _chart_payload(stock), "XLK": _chart_payload(sector), "SPY": _chart_payload(spy)})
    result = assess_relative_strength("CRDO", fetcher=fetcher, sector_etf="XLK")
    assert result["attribution"]["verdict"] == "idiosyncratic"
    assert "不能假设错杀" in result["summary_zh"]


def test_spy_proxy_when_sector_missing():
    stock = _flat(100.0, 240) + _series(100.0, 80.0, 21)[1:]
    spy = _flat(400.0, 240) + _series(400.0, 340.0, 21)[1:]
    fetcher = _fetcher({"CRDO": _chart_payload(stock), "SPY": _chart_payload(spy)})

    def failing_profile(url):
        raise RuntimeError("429")

    result = assess_relative_strength("CRDO", fetcher=fetcher, profile_fetcher=failing_profile)
    assert result["attribution"]["benchmark_is_spy_proxy"] is True
    assert result["attribution"]["verdict"] == "sector_driven"


def test_stale_null_close_uses_meta_live_price():
    closes = _flat(100.0, 259) + [None]
    fetcher = _fetcher(
        {
            "CRDO": _chart_payload(closes, live=90.0),
            "XLK": _chart_payload(_flat(50.0)),
            "SPY": _chart_payload(_flat(400.0)),
        }
    )
    result = assess_relative_strength("CRDO", fetcher=fetcher, sector_etf="XLK")
    assert result["trend"]["price"] == 90.0


def test_short_history_unavailable():
    fetcher = _fetcher({"CRDO": _chart_payload(_flat(100.0, 10))})
    result = assess_relative_strength("CRDO", fetcher=fetcher, sector_etf="XLK")
    assert result["status"] == "unavailable"


def test_rsi_extremes():
    rising = _series(50.0, 150.0)
    fetcher = _fetcher(
        {"CRDO": _chart_payload(rising), "XLK": _chart_payload(_flat(50.0)), "SPY": _chart_payload(_flat(400.0))}
    )
    result = assess_relative_strength("CRDO", fetcher=fetcher, sector_etf="XLK")
    assert result["trend"]["rsi_14"] == 100.0
    assert result["trend"]["ma_stack"] == "uptrend_stack"
