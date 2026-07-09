"""Send a run summary to Telegram via a plain HTTPS request (no SDK)."""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("notifier")

# Update these if you rename the repo / GitHub user.
SITE_URL = os.getenv("SITE_URL", "https://rim-19.github.io/job_search/")


def _escape(text: str) -> str:
    """Escape the few characters Telegram HTML parse mode cares about."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(total_scanned: int, keepers: list[dict]) -> str:
    lines = [
        "\U0001F380 <b>Job Agent — today's run</b> \U0001F380",
        "",
        f"\U0001F50D Scanned: <b>{total_scanned}</b> listings",
        f"\U0001F338 Strong matches (score ≥ 7): <b>{len(keepers)}</b>",
    ]
    top = sorted(keepers, key=lambda j: j.get("score", 0), reverse=True)[:5]
    if top:
        lines.append("")
        lines.append("<b>Top picks:</b>")
        for j in top:
            title = _escape(j.get("title", "?"))
            company = _escape(j.get("company", "?"))
            score = j.get("score", "?")
            url = j.get("url", "")
            lines.append(f"• <a href=\"{_escape(url)}\">{title}</a> @ {company} — {score}/10")
    lines.append("")
    lines.append(f"\U0001F49D Full board: {SITE_URL}")
    return "\n".join(lines)


def notify(total_scanned: int, keepers: list[dict]) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) — skipping.")
        return False

    message = build_message(total_scanned, keepers)
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
            log.info("Telegram summary sent.")
            return True
        log.warning("Telegram send failed HTTP %d: %s", resp.status_code, resp.text[:200])
    except requests.RequestException as exc:
        log.warning("Telegram send error: %s", exc)
    return False
