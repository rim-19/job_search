"""Two-layer filter + scoring.

Layer 1 (rule-based, free, instant): drop listings whose location field matches
config/restricted_locations.yaml. No AI call.

Layer 2 (Gemini): for survivors, score 1-10 vs the CV and return a one-sentence
reason. The prompt tells the model to score 1 if the *description* hides a
location / work-authorization restriction that Layer 1 couldn't see, since the
user needs remote / worldwide / no-country-restriction roles.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from . import gemini

log = logging.getLogger("scorer")

_ROOT = Path(__file__).resolve().parents[1]
_RESTRICTED = _ROOT / "config" / "restricted_locations.yaml"
_KEYWORDS = _ROOT / "config" / "keywords.yaml"
_CV = _ROOT / "config" / "cv.txt"

# Cap how many listings we send to Gemini per run, to respect the free-tier daily
# quota. 0 = unlimited. We pre-rank cheaply and score the most promising first.
_MAX_SCORE = int(os.getenv("MAX_SCORE", "80"))


def _load_restricted() -> list[str]:
    if not _RESTRICTED.exists():
        return []
    data = yaml.safe_load(_RESTRICTED.read_text(encoding="utf-8")) or {}
    return [s.lower() for s in (data.get("restricted") or [])]


def _load_keywords() -> dict:
    if not _KEYWORDS.exists():
        return {}
    return yaml.safe_load(_KEYWORDS.read_text(encoding="utf-8")) or {}


def _prerank(listings: list[dict]) -> list[dict]:
    """Cheap keyword heuristic to order listings before spending AI quota.

    Rewards stack matches, junior signals and worldwide/remote locations; punishes
    senior signals. No AI call — pure string matching.
    """
    kw = _load_keywords()
    stack = [s.lower() for s in kw.get("preferred_stack", [])]
    junior = [s.lower() for s in kw.get("seniority_include", [])]
    senior = [s.lower() for s in kw.get("seniority_exclude", [])]

    def heuristic(job: dict) -> int:
        text = " ".join([
            job.get("title", ""), job.get("company", ""),
            job.get("location", ""), job.get("description", ""),
        ]).lower()
        title = job.get("title", "").lower()
        loc = job.get("location", "").lower()

        score = 0
        score += sum(2 for s in stack if s in text)
        score += sum(4 for s in junior if s in title)      # junior in title = strong
        score += sum(1 for s in junior if s in text)
        score -= sum(6 for s in senior if s in title)       # senior in title = kill
        if any(w in loc for w in ("worldwide", "anywhere", "global", "remote")):
            score += 5
        return score

    return sorted(listings, key=heuristic, reverse=True)


def _load_cv() -> str:
    return _CV.read_text(encoding="utf-8") if _CV.exists() else ""


def layer1_filter(listings: list[dict]) -> tuple[list[dict], int]:
    """Return (survivors, dropped_count) after the rule-based location filter."""
    restricted = _load_restricted()
    survivors, dropped = [], 0
    for job in listings:
        loc = (job.get("location") or "").lower()
        if any(term in loc for term in restricted):
            dropped += 1
            continue
        survivors.append(job)
    log.info("Layer 1 (rules): %d in -> %d kept, %d dropped by location",
             len(listings), len(survivors), dropped)
    return survivors, dropped


_SCORE_PROMPT = """You are screening a job listing for a specific candidate.

CANDIDATE CV:
{cv}

CANDIDATE HARD REQUIREMENTS:
- Wants a JUNIOR / entry-level / graduate role (not senior/lead/staff/principal).
- Must be FULLY REMOTE.
- Must be open WORLDWIDE with NO country restriction. The candidate lives in
  Morocco (UTC+0/+1) and cannot relocate. Reject roles that require living in,
  being a citizen of, or being authorized to work in a specific country/region,
  or that require heavy overlap with a distant timezone (e.g. US Pacific hours).
- Tech fit: Python, JavaScript/TypeScript, React, Next.js, Node.js, Express,
  HTML/CSS, Java, C#, plus AI/LLM/NLP/automation. Web / software / AI roles fit.

JOB LISTING:
Title: {title}
Company: {company}
Location field: {location}
Description: {description}

Score 1-10 how good a match this is for the candidate.
- Score 1-3 if it is senior-level, not remote, or restricted to a country/region
  the candidate can't work from (INCLUDING restrictions hidden in the description
  text that aren't obvious from the location field).
- Score 4-6 for a partial fit (e.g. remote+worldwide but wrong stack, or right
  stack but ambiguous on remote/worldwide).
- Score 7-10 for a strong fit: junior-friendly, fully remote, worldwide/no
  country restriction, and matching tech.

Respond with STRICT JSON only, no prose, no markdown:
{{"score": <integer 1-10>, "reason": "<one concise sentence>"}}"""


def score_listing(job: dict, cv: str) -> dict | None:
    """Return {'score': int, 'reason': str} or None if scoring failed."""
    prompt = _SCORE_PROMPT.format(
        cv=cv[:6000],
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        description=(job.get("description", "") or "")[:4000],
    )
    try:
        result = gemini.generate_json(prompt)
    except gemini.GeminiError as exc:
        log.warning("Score failed for %r: %s", job.get("title"), exc)
        return None

    try:
        score = int(result.get("score"))
    except (TypeError, ValueError):
        log.warning("Score not an int for %r: %r", job.get("title"), result.get("score"))
        return None
    score = max(1, min(10, score))
    reason = str(result.get("reason", "")).strip()[:300]
    return {"score": score, "reason": reason}


def score_all(listings: list[dict]) -> list[dict]:
    """Run both layers; annotate survivors with `score` and `reason`.

    Returns every scored listing (not just >=7) so the DB keeps a full history.
    Filtering to keepers happens in main.py so counts stay visible.
    """
    survivors, _ = layer1_filter(listings)

    # Pre-rank by cheap keyword heuristic so the best candidates get scored first.
    survivors = _prerank(survivors)

    if not gemini.available():
        log.warning("No Gemini key — assigning neutral score 5 to all survivors.")
        for job in survivors:
            job["score"] = 5
            job["reason"] = "Not scored (no Gemini API key configured)."
        return survivors

    # Respect the free-tier daily quota: only score the top _MAX_SCORE survivors.
    if _MAX_SCORE and len(survivors) > _MAX_SCORE:
        log.info("Capping scoring to top %d of %d survivors (MAX_SCORE) to save quota.",
                 _MAX_SCORE, len(survivors))
        survivors = survivors[:_MAX_SCORE]

    cv = _load_cv()
    scored: list[dict] = []
    log.info("Layer 2 (Gemini): scoring %d listings...", len(survivors))
    for i, job in enumerate(survivors, 1):
        result = score_listing(job, cv)
        if result is None:
            continue
        job["score"] = result["score"]
        job["reason"] = result["reason"]
        scored.append(job)
        if i % 10 == 0:
            log.info("  scored %d/%d", i, len(survivors))
    log.info("Layer 2 done: %d listings scored.", len(scored))
    return scored
