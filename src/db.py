"""SQLite source of truth for scored job listings (data/jobs.db).

Table `jobs`:
    url TEXT PRIMARY KEY, title, company, location, link, score, reason,
    summary, cover_note, checklist, status (default 'Not Applied'),
    date_posted, days_since_posted, freshness, first_seen, date_scored, source

Rules:
- upsert_job() updates every field EXCEPT `status` and `first_seen` when the row
  already exists — a hand-set status is never clobbered, and first_seen records
  when we FIRST saw the listing (drives cross-run "new" detection + Telegram).
- get_existing_urls() lets the pipeline tell new listings from ones we've already
  seen in a previous run, so the evening run never re-notifies the morning's.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger("db")

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "jobs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    url               TEXT PRIMARY KEY,
    title             TEXT,
    company           TEXT,
    location          TEXT,
    link              TEXT,
    score             INTEGER,
    reason            TEXT,
    summary           TEXT,
    cover_note        TEXT,
    checklist         TEXT,
    status            TEXT DEFAULT 'Not Applied',
    date_posted       TEXT,
    days_since_posted INTEGER,
    freshness         TEXT,
    first_seen        TEXT,
    date_scored       TEXT,
    source            TEXT
);
"""

# Columns added after the first release — created on existing DBs via migration.
_MIGRATIONS = {
    "summary": "ALTER TABLE jobs ADD COLUMN summary TEXT",
    "date_posted": "ALTER TABLE jobs ADD COLUMN date_posted TEXT",
    "days_since_posted": "ALTER TABLE jobs ADD COLUMN days_since_posted INTEGER",
    "freshness": "ALTER TABLE jobs ADD COLUMN freshness TEXT",
    "first_seen": "ALTER TABLE jobs ADD COLUMN first_seen TEXT",
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        for col, ddl in _MIGRATIONS.items():
            if col not in existing:
                conn.execute(ddl)
                log.info("Migrated DB: added column %s", col)
    log.info("DB ready at %s", DB_PATH)


def get_existing_urls() -> set[str]:
    """URLs already stored from previous runs (for cross-run dedupe)."""
    with _connect() as conn:
        return {row["url"] for row in conn.execute("SELECT url FROM jobs")}


def upsert_job(job: dict, date_scored: str) -> None:
    """Insert a new listing, or update all fields except `status`/`first_seen`."""
    url = (job.get("url") or "").strip()
    if not url:
        return

    checklist = json.dumps(job.get("checklist", []), ensure_ascii=False)
    row = {
        "url": url,
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "link": url,
        "score": int(job.get("score", 0) or 0),
        "reason": job.get("reason", ""),
        "summary": job.get("summary", ""),
        "cover_note": job.get("cover_note", ""),
        "checklist": checklist,
        "date_posted": job.get("date_posted", ""),
        "days_since_posted": job.get("days_since_posted"),
        "freshness": job.get("freshness", ""),
        "first_seen": date_scored,   # only used on INSERT (see ON CONFLICT below)
        "date_scored": date_scored,
        "source": job.get("source", ""),
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (url, title, company, location, link, score, reason,
                              summary, cover_note, checklist, status, date_posted,
                              days_since_posted, freshness, first_seen, date_scored,
                              source)
            VALUES (:url, :title, :company, :location, :link, :score, :reason,
                    :summary, :cover_note, :checklist, 'Not Applied', :date_posted,
                    :days_since_posted, :freshness, :first_seen, :date_scored,
                    :source)
            ON CONFLICT(url) DO UPDATE SET
                title             = excluded.title,
                company           = excluded.company,
                location          = excluded.location,
                link              = excluded.link,
                score             = excluded.score,
                reason            = excluded.reason,
                summary           = excluded.summary,
                cover_note        = excluded.cover_note,
                checklist         = excluded.checklist,
                date_posted       = excluded.date_posted,
                days_since_posted = excluded.days_since_posted,
                freshness         = excluded.freshness,
                date_scored       = excluded.date_scored,
                source            = excluded.source
                -- status + first_seen deliberately preserved on update.
            """,
            row,
        )


def get_all_jobs() -> list[dict]:
    """Return all rows as dicts. Parses checklist JSON."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY date_scored DESC, score DESC"
        ).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        try:
            d["checklist"] = json.loads(d.get("checklist") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["checklist"] = []
        out.append(d)
    return out


def set_status(url: str, status: str) -> None:
    """Manually update a listing's status (for the local edit helper script)."""
    with _connect() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE url = ?", (status, url))
