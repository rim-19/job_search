"""Morocco job-board scrapers (free, no API key): ReKrute + Bayt.

These sites have no RSS/JSON API, so we parse their public HTML. ReKrute encodes
title/company/city in the job URL slug (reliable even though the visible title is
JS-rendered); Bayt exposes job links with title-bearing slugs too. Both are
best-effort and fail-safe: a block, timeout, or markup change logs a warning and
returns nothing rather than breaking the run.

geo.py then keeps only remote or Casablanca/Rabat on-site/hybrid roles, so the
Morocco-city noise these boards carry is filtered downstream.
"""

from __future__ import annotations

import html as _html
import logging
import re

import requests

log = logging.getLogger("collectors.morocco")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
TIMEOUT = 25

_KNOWN_CITIES = (
    "casablanca", "rabat", "tanger", "tangier", "marrakech", "fes", "fez",
    "agadir", "meknes", "oujda", "kenitra", "tetouan", "safi", "nador",
    "mohammedia", "temara", "sale", "maroc", "morocco",
)


def _titleize(slug: str) -> str:
    return re.sub(r"\s+", " ", slug.replace("-", " ")).strip().title()


# --- ReKrute -----------------------------------------------------------------

_REKRUTE_URL = "https://www.rekrute.com/offres.html?sectorId%5B0%5D=24&s=1&p={page}&o=1"
_REKRUTE_HREF = re.compile(r"/offre-emploi-([a-z0-9-]+?)-(\d+)\.html", re.I)


def _parse_rekrute_slug(slug: str, jobid: str, href: str) -> dict | None:
    # slug = <title>-recrutement-<company>-<city>
    if "-recrutement-" in slug:
        title_part, comp_city = slug.split("-recrutement-", 1)
    else:
        title_part, comp_city = slug, ""
    tokens = [t for t in comp_city.split("-") if t]
    city = ""
    if tokens and tokens[-1] in _KNOWN_CITIES:
        city = tokens[-1]
        company = _titleize("-".join(tokens[:-1]))
    else:
        company = _titleize(comp_city)
    title = _titleize(title_part)
    if not title:
        return None
    loc = f"{city.title()}, Morocco" if city and city not in ("maroc", "morocco") else "Morocco"
    return {
        "title": title, "company": company or "—", "location": loc,
        "url": f"https://www.rekrute.com/offre-emploi-{slug}-{jobid}.html",
        "description": f"{title} at {company}. {loc}. (ReKrute — Moroccan job board)",
        "source": "ReKrute", "date_posted": "",
    }


def _rekrute(pages: int = 2) -> list[dict]:
    out, seen = [], set()
    for page in range(1, pages + 1):
        try:
            html = requests.get(_REKRUTE_URL.format(page=page), headers=HEADERS,
                                 timeout=TIMEOUT).text
        except requests.RequestException as exc:
            log.warning("  ReKrute page %d failed: %s", page, exc)
            continue
        for slug, jobid in _REKRUTE_HREF.findall(html):
            if jobid in seen:
                continue
            seen.add(jobid)
            rec = _parse_rekrute_slug(slug.lower(), jobid, "")
            if rec:
                out.append(rec)
    log.info("  ReKrute -> %d listings", len(out))
    return out


# --- Bayt (Morocco) ----------------------------------------------------------

_BAYT_URL = "https://www.bayt.com/en/morocco/jobs/?page={page}"
_BAYT_HREF = re.compile(r'href="(/en/morocco/jobs/([a-z0-9-]+?)-(\d+)/)"', re.I)


def _bayt(pages: int = 2) -> list[dict]:
    out, seen = [], set()
    for page in range(1, pages + 1):
        try:
            html = requests.get(_BAYT_URL.format(page=page), headers=HEADERS,
                                 timeout=TIMEOUT).text
        except requests.RequestException as exc:
            log.warning("  Bayt page %d failed: %s", page, exc)
            continue
        for href, slug, jobid in _BAYT_HREF.findall(html):
            if jobid in seen:
                continue
            seen.add(jobid)
            tokens = slug.split("-")
            city = ""
            # Bayt slugs often end with "...-<city>-morocco"
            for c in _KNOWN_CITIES:
                if f"-{c}-" in f"-{slug}-" and c not in ("maroc", "morocco"):
                    city = c
                    break
            title = _titleize(re.sub(r"-(morocco|" + "|".join(_KNOWN_CITIES) + r")\b", "", slug))
            if not title:
                continue
            loc = f"{city.title()}, Morocco" if city else "Morocco"
            out.append({
                "title": title, "company": "—", "location": loc,
                "url": "https://www.bayt.com" + href,
                "description": f"{title}. {loc}. (Bayt — Morocco job board)",
                "source": "Bayt", "date_posted": "",
            })
    log.info("  Bayt -> %d listings", len(out))
    return out


# Bayt (_bayt) is kept above but NOT called: it returns HTTP 403 to datacenter
# IPs (GitHub Actions), so it can't run from CI. Re-enable if that changes.
_ACTIVE = (_rekrute,)


def fetch_all() -> list[dict]:
    log.info("Scraping Morocco boards (ReKrute)...")
    listings: list[dict] = []
    for fn in _ACTIVE:
        try:
            listings.extend(fn())
        except Exception as exc:  # noqa: BLE001
            log.warning("  %s failed: %s", fn.__name__, exc)
    log.info("Morocco boards -> %d listings total", len(listings))
    return listings


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for j in fetch_all()[:12]:
        print(f"  {j['source']:<8} | {j['location']:<22} | {j['title'][:50]} @ {j['company'][:24]}")
