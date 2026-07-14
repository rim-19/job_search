"""Startup / company job boards via free public APIs: Greenhouse, Lever, Ashby.

Each provider is queried per company (slugs from config/startup_boards.yaml).
Only remote-looking listings are kept, to cut onsite noise before scoring.
Normalized to the common schema. Dead slugs are skipped with a warning.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from pathlib import Path

import aiohttp
import yaml

log = logging.getLogger("collectors.startup")

CONFIG = Path(__file__).resolve().parents[2] / "config" / "startup_boards.yaml"
TIMEOUT = aiohttp.ClientTimeout(total=30)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-agent/1.0)", "Accept": "application/json"}
_TAG_RE = re.compile(r"<[^>]+>")

# Regions whose timezone Morocco can work — if any appear, keep the listing.
_WORKABLE = (
    "anywhere", "worldwide", "global", "distributed",
    "emea", "europe", "european", "africa", "mena", "middle east", "gmt", "cet", "utc",
    "uk", "united kingdom", "london", "ireland", "portugal", "spain", "germany",
    "france", "netherlands", "poland", "morocco",
)
# If a location names one of these (and no workable region), it excludes her.
_EXCLUDE = (
    "united states", "usa", "u.s.", "canada", "ontario", "toronto",
    "new york", "san francisco", "california", "washington", "boston",
    "austin", "seattle", "chicago", "los angeles", "denver", "texas",
    "latam", "apac", "australia", "singapore", "india",
)
_PER_BOARD_CAP = 40  # avoid one huge board dominating the run


def _clean(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(str(text)))).strip()


def _remote_ok(location: str, is_remote: bool = False) -> bool:
    loc = (location or "").lower()
    # A workable region is offered -> keep (even if a US option is also listed).
    if any(h in loc for h in _WORKABLE):
        return True
    # Explicitly remote and not pinned to an excluded region -> keep.
    remote = is_remote or "remote" in loc
    if remote and not any(x in loc for x in _EXCLUDE):
        return True
    # Unknown location on a remote-listed role -> let the AI judge.
    if not loc and is_remote:
        return True
    return False


def _load_config() -> dict:
    if not CONFIG.exists():
        return {}
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


# --- Per-provider fetchers -----------------------------------------------------

async def _greenhouse(session, name, slug) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        data = await r.json(content_type=None)
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        if not _remote_ok(loc):
            continue
        out.append({
            "title": _clean(j.get("title")), "company": name, "location": loc or "Remote",
            "url": j.get("absolute_url", ""), "description": _clean(j.get("content")),
            "source": f"{name} (careers)", "date_posted": j.get("updated_at", ""),
        })
        if len(out) >= _PER_BOARD_CAP:
            break
    return out


async def _lever(session, name, slug) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        data = await r.json(content_type=None)
    out = []
    for j in data:
        cats = j.get("categories") or {}
        loc = cats.get("location", "")
        workplace = (j.get("workplaceType") or "").lower()
        if not _remote_ok(loc, is_remote=(workplace == "remote")):
            continue
        out.append({
            "title": _clean(j.get("text")), "company": name,
            "location": loc or ("Remote" if workplace == "remote" else ""),
            "url": j.get("hostedUrl", ""),
            "description": _clean(j.get("descriptionPlain") or j.get("description")),
            "source": f"{name} (careers)", "date_posted": j.get("createdAt", ""),
        })
        if len(out) >= _PER_BOARD_CAP:
            break
    return out


async def _ashby(session, name, slug) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        data = await r.json(content_type=None)
    out = []
    for j in data.get("jobs", []):
        loc = j.get("location", "")
        if not _remote_ok(loc, is_remote=bool(j.get("isRemote"))):
            continue
        out.append({
            "title": _clean(j.get("title")), "company": name,
            "location": loc or ("Remote" if j.get("isRemote") else ""),
            "url": j.get("jobUrl") or j.get("applyUrl", ""),
            "description": _clean(j.get("descriptionPlain") or j.get("descriptionHtml")),
            "source": f"{name} (careers)", "date_posted": j.get("publishedDate", ""),
        })
        if len(out) >= _PER_BOARD_CAP:
            break
    return out


_PROVIDERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


async def _run() -> list[dict]:
    cfg = _load_config()
    jobs_spec = [
        (fn, c.get("name", c.get("slug")), c["slug"])
        for provider, fn in _PROVIDERS.items()
        for c in (cfg.get(provider) or [])
        if c.get("slug")
    ]
    if not jobs_spec:
        log.info("No startup boards configured — skipping.")
        return []

    log.info("Fetching %d startup boards (Greenhouse/Lever/Ashby)...", len(jobs_spec))
    listings: list[dict] = []
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[fn(session, name, slug) for fn, name, slug in jobs_spec],
            return_exceptions=True,
        )
    kept = 0
    for (fn, name, slug), res in zip(jobs_spec, results):
        if isinstance(res, Exception):
            log.debug("  %s (%s): %s", name, slug, res)
            continue
        kept += len(res)
        listings.extend(res)
    log.info("Startup boards -> %d remote listings from %d companies", kept, len(jobs_spec))
    return listings


def fetch_all() -> list[dict]:
    try:
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        log.warning("Startup boards collector failed entirely: %s", exc)
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for j in fetch_all()[:12]:
        print(j["source"], "|", j["title"], "@", j["location"])
