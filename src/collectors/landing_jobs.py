"""Landing.jobs collector — free public JSON API (EU tech jobs).

https://landing.jobs/api/v1/jobs returns ~50 recent jobs. We keep the remote
ones (Landing.jobs is EU-focused, so remote here means EU-timezone remote — a
good fit for Morocco). Company name isn't a field, so we derive it from the URL
slug (/at/<company>/...). Normalized to the common schema.
"""

from __future__ import annotations

import logging
import re

import requests

log = logging.getLogger("collectors.landing")

API = "https://landing.jobs/api/v1/jobs"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-agent/1.0)", "Accept": "application/json"}
_TAG_RE = re.compile(r"<[^>]+>")
_SLUG_RE = re.compile(r"/at/([^/]+)/")


def _clean(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", str(text))).strip()


def _company(url: str) -> str:
    m = _SLUG_RE.search(url or "")
    return m.group(1).replace("-", " ").title() if m else ""


def _location(job: dict) -> str:
    codes = [l.get("country_code", "") for l in (job.get("locations") or []) if l.get("country_code")]
    codes = sorted(set(c for c in codes if c))
    return "Remote" + (f" ({', '.join(codes)})" if codes else "")


def fetch_all() -> list[dict]:
    log.info("Fetching from Landing.jobs API...")
    try:
        resp = requests.get(API, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Landing.jobs failed: %s", exc)
        return []

    out = []
    for j in data if isinstance(data, list) else []:
        if not j.get("remote"):
            continue  # skip onsite EU roles
        desc = " ".join(_clean(j.get(k)) for k in ("role_description", "main_requirements", "nice_to_have"))
        out.append({
            "title": _clean(j.get("title")),
            "company": _company(j.get("url", "")),
            "location": _location(j),
            "url": j.get("url", ""),
            "description": desc.strip(),
            "source": "Landing.jobs",
            "date_posted": j.get("published_at") or j.get("created_at", ""),
        })
    log.info("  Landing.jobs -> %d remote listings", len(out))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for j in fetch_all()[:8]:
        print(j["source"], "|", j["title"], "@", j["company"], "|", j["location"])
