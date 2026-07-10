"""The Muse public jobs API collector (no key required).

https://www.themuse.com/api/public/jobs?page=N&category=...&location=...

We page through a few pages of dev-relevant categories and keep only listings
whose locations look remote/flexible. Normalized to the common schema.
"""

from __future__ import annotations

import asyncio
import logging
import re

import aiohttp

log = logging.getLogger("collectors.muse")

TIMEOUT = aiohttp.ClientTimeout(total=45)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; job-agent/1.0)",
    "Accept": "application/json",
}
_TAG_RE = re.compile(r"<[^>]+>")

# Muse category names that map to the CV.
CATEGORIES = ["Software Engineering", "Data Science", "Data and Analytics"]
PAGES = 3  # pages per category (Muse returns ~20/page)


def _clean(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", str(text))).strip()


def _looks_remote(locations: list[str]) -> bool:
    joined = " ".join(locations).lower()
    return ("remote" in joined) or ("flexible" in joined) or ("anywhere" in joined)


async def _fetch_page(session, category: str, page: int) -> list[dict]:
    url = "https://www.themuse.com/api/public/jobs"
    params = {"page": page, "category": category}
    async with session.get(url, params=params, headers=HEADERS, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)

    out = []
    for j in data.get("results", []):
        locs = [l.get("name", "") for l in j.get("locations", [])]
        if not _looks_remote(locs):
            continue
        out.append({
            "title": _clean(j.get("name")),
            "company": _clean((j.get("company") or {}).get("name")),
            "location": ", ".join(locs) if locs else "Flexible / Remote",
            "url": (j.get("refs") or {}).get("landing_page", ""),
            "description": _clean(j.get("contents")),
            "source": "The Muse",
            "date_posted": j.get("publication_date", ""),
        })
    return out


async def _run() -> list[dict]:
    listings: list[dict] = []
    async with aiohttp.ClientSession() as session:
        tasks = [
            _fetch_page(session, cat, page)
            for cat in CATEGORIES
            for page in range(PAGES)
        ]
        for coro in asyncio.as_completed(tasks):
            try:
                listings.extend(await coro)
            except Exception as exc:  # noqa: BLE001
                log.warning("  Muse page failed: %s", exc)
    return listings


def fetch_all() -> list[dict]:
    log.info("Fetching from The Muse API...")
    try:
        listings = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        log.warning("Muse collector failed entirely: %s", exc)
        return []
    log.info("  The Muse -> %d remote listings", len(listings))
    return listings


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for j in fetch_all()[:8]:
        print(j["source"], "|", j["title"], "@", j["company"], "|", j["location"])
