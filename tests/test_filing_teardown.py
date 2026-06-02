from src.abnormal_news_radar.filing_teardown import build_name_index, teardown_filing
from src.abnormal_news_radar.model import Company

_CIK_MAP = {
    "MSFT": {"cik": 789019, "name": "Microsoft Corporation"},
    "MRVL": {"cik": 1835632, "name": "Marvell Technology, Inc."},
}

_HTML = """
<html><body>
<p>In April 2026, the Company completed the acquisition of Marvell Technology for $1,200 million.</p>
<p>We entered into a multi-year purchase commitment of $800 million with Microsoft for manufacturing capacity.</p>
<p>One customer represented 16% of total revenue during the quarter.</p>
<p>The Company repurchased $5,000 million of common stock under its buyback program.</p>
</body></html>
"""


def test_build_name_index_normalizes_names():
    index = build_name_index(_CIK_MAP, [])
    # Only legal-entity suffixes are stripped; distinctive words are kept.
    assert index["marvell technology"]["ticker"] == "MRVL"
    assert index["microsoft"]["ticker"] == "MSFT"


def test_teardown_resolves_companies_orders_and_concentration():
    index = build_name_index(_CIK_MAP, [Company(ticker="NVDA", name="NVIDIA", aliases=("NVIDIA",), themes=())])
    result = teardown_filing("https://sec/x.htm", index, fetcher=lambda _url: _HTML)
    assert result["status"] == "ok"

    tickers = {c["ticker"] for c in result["named_companies"]}
    assert "MRVL" in tickers and "MSFT" in tickers
    mrvl = next(c for c in result["named_companies"] if c["ticker"] == "MRVL")
    assert mrvl["relation"] == "acquisition"

    flows = result["money_flows"]
    # The acquisition amount is classified in Chinese and points at the target.
    acq = next(f for f in flows if f["purpose_zh"] == "收购")
    assert abs(acq["amount_musd"] - 1200.0) < 0.01
    assert acq["target_ticker"] == "MRVL"
    # The supply commitment resolves to Microsoft.
    supply = next(f for f in flows if f["purpose_zh"].startswith("采购承诺"))
    assert supply["target_ticker"] == "MSFT"
    # The buyback is classified too.
    assert any(f["purpose_zh"] == "股票回购" for f in flows)
    assert any(abs(c["pct"] - 16.0) < 0.01 for c in result["customer_concentration"])


def test_teardown_degrades_on_fetch_error():
    def boom(_url):
        raise RuntimeError("403")

    result = teardown_filing("https://sec/x.htm", {}, fetcher=boom)
    assert result["status"] == "unavailable"


def test_teardown_empty_document():
    result = teardown_filing("https://sec/x.htm", {}, fetcher=lambda _u: "<html><body></body></html>")
    assert result["status"] == "empty"
