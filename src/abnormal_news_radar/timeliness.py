from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

#: Hard freshness cutoff. News older than this is dropped before scoring —
#: anything past a year is either played-out hype or already-realized tech, and
#: has no trading timeliness.
MAX_FRESH_DAYS = 365


def article_age_days(article: object, now: datetime | None = None) -> float | None:
    """Age of an article in days from its published date, or None if undated."""
    if now is None:
        now = datetime.now(timezone.utc)
    parsed = parse_datetime(str(getattr(article, "published", "") or ""))
    if parsed is None:
        return None
    hours = _age_hours(parsed, now)
    return None if hours is None else hours / 24.0


def is_within_max_age(article: object, max_days: int = MAX_FRESH_DAYS, now: datetime | None = None) -> bool:
    """True if the article is fresh enough to use. Undated items are kept (many
    IR/HTML pages omit a date but are current); only items with a parsed date
    older than ``max_days`` are dropped. Future-dated items are kept."""
    age = article_age_days(article, now)
    if age is None:
        return True
    return age <= max_days


def article_timeliness(article: object, now: datetime | None = None) -> dict[str, object]:
    if now is None:
        now = datetime.now(timezone.utc)
    published = str(getattr(article, "published", "") or "")
    fetched_at = str(getattr(article, "fetched_at", "") or "")
    parsed = parse_datetime(published)
    if parsed is None:
        fetched = parse_datetime(fetched_at)
        age_hours = _age_hours(fetched, now) if fetched is not None else None
        return {
            "status": "published_unknown",
            "age_hours": age_hours,
            "score_multiplier": 0.85,
            "summary_zh": "来源未提供发布时间；按时间未知轻度降权。",
        }

    age_hours = _age_hours(parsed, now)
    if age_hours < -1:
        return {
            "status": "future_or_clock_skew",
            "age_hours": round(age_hours, 2),
            "score_multiplier": 1.0,
            "summary_zh": "发布时间晚于当前时间，可能是时区或来源时钟问题；暂不降权。",
        }
    if age_hours <= 6:
        multiplier = 1.10
        status = "breaking"
        summary = "6小时内新消息；时效性强。"
    elif age_hours <= 24:
        multiplier = 1.00
        status = "same_day"
        summary = "24小时内消息；仍具备交易时效。"
    elif age_hours <= 72:
        multiplier = 0.75
        status = "aging"
        summary = "超过24小时，影响开始衰减。"
    elif age_hours <= 168:
        multiplier = 0.50
        status = "stale"
        summary = "超过3天，通常只适合作背景资料。"
    else:
        multiplier = 0.25
        status = "old"
        summary = "超过7天，默认错过主要交易窗口。"
    return {
        "status": status,
        "age_hours": round(age_hours, 2),
        "score_multiplier": multiplier,
        "summary_zh": summary,
    }


def parse_datetime(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    normalized = text.replace(" UT", " UTC")
    try:
        parsed = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_hours(value: datetime | None, now: datetime) -> float | None:
    if value is None:
        return None
    return (now.astimezone(timezone.utc) - value.astimezone(timezone.utc)).total_seconds() / 3600
