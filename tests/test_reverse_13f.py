import json

from src.abnormal_news_radar.reverse_13f import find_institutional_holders

_INFO_TABLE = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><cusip>037833100</cusip>
    <value>1000000</value><shrsOrPrnAmt><sshPrnamt>5000</sshPrnamt></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>NVIDIA CORP</nameOfIssuer><cusip>67066G104</cusip>
    <value>5524754364</value><shrsOrPrnAmt><sshPrnamt>34969013</sshPrnamt></shrsOrPrnAmt></infoTable>
</informationTable>
"""


def _efts(_issuer, _start, _end, offset):
    if offset != 0:
        return json.dumps({"hits": {"hits": []}})
    return json.dumps({"hits": {"hits": [
        {"_id": "0001067983-26-000001:tableA.xml", "_source": {"display_names": ["BERKSHIRE HATHAWAY INC  (CIK 0001067983)"], "file_date": "2026-05-15"}},
        {"_id": "0001166588-26-000035:tableB.xml", "_source": {"display_names": ["BNP PARIBAS  (CIK 0001166588)"], "file_date": "2026-05-14"}},
        # Older duplicate of the same manager should be ignored.
        {"_id": "0001067983-25-000001:old.xml", "_source": {"display_names": ["BERKSHIRE HATHAWAY INC  (CIK 0001067983)"], "file_date": "2025-05-15"}},
    ]}})


def _doc(_url, **_kwargs):
    return _INFO_TABLE


def test_reverse_13f_finds_holders_with_shares_and_value():
    result = find_institutional_holders("NVIDIA CORP", efts_fetcher=_efts, doc_fetcher=_doc, include_notable=False)
    assert result["status"] == "ok"
    managers = {h["manager"] for h in result["holders"]}
    assert "BERKSHIRE HATHAWAY INC" in managers
    top = result["holders"][0]
    assert top["shares"] == 34969013
    assert top["value_usd"] == 5524754364
    # Deduped: each manager appears once (latest filing only).
    assert len(result["holders"]) == 2


def test_reverse_13f_matches_only_the_issuer_row():
    result = find_institutional_holders("NVIDIA CORP", efts_fetcher=_efts, doc_fetcher=_doc, include_notable=False)
    # Apple row in the same table must not be attributed to the NVIDIA query.
    assert all(h["shares"] == 34969013 for h in result["holders"])


def test_reverse_13f_no_holders():
    empty = lambda *a, **k: json.dumps({"hits": {"hits": []}})  # noqa: E731
    result = find_institutional_holders("NVIDIA CORP", efts_fetcher=empty, doc_fetcher=_doc, include_notable=False)
    assert result["status"] == "no_holders"
    assert result["holders"] == []


def test_reverse_13f_degrades_on_efts_error():
    def boom(*_a, **_k):
        raise RuntimeError("429")

    result = find_institutional_holders("NVIDIA CORP", efts_fetcher=boom, doc_fetcher=_doc, include_notable=False)
    assert result["status"] == "unavailable"


def test_reverse_13f_legacy_thousands_value_scaled():
    legacy = """<?xml version="1.0"?>
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable><nameOfIssuer>NVIDIA CORP</nameOfIssuer><cusip>67066G104</cusip>
        <value>50000</value><shrsOrPrnAmt><sshPrnamt>1000000</sshPrnamt></shrsOrPrnAmt></infoTable>
    </informationTable>"""
    result = find_institutional_holders("NVIDIA CORP", efts_fetcher=_efts, doc_fetcher=lambda *a, **k: legacy, include_notable=False)
    # value/shares < 1 -> legacy thousands -> scaled x1000 to ~$50M.
    assert result["holders"][0]["value_usd"] == 50_000_000
