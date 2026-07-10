/* 🎀 Rim's Job Board — client-side rendering + on-demand cover letters.
   No backend. Status, settings and generated letters live in localStorage only. */

const LS = {
  status: "rim-job-status",
  key: "rim-gemini-key",
  cv: "rim-cv-text",
  cover: (url) => "rim-cover:" + url,
};
const STATUSES = ["Not Applied", "Applied", "Interviewing", "Rejected", "Saved"];
const GEMINI_MODEL = "gemini-2.5-flash-lite";

// Rim's CV pre-filled as a convenient default (editable in Settings).
const DEFAULT_CV = `Rim Elrhezzal — Junior Software Developer (Casablanca, Morocco)
Skills: Python, JavaScript, TypeScript, HTML, CSS, C#, C, Java; React.js, Next.js, Node.js, Express, LangChain; PostgreSQL, SQLite; NLP, LLM fine-tuning, prompt engineering, automation, API integration; Stripe.
Experience: Web Development Intern at Indusfer (2026) — built ResumeIQ, an AI-powered CV analysis platform.
Projects: MultiMind AI (multi-topic chatbot, Node.js); Ghazala AI (LLM exam generator, fine-tuning); HR-Genius (AI + workflow automation for HR, chat & voice); Cupid (e-commerce bookshop with React, Node/Express, PostgreSQL, Stripe).
Education: Higher Diploma in Application Development (BTS). Certifications: Prompt Engineering (AWS), Generative AI (IBM), AI for Beginners (HP LIFE).
Languages: Arabic (native), French (professional), English (full professional). Seeking junior, fully-remote, worldwide roles.`;

let ALL = [];

/* ---------- localStorage helpers ---------- */
const getJSON = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const overrides = () => getJSON(LS.status, {});
function saveStatus(url, s) { const o = overrides(); o[url] = s; localStorage.setItem(LS.status, JSON.stringify(o)); }
const statusFor = (j) => overrides()[j.url] || j.status || "Not Applied";
const getKey = () => localStorage.getItem(LS.key) || "";
const getCV = () => localStorage.getItem(LS.cv) || DEFAULT_CV;

/* ---------- utils ---------- */
function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
const scoreClass = (n) => n >= 7 ? "high" : n >= 5 ? "mid" : "low";
function agoText(days) {
  if (days == null) return "";
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days <= 30) return `${days} days ago`;
  return `${Math.round(days / 30)} mo ago`;
}
function sortKey(j) {
  const fresh = j.freshness === "Fresh" ? 0 : 1;
  const days = j.days_since_posted == null ? 10000 : j.days_since_posted;
  return [fresh, -(j.score || 0), days];
}
function cmp(a, b) { const x = sortKey(a), y = sortKey(b); for (let i = 0; i < 3; i++) { if (x[i] !== y[i]) return x[i] - y[i]; } return 0; }

/* ---------- card ---------- */
function card(job) {
  const st = statusFor(job);
  const stale = job.freshness !== "Fresh";
  const cls = ["card"];
  if (stale) cls.push("stale");
  if (st === "Applied" || st === "Interviewing") cls.push("applied");
  if (st === "Rejected") cls.push("rejected");

  const score = Number(job.score) || 0;
  const badges = [];
  if (job.is_new) badges.push(`<span class="badge new">NEW ✨</span>`);
  if (job.freshness === "Fresh") badges.push(`<span class="badge fresh">🌟 Fresh</span>`);
  badges.push(`<span class="badge loc">📍 ${esc(job.location || "Remote")}</span>`);
  badges.push(`<span class="badge src">${esc(job.source || "web")}</span>`);

  const ago = agoText(job.days_since_posted);
  const options = STATUSES.map(s => `<option${s === st ? " selected" : ""}>${s}</option>`).join("");

  const el = document.createElement("article");
  el.className = cls.join(" ");
  el.innerHTML = `
    <div class="card-head">
      <div class="score ${scoreClass(score)}" title="match score">${score}</div>
      <div class="card-head-main">
        <h2>${esc(job.title)}</h2>
        <div class="company">${esc(job.company) || "—"}</div>
        <div class="badges">${badges.join("")}</div>
      </div>
    </div>
    ${ago ? `<div class="meta-line">🗓️ posted ${ago}</div>` : ""}
    <p class="summary">${esc(job.summary || job.reason || "")}</p>
    ${job.reason && job.summary ? `<p class="reason">match: ${esc(job.reason)}</p>` : ""}
    <div class="card-foot">
      <a class="btn primary" href="${esc(job.link || job.url)}" target="_blank" rel="noopener">Apply 💌</a>
      <button class="btn ghost cover-btn">✍️ Cover letter</button>
      <select class="status-select spacer" aria-label="status">${options}</select>
    </div>`;

  el.querySelector(".status-select").addEventListener("change", (e) => {
    saveStatus(job.url, e.target.value); render(); refreshStats();
  });
  el.querySelector(".cover-btn").addEventListener("click", () => openCover(job));
  return el;
}

/* ---------- filters + render ---------- */
function filters() {
  return {
    q: document.getElementById("search").value.trim().toLowerCase(),
    min: Number(document.getElementById("score-filter").value),
    status: document.getElementById("status-filter").value,
    newOnly: document.getElementById("new-only").checked,
    freshOnly: document.getElementById("fresh-only").checked,
  };
}
function render() {
  const f = filters();
  let list = ALL.filter(j => (Number(j.score) || 0) >= f.min);
  if (f.q) list = list.filter(j => (j.title || "").toLowerCase().includes(f.q) || (j.company || "").toLowerCase().includes(f.q));
  if (f.status) list = list.filter(j => statusFor(j) === f.status);
  if (f.newOnly) list = list.filter(j => j.is_new);
  if (f.freshOnly) list = list.filter(j => j.freshness === "Fresh");
  list.sort(cmp);

  const c = document.getElementById("cards");
  c.innerHTML = "";
  list.forEach(j => c.appendChild(card(j)));
  const empty = document.getElementById("empty");
  empty.hidden = list.length !== 0;
  if (!list.length) empty.textContent = ALL.length ? "no jobs match your filters — try “everything” 🎀" : "no jobs yet — the agent runs twice daily 🎀";
}
function refreshStats() {
  const n = (id, v) => document.getElementById(id).textContent = v;
  n("stat-total", ALL.length);
  n("stat-keepers", ALL.filter(j => (Number(j.score) || 0) >= 7).length);
  n("stat-fresh", ALL.filter(j => j.freshness === "Fresh").length);
  n("stat-new", ALL.filter(j => j.is_new).length);
}

/* ---------- settings drawer ---------- */
function initSettings() {
  const drawer = document.getElementById("settings");
  document.getElementById("settings-btn").addEventListener("click", () => {
    drawer.hidden = !drawer.hidden;
    if (!drawer.hidden) {
      document.getElementById("cfg-key").value = getKey();
      document.getElementById("cfg-cv").value = getCV();
    }
  });
  document.getElementById("cfg-save").addEventListener("click", () => {
    localStorage.setItem(LS.key, document.getElementById("cfg-key").value.trim());
    localStorage.setItem(LS.cv, document.getElementById("cfg-cv").value.trim());
    const s = document.getElementById("cfg-status");
    s.textContent = "saved 💗"; setTimeout(() => s.textContent = "", 2000);
  });
}

/* ---------- cover letter modal ---------- */
const modal = () => document.getElementById("modal");
function closeModal() { modal().hidden = true; document.getElementById("modal-body").innerHTML = ""; document.getElementById("modal-actions").innerHTML = ""; }

function openCover(job) {
  const m = modal();
  m.hidden = false;
  document.getElementById("modal-title").textContent = job.title;
  const cached = localStorage.getItem(LS.cover(job.url));
  if (cached) return showLetter(job, cached, true);

  if (!getKey()) return promptForKey();
  generate(job, false);
}
function promptForKey() {
  const body = document.getElementById("modal-body");
  body.className = "modal-body center";
  body.innerHTML = `Add your Gemini API key first (⚙️ Settings) to generate cover letters.<br><br>It stays in your browser and uses your own free quota.`;
  document.getElementById("modal-actions").innerHTML = `<button class="btn primary" id="go-settings">Open settings ⚙️</button>`;
  document.getElementById("go-settings").addEventListener("click", () => { closeModal(); const d = document.getElementById("settings"); d.hidden = false; document.getElementById("cfg-key").focus(); });
}
function showLetter(job, text, fromCache) {
  const body = document.getElementById("modal-body");
  body.className = "modal-body";
  body.textContent = text;
  const actions = document.getElementById("modal-actions");
  actions.innerHTML = `
    <button class="btn primary" id="cl-copy">Copy 📋</button>
    <button class="btn" id="cl-pdf">Save PDF 📄</button>
    <button class="btn ghost" id="cl-regen">Regenerate 🔄</button>
    ${fromCache ? `<span class="muted small spacer">cached — no quota used</span>` : ""}`;
  document.getElementById("cl-copy").addEventListener("click", (e) => {
    navigator.clipboard.writeText(text).then(() => { e.target.textContent = "Copied ✓"; setTimeout(() => e.target.textContent = "Copy 📋", 1500); });
  });
  document.getElementById("cl-pdf").addEventListener("click", () => savePDF(job, text));
  document.getElementById("cl-regen").addEventListener("click", () => { if (!getKey()) return promptForKey(); generate(job, true); });
}
function showSpinner(msg) {
  const body = document.getElementById("modal-body");
  body.className = "modal-body center";
  body.innerHTML = `<div class="spin">🎀</div><br>${esc(msg)}`;
  document.getElementById("modal-actions").innerHTML = "";
}

async function generate(job, force) {
  showSpinner("writing your cover letter…");
  const prompt = `You are helping a junior software developer apply to a remote job. Write a full, tailored cover letter (not a short note): a proper greeting, 3-4 paragraphs, and a sign-off. Reference specific details from the job description and match them to concrete experience from the CV. Confident and warm, honest about being early-career, leading with relevant projects and stack. Return ONLY the letter text, no preamble.

=== CV ===
${getCV()}

=== JOB ===
Title: ${job.title}
Company: ${job.company}
Location: ${job.location}
Description/summary: ${job.summary || job.reason || ""}
Link: ${job.link || job.url}`;

  try {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${encodeURIComponent(getKey())}`;
    const res = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0.6 } }),
    });
    if (!res.ok) {
      const t = await res.text();
      let msg = `Gemini error ${res.status}.`;
      if (res.status === 429) msg = "Your Gemini free quota is used up for now — try again later.";
      else if (res.status === 400 || res.status === 403) msg = "That API key was rejected. Check it in ⚙️ Settings.";
      return showError(msg, t);
    }
    const data = await res.json();
    const text = data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
    if (!text) return showError("Gemini returned an empty response. Try Regenerate.");
    localStorage.setItem(LS.cover(job.url), text);
    showLetter(job, text, false);
  } catch (e) {
    showError("Network error reaching Gemini. Check your connection and try again.", String(e));
  }
}
function showError(msg, detail) {
  const body = document.getElementById("modal-body");
  body.className = "modal-body center";
  body.innerHTML = `😿<br><br>${esc(msg)}${detail ? `<br><br><span class="muted small">${esc(String(detail).slice(0, 200))}</span>` : ""}`;
  document.getElementById("modal-actions").innerHTML = `<button class="btn" id="err-close">Close</button>`;
  document.getElementById("err-close").addEventListener("click", closeModal);
}

function savePDF(job, text) {
  const JsPDF = window.jspdf && window.jspdf.jsPDF;
  if (!JsPDF) { alert("PDF library still loading — try again in a second."); return; }
  const doc = new JsPDF({ unit: "pt", format: "a4" });
  const margin = 56, width = doc.internal.pageSize.getWidth() - margin * 2;
  let y = margin;
  doc.setFont("times", "bold"); doc.setFontSize(13);
  doc.text(`Cover Letter — ${job.title}`.slice(0, 80), margin, y); y += 22;
  doc.setFont("times", "normal"); doc.setFontSize(11);
  doc.splitTextToSize(text, width).forEach(line => {
    if (y > doc.internal.pageSize.getHeight() - margin) { doc.addPage(); y = margin; }
    doc.text(line, margin, y); y += 16;
  });
  const safe = (job.company || "job").replace(/[^a-z0-9]+/gi, "_").slice(0, 40);
  doc.save(`cover_letter_${safe}.pdf`);
}

/* ---------- init ---------- */
async function init() {
  initSettings();
  document.getElementById("modal-close").addEventListener("click", closeModal);
  modal().addEventListener("click", (e) => { if (e.target === modal()) closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal().hidden) closeModal(); });

  try {
    const res = await fetch("jobs.json", { cache: "no-store" });
    const data = await res.json();
    ALL = Array.isArray(data) ? data : (data.jobs || []);
    document.getElementById("updated").textContent = data.generated ? `updated ${data.generated}` : "";
  } catch { ALL = []; }

  refreshStats();
  render();
  ["search", "score-filter", "status-filter", "new-only", "fresh-only"].forEach(id =>
    document.getElementById(id).addEventListener("input", render));
}
init();
