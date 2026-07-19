# 📧 Recruiter Outreach

Draft personalized cold emails to recruiters, review/edit them, then send from
your own Gmail. Reuses your CV and the project's Gemini/Groq client.

**Every email is personalized** (not a mass blast), you **review before sending**,
already-emailed recruiters are **skipped**, and sending is **rate-limited** so you
stay out of spam folders and keep your reputation intact.

---

## One-time setup

### 1. Get a Gmail App Password
Your normal Gmail password won't work for SMTP. You need an **App Password**:
1. Turn on **2-Step Verification**: [myaccount.google.com/security](https://myaccount.google.com/security)
2. Then go to **App passwords**: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create one (name it "outreach") → copy the **16-character** password.

### 2. Add it to `.env` (in the repo root)
```
SMTP_EMAIL=your.email@gmail.com
SMTP_APP_PASSWORD=abcdefghijklmnop
```
(Your Gemini/Groq keys are already there and reused for drafting.)

### 3. Fill in your files
- **`recruiters.csv`** — copy `recruiters.example.csv` to `recruiters.csv` and add rows.
  Columns: `email,name,company,role,notes` (only `email` is required; the rest make
  the email more personal). This file is git-ignored so recruiter emails stay private.
- **`job_context.txt`** — paste the job posting or write a general pitch. Shared across
  all recruiters; per-recruiter details come from the CSV.
- **`config.yaml`** — check your signature (name, email, phone, LinkedIn, GitHub) and
  sending settings (`max_per_run`, `delay_seconds`).

---

## Usage (run from the repo root)

### Step 1 — draft
```bash
python -m outreach.outreach draft
```
Writes one editable draft per recruiter into `outreach/drafts/*.txt`.

### Step 2 — review & edit
Open the `.txt` files. Each has `To:`, `Subject:`, a blank line, then the body +
your signature. **Edit anything, delete any you don't want to send.**

### Step 3 — send
```bash
python -m outreach.outreach send
```
Shows each email and asks **[y]es / [s]kip / [q]uit** before sending it. Sent drafts
are renamed to `.sent` and logged in `sent_log.csv` (so they're never re-sent).

- Sends at most `max_per_run` per run (default 15), pausing `delay_seconds` between.
- Add `--yes` to skip the per-email confirm (auto-send the reviewed drafts).

---

## Good-practice reminders
- **Keep volume low** (10–20/day). Cold outreach works when it's targeted, not spammy.
- **Personalize the CSV `notes`** — one specific detail per recruiter dramatically
  raises reply rates.
- **Don't email the same person repeatedly.** The sent-log prevents accidental dupes,
  but respect a no / silence.
- These are 1:1 job-search emails from your real address — that's legitimate outreach.
  Mass identical blasting is not; the tool is built to keep you on the right side.
