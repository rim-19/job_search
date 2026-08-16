/* 🎀 Rim's Job Board — client-side rendering + on-demand cover letters.
   No backend. Status, settings and generated letters live in localStorage only. */

const LS = {
  status: "rim-job-status",
  key: "rim-gemini-key",
  groq: "rim-groq-key",
  cv: "rim-cv-text",
  cover: (url) => "rim-cover:" + url,
  kit: (url) => "rim-kit:" + url,
};
// Application-tracking pipeline (item 31).
const STATUSES = ["Not Applied", "To Apply", "Applied", "Contacted", "Follow Up",
  "Response", "Interview", "Technical", "Offer", "Rejected", "Ghosted", "Saved"];
const APPLIED_STATES = ["Applied", "Contacted", "Follow Up", "Response",
  "Interview", "Technical", "Offer"];
const PRIORITY_META = {
  APPLY_NOW: { label: "🔥 Apply now", cls: "p-now" },
  APPLY: { label: "🟢 Apply", cls: "p-apply" },
  CONSIDER: { label: "🟡 Consider", cls: "p-consider" },
  SKIP: { label: "🔴 Skip", cls: "p-skip" },
};
const PRANK = { APPLY_NOW: 0, APPLY: 1, CONSIDER: 2, SKIP: 3 };
const GEMINI_MODEL = "gemini-2.5-flash-lite";
const GROQ_MODEL = "llama-3.3-70b-versatile";

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
const getGroq = () => localStorage.getItem(LS.groq) || "";
const getCV = () => localStorage.getItem(LS.cv) || DEFAULT_CV;
const hasAnyKey = () => !!(getKey() || getGroq());

/* ---------- utils ---------- */
function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
// 0-100 scale now.
const scoreClass = (n) => n >= 85 ? "high" : n >= 55 ? "mid" : "low";
function agoText(days) {
  if (days == null) return "";
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days <= 30) return `${days} days ago`;
  return `${Math.round(days / 30)} mo ago`;
}
// Default "smart" sort: priority, then fresh, then score, then recency.
function sortKey(j) {
  const pr = PRANK[j.priority] ?? 3;
  const fresh = j.freshness === "Fresh" ? 0 : 1;
  const days = j.days_since_posted == null ? 10000 : j.days_since_posted;
  return [pr, fresh, -(j.score || 0), days];
}
function cmp(a, b) { const x = sortKey(a), y = sortKey(b); for (let i = 0; i < 4; i++) { if (x[i] !== y[i]) return x[i] - y[i]; } return 0; }

/* ---------- card ---------- */
function card(job) {
  const st = statusFor(job);
  const stale = job.freshness !== "Fresh";
  const cls = ["card"];
  if (stale) cls.push("stale");
  if (st === "Applied" || st === "Interviewing") cls.push("applied");
  if (st === "Rejected") cls.push("rejected");

  const score = Number(job.score) || 0;
  const prio = PRIORITY_META[job.priority] || null;
  const rt = (job.remote_type || "").toUpperCase();
  const rtEmoji = rt === "REMOTE" ? "🌍" : (rt === "HYBRID" || rt === "ONSITE") ? "🏢" : "📍";

  const badges = [];
  if (prio) badges.push(`<span class="badge prio ${prio.cls}">${prio.label}</span>`);
  if (job.is_new) badges.push(`<span class="badge new">NEW ✨</span>`);
  if (job.freshness === "Fresh") badges.push(`<span class="badge fresh">🌟 Fresh</span>`);
  if (rt && rt !== "UNKNOWN") badges.push(`<span class="badge rt">${rtEmoji} ${esc(rt.toLowerCase())}</span>`);
  badges.push(`<span class="badge loc">📍 ${esc(job.location || job.geographic_scope || "Remote")}</span>`);
  if (job.eligible_for_rim === "true") badges.push(`<span class="badge elig ok">✓ eligible</span>`);
  else if (job.eligible_for_rim === "uncertain") badges.push(`<span class="badge elig maybe">? verify</span>`);
  badges.push(`<span class="badge src">${esc(job.source || "web")}</span>`);

  const gaps = Array.isArray(job.gaps) ? job.gaps : [];
  const ago = agoText(job.days_since_posted);
  const options = STATUSES.map(s => `<option${s === st ? " selected" : ""}>${s}</option>`).join("");

  const el = document.createElement("article");
  el.className = cls.join(" ");
  el.innerHTML = `
    <div class="card-head">
      <div class="score ${scoreClass(score)}" title="match score out of 100">${score}</div>
      <div class="card-head-main">
        <h2>${esc(job.title)}</h2>
        <div class="company">${esc(job.company) || "—"}</div>
        <div class="badges">${badges.join("")}</div>
      </div>
    </div>
    ${ago ? `<div class="meta-line">🗓️ posted ${ago}</div>` : ""}
    <p class="summary">${esc(job.summary || job.reason || "")}</p>
    ${job.reason ? `<p class="reason">✓ ${esc(job.reason)}</p>` : ""}
    ${gaps.length ? `<p class="gaps">⚠ ${gaps.map(esc).join(" · ")}</p>` : ""}
    ${job.recommended_project ? `<p class="project">💡 Lead with: <b>${esc(job.recommended_project)}</b></p>` : ""}
    <div class="card-foot">
      <a class="btn primary" href="${esc(job.link || job.url)}" target="_blank" rel="noopener">Apply 💌</a>
      <button class="btn ghost cover-btn">✍️ Cover letter</button>
      <button class="btn ghost kit-btn">📋 Apply kit</button>
      <select class="status-select spacer" aria-label="status">${options}</select>
    </div>`;

  el.querySelector(".status-select").addEventListener("change", (e) => {
    saveStatus(job.url, e.target.value); render(); refreshStats();
  });
  el.querySelector(".cover-btn").addEventListener("click", () => openDoc(job, "cover"));
  el.querySelector(".kit-btn").addEventListener("click", () => openDoc(job, "kit"));
  return el;
}

/* ---------- filters + render ---------- */
const val = (id) => { const e = document.getElementById(id); return e ? e.value : ""; };
const checked = (id) => { const e = document.getElementById(id); return e ? e.checked : false; };

function geoMatch(j, geo) {
  const loc = (j.location || "").toLowerCase();
  const scope = (j.geographic_scope || "").toUpperCase();
  const rt = (j.remote_type || "").toUpperCase();
  switch (geo) {
    case "morocco": return scope === "MOROCCO" || loc.includes("morocco") || loc.includes("maroc");
    case "casarabat": return loc.includes("casablanca") || loc.includes("rabat");
    case "remote": return rt === "REMOTE";
    case "onsite": return rt === "ONSITE" || rt === "HYBRID";
    case "worldwide": return scope === "WORLDWIDE";
    case "eligible": return j.eligible_for_rim === "true";
    default: return true;
  }
}

function render() {
  const q = val("search").trim().toLowerCase();
  const min = Number(val("score-filter") || 0);
  const status = val("status-filter");
  const priority = val("priority-filter");
  const geo = val("geo-filter");
  const sort = val("sort");
  let list = ALL.filter(j => (Number(j.score) || 0) >= min);
  if (q) list = list.filter(j => (j.title || "").toLowerCase().includes(q) || (j.company || "").toLowerCase().includes(q));
  if (status) list = list.filter(j => statusFor(j) === status);
  if (priority) list = list.filter(j => (j.priority || "") === priority);
  if (geo) list = list.filter(j => geoMatch(j, geo));
  if (checked("new-only")) list = list.filter(j => j.is_new);
  if (checked("fresh-only")) list = list.filter(j => j.freshness === "Fresh");

  if (sort === "score") list.sort((a, b) => (b.score || 0) - (a.score || 0));
  else if (sort === "newest" || sort === "fresh") list.sort((a, b) => (a.days_since_posted ?? 1e5) - (b.days_since_posted ?? 1e5));
  else if (sort === "company") list.sort((a, b) => (a.company || "").localeCompare(b.company || ""));
  else list.sort(cmp); // smart (priority + fresh)

  const c = document.getElementById("cards");
  c.innerHTML = "";
  list.forEach(j => c.appendChild(card(j)));
  const empty = document.getElementById("empty");
  empty.hidden = list.length !== 0;
  if (!list.length) empty.textContent = ALL.length ? "no jobs match your filters 🎀" : "no jobs yet — the agent runs every 5 hours 🎀";
}
function refreshStats() {
  const n = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  n("stat-total", ALL.length);
  n("stat-keepers", ALL.filter(j => j.priority === "APPLY_NOW" || j.priority === "APPLY").length);
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
      document.getElementById("cfg-groq").value = getGroq();
      document.getElementById("cfg-cv").value = getCV();
    }
  });
  document.getElementById("cfg-save").addEventListener("click", () => {
    localStorage.setItem(LS.key, document.getElementById("cfg-key").value.trim());
    localStorage.setItem(LS.groq, document.getElementById("cfg-groq").value.trim());
    localStorage.setItem(LS.cv, document.getElementById("cfg-cv").value.trim());
    const s = document.getElementById("cfg-status");
    s.textContent = "saved 💗"; setTimeout(() => s.textContent = "", 2000);
  });
}

/* ---------- generated-document modal (cover letter + apply kit) ---------- */
const modal = () => document.getElementById("modal");
function closeModal() { modal().hidden = true; document.getElementById("modal-body").innerHTML = ""; document.getElementById("modal-actions").innerHTML = ""; }

// Two document kinds share the same modal + LLM plumbing.
function jobBlock(job) {
  const gaps = Array.isArray(job.gaps) && job.gaps.length ? job.gaps.join("; ") : "none noted";
  return `Title: ${job.title}
Company: ${job.company}
Location: ${job.location}
Description/summary: ${job.summary || job.reason || ""}
Most relevant project to lead with: ${job.recommended_project || "pick the best fit"}
Known gaps to address honestly (do not overclaim): ${gaps}`;
}
function coverPrompt(job) {
  return `You are helping a junior software developer apply to a remote job. Write a full, tailored cover letter (not a short note): a proper greeting, 3-4 paragraphs, and a sign-off. Reference specific details from the job and match them to concrete experience from the CV. Lead with the "most relevant project" below. If there are gaps, address them honestly and briefly (frame as eagerness to learn) — never invent experience. Confident, warm, honest about being early-career. Return ONLY the letter text, no preamble.

=== CV ===
${getCV()}

=== JOB ===
${jobBlock(job)}`;
}
function kitPrompt(job) {
  return `You are helping a junior software developer apply FAST to a remote job. Produce a concise "application kit" she can copy-paste. Use PLAIN TEXT with these clearly-labelled sections:

1) TAILORED CV SUMMARY — 3 sentences positioning her for THIS role.
2) MATCHING SKILLS — 4-5 bullet points, each linking one of her real skills/projects to something this job needs.
3) COMMON QUESTIONS — short first-person answers (2-3 sentences each) to: "Why do you want this role?", "Why are you a good fit?", "Tell us about a relevant project.", "What are your salary expectations?" (give a reasonable remote-junior range in USD and say flexible), "When can you start?" (immediately, flexible).
Be specific to the job and honest about being early-career. Lead the matching skills with the "most relevant project" below, and address any listed gaps honestly (never invent experience). Return ONLY the kit text.

=== CV ===
${getCV()}

=== JOB ===
${jobBlock(job)}`;
}
const DOC_KINDS = {
  cover: { label: "Cover letter", cache: (u) => LS.cover(u), pdf: "cover_letter", build: coverPrompt, spin: "writing your cover letter…" },
  kit:   { label: "Apply kit",    cache: (u) => LS.kit(u),   pdf: "apply_kit",    build: kitPrompt,   spin: "building your apply kit…" },
};

function openDoc(job, kind) {
  const spec = DOC_KINDS[kind];
  modal().hidden = false;
  document.getElementById("modal-title").textContent = `${spec.label} — ${job.title}`;
  const cached = localStorage.getItem(spec.cache(job.url));
  if (cached) return showDoc(job, kind, cached, true);
  if (!hasAnyKey()) return promptForKey(spec.label);
  generateDoc(job, kind);
}
function promptForKey(what) {
  const body = document.getElementById("modal-body");
  body.className = "modal-body center";
  body.innerHTML = `Add your Gemini API key first (⚙️ Settings) to generate ${esc((what || "documents").toLowerCase())}s.<br><br>It stays in your browser and uses your own free quota. You can also add a Groq key as an automatic fallback.`;
  document.getElementById("modal-actions").innerHTML = `<button class="btn primary" id="go-settings">Open settings ⚙️</button>`;
  document.getElementById("go-settings").addEventListener("click", () => { closeModal(); const d = document.getElementById("settings"); d.hidden = false; document.getElementById("cfg-key").focus(); });
}
function showDoc(job, kind, text, fromCache) {
  const spec = DOC_KINDS[kind];
  const body = document.getElementById("modal-body");
  body.className = "modal-body";
  body.textContent = text;
  document.getElementById("modal-actions").innerHTML = `
    <button class="btn primary" id="d-copy">Copy 📋</button>
    <button class="btn" id="d-pdf">Save PDF 📄</button>
    <button class="btn ghost" id="d-regen">Regenerate 🔄</button>
    ${fromCache ? `<span class="muted small spacer">cached — no quota used</span>` : ""}`;
  document.getElementById("d-copy").addEventListener("click", (e) => {
    navigator.clipboard.writeText(text).then(() => { e.target.textContent = "Copied ✓"; setTimeout(() => e.target.textContent = "Copy 📋", 1500); });
  });
  document.getElementById("d-pdf").addEventListener("click", () => savePDF(job, text, spec));
  document.getElementById("d-regen").addEventListener("click", () => { if (!hasAnyKey()) return promptForKey(spec.label); generateDoc(job, kind); });
}
function showSpinner(msg) {
  const body = document.getElementById("modal-body");
  body.className = "modal-body center";
  body.innerHTML = `<div class="spin">🎀</div><br>${esc(msg)}`;
  document.getElementById("modal-actions").innerHTML = "";
}

async function callGemini(prompt) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${encodeURIComponent(getKey())}`;
  const res = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0.6 } }),
  });
  if (!res.ok) return { ok: false, status: res.status, detail: await res.text() };
  const data = await res.json();
  return { ok: true, text: data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || "" };
}
async function callGroq(prompt) {
  const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + getGroq() },
    body: JSON.stringify({ model: GROQ_MODEL, messages: [{ role: "user", content: prompt }], temperature: 0.6 }),
  });
  if (!res.ok) return { ok: false, status: res.status, detail: await res.text() };
  const data = await res.json();
  return { ok: true, text: data?.choices?.[0]?.message?.content?.trim() || "" };
}

// Shared runner: Gemini first, auto-fallback to Groq on quota/bad-key.
async function runLLM(prompt) {
  let r = null, who = "Gemini";
  if (getKey()) {
    r = await callGemini(prompt);
    if (!r.ok && r.status === 429 && getGroq()) { showSpinner("Gemini quota is out — trying Groq…"); r = await callGroq(prompt); who = "Groq"; }
    else if (!r.ok && (r.status === 400 || r.status === 403) && getGroq()) { r = await callGroq(prompt); who = "Groq"; }
  } else if (getGroq()) {
    r = await callGroq(prompt); who = "Groq";
  }
  if (r) r.who = who;
  return r;
}

async function generateDoc(job, kind) {
  const spec = DOC_KINDS[kind];
  showSpinner(spec.spin);
  try {
    const r = await runLLM(spec.build(job));
    if (!r) return promptForKey(spec.label);
    if (!r.ok) {
      let msg = `${r.who} error ${r.status}.`;
      if (r.status === 429) msg = `Your ${r.who} quota is used up for now — ${r.who === "Groq" || !getGroq() ? "try again later." : "add a Groq key in ⚙️ Settings as a fallback."}`;
      else if (r.status === 400 || r.status === 403) msg = `That ${r.who} API key was rejected. Check it in ⚙️ Settings.`;
      return showError(msg, r.detail);
    }
    if (!r.text) return showError("The model returned an empty response. Try Regenerate.");
    localStorage.setItem(spec.cache(job.url), r.text);
    showDoc(job, kind, r.text, false);
  } catch (e) {
    showError("Network error reaching the AI. Check your connection and try again.", String(e));
  }
}
function showError(msg, detail) {
  const body = document.getElementById("modal-body");
  body.className = "modal-body center";
  body.innerHTML = `😿<br><br>${esc(msg)}${detail ? `<br><br><span class="muted small">${esc(String(detail).slice(0, 200))}</span>` : ""}`;
  document.getElementById("modal-actions").innerHTML = `<button class="btn" id="err-close">Close</button>`;
  document.getElementById("err-close").addEventListener("click", closeModal);
}

function savePDF(job, text, spec) {
  const JsPDF = window.jspdf && window.jspdf.jsPDF;
  if (!JsPDF) { alert("PDF library still loading — try again in a second."); return; }
  const doc = new JsPDF({ unit: "pt", format: "a4" });
  const margin = 56, width = doc.internal.pageSize.getWidth() - margin * 2;
  let y = margin;
  doc.setFont("times", "bold"); doc.setFontSize(13);
  doc.text(`${spec.label} — ${job.title}`.slice(0, 80), margin, y); y += 22;
  doc.setFont("times", "normal"); doc.setFontSize(11);
  doc.splitTextToSize(text, width).forEach(line => {
    if (y > doc.internal.pageSize.getHeight() - margin) { doc.addPage(); y = margin; }
    doc.text(line, margin, y); y += 16;
  });
  const safe = (job.company || "job").replace(/[^a-z0-9]+/gi, "_").slice(0, 40);
  doc.save(`${spec.pdf}_${safe}.pdf`);
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
  ["search", "score-filter", "status-filter", "priority-filter", "geo-filter",
   "sort", "new-only", "fresh-only"].forEach(id => {
    const e = document.getElementById(id);
    if (e) e.addEventListener("input", render);
  });
}
init();
