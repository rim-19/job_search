"""Playwright collector for target career pages without a free API.

Reads config/target_sites.yaml. For each site it opens a headless Chromium page,
optionally waits for a selector, then extracts one record per `job_selector`
match. Everything is best-effort: a broken selector or dead site logs a warning
and returns nothing for that site rather than crashing the pipeline.

Playwright is optional. If it isn't installed, this module degrades to a no-op so
the API-only pipeline still runs.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urljoin

import yaml

log = logging.getLogger("collectors.playwright")

CONFIG = Path(__file__).resolve().parents[2] / "config" / "target_sites.yaml"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


def _load_sites() -> list[dict]:
    if not CONFIG.exists():
        return []
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return data.get("sites") or []


async def _scrape_site(page, site: dict) -> list[dict]:
    name = site.get("name", site.get("url", "?"))
    base = site.get("base_url", "")
    fields = site.get("fields", {})
    out: list[dict] = []

    await page.goto(site["url"], wait_until="domcontentloaded", timeout=45000)
    if site.get("wait_for"):
        try:
            await page.wait_for_selector(site["wait_for"], timeout=15000)
        except Exception:  # noqa: BLE001
            log.warning("  %s: wait_for selector never appeared", name)

    cards = await page.query_selector_all(site["job_selector"])
    for card in cards:
        async def _text(sel):
            if not sel:
                return ""
            el = await card.query_selector(sel)
            return _clean(await el.inner_text()) if el else ""

        title = await _text(fields.get("title"))
        company = await _text(fields.get("company"))
        location = await _text(fields.get("location"))

        link_attr = site.get("link_attr", "href")
        href = await card.get_attribute(link_attr) or ""
        if href and base:
            href = urljoin(base, href)

        if title and href:
            out.append({
                "title": title,
                "company": company,
                "location": location or "Remote",
                "url": href,
                "description": await _text(fields.get("description")),
                "source": name,
                "date_posted": "",
            })
    log.info("  %-25s -> %d listings", name, len(out))
    return out


async def _run() -> list[dict]:
    sites = _load_sites()
    if not sites:
        log.info("No Playwright target sites configured — skipping.")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("Playwright not installed — skipping browser sources.")
        return []

    listings: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; job-agent/1.0)"
        )
        page = await context.new_page()
        for site in sites:
            try:
                listings.extend(await _scrape_site(page, site))
            except Exception as exc:  # noqa: BLE001
                log.warning("  %s: FAILED: %s", site.get("name", "?"), exc)
        await browser.close()
    return listings


def fetch_all() -> list[dict]:
    """Synchronous entry point for Playwright-scraped listings."""
    import asyncio
    log.info("Running Playwright target sites...")
    try:
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        log.warning("Playwright collector failed entirely: %s", exc)
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for j in fetch_all():
        print(j["source"], "|", j["title"], "@", j["company"])
