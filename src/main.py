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
    api_sources, muse_source, rss_sources, playwright_sources,
)
from . import dedupe, scorer, recency, db, site_builder, notifier  # noqa: E402

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

    # 1. Collect (APIs + keyword variants, Muse, RSS/Google-Alerts, Playwright)
    listings = api_sources.fetch_all()
    listings += muse_source.fetch_all()
    listings += rss_sources.fetch_all()
    listings += playwright_sources.fetch_all()
    log.info("STAGE collect: %d raw listings", len(listings))

    # 2. In-run dedupe
    listings = dedupe.dedupe(listings)
    log.info("STAGE dedupe: %d unique listings", len(listings))

    # 3. Score (Layer 1 rules + Layer 2 Gemini score+reason+summary)
    scored = scorer.score_all(listings)
    log.info("STAGE score: %d listings scored", len(scored))

    # 4. Recency — annotate, never drop
    recency.annotate_all(scored, now=started)

    # 5. Persistent (cross-run) dedupe: which URLs are brand new?
    existing_urls = db.get_existing_urls()
    new_listings = [j for j in scored if j.get("url") not in existing_urls]
    log.info("STAGE persist-dedupe: %d new listings (of %d scored) vs %d already in DB",
             len(new_listings), len(scored), len(existing_urls))

    # 6. Store — upsert everything (existing rows updated silently, status kept)
    db.init_db()
    stamp = started.strftime("%Y-%m-%d")
    for job in scored:
        db.upsert_job(job, date_scored=stamp)
    log.info("STAGE store: upserted %d listings into %s", len(scored), db.DB_PATH.name)

    # 7. Export snapshot for the website
    exported = site_builder.export()
    log.info("STAGE export: docs/jobs.json now holds %d listings", exported)

    # 8. Notify — only NEW keepers (score >= threshold), Fresh first
    new_keepers = [j for j in new_listings if j.get("score", 0) >= KEEP_THRESHOLD]
    notifier.notify(total_scanned=len(scored), new_keepers=new_keepers)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log.info("=" * 60)
    log.info("DONE in %.0fs — scanned %d, %d new, %d new keepers.",
             elapsed, len(scored), len(new_listings), len(new_keepers))
    log.info("=" * 60)


if __name__ == "__main__":
    run()
