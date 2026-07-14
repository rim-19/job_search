"""Send a run summary to Telegram via a plain HTTPS request (no SDK).

Only NEW listings (URLs not seen in a previous run) are surfaced, so the evening
run never re-sends what the morning run already showed. Fresh (<=7 days) listings
are listed first.
"""

from __future__ import annotations

import logging
import os

import requests

from . import recency

log = logging.getLogger("notifier")

SITE_URL = os.getenv("SITE_URL", "https://rim-19.github.io/job_search/")


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_MAX_COMPANIES = 50  # keep the message under Telegram's 4096-char limit


def _company_list(scored: list[dict]) -> tuple[str, int] | str:
    """One line per scanned offer: "Company — Post title", sorted by company."""
    items = []
    seen = set()
    for j in scored:
        company = (j.get("company") or "").strip()
        title = (j.get("title") or "").strip()
        if not (company or title):
            continue
        key = (company.casefold(), title.casefold())
        if key in seen:
            continue
        seen.add(key)
        items.append((company or "—", title or "—"))

    if not items:
        return ""

    items.sort(key=lambda t: (t[0].casefold(), t[1].casefold()))
    shown = items[:_MAX_COMPANIES]
    lines = [f"• <b>{_escape(c)}</b> — {_escape(t)}" for c, t in shown]
    body = "\n".join(lines)
    if len(items) > _MAX_COMPANIES:
        body += f"\n<i>… +{len(items) - _MAX_COMPANIES} more</i>"
    return body, len(items)


def build_message(total_collected: int, new_keepers: list[dict], scored: list[dict]) -> str:
    lines = [
        "\U0001F380 <b>Job Agent — new matches</b> \U0001F380",
        "",
        f"\U0001F50D Listings collected: <b>{total_collected}</b>",
        f"\U0001F195 New offers this run: <b>{len(scored)}</b>",
        f"\U0001F338 New good matches (score ≥ 6): <b>{len(new_keepers)}</b>",
    ]

    # Fresh first, then score.
    ordered = sorted(new_keepers, key=recency.sort_key)[:5]
    if ordered:
        lines.append("")
        lines.append("<b>Top new picks:</b>")
        for j in ordered:
            title = _escape(j.get("title", "?"))
            company = _escape(j.get("company", "?"))
            score = j.get("score", "?")
            url = j.get("url", "")
            fresh = " 🌟" if j.get("freshness") == "Fresh" else ""
            lines.append(
                f"• <a href=\"{_escape(url)}\">{title}</a> @ {company} — {score}/10{fresh}"
            )
    else:
        lines.append("")
        lines.append("No brand-new strong matches this run — check the board for the full list.")

    # New offers found this run (company — post title, one per line).
    result = _company_list(scored)
    if result:
        body, count = result
        lines.append("")
        lines.append(f"\U0001F3E2 <b>New offers this run ({count}):</b>")
        lines.append(body)

    lines.append("")
    lines.append(f"\U0001F49D Full board: {SITE_URL}")
    return "\n".join(lines)


def notify(total_collected: int, new_keepers: list[dict], scored: list[dict] | None = None) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("Telegram not configured — skipping.")
        return False

    message = build_message(total_collected, new_keepers, scored or [])
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=30,
        )
        if resp.status_code == 200:
            log.info("Telegram summary sent (%d new keepers).", len(new_keepers))
            return True
        log.warning("Telegram send failed HTTP %d: %s", resp.status_code, resp.text[:200])
    except requests.RequestException as exc:
        log.warning("Telegram send error: %s", exc)
    return False
