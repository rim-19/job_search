"""Recruiter outreach tool — draft personalized emails, review, then send.

Two phases (run from the repo root):

    python -m outreach.outreach draft     # writes one editable draft per recruiter
    # ... open outreach/drafts/*.txt, edit freely, delete any you don't want ...
    python -m outreach.outreach send      # confirms + sends each remaining draft

Design goals: every email is personalized (never an identical blast), you review
before anything is sent, already-emailed recruiters are skipped, and sending is
rate-limited for deliverability. Emails are sent from your own Gmail via SMTP.

Credentials come from .env (never hard-coded):
    SMTP_EMAIL          your Gmail address
    SMTP_APP_PASSWORD   a Gmail App Password (Google account > Security >
                        2-Step Verification > App passwords) — NOT your login pw
Optional: SMTP_HOST (default smtp.gmail.com), SMTP_PORT (default 587).
Gemini/Groq keys are reused from the main project for drafting.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Repo root on path so we can reuse the project's LLM client + CV.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src import gemini  # noqa: E402

HERE = Path(__file__).resolve().parent
DRAFTS = HERE / "drafts"
RECRUITERS = HERE / "recruiters.csv"
JOB_CONTEXT = HERE / "job_context.txt"
CONFIG = HERE / "config.yaml"
SENT_LOG = HERE / "sent_log.csv"
CV = ROOT / "config" / "cv.txt"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------- IO

def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_config() -> dict:
    cfg = _load_yaml(CONFIG)
    cfg.setdefault("sender", {})
    cfg.setdefault("sending", {})
    return cfg


def load_recruiters() -> list[dict]:
    if not RECRUITERS.exists():
        sys.exit(f"Missing {RECRUITERS.name}. Copy recruiters.example.csv to "
                 f"recruiters.csv and fill in your recruiters.")
    rows = []
    with RECRUITERS.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            email = (row.get("email") or "").strip()
            if not email or not _EMAIL_RE.match(email):
                if email:
                    print(f"  ! skipping invalid email: {email!r}")
                continue
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def load_sent() -> set[str]:
    if not SENT_LOG.exists():
        return set()
    with SENT_LOG.open(encoding="utf-8", newline="") as f:
        return {r["email"].lower() for r in csv.DictReader(f) if r.get("email")}


def log_sent(email: str, subject: str) -> None:
    new = not SENT_LOG.exists()
    with SENT_LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["email", "sent_at_utc", "subject"])
        w.writerow([email, datetime.now(timezone.utc).isoformat(timespec="seconds"), subject])


def signature(sender: dict) -> str:
    lines = ["Best regards,", sender.get("name", "")]
    contact = " | ".join(x for x in [sender.get("email"), sender.get("phone")] if x)
    if contact:
        lines.append(contact)
    links = " | ".join(
        f"{label}: {sender[key]}"
        for key, label in (("linkedin", "LinkedIn"), ("github", "GitHub"), ("portfolio", "Portfolio"))
        if sender.get(key)
    )
    if links:
        lines.append(links)
    return "\n".join(lines)


# ---------------------------------------------------------------------- drafting

_PROMPT = """Write a short, personalized cold outreach email from a junior software
developer to a recruiter. It must feel human and specific — NOT a mass template.

RULES:
- 110-160 words max. Recruiters skim; be concise.
- Open by referencing the specific company/role (below), not "Dear Sir/Madam".
- 1-2 sentences on the strongest, most relevant fit (real projects/stack from the CV).
- Be honest about being early-career; lead with value, not desperation.
- End with ONE clear, low-pressure ask (to be considered / a brief call).
- No emojis, no hype, no ALL CAPS. Tone: {tone}
- Do NOT invent facts not in the CV. Do NOT include a signature (added separately).

SUBJECT: {subject_style}

CANDIDATE CV:
{cv}

JOB / CONTEXT THIS IS ABOUT:
{context}

RECRUITER / TARGET:
Name: {name}
Company: {company}
Role: {role}
Notes: {notes}

Return STRICT JSON only: {{"subject": "<subject line>", "body": "<email body, no signature>"}}"""


def draft_email(rec: dict, cv: str, context: str, cfg: dict) -> dict | None:
    send_cfg = cfg.get("sending", {})
    prompt = _PROMPT.format(
        tone=send_cfg.get("tone", "warm, confident, concise"),
        subject_style=send_cfg.get("subject_style", "concise and specific, professional"),
        cv=cv[:2500],
        context=context[:1500],
        name=rec.get("name") or "(unknown — greet the team/company politely)",
        company=rec.get("company") or "(unknown)",
        role=rec.get("role") or "(open / general)",
        notes=rec.get("notes") or "(none)",
    )
    try:
        out = gemini.generate_json(prompt, temperature=0.6)
    except gemini.GeminiError as exc:
        print(f"  ! draft failed for {rec['email']}: {exc}")
        return None
    subject = str(out.get("subject", "")).strip()
    body = str(out.get("body", "")).strip()
    if not subject or not body:
        return None
    return {"subject": subject, "body": body}


def _safe(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]


def cmd_draft(_args) -> None:
    cfg = load_config()
    cv = CV.read_text(encoding="utf-8") if CV.exists() else ""
    context = JOB_CONTEXT.read_text(encoding="utf-8") if JOB_CONTEXT.exists() else ""
    recruiters = load_recruiters()
    already = load_sent()
    DRAFTS.mkdir(exist_ok=True)
    sig = signature(cfg["sender"])

    made = skipped = 0
    for i, rec in enumerate(recruiters, 1):
        if rec["email"].lower() in already:
            skipped += 1
            continue
        print(f"[{i}/{len(recruiters)}] drafting for {rec['email']} ...")
        d = draft_email(rec, cv, context, cfg)
        if not d:
            continue
        path = DRAFTS / f"{i:03d}_{_safe(rec['email'])}.txt"
        path.write_text(
            f"To: {rec['email']}\nSubject: {d['subject']}\n\n{d['body']}\n\n{sig}\n",
            encoding="utf-8",
        )
        made += 1

    print(f"\nDrafted {made} email(s) into {DRAFTS}"
          + (f", skipped {skipped} already-sent" if skipped else ""))
    print("Review/edit the .txt files (delete any you don't want), then run:")
    print("    python -m outreach.outreach send")


# ----------------------------------------------------------------------- sending

def _parse_draft(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    to = re.search(r"^To:\s*(.+)$", text, re.MULTILINE)
    subj = re.search(r"^Subject:\s*(.+)$", text, re.MULTILINE)
    if not (to and subj):
        return None
    # Body is everything after the first blank line following the headers.
    parts = text.split("\n\n", 1)
    body = parts[1].strip() if len(parts) > 1 else ""
    return {"to": to.group(1).strip(), "subject": subj.group(1).strip(), "body": body}


def _smtp_login():
    email = os.getenv("SMTP_EMAIL")
    pw = os.getenv("SMTP_APP_PASSWORD")
    if not email or not pw:
        sys.exit("Set SMTP_EMAIL and SMTP_APP_PASSWORD in .env "
                 "(Gmail App Password — see outreach/README.md).")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    server = smtplib.SMTP(host, port, timeout=30)
    server.starttls()
    server.login(email, pw)
    return server, email


def cmd_send(args) -> None:
    cfg = load_config()
    sender = cfg["sender"]
    send_cfg = cfg.get("sending", {})
    max_per_run = int(send_cfg.get("max_per_run", 15))
    delay = float(send_cfg.get("delay_seconds", 25))

    drafts = sorted(DRAFTS.glob("*.txt")) if DRAFTS.exists() else []
    if not drafts:
        sys.exit("No drafts found. Run 'draft' first.")

    already = load_sent()
    from_hdr = f"{sender.get('name','')} <{os.getenv('SMTP_EMAIL','')}>"
    server = email_addr = None
    sent = 0

    try:
        for path in drafts:
            if sent >= max_per_run:
                print(f"\nReached max_per_run ({max_per_run}). Re-run 'send' to continue.")
                break
            d = _parse_draft(path)
            if not d:
                print(f"  ! could not parse {path.name}, skipping")
                continue
            if d["to"].lower() in already:
                print(f"  - {d['to']} already emailed, skipping")
                continue

            print("\n" + "=" * 66)
            print(f"To:      {d['to']}")
            print(f"Subject: {d['subject']}")
            print("-" * 66)
            print(d["body"])
            print("=" * 66)

            if args.yes:
                choice = "y"
            else:
                choice = input("Send this? [y]es / [s]kip / [q]uit: ").strip().lower()
            if choice in ("q", "quit"):
                break
            if choice not in ("y", "yes", ""):
                print("  skipped.")
                continue

            if server is None:
                server, email_addr = _smtp_login()
                from_hdr = f"{sender.get('name','')} <{email_addr}>"

            msg = EmailMessage()
            msg["From"] = from_hdr
            msg["To"] = d["to"]
            msg["Subject"] = d["subject"]
            if sender.get("email"):
                msg["Reply-To"] = sender["email"]
            msg.set_content(d["body"])

            try:
                server.send_message(msg)
                log_sent(d["to"], d["subject"])
                already.add(d["to"].lower())
                path.rename(path.with_suffix(".sent"))
                sent += 1
                print(f"  ✓ sent to {d['to']}")
            except Exception as exc:  # noqa: BLE001
                print(f"  ! send failed for {d['to']}: {exc}")
                continue

            if sent < max_per_run:
                time.sleep(delay)
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass

    print(f"\nDone. Sent {sent} email(s) this run. Log: {SENT_LOG}")


def main() -> None:
    p = argparse.ArgumentParser(description="Recruiter outreach: draft -> review -> send.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("draft", help="generate a personalized draft per recruiter")
    s = sub.add_parser("send", help="review + send the drafts")
    s.add_argument("--yes", action="store_true",
                   help="skip the per-email confirm (auto-send reviewed drafts)")
    args = p.parse_args()
    {"draft": cmd_draft, "send": cmd_send}[args.cmd](args)


if __name__ == "__main__":
    main()
