"""Pipeline orchestrator: collect -> dedupe -> score -> filter -> draft -> store
-> export -> notify.

Run from the project root as a module so relative imports resolve:
    python -m src.main
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

# Load .env from the project root before importing modules that read env vars.
load_dotenv()

from .collectors import api_sources, playwright_sources  # noqa: E402
from . import dedupe, scorer, drafter, db, site_builder, notifier  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-18s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

KEEP_THRESHOLD = int(os.getenv("KEEP_THRESHOLD", "7"))


def run() -> None:
    started = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("JOB AGENT RUN — %s UTC", started.strftime("%Y-%m-%d %H:%M"))
    log.info("=" * 60)

    # 1. Collect
    listings = api_sources.fetch_all()
    listings += playwright_sources.fetch_all()
    log.info("STAGE collect: %d raw listings", len(listings))

    # 2. Dedupe
    listings = dedupe.dedupe(listings)
    log.info("STAGE dedupe: %d unique listings", len(listings))

    # 3 + 4. Score (includes Layer 1 rule filter + Layer 2 Gemini)
    scored = scorer.score_all(listings)
    log.info("STAGE score: %d listings scored", len(scored))

    # 4b. Filter to keepers (score >= threshold)
    keepers = [j for j in scored if j.get("score", 0) >= KEEP_THRESHOLD]
    log.info("STAGE filter: %d keepers (score >= %d)", len(keepers), KEEP_THRESHOLD)

    # 5. Draft cover notes for keepers only
    drafter.draft_all(keepers)
    log.info("STAGE draft: cover notes generated for %d keepers", len(keepers))

    # 6. Store — upsert EVERY scored listing (full history), keepers carry drafts
    db.init_db()
    stamp = started.strftime("%Y-%m-%d")
    for job in scored:
        db.upsert_job(job, date_scored=stamp)
    log.info("STAGE store: upserted %d listings into %s", len(scored), db.DB_PATH.name)

    # 7. Export snapshot for the website
    exported = site_builder.export()
    log.info("STAGE export: docs/jobs.json now holds %d listings", exported)

    # 8. Notify
    notifier.notify(total_scanned=len(scored), keepers=keepers)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log.info("=" * 60)
    log.info("DONE in %.0fs — scanned %d, %d keepers this run.",
             elapsed, len(scored), len(keepers))
    log.info("=" * 60)


if __name__ == "__main__":
    run()
