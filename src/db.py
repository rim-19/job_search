"""SQLite source of truth for scored job listings (data/jobs.db).

Schema — one table `jobs`:
    url TEXT PRIMARY KEY, title, company, location, link, score, reason,
    cover_note, checklist (JSON text), status (default 'Not Applied'),
    date_scored, source

Key rule: upsert_job() updates every field EXCEPT `status` when the row already
exists, so a status the user set by hand is never clobbered by a later run.
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
    url         TEXT PRIMARY KEY,
    title       TEXT,
    company     TEXT,
    location    TEXT,
    link        TEXT,
    score       INTEGER,
    reason      TEXT,
    cover_note  TEXT,
    checklist   TEXT,
    status      TEXT DEFAULT 'Not Applied',
    date_scored TEXT,
    source      TEXT
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
    log.info("DB ready at %s", DB_PATH)


def upsert_job(job: dict, date_scored: str) -> None:
    """Insert a new listing, or update all fields except `status` if it exists."""
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
        "cover_note": job.get("cover_note", ""),
        "checklist": checklist,
        "date_scored": date_scored,
        "source": job.get("source", ""),
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (url, title, company, location, link, score, reason,
                              cover_note, checklist, status, date_scored, source)
            VALUES (:url, :title, :company, :location, :link, :score, :reason,
                    :cover_note, :checklist, 'Not Applied', :date_scored, :source)
            ON CONFLICT(url) DO UPDATE SET
                title       = excluded.title,
                company     = excluded.company,
                location    = excluded.location,
                link        = excluded.link,
                score       = excluded.score,
                reason      = excluded.reason,
                cover_note  = excluded.cover_note,
                checklist   = excluded.checklist,
                date_scored = excluded.date_scored,
                source      = excluded.source
            -- status is deliberately NOT updated: preserve manual changes.
            """,
            row,
        )


def get_all_jobs() -> list[dict]:
    """Return all rows as dicts, newest+highest first. Parses checklist JSON."""
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
