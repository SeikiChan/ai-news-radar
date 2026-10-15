import json
from datetime import datetime, timezone

from src.abnormal_news_radar.gamma import assess_options_structure

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
SPOT = 100.0


def _contract(symbol, gamma, oi, volume, iv):
    return {
        "option": symbol,
        "gamma": gamma,
        "open_interest": oi,
        "volume": volume,
        "iv": iv,
        "delta": 0.5,
    }


def _payload(options, spot=SPOT, iv30=45.0):
    return json.dumps(
        {
            "data": {
                "symbol": "TST",
                "current_price": spot,
                "iv30": iv30,
                "last_trade_time": "2026-06-10T16:00:00",
                "options": options,
            }
        }
    )


def _chain():
    # front expiry 2026-06-12 (dte 2), back expiry 2026-07-17 (dte 37).
    return [
        # heavy put OI low strike -> negative GEX at 90, put wall there
        _contract("TST260612P00090000", 0.05, 3000, 500, 0.80),
        _contract("TST260612C00090000", 0.01, 100, 10, 0.80),
        # calls clustered at 110 -> call wall and positive GEX above spot
        _contract("TST260612C00110000", 0.05, 4000, 800, 0.78),
        _contract("TST260612P00110000", 0.01, 200, 20, 0.78),
        # back month, calmer IV -> term inversion vs the 0.80 front
        _contract("TST260717C00100000", 0.03, 1000, 100, 0.50),
        _contract("TST260717P00100000", 0.03, 900, 100, 0.50),
    ]


def _fetcher(payload):
    def fetch(url):
        if isinstance(payload, Exception):
            raise payload
        return payload

    return fetch


def test_gex_profile_peaks_and_no_invalid_flip(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    assert result["status"] == "ok"
    gex = result["gex"]
    assert gex["status"] == "ok"
    assert gex["call_wall"] == 110.0
    assert gex["put_wall"] == 90.0
    # A cumulative zero across strikes is not a hypothetical spot gamma flip.
    assert gex["flip_level"] is None
    assert gex["flip_status"] == "not_estimated"
    assert "假设价格" in gex["flip_reason_zh"]
    assert gex["regime"] in {"positive_gamma", "negative_gamma"}


def test_put_call_ratios(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    pc = result["put_call"]
    assert pc["put_oi"] == 3000 + 200 + 900
    assert pc["call_oi"] == 100 + 4000 + 1000
    assert pc["oi_ratio"] is not None


def test_term_structure_inversion_detected(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    term = result["iv_term"]
    assert term["status"] == "ok"
    assert term["inverted"] is True
    assert "倒挂" in result["summary_zh"]


def test_snapshot_written_once_per_day(tmp_path):
    history = tmp_path / "h.jsonl"
    fetcher = _fetcher(_payload(_chain()))
    assess_options_structure("TST", fetcher=fetcher, history_path=history, now=NOW)
    assess_options_structure("TST", fetcher=fetcher, history_path=history, now=NOW)
    lines = history.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["ticker"] == "TST"
    assert row["iv30"] == 45.0


def test_iv_rank_accumulating_until_history(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    assert result["iv_rank"]["status"] == "accumulating"


def test_fetch_failure_degrades(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(RuntimeError("boom")), history_path=tmp_path / "h.jsonl", now=NOW
    )
    assert result["status"] == "unavailable"
    assert "不在缺数据时伪造" in result["summary_zh"]


def test_strike_map_top_oi_and_volume(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    strike_map = result["strike_map"]
    assert strike_map["status"] == "ok"
    assert strike_map["max_call_oi_strike"] == 110.0  # 4000 OI calls
    assert strike_map["max_put_oi_strike"] == 90.0  # 3000 OI puts
    assert strike_map["max_volume_strike"] == 110.0  # 800+20 volume
    strikes = [row["strike"] for row in strike_map["top_oi"]]
    assert strikes == sorted(strikes)
    assert "未平仓量最高" in strike_map["summary_zh"]


def test_strike_chart_has_per_strike_gex_and_oi(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    chart = result["strike_chart"]
    assert chart["status"] == "ok"
    assert chart["spot"] == SPOT
    strikes = [bar["strike"] for bar in chart["bars"]]
    assert strikes == sorted(strikes)  # ascending for the ladder
    by_strike = {bar["strike"]: bar for bar in chart["bars"]}
    # 110 strike: heavy call OI -> positive net GEX, call OI > put OI.
    assert by_strike[110.0]["net_gex_usd"] > 0
    assert by_strike[110.0]["call_oi"] == 4000
    # 90 strike: heavy put OI -> negative net GEX.
    assert by_strike[90.0]["net_gex_usd"] < 0
    assert by_strike[90.0]["put_oi"] == 3000
    # reference levels ride along for the chart overlay
    assert chart["call_wall"] == 110.0
    assert chart["put_wall"] == 90.0


def test_honesty_note_present(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    assert "不代表真实做市商仓位" in result["source_policy_zh"]
