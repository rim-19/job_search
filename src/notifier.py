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


_MAX_COMPANIES = 60  # keep the message under Telegram's 4096-char limit


def _company_list(scored: list[dict]) -> str:
    """Unique, sorted company names from everything scanned this run."""
    names = sorted(
        {(j.get("company") or "").strip() for j in scored if (j.get("company") or "").strip()},
        key=str.casefold,
    )
    if not names:
        return ""
    shown = names[:_MAX_COMPANIES]
    body = ", ".join(_escape(n) for n in shown)
    if len(names) > _MAX_COMPANIES:
        body += f" … <i>+{len(names) - _MAX_COMPANIES} more</i>"
    return body, len(names)


def build_message(total_scanned: int, new_keepers: list[dict], scored: list[dict]) -> str:
    lines = [
        "\U0001F380 <b>Job Agent — new matches</b> \U0001F380",
        "",
        f"\U0001F50D Scanned this run: <b>{total_scanned}</b>",
        f"\U0001F338 New strong matches (score ≥ 7): <b>{len(new_keepers)}</b>",
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

    # Companies whose offers were scanned this run.
    result = _company_list(scored)
    if result:
        body, count = result
        lines.append("")
        lines.append(f"\U0001F3E2 <b>Companies scanned ({count}):</b>")
        lines.append(body)

    lines.append("")
    lines.append(f"\U0001F49D Full board: {SITE_URL}")
    return "\n".join(lines)


def notify(total_scanned: int, new_keepers: list[dict], scored: list[dict] | None = None) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("Telegram not configured — skipping.")
        return False

    message = build_message(total_scanned, new_keepers, scored or [])
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
