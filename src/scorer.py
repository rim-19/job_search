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

# Cap how many NEW listings we send to the LLM per run (already-scored ones are
# skipped upstream). 0 = unlimited. We pre-rank cheaply and score the best first.
# Higher than before because runs are frequent and only score net-new listings.
_MAX_SCORE = int(os.getenv("MAX_SCORE", "120"))


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

        # A senior title (staff/lead/principal/senior/manager/…) sinks the
        # listing so it doesn't eat scoring budget, no matter its stack keywords.
        if any(s in title for s in senior):
            return -100

        score = 0
        score += sum(2 for s in stack if s in text)
        score += sum(4 for s in junior if s in title)      # junior in title = strong
        score += sum(1 for s in junior if s in text)
        # Location bonus: worldwide is ideal; workable regions still surface well.
        if any(w in loc for w in ("worldwide", "anywhere", "global", "no restriction")):
            score += 5
        elif any(w in loc for w in ("remote", "emea", "europe", "africa", "mena",
                                     "uk", "gmt", "cet", "morocco")):
            score += 3
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

CANDIDATE PROFILE:
- Lives in Morocco (Casablanca), timezone UTC+0/+1 (same as GMT/WET; ~CET-1).
  Cannot relocate; works fully remotely as a contractor / via Employer of Record.
- Wants a JUNIOR / entry-level / graduate role (not senior/lead/staff/principal).
- Must be FULLY REMOTE (not onsite, not hybrid).
- Tech fit: Python, JavaScript/TypeScript, React, Next.js, Node.js, Express,
  HTML/CSS, Java, C#, plus AI/LLM/NLP/automation. Web / software / AI roles fit.

CRITICAL — WHERE THE CANDIDATE CAN WORK (read carefully, this is often misjudged):
She is NOT limited to "worldwide only" roles. She can realistically take a role if
ANY of these is true, and such roles should score WELL on location:
  * Open worldwide / "anywhere" / global / no location restriction.
  * Restricted to EUROPE / EMEA / EU-timezone / CET / GMT / "European hours" —
    her timezone overlaps perfectly. (Location says "Europe"/"EMEA" = GOOD.)
  * Restricted to AFRICA, MENA, Middle East, Arab region, or Morocco itself —
    these are her OWN region; treat as a STRONG positive, not a restriction.
  * Hires globally via "Employer of Record", "international contractor",
    "contractor anywhere", or pays in USD/EUR to remote contractors.
  * UK-timezone / GMT-overlap contractor roles that don't require UK residency.
Only treat location as a REAL blocker (score low) when the role genuinely
excludes her, e.g.:
  * "US only", "US citizens/residents only", requires US/UK/EU/Canada legal work
    authorization, visa, SSN, or being physically located there.
  * Americas-only, LATAM-only, US-timezone-only (EST/PST core hours), or
    APAC/Asia-Pacific-only (night shifts for her).
  * Onsite or hybrid anywhere.
When a role is remote but its allowed region is unclear, do NOT assume the worst —
lean toward giving it a chance (mid score) rather than rejecting it.

JOB LISTING:
Title: {title}
Company: {company}
Location field: {location}
Description: {description}

Do TWO things:

A) Score 1-10 how good a match this is for the candidate.
- Score 1-3 ONLY if it is senior-level, not remote (onsite/hybrid), or genuinely
  excludes her location (needs specific US/UK/EU/Canada work authorization, or is
  Americas/US-timezone/APAC-locked) per the rules above.
- Score 4-6 for a partial fit (right location but wrong stack or too senior, or
  location genuinely ambiguous).
- Score 7-10 for a strong fit: junior-friendly, fully remote, in a region she can
  work (worldwide OR Europe/EMEA/Africa/MENA/EOR/contractor), and matching tech.
  A junior remote role in her own region (Africa/MENA) with decent tech = 8-10.

B) Write a 2-3 sentence plain-English SUMMARY of the listing for the candidate:
what the role is, the main tech/responsibilities, and the remote/location scope.
No hype, no fluff — just the key facts she needs to decide at a glance.

Respond with STRICT JSON only, no prose, no markdown:
{{"score": <integer 1-10>, "reason": "<one concise sentence>", "summary": "<2-3 sentences>"}}"""


def score_listing(job: dict, cv: str) -> dict | None:
    """Return {'score': int, 'reason': str} or None if scoring failed."""
    # Keep the prompt compact — big prompts blow the LLM's tokens-per-minute
    # limits during bulk scoring (esp. the Groq fallback). This is plenty for a
    # score + a 2-3 sentence summary.
    prompt = _SCORE_PROMPT.format(
        cv=cv[:1800],
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        description=(job.get("description", "") or "")[:1800],
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
    summary = str(result.get("summary", "")).strip()[:600]
    return {"score": score, "reason": reason, "summary": summary}


def score_all(listings: list[dict], skip_urls: set[str] | None = None) -> list[dict]:
    """Run both layers; annotate survivors with `score`, `reason`, `summary`.

    `skip_urls` are URLs already scored in a previous run — they're excluded so
    frequent runs only spend the LLM on genuinely new listings (existing ones
    keep their stored scores in the DB). Returns the newly-scored listings.
    """
    survivors, _ = layer1_filter(listings)

    # Skip listings we've already scored before (cross-run efficiency).
    if skip_urls:
        before = len(survivors)
        survivors = [j for j in survivors if j.get("url") not in skip_urls]
        log.info("Skipping %d already-scored listings; %d new to score.",
                 before - len(survivors), len(survivors))

    if not survivors:
        log.info("No new listings to score this run.")
        return []

    # Pre-rank by cheap keyword heuristic so the best candidates get scored first.
    survivors = _prerank(survivors)

    if not gemini.available():
        log.warning("No Gemini key — assigning neutral score 5 to all survivors.")
        for job in survivors:
            job["score"] = 5
            job["reason"] = "Not scored (no Gemini API key configured)."
            job["summary"] = (job.get("description", "") or "")[:300]
        return survivors

    # Respect the free-tier daily quota: only score the top _MAX_SCORE survivors.
    if _MAX_SCORE and len(survivors) > _MAX_SCORE:
        log.info("Capping scoring to top %d of %d survivors (MAX_SCORE) to save quota.",
                 _MAX_SCORE, len(survivors))
        survivors = survivors[:_MAX_SCORE]

    cv = _load_cv()
    scored: list[dict] = []
    log.info("Layer 2 (%s): scoring %d listings...", gemini.active_provider(), len(survivors))
    for i, job in enumerate(survivors, 1):
        result = score_listing(job, cv)
        if result is None:
            continue
        job["score"] = result["score"]
        job["reason"] = result["reason"]
        job["summary"] = result["summary"]
        scored.append(job)
        if i % 10 == 0:
            log.info("  scored %d/%d", i, len(survivors))
    log.info("Layer 2 done: %d listings scored.", len(scored))
    return scored
