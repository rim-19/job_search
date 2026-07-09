"""Fetch remote jobs from five free JSON APIs and normalize them.

Common schema per listing:
    {title, company, location, url, description, source, date_posted}

All fetches run concurrently via asyncio + a shared aiohttp session. Any single
source that errors out (network, schema change, rate-limit) is logged and
skipped — one bad source never sinks the whole run.
"""

from __future__ import annotations

import asyncio
import logging
import re

import aiohttp

log = logging.getLogger("collectors.api")

# Polite timeout per request; some of these endpoints can be slow.
TIMEOUT = aiohttp.ClientTimeout(total=45)
HEADERS = {
    # RemoteOK and a few others block the default aiohttp UA.
    "User-Agent": "Mozilla/5.0 (compatible; job-agent/1.0; +https://github.com/rim-19/job_search)",
    "Accept": "application/json",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text) -> str:
    """Strip HTML tags and collapse whitespace from description blobs."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", str(text))
    return re.sub(r"\s+", " ", text).strip()


def _record(title, company, location, url, description, source, date_posted) -> dict:
    return {
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location": (location or "").strip(),
        "url": (url or "").strip(),
        "description": _clean(description),
        "source": source,
        "date_posted": (str(date_posted) if date_posted else "").strip(),
    }


async def _get_json(session: aiohttp.ClientSession, url: str):
    async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        # Some APIs mislabel content-type; parse leniently.
        return await resp.json(content_type=None)


# --- Individual source parsers -------------------------------------------------

async def _remotive(session) -> list[dict]:
    data = await _get_json(session, "https://remotive.com/api/remote-jobs")
    out = []
    for j in data.get("jobs", []):
        out.append(_record(
            j.get("title"), j.get("company_name"),
            j.get("candidate_required_location"), j.get("url"),
            j.get("description"), "Remotive", j.get("publication_date"),
        ))
    return out


async def _arbeitnow(session) -> list[dict]:
    data = await _get_json(session, "https://www.arbeitnow.com/api/job-board-api")
    out = []
    for j in data.get("data", []):
        remote = j.get("remote")
        loc = j.get("location") or ""
        if remote and "remote" not in loc.lower():
            loc = (loc + " (remote)").strip()
        out.append(_record(
            j.get("title"), j.get("company_name"), loc, j.get("url"),
            j.get("description"), "Arbeitnow", j.get("created_at"),
        ))
    return out


async def _remoteok(session) -> list[dict]:
    data = await _get_json(session, "https://remoteok.com/api")
    out = []
    for j in data:
        # First element is a legal/notice object, not a job.
        if not isinstance(j, dict) or not j.get("position"):
            continue
        out.append(_record(
            j.get("position"), j.get("company"), j.get("location") or "Remote",
            j.get("url"), j.get("description"), "RemoteOK", j.get("date"),
        ))
    return out


async def _jobicy(session) -> list[dict]:
    data = await _get_json(session, "https://jobicy.com/api/v2/remote-jobs")
    out = []
    for j in data.get("jobs", []):
        out.append(_record(
            j.get("jobTitle"), j.get("companyName"),
            j.get("jobGeo") or "Remote", j.get("url"),
            j.get("jobDescription") or j.get("jobExcerpt"),
            "Jobicy", j.get("pubDate"),
        ))
    return out


async def _himalayas(session) -> list[dict]:
    data = await _get_json(session, "https://himalayas.app/jobs/api")
    out = []
    for j in data.get("jobs", []):
        # Himalayas returns location restrictions as a list of country names.
        loc = j.get("locationRestrictions")
        if isinstance(loc, list):
            loc = ", ".join(loc) if loc else "Worldwide"
        out.append(_record(
            j.get("title"), j.get("companyName"), loc or "Worldwide",
            j.get("applicationLink") or j.get("guid"),
            j.get("description") or j.get("excerpt"),
            "Himalayas", j.get("pubDate"),
        ))
    return out


_SOURCES = {
    "Remotive": _remotive,
    "Arbeitnow": _arbeitnow,
    "RemoteOK": _remoteok,
    "Jobicy": _jobicy,
    "Himalayas": _himalayas,
}


async def _run_all() -> list[dict]:
    async with aiohttp.ClientSession() as session:
        tasks = {name: asyncio.create_task(fn(session)) for name, fn in _SOURCES.items()}
        listings: list[dict] = []
        for name, task in tasks.items():
            try:
                jobs = await task
                log.info("  %-10s -> %d listings", name, len(jobs))
                listings.extend(jobs)
            except Exception as exc:  # noqa: BLE001 - never let one source kill the run
                log.warning("  %-10s -> FAILED: %s", name, exc)
        return listings


def fetch_all() -> list[dict]:
    """Synchronous entry point: returns combined normalized listings from all APIs."""
    log.info("Fetching from %d free APIs...", len(_SOURCES))
    listings = asyncio.run(_run_all())
    log.info("API sources returned %d raw listings total.", len(listings))
    return listings


if __name__ == "__main__":  # manual smoke test
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    jobs = fetch_all()
    for j in jobs[:5]:
        print(j["source"], "|", j["title"], "@", j["company"], "|", j["location"])
