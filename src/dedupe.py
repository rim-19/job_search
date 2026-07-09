"""Deduplicate combined listings by a hash of lowercased (title + company + url)."""

from __future__ import annotations

import hashlib
import logging

log = logging.getLogger("dedupe")


def _key(job: dict) -> str:
    raw = "".join([
        (job.get("title") or "").lower().strip(),
        (job.get("company") or "").lower().strip(),
        (job.get("url") or "").lower().strip(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def dedupe(listings: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for job in listings:
        # A listing with no URL can't be applied to or upserted — drop it.
        if not (job.get("url") or "").strip():
            continue
        h = _key(job)
        if h in seen:
            continue
        seen.add(h)
        out.append(job)
    log.info("Dedupe: %d in -> %d unique out", len(listings), len(out))
    return out
