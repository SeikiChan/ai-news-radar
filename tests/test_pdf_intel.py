from src.abnormal_news_radar.pdf_intel import (
    enrich_candidates_with_pdf_intel,
    fetch_pdf_text,
    resolve_pdf_url,
)


def test_resolve_arxiv_abs_to_pdf():
    assert resolve_pdf_url("https://arxiv.org/abs/2601.01234") == "https://arxiv.org/pdf/2601.01234"


def test_resolve_direct_pdf_link():
    assert resolve_pdf_url("https://example.com/ir/q1.pdf") == "https://example.com/ir/q1.pdf"


def test_resolve_arxiv_pdf_link_passthrough():
    assert resolve_pdf_url("https://arxiv.org/pdf/2601.01234") == "https://arxiv.org/pdf/2601.01234"


def test_resolve_html_link_returns_none():
    assert resolve_pdf_url("https://example.com/news/story") is None
    assert resolve_pdf_url("") is None


def test_fetch_pdf_text_with_injected_extractor():
    doc = fetch_pdf_text(
        "https://x/p.pdf",
        fetcher=lambda _url: b"%PDF-bytes",
        extractor=lambda _data, _pages: ("hello world body", 7),
    )
    assert doc["status"] == "ok"
    assert doc["page_count"] == 7
    assert doc["text"] == "hello world body"


def test_fetch_pdf_text_no_text():
    doc = fetch_pdf_text("https://x/p.pdf", fetcher=lambda _u: b"x", extractor=lambda _d, _p: ("", 3))
    assert doc["status"] == "no_text"


def test_fetch_pdf_text_unavailable_on_error():
    def boom(_url):
        raise RuntimeError("429")

    doc = fetch_pdf_text("https://x/p.pdf", fetcher=boom, extractor=lambda _d, _p: ("x", 1))
    assert doc["status"] == "unavailable"


def test_enrich_extracts_extra_evidence_from_full_text():
    # Headline carries no hard evidence; the PDF body does.
    candidate = {
        "article": {"source": "arXiv", "title": "A study of neural network hardware", "link": "https://arxiv.org/abs/2601.99999"},
        "matched_terms": [],
    }
    full_text = "The program covers mass production and a customer prepayment tied to capacity reservation."
    rows = enrich_candidates_with_pdf_intel(
        [candidate],
        fetcher=lambda _url: b"%PDF",
        extractor=lambda _data, _pages: (full_text, 12),
    )
    intel = rows[0]["pdf_intel"]
    assert intel["status"] == "ok"
    assert intel["page_count"] == 12
    assert intel["evidence_tier"] == "hard_evidence"
    assert "mass production" in intel["extra_terms"]
    assert "capacity reservation" in intel["extra_terms"]
    assert intel["excerpt"]


def test_enrich_skips_non_pdf_links():
    rows = enrich_candidates_with_pdf_intel(
        [{"article": {"link": "https://example.com/news"}, "matched_terms": []}],
        fetcher=lambda _u: b"x",
        extractor=lambda _d, _p: ("x", 1),
    )
    assert rows[0]["pdf_intel"]["status"] == "not_pdf"


def test_enrich_respects_download_budget():
    candidates = [
        {"article": {"link": f"https://arxiv.org/abs/2601.0000{i}"}, "matched_terms": []}
        for i in range(4)
    ]
    rows = enrich_candidates_with_pdf_intel(
        candidates,
        fetcher=lambda _u: b"x",
        extractor=lambda _d, _p: ("mass production order", 1),
        max_docs=2,
    )
    statuses = [r["pdf_intel"]["status"] for r in rows]
    assert statuses.count("ok") == 2
    assert statuses.count("skipped_budget") == 2
