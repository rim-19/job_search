"""SQLite source of truth for scored job listings (data/jobs.db).

Upgraded schema keeps every original column and adds the match/eligibility fields
(priority, eligibility, geographic scope, seniority, experience, gaps, recommended
project, application tracking). Existing columns and behaviour are preserved:
`upsert_job()` never overwrites a manually-set `status` or the original
`first_seen`.

Migrations are additive (ALTER TABLE per new column) plus a one-time score
normalization guarded by PRAGMA user_version, so the pre-upgrade 1-10 scores are
lifted onto the new 0-100 scale exactly once.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger("db")

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "jobs.db"
SCHEMA_VERSION = 2  # bump when a one-time data migration is added below

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    url                   TEXT PRIMARY KEY,
    title                 TEXT,
    company               TEXT,
    location              TEXT,
    link                  TEXT,
    score                 INTEGER,
    reason                TEXT,
    summary               TEXT,
    cover_note            TEXT,
    checklist             TEXT,
    status                TEXT DEFAULT 'Not Applied',
    date_posted           TEXT,
    days_since_posted     INTEGER,
    freshness             TEXT,
    first_seen            TEXT,
    last_seen             TEXT,
    date_scored           TEXT,
    source                TEXT,
    priority              TEXT,
    eligible_for_rim      TEXT,
    eligibility_reason    TEXT,
    geographic_scope      TEXT,
    remote_type           TEXT,
    seniority             TEXT,
    min_years             INTEGER,
    max_years             INTEGER,
    education_requirement TEXT,
    gaps                  TEXT,
    recommended_project   TEXT,
    application_url       TEXT
);
"""

# Columns added after earlier releases — created on existing DBs via migration.
_MIGRATIONS = {
    "summary": "TEXT", "date_posted": "TEXT", "days_since_posted": "INTEGER",
    "freshness": "TEXT", "first_seen": "TEXT", "last_seen": "TEXT",
    "priority": "TEXT", "eligible_for_rim": "TEXT", "eligibility_reason": "TEXT",
    "geographic_scope": "TEXT", "remote_type": "TEXT", "seniority": "TEXT",
    "min_years": "INTEGER", "max_years": "INTEGER", "education_requirement": "TEXT",
    "gaps": "TEXT", "recommended_project": "TEXT", "application_url": "TEXT",
}

_JSON_COLS = ("checklist", "gaps")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        for col, coltype in _MIGRATIONS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {coltype}")
                log.info("Migrated DB: added column %s", col)

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 2:
            # One-time: lift the old 1-10 scores onto the new 0-100 scale.
            n = conn.execute(
                "UPDATE jobs SET score = score * 10 WHERE score > 0 AND score <= 10"
            ).rowcount
            if n:
                log.info("Normalized %d legacy 1-10 scores to 0-100.", n)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
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
        "checklist": json.dumps(job.get("checklist", []), ensure_ascii=False),
        "date_posted": job.get("date_posted", ""),
        "days_since_posted": job.get("days_since_posted"),
        "freshness": job.get("freshness", ""),
        "first_seen": date_scored,   # INSERT only (preserved on conflict)
        "last_seen": date_scored,
        "date_scored": date_scored,
        "source": job.get("source", ""),
        "priority": job.get("priority", ""),
        "eligible_for_rim": job.get("eligible_for_rim", ""),
        "eligibility_reason": job.get("eligibility_reason", ""),
        "geographic_scope": job.get("geographic_scope", ""),
        "remote_type": job.get("remote_type", ""),
        "seniority": job.get("seniority", ""),
        "min_years": job.get("min_years"),
        "max_years": job.get("max_years"),
        "education_requirement": job.get("education_requirement", ""),
        "gaps": json.dumps(job.get("gaps", []), ensure_ascii=False),
        "recommended_project": job.get("recommended_project", ""),
        "application_url": url,
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                url, title, company, location, link, score, reason, summary,
                cover_note, checklist, status, date_posted, days_since_posted,
                freshness, first_seen, last_seen, date_scored, source, priority,
                eligible_for_rim, eligibility_reason, geographic_scope, remote_type,
                seniority, min_years, max_years, education_requirement, gaps,
                recommended_project, application_url)
            VALUES (
                :url, :title, :company, :location, :link, :score, :reason, :summary,
                :cover_note, :checklist, 'Not Applied', :date_posted, :days_since_posted,
                :freshness, :first_seen, :last_seen, :date_scored, :source, :priority,
                :eligible_for_rim, :eligibility_reason, :geographic_scope, :remote_type,
                :seniority, :min_years, :max_years, :education_requirement, :gaps,
                :recommended_project, :application_url)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title, company=excluded.company, location=excluded.location,
                link=excluded.link, score=excluded.score, reason=excluded.reason,
                summary=excluded.summary, cover_note=excluded.cover_note,
                checklist=excluded.checklist, date_posted=excluded.date_posted,
                days_since_posted=excluded.days_since_posted, freshness=excluded.freshness,
                last_seen=excluded.last_seen, date_scored=excluded.date_scored,
                source=excluded.source, priority=excluded.priority,
                eligible_for_rim=excluded.eligible_for_rim,
                eligibility_reason=excluded.eligibility_reason,
                geographic_scope=excluded.geographic_scope, remote_type=excluded.remote_type,
                seniority=excluded.seniority, min_years=excluded.min_years,
                max_years=excluded.max_years, education_requirement=excluded.education_requirement,
                gaps=excluded.gaps, recommended_project=excluded.recommended_project,
                application_url=excluded.application_url
                -- status + first_seen deliberately preserved on update.
            """,
            row,
        )


def get_all_jobs() -> list[dict]:
    """Return all rows as dicts, parsing JSON columns."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY date_scored DESC, score DESC"
        ).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        for col in _JSON_COLS:
            try:
                d[col] = json.loads(d.get(col) or "[]")
            except (json.JSONDecodeError, TypeError):
                d[col] = []
        out.append(d)
    return out


def set_status(url: str, status: str) -> None:
    """Manually update a listing's status (for the local edit helper script)."""
    with _connect() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE url = ?", (status, url))
