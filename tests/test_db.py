"""Database persistence, migrations, and manual-status preservation."""
from src import db


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()


def test_status_and_first_seen_survive_upsert(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    job = {"url": "u1", "title": "T", "score": 80, "priority": "APPLY"}
    db.upsert_job(job, "2026-01-01")
    db.set_status("u1", "Applied")
    db.upsert_job(job, "2026-01-02")  # a later run re-upserts
    row = {r["url"]: r for r in db.get_all_jobs()}["u1"]
    assert row["status"] == "Applied"        # manual status preserved
    assert row["first_seen"] == "2026-01-01"  # first_seen preserved
    assert row["last_seen"] == "2026-01-02"   # last_seen updated


def test_new_fields_round_trip(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    job = {"url": "u", "title": "T", "score": 90, "priority": "APPLY_NOW",
           "eligible_for_rim": "true", "geographic_scope": "MOROCCO",
           "remote_type": "REMOTE", "seniority": "JUNIOR", "min_years": 0,
           "gaps": ["AWS preferred"], "recommended_project": "Nexus AI"}
    db.upsert_job(job, "2026-01-01")
    r = db.get_all_jobs()[0]
    assert r["priority"] == "APPLY_NOW"
    assert r["recommended_project"] == "Nexus AI"
    assert r["gaps"] == ["AWS preferred"]
    assert r["eligible_for_rim"] == "true"


def test_legacy_score_normalization(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    # Simulate a pre-upgrade DB: old 1-10 score, schema version 0.
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("UPDATE jobs SET score=8 WHERE 1=0")  # ensure table exists
        c.execute("INSERT INTO jobs (url, title, score) VALUES ('leg', 'T', 8)")
        c.execute("PRAGMA user_version = 0")
    db.init_db()  # migration should lift 8 -> 80
    row = {r["url"]: r for r in db.get_all_jobs()}["leg"]
    assert row["score"] == 80


def test_url_uniqueness(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    db.upsert_job({"url": "same", "title": "A", "score": 10}, "2026-01-01")
    db.upsert_job({"url": "same", "title": "B", "score": 20}, "2026-01-02")
    rows = db.get_all_jobs()
    assert len(rows) == 1 and rows[0]["title"] == "B"
