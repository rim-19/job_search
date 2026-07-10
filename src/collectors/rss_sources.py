"""RSS / Atom collector (Working Nomads, NoDesk, Jobicy RSS, Google Alerts).

Uses `feedparser`. Reads config/rss_feeds.yaml. Each entry becomes one record in
the common schema. RSS rarely has clean company/location fields, so we do
best-effort extraction from the title ("Title at Company") and default location
to "Remote". Dead feeds are skipped with a warning.

Google Alerts feeds are treated identically to any other feed — they're just
another list of URLs in the config.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

log = logging.getLogger("collectors.rss")

CONFIG = Path(__file__).resolve().parents[2] / "config" / "rss_feeds.yaml"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", str(text))).strip()


def _load_config() -> tuple[list[dict], list[str]]:
    if not CONFIG.exists():
        return [], []
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return (data.get("feeds") or []), (data.get("google_alerts") or [])


def _split_title_company(entry) -> tuple[str, str]:
    """Try to pull (title, company) out of an RSS entry.

    Handles common patterns like "Senior Dev at Acme" or "Acme: Senior Dev",
    and falls back to the entry author for company.
    """
    raw = _clean(entry.get("title", ""))
    company = _clean(entry.get("author", "")) or ""

    # "Title at Company"
    m = re.search(r"^(.*?)\s+(?:at|@)\s+(.+)$", raw, re.IGNORECASE)
    if m:
        return m.group(1).strip(), (company or m.group(2).strip())
    # "Company: Title"
    if ":" in raw and not company:
        left, right = raw.split(":", 1)
        if len(left) < 40:  # left side looks like a company, not a sentence
            return right.strip(), left.strip()
    return raw, company


def _entry_location(entry, description: str) -> str:
    # Some feeds tag region/location; otherwise infer from text.
    for key in ("region", "location"):
        val = entry.get(key)
        if val:
            return _clean(val)
    text = (description or "").lower()
    if "worldwide" in text or "anywhere" in text:
        return "Worldwide"
    return "Remote"


def _parse_feed(name: str, url: str) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        log.warning("feedparser not installed — skipping RSS sources.")
        return []

    parsed = feedparser.parse(url)
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        log.warning("  %-22s -> unreadable feed (%s)", name, url)
        return []

    out = []
    for entry in parsed.entries:
        link = _clean(entry.get("link", ""))
        if not link:
            continue
        description = _clean(entry.get("summary", "") or entry.get("description", ""))
        title, company = _split_title_company(entry)
        # published / updated string; recency.py parses it later.
        date_posted = entry.get("published", "") or entry.get("updated", "")
        out.append({
            "title": title,
            "company": company,
            "location": _entry_location(entry, description),
            "url": link,
            "description": description,
            "source": name,
            "date_posted": date_posted,
        })
    log.info("  %-22s -> %d listings", name, len(out))
    return out


def fetch_all() -> list[dict]:
    feeds, alerts = _load_config()
    all_feeds = list(feeds) + [
        {"name": f"Google Alert {i+1}", "url": u} for i, u in enumerate(alerts)
    ]
    if not all_feeds:
        log.info("No RSS feeds configured — skipping.")
        return []

    log.info("Fetching %d RSS feeds...", len(all_feeds))
    listings: list[dict] = []
    for feed in all_feeds:
        try:
            listings.extend(_parse_feed(feed["name"], feed["url"]))
        except Exception as exc:  # noqa: BLE001
            log.warning("  %s: FAILED: %s", feed.get("name", "?"), exc)
    log.info("RSS sources returned %d listings total.", len(listings))
    return listings


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for j in fetch_all()[:10]:
        print(j["source"], "|", j["title"], "@", j["company"])
