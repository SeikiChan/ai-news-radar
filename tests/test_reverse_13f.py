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


_PREV_INFO_TABLE = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>NVIDIA CORP</nameOfIssuer><cusip>67066G104</cusip>
    <value>4500000000</value><shrsOrPrnAmt><sshPrnamt>30000000</sshPrnamt></shrsOrPrnAmt></infoTable>
</informationTable>
"""


def _doc_with_history(prev_table=_PREV_INFO_TABLE):
    """Route submissions/index/info-table URLs so the QoQ diff can resolve."""

    def doc(url, **_kwargs):
        if "data.sec.gov/submissions/" in url:
            return json.dumps({"filings": {"recent": {
                "form": ["13F-HR", "13F-HR"],
                "accessionNumber": ["0001067983-26-000001", "0001067983-25-000077"],
                "filingDate": ["2026-05-15", "2026-02-14"],
            }}})
        if url.endswith("/index.json"):
            return json.dumps({"directory": {"item": [{"name": "prev_infotable.xml"}]}})
        if "prev_infotable.xml" in url:
            return prev_table
        return _INFO_TABLE

    return doc


def _single_manager_efts(_issuer, _start, _end, offset):
    if offset != 0:
        return json.dumps({"hits": {"hits": []}})
    return json.dumps({"hits": {"hits": [
        {"_id": "0001067983-26-000001:tableA.xml", "_source": {"display_names": ["BERKSHIRE HATHAWAY INC  (CIK 0001067983)"], "file_date": "2026-05-15"}},
    ]}})


def test_reverse_13f_qoq_increase_detected():
    result = find_institutional_holders(
        "NVIDIA CORP", efts_fetcher=_single_manager_efts, doc_fetcher=_doc_with_history(), include_notable=False
    )
    holder = result["holders"][0]
    assert holder["change_label"] == "increased"
    assert holder["prev_shares"] == 30000000
    assert holder["change_pct"] == 16.6  # 34,969,013 vs 30,000,000
    assert "加仓" in holder["change_zh"]
    assert "1 家加仓" in result["summary_zh"]


def test_reverse_13f_qoq_new_position_detected():
    no_nvda = """<?xml version="1.0"?>
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><cusip>037833100</cusip>
        <value>1000000</value><shrsOrPrnAmt><sshPrnamt>5000</sshPrnamt></shrsOrPrnAmt></infoTable>
    </informationTable>"""
    result = find_institutional_holders(
        "NVIDIA CORP", efts_fetcher=_single_manager_efts, doc_fetcher=_doc_with_history(no_nvda), include_notable=False
    )
    holder = result["holders"][0]
    assert holder["change_label"] == "new"
    assert holder["change_zh"] == "新建仓"


def test_reverse_13f_progress_reports_stages():
    stages = []
    find_institutional_holders(
        "NVIDIA CORP",
        efts_fetcher=_single_manager_efts,
        doc_fetcher=_doc_with_history(),
        include_notable=False,
        progress=lambda stage, done, total: stages.append((stage, done, total)),
    )
    names = [stage for stage, _, _ in stages]
    assert names[0] == "全文检索 13F 申报"
    assert "解析各机构信息表" in names
    assert "对比各机构上一季持仓" in names
    assert names[-1] == "完成"


def test_reverse_13f_qoq_unavailable_degrades():
    # The plain _doc fetcher returns XML for the submissions URL too -> the
    # diff cannot resolve and must degrade to unknown, never break the result.
    result = find_institutional_holders("NVIDIA CORP", efts_fetcher=_efts, doc_fetcher=_doc, include_notable=False)
    assert result["status"] == "ok"
    assert all(h.get("change_label") == "unknown" for h in result["holders"])


def test_reverse_13f_legacy_thousands_value_scaled():
    legacy = """<?xml version="1.0"?>
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable><nameOfIssuer>NVIDIA CORP</nameOfIssuer><cusip>67066G104</cusip>
        <value>50000</value><shrsOrPrnAmt><sshPrnamt>1000000</sshPrnamt></shrsOrPrnAmt></infoTable>
    </informationTable>"""
    result = find_institutional_holders("NVIDIA CORP", efts_fetcher=_efts, doc_fetcher=lambda *a, **k: legacy, include_notable=False)
    # value/shares < 1 -> legacy thousands -> scaled x1000 to ~$50M.
    assert result["holders"][0]["value_usd"] == 50_000_000
