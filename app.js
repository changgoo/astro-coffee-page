"use strict";

const ASTRO_CATS = ["astro-ph.GA", "astro-ph.CO", "astro-ph.EP", "astro-ph.HE", "astro-ph.IM", "astro-ph.SR"];
const CAT_LABELS = {
  "astro-ph.GA": "GA – Galaxies",
  "astro-ph.CO": "CO – Cosmology",
  "astro-ph.EP": "EP – Planets",
  "astro-ph.HE": "HE – High Energy",
  "astro-ph.IM": "IM – Instrumentation",
  "astro-ph.SR": "SR – Stars",
};

let allPapers = [];
let favoriteAuthors = [];
let activeCats = new Set(ASTRO_CATS);
let currentSort = "default";
let availableDates = [];
let currentDate = null;

// ── Initialise ────────────────────────────────────────────────────────────────

async function init() {
  await Promise.all([loadIndex(), loadAuthors()]);
  buildCatFilter();

  if (availableDates.length === 0) {
    showEmptyState("No data available yet. The GitHub Action will populate data daily.");
    return;
  }

  // Honour ?date= query param
  const params = new URLSearchParams(location.search);
  const requested = params.get("date");
  currentDate = availableDates.includes(requested) ? requested : availableDates[0];

  populateDateSelector();
  await loadDay(currentDate);
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadIndex() {
  const res = await fetch("data/index.json");
  const data = await res.json();
  availableDates = data.dates || [];
}

async function loadAuthors() {
  try {
    const res = await fetch("config/authors.json");
    const data = await res.json();
    favoriteAuthors = (data.authors || []).map((a) => a.toLowerCase());
  } catch {
    favoriteAuthors = [];
  }
}

async function loadDay(dateStr) {
  document.getElementById("loading").style.display = "block";
  document.getElementById("paper-list").innerHTML = "";
  document.getElementById("stats").textContent = "";

  try {
    const res = await fetch(`data/${dateStr}.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allPapers = data.papers || [];
    document.getElementById("fetched-at").textContent =
      data.fetched_at ? `fetched ${data.fetched_at.slice(0, 16).replace("T", " ")} UTC` : "";
  } catch (e) {
    allPapers = [];
    showEmptyState(`Could not load data for ${dateStr}.`);
  } finally {
    document.getElementById("loading").style.display = "none";
  }

  render();
}

// ── UI builders ───────────────────────────────────────────────────────────────

function populateDateSelector() {
  const sel = document.getElementById("date-select");
  sel.innerHTML = "";
  availableDates.forEach((d) => {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = formatDate(d);
    if (d === currentDate) opt.selected = true;
    sel.appendChild(opt);
  });

  // Prev/Next buttons
  updateNavButtons();
}

function updateNavButtons() {
  const idx = availableDates.indexOf(currentDate);
  document.getElementById("btn-prev").disabled = idx >= availableDates.length - 1;
  document.getElementById("btn-next").disabled = idx <= 0;
}

function buildCatFilter() {
  const container = document.getElementById("cat-filter");
  ASTRO_CATS.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = "cat-toggle active";
    btn.dataset.cat = cat;
    btn.title = CAT_LABELS[cat] || cat;
    btn.textContent = cat.split(".")[1]; // GA, CO, etc.
    btn.addEventListener("click", () => toggleCat(cat, btn));
    container.appendChild(btn);
  });

  // "All" / "None" shortcuts
  const all = document.createElement("button");
  all.className = "cat-toggle";
  all.textContent = "All";
  all.style.marginLeft = "8px";
  all.addEventListener("click", () => {
    activeCats = new Set(ASTRO_CATS);
    document.querySelectorAll(".cat-toggle[data-cat]").forEach((b) => b.classList.add("active"));
    render();
  });

  const none = document.createElement("button");
  none.className = "cat-toggle";
  none.textContent = "None";
  none.addEventListener("click", () => {
    activeCats.clear();
    document.querySelectorAll(".cat-toggle[data-cat]").forEach((b) => b.classList.remove("active"));
    render();
  });

  container.appendChild(all);
  container.appendChild(none);
}

function toggleCat(cat, btn) {
  if (activeCats.has(cat)) {
    activeCats.delete(cat);
    btn.classList.remove("active");
  } else {
    activeCats.add(cat);
    btn.classList.add("active");
  }
  render();
}

// ── Render ────────────────────────────────────────────────────────────────────

function render() {
  const list = document.getElementById("paper-list");
  list.innerHTML = "";

  // Filter: include paper if its primary_category is active,
  // OR if it has any active category and no primary.
  let papers = allPapers.filter((p) => {
    const primary = p.primary_category;
    if (primary && activeCats.has(primary)) return true;
    // cross-listed: include if any active category matches
    if (!primary) return p.categories.some((c) => activeCats.has(c));
    return false;
  });

  // Sort
  papers = sortPapers(papers, currentSort);

  document.getElementById("stats").textContent =
    `${papers.length} of ${allPapers.length} papers`;

  if (papers.length === 0) {
    list.innerHTML = `<div id="empty-state">No papers match the current filters.</div>`;
    return;
  }

  papers.forEach((paper, i) => {
    list.appendChild(buildCard(paper, i));
  });
}

function sortPapers(papers, mode) {
  const copy = [...papers];
  if (mode === "title") {
    copy.sort((a, b) => a.title.localeCompare(b.title));
  } else if (mode === "author") {
    copy.sort((a, b) => {
      const aFirst = a.authors[0] || "";
      const bFirst = b.authors[0] || "";
      return aFirst.localeCompare(bFirst);
    });
  } else if (mode === "category") {
    copy.sort((a, b) => (a.primary_category || "").localeCompare(b.primary_category || ""));
  }
  // "default" keeps arXiv order
  return copy;
}

function buildCard(paper, idx) {
  const card = document.createElement("div");
  card.className = "paper-card";

  // Check if any favorite author matches
  const hasHighlight = favoriteAuthors.length > 0 &&
    paper.authors.some((a) => favoriteAuthors.some((fav) => a.toLowerCase().includes(fav)));
  if (hasHighlight) card.classList.add("highlighted");

  // Meta row: ID, PDF link, categories
  const meta = document.createElement("div");
  meta.className = "paper-meta";

  const idSpan = document.createElement("span");
  idSpan.className = "paper-id";
  idSpan.innerHTML = `[<a href="${paper.arxiv_url}" target="_blank" rel="noopener">${paper.id}</a>]`;

  const pdfLink = document.createElement("a");
  pdfLink.className = "pdf-link";
  pdfLink.href = paper.pdf_url;
  pdfLink.target = "_blank";
  pdfLink.rel = "noopener";
  pdfLink.textContent = "[PDF]";

  const primaryBadge = buildCatBadge(paper.primary_category);

  const secondaryCats = paper.categories
    .filter((c) => c !== paper.primary_category)
    .map((c) => c);
  const secSpan = document.createElement("span");
  secSpan.className = "secondary-cats";
  if (secondaryCats.length) secSpan.textContent = "+ " + secondaryCats.join(", ");

  meta.append(idSpan, pdfLink, primaryBadge, secSpan);

  // Title
  const titleDiv = document.createElement("div");
  titleDiv.className = "paper-title";
  const titleLink = document.createElement("a");
  titleLink.href = paper.arxiv_url;
  titleLink.target = "_blank";
  titleLink.rel = "noopener";
  titleLink.textContent = paper.title;
  titleDiv.appendChild(titleLink);

  // Authors
  const authorsDiv = document.createElement("div");
  authorsDiv.className = "paper-authors";
  authorsDiv.innerHTML = paper.authors.map((a) => highlightAuthor(a)).join(", ");

  // Abstract toggle
  const toggleBtn = document.createElement("button");
  toggleBtn.className = "abstract-toggle";
  toggleBtn.textContent = "Show abstract";
  toggleBtn.addEventListener("click", () => {
    const abs = card.querySelector(".paper-abstract");
    const open = abs.classList.toggle("open");
    toggleBtn.textContent = open ? "Hide abstract" : "Show abstract";
  });

  const abstractDiv = document.createElement("div");
  abstractDiv.className = "paper-abstract";
  abstractDiv.textContent = paper.abstract;

  card.append(meta, titleDiv, authorsDiv, toggleBtn, abstractDiv);
  return card;
}

function buildCatBadge(cat) {
  const badge = document.createElement("span");
  badge.className = "cat-badge";
  if (cat) {
    const safe = cat.replace(".", "\\.");
    badge.classList.add(cat);
    badge.textContent = cat.split(".")[1] || cat;
    badge.title = CAT_LABELS[cat] || cat;
  } else {
    badge.classList.add("other");
    badge.textContent = "other";
  }
  return badge;
}

function highlightAuthor(name) {
  const lower = name.toLowerCase();
  if (favoriteAuthors.some((fav) => lower.includes(fav))) {
    return `<span class="author-highlight">${escHtml(name)}</span>`;
  }
  return escHtml(name);
}

function escHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(dateStr) {
  const d = new Date(dateStr + "T12:00:00Z");
  return d.toLocaleDateString("en-US", { weekday: "short", year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
}

function showEmptyState(msg) {
  document.getElementById("loading").style.display = "none";
  document.getElementById("paper-list").innerHTML =
    `<div id="empty-state"><p>${msg}</p></div>`;
}

// ── Event listeners ───────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("sort-select").addEventListener("change", (e) => {
    currentSort = e.target.value;
    render();
  });

  document.getElementById("date-select").addEventListener("change", async (e) => {
    currentDate = e.target.value;
    updateNavButtons();
    history.pushState({}, "", `?date=${currentDate}`);
    await loadDay(currentDate);
  });

  document.getElementById("btn-prev").addEventListener("click", async () => {
    const idx = availableDates.indexOf(currentDate);
    if (idx < availableDates.length - 1) {
      currentDate = availableDates[idx + 1];
      document.getElementById("date-select").value = currentDate;
      updateNavButtons();
      history.pushState({}, "", `?date=${currentDate}`);
      await loadDay(currentDate);
    }
  });

  document.getElementById("btn-next").addEventListener("click", async () => {
    const idx = availableDates.indexOf(currentDate);
    if (idx > 0) {
      currentDate = availableDates[idx - 1];
      document.getElementById("date-select").value = currentDate;
      updateNavButtons();
      history.pushState({}, "", `?date=${currentDate}`);
      await loadDay(currentDate);
    }
  });

  init();
});
