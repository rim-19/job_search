/* 🎀 Rim's Job Board — client-side rendering of jobs.json 🎀
   No backend. Status edits are stored in localStorage (this browser only). */

const STORAGE_KEY = "rim-job-status";
const STATUSES = ["Not Applied", "Applied", "Interviewing", "Rejected", "Saved"];

let ALL = [];

/* ---- local status overrides (browser only) ---- */
function loadOverrides() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
  catch { return {}; }
}
function saveOverride(url, status) {
  const o = loadOverrides();
  o[url] = status;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(o));
}
function statusFor(job) {
  const o = loadOverrides();
  return o[job.url] || job.status || "Not Applied";
}

/* ---- helpers ---- */
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function scoreClass(n) { return n >= 7 ? "high" : n >= 5 ? "mid" : "low"; }

/* ---- rendering ---- */
function card(job) {
  const st = statusFor(job);
  const cls = st === "Applied" || st === "Interviewing" ? "applied"
            : st === "Rejected" ? "rejected" : "";
  const score = Number(job.score) || 0;

  const checklist = (job.checklist && job.checklist.length)
    ? `<div class="checklist-wrap"><details><summary>application checklist</summary>
         <ul class="checklist">${job.checklist.map(i => `<li>${esc(i)}</li>`).join("")}</ul>
       </details></div>` : "";

  const cover = job.cover_note
    ? `<div class="cover"><details><summary>tailored cover note</summary>
         <p>${esc(job.cover_note)}</p></details></div>` : "";

  const options = STATUSES.map(s =>
    `<option value="${s}"${s === st ? " selected" : ""}>${s}</option>`).join("");

  const el = document.createElement("article");
  el.className = `card ${cls}`;
  el.innerHTML = `
    <div class="card-head">
      <div>
        <h2>${esc(job.title)}</h2>
        <div class="company">${esc(job.company) || "—"}</div>
        <div class="meta">
          <span>📍 ${esc(job.location) || "Remote"}</span>
          <span>🗓️ ${esc(job.date_scored) || ""}</span>
        </div>
      </div>
      <div class="score-badge ${scoreClass(score)}" title="match score">${score}</div>
    </div>
    ${job.reason ? `<p class="reason">“${esc(job.reason)}”</p>` : ""}
    ${cover}
    ${checklist}
    <div class="card-foot">
      <a class="apply-btn" href="${esc(job.link || job.url)}" target="_blank" rel="noopener">Apply 💌</a>
      <select class="status-select" aria-label="status">${options}</select>
      <span class="src-tag">${esc(job.source) || "web"}</span>
    </div>`;

  el.querySelector(".status-select").addEventListener("change", (e) => {
    saveOverride(job.url, e.target.value);
    render();
    refreshStats();
  });
  return el;
}

function currentFilters() {
  return {
    q: document.getElementById("search").value.trim().toLowerCase(),
    minScore: Number(document.getElementById("score-filter").value),
    status: document.getElementById("status-filter").value,
    sort: document.getElementById("sort").value,
  };
}

function render() {
  const f = currentFilters();
  let list = ALL.filter(j => (Number(j.score) || 0) >= f.minScore);

  if (f.q) {
    list = list.filter(j =>
      (j.title || "").toLowerCase().includes(f.q) ||
      (j.company || "").toLowerCase().includes(f.q));
  }
  if (f.status) list = list.filter(j => statusFor(j) === f.status);

  if (f.sort === "score") list.sort((a, b) => (b.score || 0) - (a.score || 0));
  else if (f.sort === "date") list.sort((a, b) => String(b.date_scored).localeCompare(String(a.date_scored)));
  else if (f.sort === "company") list.sort((a, b) => String(a.company).localeCompare(String(b.company)));

  const container = document.getElementById("cards");
  container.innerHTML = "";
  list.forEach(j => container.appendChild(card(j)));
  document.getElementById("empty").hidden = list.length !== 0;
}

function refreshStats() {
  document.getElementById("stat-total").textContent = ALL.length;
  document.getElementById("stat-keepers").textContent =
    ALL.filter(j => (Number(j.score) || 0) >= 7).length;
  document.getElementById("stat-applied").textContent =
    ALL.filter(j => ["Applied", "Interviewing"].includes(statusFor(j))).length;
}

async function init() {
  try {
    const res = await fetch("jobs.json", { cache: "no-store" });
    const data = await res.json();
    ALL = Array.isArray(data) ? data : (data.jobs || []);
  } catch (e) {
    ALL = [];
    document.getElementById("empty").hidden = false;
    document.getElementById("empty").textContent =
      "couldn't load jobs.json yet — run the pipeline first 🎀";
  }

  refreshStats();
  render();

  const updated = ALL.reduce((m, j) => j.date_scored > m ? j.date_scored : m, "");
  document.getElementById("updated").textContent =
    updated ? `last updated ${updated}` : "";

  ["search", "score-filter", "status-filter", "sort"].forEach(id =>
    document.getElementById(id).addEventListener("input", render));
}

init();
