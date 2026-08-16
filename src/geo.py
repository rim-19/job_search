"""Deterministic geographic classification + eligibility for a Morocco-based
remote candidate. No AI — pure string logic, so it's fast, free, and testable.

Two jobs:
  * classify(job)     -> structured geo fields (scope, remote_type, city, ...)
  * hard_reject(job)  -> True only when we're CONFIDENT the candidate is excluded
                         (used by the rule filter before any AI call). Ambiguous
                         cases return False here and are left for the AI to judge.

Rules (from config/candidate_profile.yaml, item 7-9 of the spec):
  * Onsite/hybrid are acceptable ONLY in Casablanca or Rabat.
  * Onsite/hybrid anywhere else (other Moroccan cities, or abroad) -> reject.
  * Remote anywhere in Morocco -> accept.
  * International remote -> accept only if someone in Morocco can genuinely work it
    (reject explicit US/Canada/UK/EU work-authorization or residency requirements).
  * "Engineer" in a title is NEVER a geographic signal.
"""

from __future__ import annotations

import re

# --- vocabularies -------------------------------------------------------------

_CASA_RABAT = ("casablanca", "casa", "rabat")

_MOROCCO_CITIES_REJECT = (
    "tangier", "tanger", "marrakech", "marrakesh", "fes", "fez", "fès",
    "agadir", "meknes", "meknès", "oujda", "kenitra", "tetouan", "tétouan",
    "safi", "beni mellal", "nador", "el jadida", "mohammedia", "temara",
    "salé",
)
_MOROCCO_WORDS = ("morocco", "maroc", "moroccan", "marocain")

_HYBRID = ("hybrid", "hybride")
_ONSITE = ("on-site", "on site", "onsite", "in office", "in-office", "in-person",
           "in person", "présentiel", "presentiel", "sur site")
_REMOTE = ("remote", "fully remote", "work from home", "wfh", "télétravail",
           "teletravail", "télé-travail", "distanciel", "anywhere", "work from anywhere")

# Explicit exclusions — the candidate cannot satisfy these.
_WORKAUTH_REJECT = (
    "us citizen", "u.s. citizen", "us citizens", "citizens only",
    "authorized to work in the us", "authorized to work in the united states",
    "us work authorization", "must be authorized to work in the u.s",
    "green card", "security clearance", "must be based in the us",
    "must reside in the united states", "based in the us",
    "canadian work authorization", "authorized to work in canada",
    "right to work in the uk", "uk work authorization",
    "authorized to work in the uk", "must be based in the uk",
    "eu work authorization", "authorized to work in the eu",
    "must be based in the eu", "eu citizen", "eu residents only",
    "work permit for", "valid visa for", "must hold a", "citizenship required",
)

# Scope keyword groups. Order matters: more specific / excluding first.
_US_ONLY = ("us only", "u.s. only", "usa only", "united states only", "us-only",
            "us based", "us-based", "americas only", "latam only", "north america only")
_CANADA_ONLY = ("canada only", "canadian only", "canada-based")
_UK_ONLY = ("uk only", "u.k. only", "united kingdom only", "uk-based")
_WORLDWIDE = ("worldwide", "anywhere in the world", "global", "fully distributed",
              "work from anywhere", "no location restriction", "any location",
              "any country", "location independent")
_MENA = ("mena", "middle east", "arab", "gcc")
_AFRICA = ("africa", "afrique")
_EMEA = ("emea",)
_EUROPE = ("europe", "european", "eu ", " eu", "eea", "schengen")

_TAG_RE = re.compile(r"[^a-z0-9+#]+")


def _text(job: dict) -> tuple[str, str]:
    """Return (location_lower, full_text_lower)."""
    loc = (job.get("location") or "").lower()
    full = " ".join([
        job.get("title", ""), job.get("location", ""), job.get("description", ""),
    ]).lower()
    return loc, full


def _has(text: str, terms) -> bool:
    return any(t in text for t in terms)


def detect_remote_type(loc: str, full: str) -> str:
    """REMOTE | HYBRID | ONSITE | UNKNOWN — location field weighted first."""
    for field in (loc, full):
        if _has(field, _HYBRID):
            return "HYBRID"
    # Onsite only if explicitly onsite AND not also flagged remote.
    onsite = _has(loc, _ONSITE) or _has(full, _ONSITE)
    remote = _has(loc, _REMOTE) or _has(full, _REMOTE)
    if remote and not onsite:
        return "REMOTE"
    if onsite and not remote:
        return "ONSITE"
    if remote and onsite:
        return "HYBRID"  # mentions both -> effectively hybrid
    return "UNKNOWN"


def morocco_city(loc: str, full: str) -> str | None:
    """Return the Moroccan city named, or None. Prefers the location field."""
    for field in (loc, full):
        if any(c in field for c in _CASA_RABAT):
            return "casablanca" if ("casa" in field) else "rabat" if "rabat" in field else "casablanca"
        for c in _MOROCCO_CITIES_REJECT:
            if c in field:
                return c
    return None


def is_morocco(loc: str, full: str) -> bool:
    return _has(loc, _MOROCCO_WORDS) or _has(full, _MOROCCO_WORDS) \
        or morocco_city(loc, full) is not None


def geographic_scope(loc: str, full: str) -> str:
    if _has(loc, _US_ONLY) or _has(full, _US_ONLY):
        return "US_ONLY"
    if _has(loc, _CANADA_ONLY) or _has(full, _CANADA_ONLY):
        return "CANADA_ONLY"
    if _has(loc, _UK_ONLY) or _has(full, _UK_ONLY):
        return "UK_ONLY"
    if _has(loc, _WORLDWIDE):
        return "WORLDWIDE"
    if is_morocco(loc, full):
        return "MOROCCO"
    if _has(loc, _MENA) or _has(full, _MENA):
        return "MENA"
    if _has(loc, _AFRICA):
        return "AFRICA"
    if _has(loc, _EMEA) or _has(full, _EMEA):
        return "EMEA"
    if _has(loc, _EUROPE):
        return "EUROPE"
    if _has(loc, _WORLDWIDE):
        return "WORLDWIDE"
    if loc.strip():
        return "COUNTRY_SPECIFIC"
    return "UNKNOWN"


def classify(job: dict) -> dict:
    """Full structured geo classification for a listing."""
    loc, full = _text(job)
    remote_type = detect_remote_type(loc, full)
    city = morocco_city(loc, full)
    morocco = is_morocco(loc, full)
    scope = geographic_scope(loc, full)

    eligible, reason = _eligibility(remote_type, city, morocco, scope, loc, full)
    return {
        "remote_type": remote_type,
        "morocco_city": city,
        "is_morocco": morocco,
        "geographic_scope": scope,
        "eligible_for_rim": eligible,          # "true" | "false" | "uncertain"
        "eligibility_reason": reason,
    }


def _eligibility(remote_type, city, morocco, scope, loc, full):
    """Return ('true'|'false'|'uncertain', reason)."""
    # Explicit work-authorization / residency the candidate can't satisfy.
    if _has(full, _WORKAUTH_REJECT):
        return "false", "Requires work authorization/residency the candidate can't provide."
    if scope in ("US_ONLY", "CANADA_ONLY", "UK_ONLY"):
        return "false", f"Role is {scope.replace('_', '-').lower()}."

    onsite_or_hybrid = remote_type in ("ONSITE", "HYBRID")
    if onsite_or_hybrid:
        if morocco and city in ("casablanca", "rabat"):
            return "true", f"On-site/hybrid in {city.title()} — commutable for the candidate."
        if morocco and city:  # a rejected Moroccan city
            return "false", f"On-site/hybrid in {city.title()} — outside Casablanca/Rabat."
        if morocco and not city:
            return "uncertain", "Moroccan on-site/hybrid but city unspecified — verify Casablanca/Rabat."
        # On-site/hybrid abroad — candidate cannot relocate.
        return "false", "On-site/hybrid outside Morocco — relocation not possible."

    # From here the role is REMOTE or UNKNOWN remote policy.
    if scope == "WORLDWIDE":
        return "true", "Remote and open worldwide."
    if scope in ("MOROCCO", "AFRICA", "MENA"):
        return "true", f"Remote within the candidate's own region ({scope.title()})."
    if scope in ("EMEA", "EUROPE"):
        return "uncertain", "Europe/EMEA remote — check for EU work-authorization or timezone locks."
    if remote_type == "REMOTE":
        return "uncertain", "Remote but eligible region unclear — verify no country lock."
    return "uncertain", "Remote policy/eligibility unclear."


def hard_reject(job: dict) -> tuple[bool, str]:
    """CONFIDENT deterministic reject for the rule filter. Only True when we're
    sure — ambiguous cases go to the AI. Returns (reject, reason)."""
    c = classify(job)
    if c["eligible_for_rim"] == "false":
        return True, c["eligibility_reason"]
    return False, ""


if __name__ == "__main__":
    samples = [
        {"title": "Full-Stack Developer", "location": "Casablanca, Morocco", "description": "on-site"},
        {"title": "Backend Developer", "location": "Tangier, Morocco", "description": "on-site role"},
        {"title": "Software Developer", "location": "Marrakech", "description": "hybrid, 3 days office"},
        {"title": "Dev", "location": "Remote - Morocco", "description": "fully remote"},
        {"title": "React Dev", "location": "Remote (US)", "description": "must be authorized to work in the US"},
        {"title": "AI Developer", "location": "Anywhere in the World", "description": "remote"},
        {"title": "Engineer", "location": "EMEA", "description": "remote, CET hours"},
    ]
    for s in samples:
        c = classify(s)
        print(f"{s['location']:<24} -> {c['remote_type']:<7} {c['geographic_scope']:<14} "
              f"{c['eligible_for_rim']:<9} | {c['eligibility_reason']}")
