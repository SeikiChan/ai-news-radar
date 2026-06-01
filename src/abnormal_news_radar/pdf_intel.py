"""Public-PDF download and full-text analysis.

The feed layer only sees an article's title + summary. For technical papers and
some IR/filing documents the real evidence lives in the PDF body. This module
downloads *publicly available* PDFs (open-access arXiv papers, and any link that
is already a ``.pdf`` from our curated trusted feeds), extracts the text with
``pypdf``, and re-scores the full text — surfacing hard-evidence terms that the
headline alone never showed.

Safety: only arXiv and explicit ``.pdf`` links are fetched (no paywalled
scraping); downloads are size- and page-capped; failures degrade to a status
flag and never break the scan. ``fetcher``/``extractor`` are injectable for
deterministic tests.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .model import Article
from .net import fetch_bytes
from .scoring import analyze_evidence

MAX_PDF_BYTES = 12_000_000  # 12 MB cap per document
MAX_PAGES = 30
MAX_ANALYZE_CHARS = 20_000
MAX_DOCS_PER_SCAN = 5
EXCERPT_CHARS = 500

_ARXIV_ABS_RE = re.compile(r"arxiv\.org/abs/(?P<id>[\w.\-/]+)", re.IGNORECASE)


def resolve_pdf_url(link: str) -> str | None:
    """Map an article link to a downloadable, public PDF URL, or None.

    Only open-access / already-PDF sources qualify: arXiv abstract pages, arXiv
    PDF links, and any URL whose path ends in ``.pdf``.
    """
    if not link:
        return None
    match = _ARXIV_ABS_RE.search(link)
    if match:
        return f"https://arxiv.org/pdf/{match.group('id')}"
    path = urlsplit(link).path.lower()
    if path.endswith(".pdf") or "arxiv.org/pdf/" in link.lower():
        return link
    return None


def fetch_pdf_text(
    pdf_url: str,
    fetcher: object | None = None,
    extractor: object | None = None,
    max_pages: int = MAX_PAGES,
    max_bytes: int = MAX_PDF_BYTES,
) -> dict[str, object]:
    fetch = fetcher or (lambda url: fetch_bytes(url, accept="application/pdf", timeout=20, max_bytes=max_bytes))
    extract = extractor or _pypdf_extract
    try:
        data = fetch(pdf_url)  # type: ignore[operator]
        if not data:
            return {"status": "empty"}
        text, page_count = extract(data, max_pages)  # type: ignore[operator]
        text = (text or "").strip()
        if not text:
            return {"status": "no_text", "page_count": page_count}
        return {"status": "ok", "page_count": page_count, "char_count": len(text), "text": text}
    except Exception as exc:  # noqa: BLE001 - degrade cleanly; never break the scan.
        return {"status": "unavailable", "reason": str(exc)[:160]}


def enrich_candidates_with_pdf_intel(
    candidates: list[dict[str, object]],
    fetcher: object | None = None,
    extractor: object | None = None,
    max_docs: int = MAX_DOCS_PER_SCAN,
) -> list[dict[str, object]]:
    enriched = []
    budget = max_docs
    for candidate in candidates:
        row = dict(candidate)
        article = row.get("article") if isinstance(row.get("article"), dict) else {}
        pdf_url = resolve_pdf_url(str(article.get("link") or ""))
        if not pdf_url:
            row["pdf_intel"] = {"status": "not_pdf"}
        elif budget <= 0:
            row["pdf_intel"] = {"status": "skipped_budget", "source_url": pdf_url}
        else:
            budget -= 1
            row["pdf_intel"] = _analyze_candidate(row, pdf_url, fetcher, extractor)
        enriched.append(row)
    return enriched


def _analyze_candidate(
    candidate: dict[str, object],
    pdf_url: str,
    fetcher: object | None,
    extractor: object | None,
) -> dict[str, object]:
    doc = fetch_pdf_text(pdf_url, fetcher, extractor)
    if doc.get("status") != "ok":
        return {
            "status": doc.get("status", "unavailable"),
            "source_url": pdf_url,
            "summary_zh": "未能下载/解析该 PDF 全文（可能限流、非文本 PDF 或超出大小限制）。",
        }

    text = str(doc["text"])
    article = candidate.get("article") if isinstance(candidate.get("article"), dict) else {}
    profile = analyze_evidence(
        Article(
            source=str(article.get("source") or ""),
            source_trust=1.0,
            title=str(article.get("title") or ""),
            link=pdf_url,
            summary=text[:MAX_ANALYZE_CHARS],
        )
    )
    headline_terms = {str(term) for term in (candidate.get("matched_terms") or [])}
    full_terms = [str(term) for term in profile["matched_terms"]]
    extra_terms = [term for term in full_terms if term not in headline_terms]
    excerpt = _excerpt(text)
    return {
        "status": "ok",
        "source_url": pdf_url,
        "page_count": doc.get("page_count"),
        "char_count": doc.get("char_count"),
        "full_text_score": int(profile["raw_score"]),
        "evidence_tier": str(profile["evidence_tier"]),
        "confidence": float(profile["confidence"]),
        "matched_terms": full_terms[:20],
        "extra_terms": extra_terms[:12],
        "excerpt": excerpt,
        "summary_zh": _summary_zh(doc, profile, extra_terms),
    }


def _summary_zh(doc: dict[str, object], profile: dict[str, object], extra_terms: list[str]) -> str:
    extra = "、".join(extra_terms[:6]) if extra_terms else "无标题外新增"
    return (
        f"已下载并解析全文 {doc.get('page_count', '?')} 页（{doc.get('char_count', 0)} 字）。"
        f"全文证据层={profile.get('evidence_tier')}，全文证据分={int(profile.get('raw_score') or 0)}；"
        f"较标题/摘要新增硬证据：{extra}。"
    )


def _excerpt(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= EXCERPT_CHARS:
        return collapsed
    return collapsed[:EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"


def _pypdf_extract(data: bytes, max_pages: int) -> tuple[str, int]:
    from io import BytesIO

    from pypdf import PdfReader  # imported lazily so the module loads without pypdf

    reader = PdfReader(BytesIO(data))
    parts: list[str] = []
    for page in list(reader.pages)[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - skip unparseable pages.
            continue
    return "\n".join(parts), len(reader.pages)
