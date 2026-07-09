"""Export the SQLite contents to docs/jobs.json for the static website.

The database is the source of truth; jobs.json is a read-only snapshot the
Hello-Kitty dashboard fetches. The HTML/CSS/JS live in docs/ as committed static
files — this module only regenerates the JSON data each run.
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

    payload = {
        "jobs": jobs,
        "count": len(jobs),
        "keepers": sum(1 for j in jobs if (j.get("score") or 0) >= 7),
    }
    JOBS_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Exported %d listings -> %s", len(jobs), JOBS_JSON)
    return len(jobs)
