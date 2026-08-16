"""Two-layer filter + scoring (upgraded to a match/eligibility engine).

Layer 1 (rule-based, free, instant): drop listings that config/restricted_locations
matches OR that src/geo.py can confidently reject (e.g. on-site outside
Casablanca/Rabat, US/Canada/UK/EU work-authorization requirements).

Layer 2 (LLM): for survivors, return a rich structured judgement — a 0-100 match
score, a priority bucket, geographic eligibility, seniority/experience extraction,
match gaps, and the single most relevant project. A deterministic geo check
overrides the model on eligibility so a technically-perfect but ineligible role is
never surfaced as a match.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from . import gemini, geo

log = logging.getLogger("scorer")

_ROOT = Path(__file__).resolve().parents[1]
_RESTRICTED = _ROOT / "config" / "restricted_locations.yaml"
_KEYWORDS = _ROOT / "config" / "keywords.yaml"
_PROFILE = _ROOT / "config" / "candidate_profile.yaml"
_CV = _ROOT / "config" / "cv.txt"

_MAX_SCORE = int(os.getenv("MAX_SCORE", "120"))

PRIORITIES = ("APPLY_NOW", "APPLY", "CONSIDER", "SKIP")
_PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}


# --- config loaders -----------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_restricted() -> list[str]:
    return [s.lower() for s in (_load_yaml(_RESTRICTED).get("restricted") or [])]


def _load_keywords() -> dict:
    return _load_yaml(_KEYWORDS)


def _load_cv() -> str:
    return _CV.read_text(encoding="utf-8") if _CV.exists() else ""


def _profile_block() -> str:
    """Compact candidate summary for the prompt, from candidate_profile.yaml."""
    p = _load_yaml(_PROFILE)
    pos = p.get("positioning", {})
    roles = p.get("target_roles", {})
    tech = p.get("tech", {})
    projects = p.get("projects", [])
    tech_line = "; ".join(
        f"{k}: {', '.join(v)}" for k, v in tech.items() if v
    )
    proj_line = "; ".join(f"{x['name']} ({x['proves']})" for x in projects)
    return (
        f"Positioning: {pos.get('primary', 'AI + Full-Stack Software Developer')}. "
        f"Not a single-language specialist.\n"
        f"Primary target roles: {', '.join(roles.get('primary', [])[:12])}, "
        f"plus internships/graduate.\n"
        f"Tech: {tech_line}\n"
        f"Projects (evidence): {proj_line}"
    )


# --- pre-ranking --------------------------------------------------------------

def _prerank(listings: list[dict]) -> list[dict]:
    """Cheap keyword heuristic to order listings before spending AI quota."""
    kw = _load_keywords()
    stack = [s.lower() for s in kw.get("preferred_stack", [])]
    junior = [s.lower() for s in kw.get("seniority_include", [])]
    senior = [s.lower() for s in kw.get("seniority_exclude", [])]

    def heuristic(job: dict) -> int:
        title = job.get("title", "").lower()
        loc = job.get("location", "").lower()
        text = " ".join([title, job.get("company", ""), loc,
                         job.get("description", "")]).lower()

        if any(s in title for s in senior):
            return -100

        score = 0
        score += sum(2 for s in stack if s in text)
        score += sum(4 for s in junior if s in title)
        score += sum(1 for s in junior if s in text)
        if any(w in loc for w in ("worldwide", "anywhere", "global", "no restriction")):
            score += 5
        elif any(w in loc for w in ("remote", "emea", "europe", "africa", "mena",
                                     "uk", "gmt", "cet", "morocco", "maroc")):
            score += 3
        # Casablanca / Rabat on-site is genuinely applyable — lift it too.
        if "casablanca" in loc or "rabat" in loc:
            score += 4
        return score

    return sorted(listings, key=heuristic, reverse=True)


# --- Layer 1 ------------------------------------------------------------------

def layer1_filter(listings: list[dict]) -> tuple[list[dict], int]:
    """Drop listings by the restricted-string list OR a confident geo reject."""
    restricted = _load_restricted()
    survivors, dropped = [], 0
    for job in listings:
        loc = (job.get("location") or "").lower()
        if any(term in loc for term in restricted):
            dropped += 1
            continue
        reject, _reason = geo.hard_reject(job)
        if reject:
            dropped += 1
            continue
        survivors.append(job)
    log.info("Layer 1 (rules+geo): %d in -> %d kept, %d dropped",
             len(listings), len(survivors), dropped)
    return survivors, dropped


# --- Layer 2 (LLM) ------------------------------------------------------------

_SCORE_PROMPT = """You screen ONE job for a specific candidate and return STRICT JSON only.

CANDIDATE (source of truth — never invent skills/experience beyond this):
{profile}

CV excerpt:
{cv}

GEOGRAPHIC RULES (hard requirement):
- Based in Morocco (Casablanca), timezone UTC+0/+1. Cannot relocate.
- ACCEPT: remote worldwide; remote anywhere in Morocco; remote Africa/MENA/Arab region; on-site OR hybrid ONLY in Casablanca or Rabat; Europe/EMEA remote IF it does not require EU work authorization and the timezone is workable.
- REJECT: on-site/hybrid anywhere except Casablanca or Rabat; roles requiring US/Canada/UK/EU work authorization, a visa, citizenship, or residency; US/Americas/APAC-timezone-locked roles.
- The word "Engineer" in a title is NEVER a reason to reject. Judge by actual seniority, years and requirements. Reject Senior/Lead/Staff/Principal/Manager or 5+ years required.

DETERMINISTIC GEO HINT (from the rules above — trust unless the text clearly contradicts): remote_type={geo_remote}, scope={geo_scope}, eligible={geo_elig} ({geo_reason})

ROLE TARGETING: primary fit = full-stack / backend / software / web / application / AI / LLM / generative-AI developer at junior / entry / intern / graduate level (score these highest). Language-specific titles (Python/Node/Java/C# Developer) are only a secondary fit — fine if junior and the stack matches, but she is NOT a single-language specialist.

JOB:
Title: {title}
Company: {company}
Location: {location}
Description: {description}

Score 0-100 weighing technical fit (~30), experience/seniority fit (~20), geographic eligibility (~20), AI/LLM relevance (~10), stack overlap (~10), accessibility+freshness (~10). If the candidate is geographically ineligible, OR the role clearly needs senior-level / 5+ years experience, the score MUST be below 55.
Pick the single most relevant project or "None": Nexus AI, PromptCheck, Noesis, Cupid, HR-Genius, Ghazala AI, MultiMind AI — only when genuinely relevant.

Return STRICT JSON only, no markdown:
{{"score": <0-100 int>, "priority": "APPLY_NOW|APPLY|CONSIDER|SKIP", "eligible": <true|false|"uncertain">, "eligibility_reason": "<short>", "geographic_scope": "<WORLDWIDE|MOROCCO|AFRICA|MENA|EMEA|EUROPE|COUNTRY_SPECIFIC|US_ONLY|CANADA_ONLY|UK_ONLY|OTHER|UNKNOWN>", "remote_type": "<REMOTE|HYBRID|ONSITE|UNKNOWN>", "seniority": "<INTERN|ENTRY_LEVEL|JUNIOR|EARLY_CAREER|MID|SENIOR|LEAD|STAFF|PRINCIPAL|MANAGER|UNKNOWN>", "min_years": <int or null>, "max_years": <int or null>, "education_requirement": "<required|preferred|equivalent_allowed|unspecified>", "reason": "<one sentence>", "summary": "<2-3 sentences>", "gaps": ["<short gap>"], "recommended_project": "<project name or None>"}}"""


def _priority_from_score(score: int) -> str:
    if score >= 85:
        return "APPLY_NOW"
    if score >= 70:
        return "APPLY"
    if score >= 55:
        return "CONSIDER"
    return "SKIP"


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def score_listing(job: dict, cv: str, profile: str) -> dict | None:
    """Return the rich judgement dict, or None if scoring failed."""
    g = geo.classify(job)
    prompt = _SCORE_PROMPT.format(
        profile=profile,
        cv=cv[:1200],
        geo_remote=g["remote_type"], geo_scope=g["geographic_scope"],
        geo_elig=g["eligible_for_rim"], geo_reason=g["eligibility_reason"][:80],
        title=job.get("title", ""), company=job.get("company", ""),
        location=job.get("location", ""),
        description=(job.get("description", "") or "")[:1600],
    )
    try:
        r = gemini.generate_json(prompt)
    except gemini.GeminiError as exc:
        log.warning("Score failed for %r: %s", job.get("title"), exc)
        return None

    score = _as_int(r.get("score"))
    if score is None:
        log.warning("No int score for %r: %r", job.get("title"), r.get("score"))
        return None
    score = max(0, min(100, score))

    # Normalise eligibility (accept bool or string).
    elig = r.get("eligible")
    if isinstance(elig, bool):
        elig = "true" if elig else "false"
    elig = str(elig).lower()
    if elig not in ("true", "false", "uncertain"):
        elig = g["eligible_for_rim"]

    # Deterministic geo override: a confident geo reject wins over the model.
    if g["eligible_for_rim"] == "false":
        elig = "false"

    priority = str(r.get("priority", "")).upper()
    if priority not in PRIORITIES:
        priority = _priority_from_score(score)

    # Eligibility override: ineligible roles can never be a match.
    if elig == "false":
        score = min(score, 40)
        priority = "SKIP"

    gaps = r.get("gaps", [])
    gaps = [str(x).strip() for x in gaps if str(x).strip()] if isinstance(gaps, list) else []
    project = str(r.get("recommended_project", "") or "").strip()
    if project.lower() in ("none", "n/a", "-"):
        project = ""

    return {
        "score": score,
        "priority": priority,
        "reason": str(r.get("reason", "")).strip()[:300],
        "summary": str(r.get("summary", "")).strip()[:600],
        "eligible_for_rim": elig,
        "eligibility_reason": str(r.get("eligibility_reason", "")).strip()[:200] or g["eligibility_reason"],
        "geographic_scope": str(r.get("geographic_scope", "")).strip().upper() or g["geographic_scope"],
        "remote_type": str(r.get("remote_type", "")).strip().upper() or g["remote_type"],
        "seniority": str(r.get("seniority", "")).strip().upper() or "UNKNOWN",
        "min_years": _as_int(r.get("min_years")),
        "max_years": _as_int(r.get("max_years")),
        "education_requirement": str(r.get("education_requirement", "unspecified")).strip().lower(),
        "gaps": gaps,
        "recommended_project": project,
    }


def _fallback_fields(job: dict) -> None:
    """When no LLM is available, fill deterministic geo fields + neutral score."""
    g = geo.classify(job)
    job.update({
        "score": 50, "priority": "CONSIDER",
        "reason": "Not AI-scored (no LLM key configured).",
        "summary": (job.get("description", "") or "")[:300],
        "eligible_for_rim": g["eligible_for_rim"],
        "eligibility_reason": g["eligibility_reason"],
        "geographic_scope": g["geographic_scope"], "remote_type": g["remote_type"],
        "seniority": "UNKNOWN", "min_years": None, "max_years": None,
        "education_requirement": "unspecified", "gaps": [], "recommended_project": "",
    })
    if g["eligible_for_rim"] == "false":
        job["score"], job["priority"] = 30, "SKIP"


def score_all(listings: list[dict], skip_urls: set[str] | None = None) -> list[dict]:
    """Run both layers; annotate survivors with the rich judgement fields.
    Only net-new listings (not in skip_urls) are scored."""
    survivors, _ = layer1_filter(listings)

    if skip_urls:
        before = len(survivors)
        survivors = [j for j in survivors if j.get("url") not in skip_urls]
        log.info("Skipping %d already-scored listings; %d new to score.",
                 before - len(survivors), len(survivors))

    if not survivors:
        log.info("No new listings to score this run.")
        return []

    survivors = _prerank(survivors)

    if not gemini.available():
        log.warning("No LLM key — assigning deterministic fallback fields.")
        for job in survivors:
            _fallback_fields(job)
        return survivors

    if _MAX_SCORE and len(survivors) > _MAX_SCORE:
        log.info("Capping scoring to top %d of %d survivors (MAX_SCORE).",
                 _MAX_SCORE, len(survivors))
        survivors = survivors[:_MAX_SCORE]

    cv = _load_cv()
    profile = _profile_block()
    scored: list[dict] = []
    log.info("Layer 2 (%s): scoring %d listings...", gemini.active_provider(), len(survivors))
    for i, job in enumerate(survivors, 1):
        result = score_listing(job, cv, profile)
        if result is None:
            continue
        job.update(result)
        scored.append(job)
        if i % 10 == 0:
            log.info("  scored %d/%d", i, len(survivors))
    log.info("Layer 2 done: %d listings scored.", len(scored))
    return scored
