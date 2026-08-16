"""Send a priority-ranked run summary to Telegram (plain HTTPS, no SDK).

Only NEW listings are surfaced. They're grouped by priority — 🔥 APPLY NOW gets
full detail (why it matches, gaps, recommended project, eligibility), 🟢 APPLY and
🟡 CONSIDER get compact one-liners. Fresh listings sort first within each group.
"""

from __future__ import annotations

import logging
import os

import requests

from . import recency

log = logging.getLogger("notifier")

SITE_URL = os.getenv("SITE_URL", "https://rim-19.github.io/job_search/")

_REMOTE_EMOJI = {"REMOTE": "🌍", "HYBRID": "🏢", "ONSITE": "🏢", "UNKNOWN": "📍"}


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _detailed(j: dict) -> str:
    title = _esc(j.get("title", "?"))
    company = _esc(j.get("company", "") or "—")
    url = _esc(j.get("url", ""))
    score = j.get("score", "?")
    loc = _esc(j.get("location", "") or j.get("geographic_scope", "") or "—")
    rt = (j.get("remote_type") or "").upper()
    rt_e = _REMOTE_EMOJI.get(rt, "📍")
    fresh = " · 🌟 Fresh" if j.get("freshness") == "Fresh" else ""
    lines = [
        f"• <b><a href=\"{url}\">{title}</a></b> — {company} — <b>{score}/100</b>",
        f"    {rt_e} {loc}{fresh}",
    ]
    if j.get("reason"):
        lines.append(f"    ✓ {_esc(j['reason'])}")
    gaps = j.get("gaps") or []
    if gaps:
        lines.append(f"    ⚠ {_esc(gaps[0])}")
    if j.get("recommended_project"):
        lines.append(f"    💡 Lead with: {_esc(j['recommended_project'])}")
    return "\n".join(lines)


def _compact(j: dict) -> str:
    title = _esc(j.get("title", "?"))
    company = _esc(j.get("company", "") or "—")
    url = _esc(j.get("url", ""))
    score = j.get("score", "?")
    fresh = " 🌟" if j.get("freshness") == "Fresh" else ""
    return f"• <a href=\"{url}\">{title}</a> — {company} — {score}/100{fresh}"


def build_message(total_collected: int, new_keepers: list[dict], scored: list[dict]) -> str:
    by = {"APPLY_NOW": [], "APPLY": [], "CONSIDER": []}
    for j in new_keepers:
        p = (j.get("priority") or "").upper()
        if p in by:
            by[p].append(j)
    for k in by:
        by[k].sort(key=recency.sort_key)

    lines = [
        "\U0001F380 <b>Job Agent — new matches</b> \U0001F380",
        "",
        f"\U0001F50D Collected: <b>{total_collected}</b>  ·  🆕 New: <b>{len(scored)}</b>",
        f"🔥 Apply now: <b>{len(by['APPLY_NOW'])}</b>  ·  "
        f"🟢 Apply: <b>{len(by['APPLY'])}</b>  ·  🟡 Consider: <b>{len(by['CONSIDER'])}</b>",
    ]

    if by["APPLY_NOW"]:
        lines += ["", "🔥 <b>APPLY NOW</b>"]
        lines += [_detailed(j) for j in by["APPLY_NOW"][:6]]

    if by["APPLY"]:
        lines += ["", "🟢 <b>APPLY THIS WEEK</b>"]
        lines += [_compact(j) for j in by["APPLY"][:8]]
        if len(by["APPLY"]) > 8:
            lines.append(f"<i>… +{len(by['APPLY']) - 8} more</i>")

    if by["CONSIDER"]:
        lines += ["", "🟡 <b>CONSIDER</b>"]
        lines += [_compact(j) for j in by["CONSIDER"][:5]]
        if len(by["CONSIDER"]) > 5:
            lines.append(f"<i>… +{len(by['CONSIDER']) - 5} more</i>")

    if not any(by.values()):
        lines += ["", "No new matches worth surfacing this run — the board has the full list."]

    lines += ["", f"\U0001F49D Full board: {SITE_URL}"]
    msg = "\n".join(lines)
    return msg[:4000]  # stay under Telegram's 4096-char limit


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
            data={"chat_id": chat_id, "text": message, "parse_mode": "HTML",
                  "disable_web_page_preview": "true"},
            timeout=30,
        )
        if resp.status_code == 200:
            log.info("Telegram summary sent (%d matches).", len(new_keepers))
            return True
        log.warning("Telegram send failed HTTP %d: %s", resp.status_code, resp.text[:200])
    except requests.RequestException as exc:
        log.warning("Telegram send error: %s", exc)
    return False
