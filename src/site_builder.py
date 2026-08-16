"""Export the SQLite contents to docs/jobs.json for the static website.

The database is the source of truth; jobs.json is a read-only snapshot the
dashboard fetches. This module regenerates the JSON each run and derives an
`is_new` flag (first seen in the latest run) so the site can highlight today's
fresh additions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import db

log = logging.getLogger("site_builder")

DOCS = Path(__file__).resolve().parents[1] / "docs"
JOBS_JSON = DOCS / "jobs.json"


def export() -> int:
    """Write docs/jobs.json from the DB. Returns the number of listings written."""
    DOCS.mkdir(parents=True, exist_ok=True)
    jobs = db.get_all_jobs()

    # "New today" = first seen on the most recent run date present in the data.
    latest = max((j.get("date_scored") or "" for j in jobs), default="")
    for j in jobs:
        j["is_new"] = bool(latest) and (j.get("first_seen") == latest)

    def pcount(p):
        return sum(1 for j in jobs if (j.get("priority") or "") == p)

    payload = {
        "generated": latest,
        "jobs": jobs,
        "count": len(jobs),
        # 0-100 scale now: "keepers" = CONSIDER+ (score >= 55).
        "keepers": sum(1 for j in jobs if (j.get("score") or 0) >= 55),
        "fresh": sum(1 for j in jobs if j.get("freshness") == "Fresh"),
        "new_today": sum(1 for j in jobs if j.get("is_new")),
        "apply_now": pcount("APPLY_NOW"),
        "apply": pcount("APPLY"),
        "consider": pcount("CONSIDER"),
        "morocco": sum(1 for j in jobs if (j.get("geographic_scope") or "") == "MOROCCO"),
        "eligible": sum(1 for j in jobs if (j.get("eligible_for_rim") or "") == "true"),
    }
    JOBS_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Exported %d listings (%d new today) -> %s",
             len(jobs), payload["new_today"], JOBS_JSON)
    return len(jobs)
