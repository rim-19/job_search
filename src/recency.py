"""Recency handling: compute days_since_posted + a 'Fresh' label.

Nothing is ever dropped for being old — recency is purely informational and used
for sorting/deprioritizing. Missing or unparseable dates are treated as unknown
(days_since_posted = None, freshness = "").
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("recency")

FRESH_DAYS = 7


def _parse_date(value) -> datetime | None:
    """Best-effort parse of the many date shapes our sources emit.

    Handles ISO 8601, RFC 822 (RSS), and unix timestamps (int or digit string).
    Returns a timezone-aware UTC datetime, or None if unparseable.
    """
    if value is None or value == "":
        return None

    # Unix timestamp (Arbeitnow etc.) — int or all-digit string.
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        try:
            ts = float(value)
            # Milliseconds vs seconds heuristic.
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None

    text = str(value).strip()

    # Try dateutil if available (handles ISO + RFC 822 + lots of oddities).
    try:
        from dateutil import parser as dateutil_parser
        dt = dateutil_parser.parse(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001 - fall through to manual formats
        pass

    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def annotate(job: dict, now: datetime | None = None) -> dict:
    """Add `days_since_posted` (int|None) and `freshness` ("Fresh"|"") to a job."""
    now = now or datetime.now(timezone.utc)
    posted = _parse_date(job.get("date_posted"))
    if posted is None:
        job["days_since_posted"] = None
        job["freshness"] = ""
        return job

    days = max(0, (now - posted).days)
    job["days_since_posted"] = days
    job["freshness"] = "Fresh" if days <= FRESH_DAYS else ""
    return job


def annotate_all(jobs: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    for job in jobs:
        annotate(job, now)
    fresh = sum(1 for j in jobs if j.get("freshness") == "Fresh")
    log.info("Recency: %d/%d listings are Fresh (<= %d days).", fresh, len(jobs), FRESH_DAYS)
    return jobs


def sort_key(job: dict) -> tuple:
    """Sort helper: Fresh first, then by score desc, then by recency asc.

    Unknown recency sorts after known (large sentinel)."""
    is_fresh = 0 if job.get("freshness") == "Fresh" else 1
    score = -(job.get("score") or 0)
    days = job.get("days_since_posted")
    days = 10_000 if days is None else days
    return (is_fresh, score, days)
