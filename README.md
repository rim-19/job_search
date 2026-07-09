# 🎀 Rim's Remote Job Agent

A $0-cost automated agent that every day:

1. **Collects** remote web-dev jobs from 5 free APIs (Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas) + optional Playwright scraping of career pages.
2. **Dedupes** them by `(title + company + url)`.
3. **Filters** — a rule-based location filter drops obviously country-locked roles (US only, hybrid, onsite…), then **Gemini** reads the full description and scores the rest **1–10** against the CV, catching hidden restrictions (visa/work-auth/timezone locks).
4. **Drafts** a tailored cover note + application checklist for strong matches (score ≥ 7).
5. **Stores** everything in SQLite (`data/jobs.db`, the source of truth) and exports `docs/jobs.json`.
6. **Publishes** a cute 🎀 Hello-Kitty-themed dashboard on **GitHub Pages**.
7. **Pings** you on **Telegram** with the day's top picks.

Search profile baked in: **junior · remote · worldwide / no country restriction**, tech stack from the CV (Python, JS/TS, React, Next.js, Node, HTML/CSS, Java, C#, AI/LLM/NLP).

---

## 🗂️ Project layout

```
job_search/
├── .github/workflows/daily-search.yml   # daily cron + manual trigger
├── src/
│   ├── collectors/api_sources.py        # 5 free JSON APIs (async)
│   ├── collectors/playwright_sources.py # optional headless scraping
│   ├── gemini.py                        # tiny Gemini REST client
│   ├── dedupe.py  scorer.py  drafter.py
│   ├── db.py  site_builder.py  notifier.py
│   └── main.py                          # orchestrates the pipeline
├── config/
│   ├── cv.txt                     # your CV (already filled in)
│   ├── keywords.yaml              # stack + seniority hints
│   ├── restricted_locations.yaml  # rule-based auto-reject strings
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
`GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

> `.env` is git-ignored, so your keys never land in the repo — GitHub Actions reads them from these secrets instead.

### 6. Enable GitHub Pages

**Settings → Pages → Source: "Deploy from a branch" → branch `main`, folder `/docs`**.
Your board goes live at **https://rim-19.github.io/job_search/**.

### 7. First run

**Actions tab → "Daily Job Search" → Run workflow** (manual trigger). This creates/updates the DB, writes `jobs.json`, commits them back, and Pages auto-rebuilds. After that the cron runs daily at **07:00 UTC** (~08:00 Morocco).

---

## 🖥️ Using the dashboard

- **Search** by title/company, filter by **score** and **status**, sort by score/date/company.
- Each card has the match **score** (in a heart 💗), the AI's one-line **reason**, an expandable **cover note** and **application checklist**, an **Apply** button, and a **status** dropdown.
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
| `config/cv.txt` | Your CV text — the AI scores/drafts against this. |
| `config/keywords.yaml` | Stack + seniority hints used for pre-ranking. |
| `config/restricted_locations.yaml` | Strings that auto-reject a listing by location. |
| `config/target_sites.yaml` | Add career pages for Playwright to scrape (see the commented example). |
| env `KEEP_THRESHOLD` | Min score to count as a "keeper" (default 7). |
| env `MAX_SCORE` | Max listings scored per run (default 80; 0 = unlimited). |

---

## 💸 Cost

Everything (job APIs, Gemini free tier, SQLite, GitHub Pages, Telegram, GitHub Actions) is **$0**.

## ⚠️ What it does **not** do

- Doesn't auto-apply — you still click submit.
- Coverage is real but partial (great for API-listed jobs, thinner on LinkedIn-only / company-direct postings).
- Doesn't guarantee replies — junior remote roles are competitive; this removes the search grind, not the competition.
