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


def test_gex_profile_walls_and_flip(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    assert result["status"] == "ok"
    gex = result["gex"]
    assert gex["status"] == "ok"
    assert gex["call_wall"] == 110.0
    assert gex["put_wall"] == 90.0
    # cumulative profile starts negative at 90 and crosses zero before 110
    assert gex["flip_level"] is not None
    assert 90.0 < gex["flip_level"] <= 110.0
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


def test_honesty_note_present(tmp_path):
    result = assess_options_structure(
        "TST", fetcher=_fetcher(_payload(_chain())), history_path=tmp_path / "h.jsonl", now=NOW
    )
    assert "不是真实做市商持仓" in result["source_policy_zh"]
