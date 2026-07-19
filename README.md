# 🎀 Rim's Remote Job Agent

A $0-cost automated agent that runs **every 5 hours** (so you're an early applicant):

1. **Collects** remote dev jobs from many free sources — 5 JSON APIs (Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas), **The Muse** and **Landing.jobs** APIs, **RSS feeds** (Jobicy, WeWorkRemotely, Jobspresso, Remote Woman, Authentic Jobs), your own **Google Alerts** RSS feeds (incl. LinkedIn-scoped), **~80 startup career boards** (Greenhouse / Lever / Ashby), plus **keyword-variant searches** (junior-dev + adjacent roles like solutions/support/forward-deployed engineer, developer advocate, AI trainer), and optional Playwright scraping.
2. **Dedupes** within the run by `(title + company + url)`, **and across runs** via the database — the evening run never re-surfaces what the morning already showed.
3. **Filters** — a rule-based location filter drops obviously country-locked roles (US only, hybrid, onsite…), then **Gemini** reads each description and returns a **score 1–10**, a one-line **reason**, and a 2–3 sentence **summary** — catching hidden restrictions (work-auth/timezone locks).
4. **Flags recency** — every listing gets `days_since_posted` and a **Fresh** label (≤ 7 days). Nothing is ever discarded; Fresh listings just sort first, older ones show muted with a "posted X days ago" caption.
5. **Stores** everything in SQLite (`data/jobs.db`, the source of truth) and exports `docs/jobs.json`.
6. **Publishes** a clean, responsive 🎀 Hello-Kitty dashboard on **GitHub Pages** — with per-job AI summaries, clear key info, and **on-demand cover-letter generation** (see below).
7. **Pings** you on **Telegram** with only the **new** strong matches (Fresh first), plus the list of **companies scanned** this run.

Search profile baked in: **junior · remote**, tech stack from the CV (Python, JS/TS, React, Next.js, Node, HTML/CSS, Java, C#, AI/LLM/NLP). The candidate is in **Morocco (UTC+0/+1)**, so the AI treats **worldwide, Europe/EMEA, Africa/MENA, GMT/CET-timezone, and Employer-of-Record / international-contractor** roles as good matches — and only rejects roles that genuinely exclude her (US/Canada-only work authorization, Americas/APAC-locked, onsite/hybrid). Notifies on **score ≥ 6** (cast a wide net as a junior).

### ✍️ Cover letters & 📋 Apply kits — on demand, not automatic
To save Gemini's free quota, nothing is generated automatically. Each job card has a **"Cover letter"** button and an **"Apply kit"** button. On first use you paste your Gemini API key + CV once in **⚙️ Settings** (stored **only in your browser**, never uploaded; add an optional **Groq key** as a fallback). Clicking generates in-browser:
- **Cover letter** — a full tailored letter.
- **Apply kit** — a tailored CV summary, matching-skills bullets, and ready answers to common application questions (why this role, salary expectations, start date…) so you apply in ~2 minutes.

Both have **Copy** and **Save as PDF**, and are cached per-job (with **Regenerate**) so re-opening spends no extra quota.

---

## 🗂️ Project layout

```
job_search/
├── .github/workflows/daily-search.yml   # twice-daily cron + manual trigger
├── src/
│   ├── collectors/api_sources.py        # 5 JSON APIs + keyword-variant search
│   ├── collectors/muse_source.py        # The Muse API
│   ├── collectors/rss_sources.py        # RSS feeds + Google Alerts
│   ├── collectors/startup_boards.py     # Greenhouse / Lever / Ashby boards
│   ├── collectors/playwright_sources.py # optional headless scraping
│   ├── gemini.py                        # LLM client (Gemini + Groq fallback)
│   ├── dedupe.py  scorer.py  recency.py
│   ├── db.py  site_builder.py  notifier.py
│   └── main.py                          # orchestrates the pipeline
├── config/
│   ├── cv.txt                     # your CV (already filled in)
│   ├── keywords.yaml              # stack/seniority hints + search variants
│   ├── restricted_locations.yaml  # rule-based auto-reject strings
│   ├── rss_feeds.yaml             # RSS feeds + your Google Alerts URLs
│   ├── startup_boards.yaml        # Greenhouse/Lever/Ashby company slugs
│   └── target_sites.yaml          # Playwright targets (empty by default)
├── docs/                          # the 🎀 website (GitHub Pages serves this)
│   ├── index.html  style.css  app.js  jobs.json
├── data/jobs.db                   # SQLite source of truth (committed each run)
├── scripts/set_status.py          # permanently change a job's status
├── requirements.txt   .env.example   .gitignore
```

---

## 🚀 First-time setup

### 1. Get the API keys (all free)

**Gemini** — go to [Google AI Studio → API keys](https://aistudio.google.com/app/apikey), create a key.

**Telegram bot**
1. Message [@BotFather](https://t.me/BotFather), send `/newbot`, follow prompts → copy the **bot token**.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser → find `"chat":{"id":...}` → that number is your **chat id**.

### 2. Local `.env`

Copy `.env.example` → `.env` and fill in:

```
GEMINI_API_KEY=your-gemini-key      # (gemini_key also accepted)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

> The model defaults to `gemini-2.5-flash-lite` (best free-tier limits). Override with `GEMINI_MODEL`.
> To conserve the free daily quota, only the top **80** pre-ranked listings are scored per run (`MAX_SCORE`, set `0` for unlimited).

### 3. Run it locally

```bash
pip install -r requirements.txt
python -m playwright install chromium        # only needed if you add target_sites
python -m src.main
```

You'll see per-stage logs, `data/jobs.db` + `docs/jobs.json` get written, and a Telegram summary arrives.

Preview the site locally:

```bash
python -m http.server 8000 --directory docs
# open http://localhost:8000
```

### 4. Push to GitHub (repo: `rim-19/job_search`)

```bash
git init
git add .
git commit -m "🎀 initial job agent"
git branch -M main
git remote add origin https://github.com/rim-19/job_search.git
git push -u origin main
```

### 5. Add repo secrets

**Settings → Secrets and variables → Actions → New repository secret** — add:
`GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and (optional but recommended) `GROQ_API_KEY`.

> **Groq fallback:** if Gemini's free quota runs out mid-run (HTTP 429), the pipeline automatically switches to **Groq** (`llama-3.3-70b-versatile`) for the rest of that run — so scoring never stalls. Get a free key at [console.groq.com/keys](https://console.groq.com/keys). Without it, the run just backs off on Gemini as before.

> `.env` is git-ignored, so your keys never land in the repo — GitHub Actions reads them from these secrets instead.

### 6. Enable GitHub Pages

**Settings → Pages → Source: "Deploy from a branch" → branch `main`, folder `/docs`**.
Your board goes live at **https://rim-19.github.io/job_search/**.

### 7. First run

**Actions tab → "Daily Job Search" → Run workflow** (manual trigger). This creates/updates the DB, writes `jobs.json`, commits them back, and Pages auto-rebuilds. After that the cron runs **every 5 hours** (00/05/10/15/20 UTC). Each run only scores **net-new** listings (already-scored ones are skipped), so frequent runs stay cheap and never re-notify old jobs.

### 8. (Optional but recommended) Set up Google Alerts

Google Alerts catches postings the job boards miss. Create each alert, export it as RSS, and paste the feed URL into `config/rss_feeds.yaml` under `google_alerts:`.

1. Go to **https://www.google.com/alerts**
2. Create an alert for each query below.
3. Click **Show options → Deliver to → RSS feed**.
4. Click the **RSS icon** next to the created alert and copy the feed URL.
5. Paste each URL into `config/rss_feeds.yaml`, then commit.

Recommended 7 queries (tuned to your CV, low-noise):
```
1. "remote junior developer" hiring
2. "junior AI engineer" remote LangChain
3. "remote LLM developer" entry level
4. "remote React developer" junior hiring
5. "remote AI agents developer" "entry level"
6. "remote software developer" "hire worldwide"
7. "prompt engineer" remote junior hiring
```

---

## 🖥️ Using the dashboard

- **Search** by title/company; filter by **score** and **status**; toggle **new today** / **fresh only**. Fresh (≤ 7-day) listings sort first; older ones show muted with "posted X days ago".
- Each card shows: the match **score** (in a heart 💗), a 2–3 sentence **AI summary**, the **company**, **location/remote scope**, **source**, **Fresh**/**NEW** badges, an **Apply** link to the original posting, a **Cover letter** button, and a **status** dropdown.
- **Cover letters** generate on demand — click the button, and (first time) open **⚙️ Settings** to paste your Gemini key + CV once. They stay in your browser. Generated letters have **Copy** + **Save as PDF** and are cached per job.
- ⚠️ Status changes on the site are saved **in your browser only** (static site, no backend).

### Making a status change permanent

The website can't write to the database. To persist a status into `data/jobs.db`:

```bash
python -m scripts.set_status --list                       # see all jobs + urls
python -m scripts.set_status "https://the-job-url" "Applied"
```

Then commit `data/jobs.db`. Or open the DB directly with the free
[**DB Browser for SQLite**](https://sqlitebrowser.org/) to edit/clean rows by hand,
or the `sqlite3` CLI:

```bash
sqlite3 data/jobs.db "UPDATE jobs SET status='Applied' WHERE url='...';"
```

---

## 🔧 Tuning

| File | What to change |
|---|---|
| `config/cv.txt` | Your CV text — the AI scores/summarizes against this. |
| `config/keywords.yaml` | Stack + seniority hints (pre-ranking) and `search_variants` (broad-net queries). `max_search_queries` bounds how many fire per run. |
| `config/restricted_locations.yaml` | Strings that auto-reject a listing by location. |
| `config/rss_feeds.yaml` | RSS feeds + your Google Alerts feed URLs. |
| `config/startup_boards.yaml` | Company slugs for Greenhouse/Lever/Ashby boards — add any company by its careers-page slug. |
| `config/target_sites.yaml` | Add career pages for Playwright to scrape (see the commented example). |
| env `KEEP_THRESHOLD` | Min score to notify on Telegram (default 6). |
| env `MAX_SCORE` | Max NEW listings scored per run (default 120; 0 = unlimited). |
| env `GROQ_MODEL` | Groq fallback model (default `llama-3.3-70b-versatile`). |

---

## 💸 Cost

Everything (job APIs, Gemini free tier, SQLite, GitHub Pages, Telegram, GitHub Actions) is **$0**.

## ⚠️ What it does **not** do

- Doesn't auto-apply — you still click submit.
- Coverage is real but partial (great for API-listed jobs, thinner on LinkedIn-only / company-direct postings).
- Doesn't guarantee replies — junior remote roles are competitive; this removes the search grind, not the competition.
