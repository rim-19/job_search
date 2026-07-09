"""Generate a tailored cover note + application checklist for strong matches.

Only listings with score >= threshold get here (keeps free-tier quota focused on
jobs actually worth applying to). One Gemini call per keeper.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import gemini

log = logging.getLogger("drafter")

_CV = Path(__file__).resolve().parents[1] / "config" / "cv.txt"


def _load_cv() -> str:
    return _CV.read_text(encoding="utf-8") if _CV.exists() else ""


_DRAFT_PROMPT = """You are helping a JUNIOR software developer apply to a remote job.

CANDIDATE CV:
{cv}

JOB:
Title: {title}
Company: {company}
Description: {description}

Write:
1. A warm, confident ONE-paragraph cover note (about 4-6 sentences) tailored to
   this specific role and company, in the first person, honest about being a
   junior/early-career developer but leading with relevant projects and stack.
2. A short application checklist (3-6 bullet items) of what this application
   likely needs (e.g. portfolio link, GitHub, tailored CV, cover letter, specific
   answers). Keep items concrete and actionable.

Respond with STRICT JSON only, no markdown:
{{"cover_note": "<one paragraph>", "checklist": ["<item>", "<item>", ...]}}"""


def draft_for(job: dict, cv: str) -> dict:
    """Return {'cover_note': str, 'checklist': [str]}; empty strings on failure."""
    prompt = _DRAFT_PROMPT.format(
        cv=cv[:6000],
        title=job.get("title", ""),
        company=job.get("company", ""),
        description=(job.get("description", "") or "")[:4000],
    )
    try:
        result = gemini.generate_json(prompt, temperature=0.6)
    except gemini.GeminiError as exc:
        log.warning("Draft failed for %r: %s", job.get("title"), exc)
        return {"cover_note": "", "checklist": []}

    cover = str(result.get("cover_note", "")).strip()
    checklist = result.get("checklist", [])
    if not isinstance(checklist, list):
        checklist = []
    checklist = [str(x).strip() for x in checklist if str(x).strip()]
    return {"cover_note": cover, "checklist": checklist}


def draft_all(keepers: list[dict]) -> list[dict]:
    """Attach `cover_note` (str) and `checklist` (list) to each keeper in place."""
    if not keepers:
        return keepers
    if not gemini.available():
        log.warning("No Gemini key — skipping cover-note drafting.")
        for job in keepers:
            job.setdefault("cover_note", "")
            job.setdefault("checklist", [])
        return keepers

    cv = _load_cv()
    log.info("Drafting cover notes for %d keepers...", len(keepers))
    for i, job in enumerate(keepers, 1):
        draft = draft_for(job, cv)
        job["cover_note"] = draft["cover_note"]
        job["checklist"] = draft["checklist"]
        if i % 5 == 0:
            log.info("  drafted %d/%d", i, len(keepers))
    return keepers
