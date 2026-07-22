# 🎀 Rim's Remote Job Agent

A $0-cost automated agent that runs **every 5 hours** (so you're an early applicant):

1. **Collects** remote dev jobs from many free sources — 5 JSON APIs (Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas), **The Muse** and **Landing.jobs** APIs, **RSS feeds** (Jobicy, WeWorkRemotely, Jobspresso, Remote Woman, Authentic Jobs), **Google Alerts** RSS feeds (incl. LinkedIn-scoped), **~80 startup career boards** (Greenhouse / Lever / Ashby), plus **keyword-variant searches** (junior-dev + adjacent roles like solutions/support/forward-deployed engineer, developer advocate, AI trainer), and optional Playwright scraping.
2. **Dedupes** within the run by `(title + company + url)`, **and across runs** via the database — a later run never re-surfaces what an earlier one already showed.
3. **Filters** — a rule-based location filter drops obviously country-locked roles (US only, hybrid, onsite…), then **Gemini** reads each description and returns a **score 1–10**, a one-line **reason**, and a 2–3 sentence **summary** — catching hidden restrictions (work-auth/timezone locks).
4. **Flags recency** — every listing gets `days_since_posted` and a **Fresh** label (≤ 7 days). Nothing is ever discarded; Fresh listings just sort first, older ones show muted with a "posted X days ago" caption.
5. **Stores** everything in SQLite (`data/jobs.db`, the source of truth) and exports `docs/jobs.json`.
6. **Publishes** a clean, responsive 🎀 Hello-Kitty dashboard on **GitHub Pages** — with per-job AI summaries, clear key info, and on-demand generation tools (below).
7. **Pings** you on **Telegram** with only the **new good matches & top picks** (Fresh first).

Search profile: **junior · remote**, tech stack from the CV (Python, JS/TS, React, Next.js, Node, HTML/CSS, Java, C#, AI/LLM/NLP). Based in **Morocco (UTC+0/+1)**, so the AI treats **worldwide, Europe/EMEA, Africa/MENA, GMT/CET-timezone, and Employer-of-Record / international-contractor** roles as good matches — and only rejects roles that genuinely exclude her (US/Canada-only work authorization, Americas/APAC-locked, onsite/hybrid).

### ✍️ Cover letters & 📋 Apply kits — on demand
Each job card has a **"Cover letter"** button and an **"Apply kit"** button that generate in-browser from the CV + that job:
- **Cover letter** — a full tailored letter.
- **Apply kit** — a tailored CV summary, matching-skills bullets, and ready answers to common application questions (why this role, salary expectations, start date…).

Both have **Copy** and **Save as PDF**, and are cached per-job (with **Regenerate**).

### 📧 Recruiter outreach
A separate `outreach/` tool drafts personalized cold emails to recruiters from the CV + a job context, lets you review/edit each, and sends them from Gmail — personalized per recruiter, rate-limited, and de-duplicated.

---

## 🗂️ Project layout

```
job_search/
├── .github/workflows/daily-search.yml   # every-5-hours cron + manual trigger
├── src/
│   ├── collectors/api_sources.py        # 5 JSON APIs + keyword-variant search
│   ├── collectors/muse_source.py        # The Muse API
│   ├── collectors/landing_jobs.py       # Landing.jobs API
│   ├── collectors/rss_sources.py        # RSS feeds + Google Alerts
│   ├── collectors/startup_boards.py     # Greenhouse / Lever / Ashby boards
│   ├── collectors/playwright_sources.py # optional headless scraping
│   ├── gemini.py                        # LLM client (Gemini + Groq fallback)
│   ├── dedupe.py  scorer.py  recency.py
│   ├── db.py  site_builder.py  notifier.py
│   └── main.py                          # orchestrates the pipeline
├── config/                              # cv, keywords, locations, feeds, boards
├── docs/                                # the 🎀 website (GitHub Pages serves this)
│   ├── index.html  style.css  app.js  jobs.json
├── outreach/                            # recruiter outreach tool
├── data/jobs.db                         # SQLite source of truth
└── requirements.txt
```

---

## 🖥️ The dashboard

- **Search** by title/company; filter by **score** and **status**; toggle **new today** / **fresh only**. Fresh (≤ 7-day) listings sort first; older ones show muted with "posted X days ago".
- Each card shows: the match **score** (in a heart 💗), a 2–3 sentence **AI summary**, the **company**, **location/remote scope**, **source**, **Fresh**/**NEW** badges, an **Apply** link, **Cover letter** + **Apply kit** buttons, and a **status** dropdown.
- On-demand generation runs in your browser with your own key; nothing is uploaded.

---

## 💸 Cost

Everything (job APIs, Gemini free tier, SQLite, GitHub Pages, Telegram, GitHub Actions) is **$0**.

## ⚠️ What it does **not** do

- Doesn't auto-apply — you still click submit.
- Coverage is real but partial (great for API-listed jobs, thinner on LinkedIn-only / company-direct postings).
- Doesn't guarantee replies — junior remote roles are competitive; this removes the search grind, not the competition.
