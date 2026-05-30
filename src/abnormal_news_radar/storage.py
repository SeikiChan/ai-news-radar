from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .model import Candidate, Signal


def load_signal_rows(path: Path, limit: int = 200) -> list[dict[str, object]]:
    if not path.exists():
        return []

    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows[-limit:]


def load_candidate_rows(path: Path, limit: int = 200) -> list[dict[str, object]]:
    return load_signal_rows(path, limit=limit)


def load_review_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def save_review_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_signals(path: Path, signals: list[Signal]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing_keys(path)
    saved_count = 0
    with path.open("a", encoding="utf-8") as handle:
        for signal in signals:
            key = _signal_key(signal)
            if key in existing:
                continue
            handle.write(json.dumps(asdict(signal), ensure_ascii=False) + "\n")
            existing.add(key)
            saved_count += 1
    return saved_count


def append_candidates(path: Path, candidates: list[Candidate | dict[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_candidate_keys(path)
    saved_count = 0
    with path.open("a", encoding="utf-8") as handle:
        for candidate in candidates:
            row = _candidate_row(candidate)
            key = _candidate_key(row)
            if key in existing:
                continue
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            existing.add(key)
            saved_count += 1
    return saved_count


def _candidate_row(candidate: Candidate | dict[str, object]) -> dict[str, object]:
    if isinstance(candidate, dict):
        return candidate
    if is_dataclass(candidate):
        return asdict(candidate)
    raise TypeError("candidate must be a Candidate dataclass or dict row")


def _read_existing_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()

    keys: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            article = payload.get("article", {})
            keys.add(_article_key(article))
    return keys


def _read_candidate_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()

    keys: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                keys.add(_candidate_key(payload))
    return keys


def _signal_key(signal: Signal) -> str:
    return _article_key(asdict(signal.article))


def _article_key(article: dict[str, object]) -> str:
    link = str(article.get("link") or "").strip()
    if link:
        return link
    source = str(article.get("source") or "").strip()
    title = str(article.get("title") or "").strip()
    published = str(article.get("published") or "").strip()
    return f"{source}|{title}|{published}"


def _candidate_key(candidate: dict[str, object]) -> str:
    article = candidate.get("article")
    if not isinstance(article, dict):
        article = {}
    company_name = str(candidate.get("company_name") or "").strip().lower()
    return f"{company_name}|{_article_key(article)}"


def candidate_row_key(candidate: dict[str, object]) -> str:
    return _candidate_key(candidate)
