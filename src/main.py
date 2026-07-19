"""Pipeline orchestrator:
collect -> dedupe (in-run) -> score(+summary) -> recency -> persistent-dedupe
-> store -> export -> notify (new only).

Run from the project root as a module:
    python -m src.main
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from .collectors import (  # noqa: E402
    api_sources, muse_source, rss_sources, landing_jobs, startup_boards,
    playwright_sources,
)
from . import dedupe, scorer, recency, db, site_builder, notifier  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-18s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

# Lowered to 6: as a junior, casting a wider net (worth-a-look roles) beats
# waiting for perfect 7+ matches. Override with KEEP_THRESHOLD.
KEEP_THRESHOLD = int(os.getenv("KEEP_THRESHOLD", "6"))


def run() -> None:
    started = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("JOB AGENT RUN — %s UTC", started.strftime("%Y-%m-%d %H:%M"))
    log.info("=" * 60)

    # Ensure DB exists so we can read already-scored URLs before scoring.
    db.init_db()
    existing_urls = db.get_existing_urls()

    # 1. Collect (APIs + keyword variants, Muse, RSS/Google-Alerts, startup
    #    boards, Playwright)
    listings = api_sources.fetch_all()
    listings += muse_source.fetch_all()
    listings += rss_sources.fetch_all()
    listings += landing_jobs.fetch_all()
    listings += startup_boards.fetch_all()
    listings += playwright_sources.fetch_all()
    log.info("STAGE collect: %d raw listings", len(listings))

    # 2. In-run dedupe
    listings = dedupe.dedupe(listings)
    log.info("STAGE dedupe: %d unique listings", len(listings))

    # 3. Score ONLY net-new listings (already-scored ones keep DB scores).
    scored = scorer.score_all(listings, skip_urls=existing_urls)
    log.info("STAGE score: %d new listings scored", len(scored))

    # 4. Recency — annotate, never drop
    recency.annotate_all(scored, now=started)

    # 5. Everything freshly scored is, by definition, new this run.
    new_listings = scored
    log.info("STAGE persist-dedupe: %d new listings vs %d already in DB",
             len(new_listings), len(existing_urls))

    # 6. Store — upsert the newly scored listings
    stamp = started.strftime("%Y-%m-%d")
    for job in scored:
        db.upsert_job(job, date_scored=stamp)
    log.info("STAGE store: upserted %d listings into %s", len(scored), db.DB_PATH.name)

    # 7. Export snapshot for the website
    exported = site_builder.export()
    log.info("STAGE export: docs/jobs.json now holds %d listings", exported)

    # 8. Notify — only NEW keepers (score >= threshold), Fresh first
    new_keepers = [j for j in new_listings if j.get("score", 0) >= KEEP_THRESHOLD]
    notifier.notify(total_collected=len(listings), new_keepers=new_keepers, scored=scored)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log.info("=" * 60)
    log.info("DONE in %.0fs — scanned %d, %d new, %d new keepers.",
             elapsed, len(scored), len(new_listings), len(new_keepers))
    log.info("=" * 60)


if __name__ == "__main__":
    run()
