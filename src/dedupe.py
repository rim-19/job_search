"""Deduplicate combined listings.

Two layers (item 21):
  1. Canonical-URL identity — strip tracking query params, fragments and trailing
     slashes so the same posting via different links collapses to one.
  2. (title + company) identity — the same job surfacing through an API, an RSS
     feed, a Google Alert and a company board becomes a single logical record.

The first occurrence wins (source order in main.py puts the richer APIs first).
"""

from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import urlsplit, urlunsplit

log = logging.getLogger("dedupe")

_TRACKING = re.compile(r"^(utm_|ref|source|src|gh_|lever-|mc_|fbclid|gclid)", re.I)
_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^a-z0-9]+")


def canonical_url(url: str) -> str:
    """Lowercase host, drop fragment + tracking query params, trim trailing slash."""
    try:
        s = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    query = "&".join(
        p for p in s.query.split("&")
        if p and not _TRACKING.match(p.split("=", 1)[0])
    )
    path = s.path.rstrip("/") or "/"
    return urlunsplit((s.scheme.lower(), s.netloc.lower(), path, query, "")).lower()


def _norm(text: str) -> str:
    return _NONWORD.sub(" ", (text or "").lower()).strip()


def _url_key(job: dict) -> str:
    return hashlib.sha256(canonical_url(job.get("url") or "").encode()).hexdigest()


def _content_key(job: dict) -> str:
    raw = _norm(job.get("title", "")) + "|" + _norm(job.get("company", ""))
    return hashlib.sha256(raw.encode()).hexdigest()


def dedupe(listings: list[dict]) -> list[dict]:
    seen_url: set[str] = set()
    seen_content: set[str] = set()
    out: list[dict] = []
    dropped_url = dropped_content = 0

    for job in listings:
        if not (job.get("url") or "").strip():
            continue  # can't apply to or upsert a listing with no URL

        uk = _url_key(job)
        if uk in seen_url:
            dropped_url += 1
            continue

        # Cross-source content collapse — but only when we have a real company
        # name (empty-company RSS items would otherwise over-merge).
        ck = _content_key(job)
        has_company = bool((job.get("company") or "").strip())
        if has_company and ck in seen_content:
            dropped_content += 1
            continue

        seen_url.add(uk)
        if has_company:
            seen_content.add(ck)
        out.append(job)

    log.info("Dedupe: %d in -> %d unique (dropped %d url-dupes, %d cross-source dupes)",
             len(listings), len(out), dropped_url, dropped_content)
    return out
