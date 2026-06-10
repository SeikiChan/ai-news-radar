import json
import urllib.error
from datetime import datetime, timezone

from src.abnormal_news_radar.diagnose import diagnose_ticker

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _chart_payload(closes):
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {},
                        "indicators": {"quote": [{"close": closes, "volume": [1_000_000] * len(closes)}]},
                    }
                ]
            }
        }
    )


def _series(start, end, points):
    step = (end - start) / (points - 1)
    return [round(start + step * index, 4) for index in range(points)]


def _chart_fetcher():
    stock = [100.0] * 240 + _series(100.0, 70.0, 21)[1:]
    sector = [50.0] * 240 + _series(50.0, 39.0, 21)[1:]
    by_symbol = {
        "CRDO": _chart_payload(stock),
        "XLK": _chart_payload(sector),
        "SPY": _chart_payload([400.0] * 260),
        "%5EVIX": _chart_payload([22.0] * 60),
    }

    def fetch(url):
        symbol = url.split("/chart/")[1].split("?")[0]
        return by_symbol[symbol]

    return fetch


def _yahoo_fetcher(url):
    if "assetProfile" in url:
        return json.dumps({"quoteSummary": {"result": [{"assetProfile": {"sector": "Technology"}}]}})
    return json.dumps(
        {
            "quoteSummary": {
                "result": [
                    {
                        "defaultKeyStatistics": {
                            "shortPercentOfFloat": {"raw": 0.18},
                            "sharesShort": {"raw": 1_000_000},
                            "floatShares": {"raw": 5_000_000},
                            "shortRatio": {"raw": 4.0},
                            "dateShortInterest": {"raw": 1781000000},
                        }
                    }
                ]
            }
        }
    )


def _finra_fetcher():
    from datetime import timedelta

    days = []
    day = NOW.date()
    while len(days) < 10:
        if day.weekday() < 5:
            days.append(day.strftime("%Y%m%d"))
        day -= timedelta(days=1)

    def fetch(url):
        date = url.rsplit("CNMSshvol", 1)[1].split(".")[0]
        if date not in days:
            raise urllib.error.HTTPError(url, 404, "not found", None, None)
        ratio = 0.40 if days.index(date) < 4 else 0.60  # falling = covering
        header = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"
        return f"{header}\n{date}|CRDO|{int(ratio * 1000)}|0|1000|B,Q,N\n"

    return fetch


def _cboe_fetcher(url):
    options = [
        {"option": "CRDO260612P00060000", "gamma": 0.05, "open_interest": 3000, "volume": 500, "iv": 0.95},
        {"option": "CRDO260612C00080000", "gamma": 0.05, "open_interest": 2500, "volume": 800, "iv": 0.90},
        {"option": "CRDO260717C00070000", "gamma": 0.03, "open_interest": 1000, "volume": 100, "iv": 0.55},
        {"option": "CRDO260717P00070000", "gamma": 0.03, "open_interest": 1500, "volume": 100, "iv": 0.55},
    ]
    return json.dumps(
        {
            "data": {
                "symbol": "CRDO",
                "current_price": 70.0,
                "iv30": 80.0,
                "last_trade_time": "2026-06-10T16:00:00",
                "options": options,
            }
        }
    )


def _write_signals(data_dir):
    row = {
        "article": {
            "title": "Credo receives $100M capacity prepayment",
            "link": "https://example.com/crdo",
            "published": "Mon, 01 Jun 2026 22:00 GMT",
            "fetched_at": "2026-06-01T23:00:00+00:00",
        },
        "tickers": ["CRDO"],
        "score": 50.0,
        "evidence_tier": "hard_evidence",
        "matched_terms": ["prepayment"],
    }
    (data_dir / "signals.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")


def _diagnose(tmp_path):
    _write_signals(tmp_path)
    return diagnose_ticker(
        "CRDO",
        chart_fetcher=_chart_fetcher(),
        finra_fetcher=_finra_fetcher(),
        cboe_fetcher=_cboe_fetcher,
        yahoo_fetcher=_yahoo_fetcher,
        data_dir=tmp_path,
        now=NOW,
    )


def test_full_diagnosis_composes_all_components(tmp_path):
    result = _diagnose(tmp_path)
    assert result["status"] == "ok"
    assert result["premise"]["in_drawdown"] is True
    assert 0 <= result["score"] <= 100
    assert result["verdict"] in {"mispriced_candidate", "watchlist", "high_risk_or_unproven"}
    names = [component["name"] for component in result["score_components"]]
    assert names == ["跌幅归因", "卖压衰竭", "空头行为", "期权结构", "基本面证据"]
    assert result["triggers_zh"]


def test_sector_driven_drop_scores_high(tmp_path):
    result = _diagnose(tmp_path)
    attribution_component = result["score_components"][0]
    assert attribution_component["points"] == 25  # sector explains most of the drop
    evidence_component = result["score_components"][4]
    assert evidence_component["points"] == 15  # hard evidence hit found
    assert result["components"]["radar_news"]["hard_evidence_hits"] == 1


def test_diagnosis_archived_once_per_day(tmp_path):
    _diagnose(tmp_path)
    _diagnose(tmp_path)
    lines = (tmp_path / "diagnoses.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["ticker"] == "CRDO"
    assert row["verdict"] == json.loads(lines[0])["verdict"]


def test_no_drawdown_blocks_actionable_verdict(tmp_path):
    _write_signals(tmp_path)

    def flat_chart(url):
        symbol = url.split("/chart/")[1].split("?")[0]
        closes = [100.0] * 260 if symbol == "CRDO" else [50.0] * 260
        if symbol == "%5EVIX":
            closes = [18.0] * 60
        return _chart_payload(closes)

    result = diagnose_ticker(
        "CRDO",
        chart_fetcher=flat_chart,
        finra_fetcher=_finra_fetcher(),
        cboe_fetcher=_cboe_fetcher,
        yahoo_fetcher=_yahoo_fetcher,
        data_dir=tmp_path,
        now=NOW,
    )
    assert result["premise"]["in_drawdown"] is False
    assert result["verdict"] == "no_mispricing_premise"
    assert result["score"] <= 30
    assert "等待错杀前提" in result["triggers_zh"][0]


def test_missing_chart_data_is_insufficient(tmp_path):
    def broken_chart(url):
        raise RuntimeError("offline")

    result = diagnose_ticker(
        "CRDO",
        chart_fetcher=broken_chart,
        finra_fetcher=_finra_fetcher(),
        cboe_fetcher=_cboe_fetcher,
        yahoo_fetcher=_yahoo_fetcher,
        data_dir=tmp_path,
        now=NOW,
    )
    assert result["status"] == "insufficient_data"
