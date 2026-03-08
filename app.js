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
const CAT_COLORS = {
  "astro-ph.GA": { bg: "var(--cat-ga)", color: "#fff" },
  "astro-ph.CO": { bg: "var(--cat-co)", color: "#000" },
  "astro-ph.EP": { bg: "var(--cat-ep)", color: "#fff" },
  "astro-ph.HE": { bg: "var(--cat-he)", color: "#fff" },
  "astro-ph.IM": { bg: "var(--cat-im)", color: "#fff" },
  "astro-ph.SR": { bg: "var(--cat-sr)", color: "#fff" },
};

let allPapers = [];
let favoriteAuthors = [];
let activeCats = new Set(ASTRO_CATS);
let currentSort = "local";
let currentDate = null;
let archiveMode = false;
let archivePapers = [];
let archiveDisplayCount = 100;
let archiveSearchQuery = "";

// ── Initialise ────────────────────────────────────────────────────────────────

async function init() {
  await Promise.all([loadIndex(), loadAuthors()]);
  buildCatFilter();

  if (!currentDate) {
    showEmptyState("No data available yet. The GitHub Action will populate data daily.");
    return;
  }

  updateDateLabel(currentDate);
  await loadDay(currentDate);
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadIndex() {
  const res = await fetch("data/index.json");
  const data = await res.json();
  currentDate = data.current || null;
}

async function loadAuthors() {
  const load = async (path) => {
    try {
      const res = await fetch(path);
      const data = await res.json();
      return data.authors || [];
    } catch {
      return [];
    }
  };
  const [auto, manual] = await Promise.all([
    load("config/authors.json"),
    load("config/authors_manual.json"),
  ]);
  const seen = new Set();
  favoriteAuthors = [...manual, ...auto].filter((name) => {
    if (seen.has(name)) return false;
    seen.add(name);
    return true;
  });
}

async function loadDay(dateStr) {
  document.getElementById("loading").style.display = "block";
  document.getElementById("paper-list").innerHTML = "";
  document.getElementById("stats").textContent = "";

  try {
    const res = await fetch(`data/${dateStr}.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const raw = data.papers || [];

    // Assign arXiv listing numbers by ascending ID within each group
    const newSubs = raw.filter((p) => (p.primary_category || "").startsWith("astro-ph"))
                       .sort((a, b) => a.id.localeCompare(b.id));
    const crossList = raw.filter((p) => !(p.primary_category || "").startsWith("astro-ph"))
                         .sort((a, b) => a.id.localeCompare(b.id));
    const newNums  = new Map(newSubs.map((p, i)  => [p.id, i + 1]));
    const crossNums = new Map(crossList.map((p, i) => [p.id, newSubs.length + i + 1]));

    // _arxivIndex: position in descending-ID order (used for sort); _arxivNum: display number
    allPapers = raw.map((p, i) => ({
      ...p,
      _arxivIndex: raw.length - i,
      _arxivNum: newNums.get(p.id) ?? crossNums.get(p.id),
      _isCrossListing: !(p.primary_category || "").startsWith("astro-ph"),
    }));

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

async function loadArchive() {
  document.getElementById("loading").style.display = "block";
  document.getElementById("loading").textContent = "Loading archive (1000 papers)…";
  document.getElementById("paper-list").innerHTML = "";
  document.getElementById("stats").textContent = "";

  try {
    const res = await fetch("data/archive.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const raw = data.papers || [];
    // Precompute match strength once so sorting 1000 papers is fast
    archivePapers = raw.map((p, i) => ({
      ...p,
      _arxivIndex: raw.length - i,
      _matchStrength: bestMatchStrength(p),
    }));
    document.getElementById("fetched-at").textContent =
      data.fetched_at ? `archive fetched ${data.fetched_at.slice(0, 16).replace("T", " ")} UTC` : "";
  } catch (e) {
    archivePapers = [];
    showEmptyState("Could not load archive.");
  } finally {
    document.getElementById("loading").style.display = "none";
    document.getElementById("loading").textContent = "Loading…";
  }

  archiveDisplayCount = 100;
  renderArchive();
}

// ── UI builders ───────────────────────────────────────────────────────────────

function updateDateLabel(dateStr) {
  const label = document.getElementById("current-date-label");
  if (!label) return;
  label.textContent = dateStr === "archive" ? "Archive (1000 papers)" : formatDate(dateStr);
}

function buildCatFilter() {
  const container = document.getElementById("cat-filter");
  ASTRO_CATS.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = "cat-toggle active";
    btn.dataset.cat = cat;
    btn.title = CAT_LABELS[cat] || cat;
    btn.textContent = cat.split(".")[1];
    btn.addEventListener("click", () => toggleCat(cat, btn));
    container.appendChild(btn);
  });

  const all = document.createElement("button");
  all.className = "cat-toggle";
  all.textContent = "All";
  all.style.marginLeft = "8px";
  all.addEventListener("click", () => {
    activeCats = new Set(ASTRO_CATS);
    document.querySelectorAll(".cat-toggle[data-cat]").forEach((b) => b.classList.add("active"));
    if (archiveMode) renderArchive(); else render();
  });

  const none = document.createElement("button");
  none.className = "cat-toggle";
  none.textContent = "None";
  none.addEventListener("click", () => {
    activeCats.clear();
    document.querySelectorAll(".cat-toggle[data-cat]").forEach((b) => b.classList.remove("active"));
    if (archiveMode) renderArchive(); else render();
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
  if (archiveMode) renderArchive(); else render();
}

// ── Render ────────────────────────────────────────────────────────────────────

function applyFilters(papers) {
  return papers.filter((p) => {
    const primary = p.primary_category;
    if (primary && activeCats.has(primary)) return true;
    // Cross-listings: include if any of their categories is active
    return p.categories.some((c) => activeCats.has(c));
  });
}

function isNewSubmission(paper) {
  return (paper.primary_category || "").startsWith("astro-ph");
}

function render() {
  const list = document.getElementById("paper-list");
  list.innerHTML = "";

  let papers = applyFilters(allPapers);
  papers = sortPapers(papers, currentSort);

  if (papers.length === 0) {
    document.getElementById("stats").textContent = `0 of ${allPapers.length} papers`;
    list.innerHTML = `<div id="empty-state">No papers match the current filters.</div>`;
    return;
  }

  const isArxivOrder = currentSort === "arxiv" || currentSort === "arxiv-rev";
  if (isArxivOrder) {
    const newSubs = papers.filter(isNewSubmission);
    const crossList = papers.filter((p) => !isNewSubmission(p));
    document.getElementById("stats").textContent =
      `${newSubs.length} new submission${newSubs.length !== 1 ? "s" : ""}` +
      (crossList.length ? `, ${crossList.length} cross-listing${crossList.length !== 1 ? "s" : ""}` : "") +
      ` (${papers.length} of ${allPapers.length} papers)`;
    newSubs.forEach((paper) => list.appendChild(buildCard(paper)));
    if (crossList.length > 0) {
      list.appendChild(makeSectionHeader(`Cross-listings (${crossList.length})`));
      crossList.forEach((paper) => list.appendChild(buildCard(paper)));
    }
  } else {
    document.getElementById("stats").textContent = `${papers.length} of ${allPapers.length} papers`;
    papers.forEach((paper) => list.appendChild(buildCard(paper)));
  }
}

function renderArchive() {
  const list = document.getElementById("paper-list");
  list.innerHTML = "";

  // Apply text search
  let papers = archivePapers;
  if (archiveSearchQuery) {
    const q = archiveSearchQuery.toLowerCase();
    papers = papers.filter((p) =>
      p.title.toLowerCase().includes(q) ||
      p.authors.some((a) => a.toLowerCase().includes(q))
    );
  }

  // Apply category filter and sort
  papers = applyFilters(papers);
  papers = sortPapers(papers, currentSort);

  const total = papers.length;
  const shown = papers.slice(0, archiveDisplayCount);

  document.getElementById("stats").textContent =
    `Showing ${shown.length} of ${total} papers in archive`;

  if (shown.length === 0) {
    list.innerHTML = `<div id="empty-state">No papers match the current filters.</div>`;
    return;
  }

  const isArxivOrder = currentSort === "arxiv" || currentSort === "arxiv-rev";
  if (isArxivOrder) {
    const newSubs = shown.filter(isNewSubmission);
    const crossList = shown.filter((p) => !isNewSubmission(p));
    newSubs.forEach((paper) => list.appendChild(buildCard(paper)));
    if (crossList.length > 0) {
      list.appendChild(makeSectionHeader(`Cross-listings (${crossList.length}${shown.length < total ? "+" : ""})`));
      crossList.forEach((paper) => list.appendChild(buildCard(paper)));
    }
  } else {
    shown.forEach((paper) => list.appendChild(buildCard(paper)));
  }

  if (shown.length < total) {
    const btn = document.createElement("button");
    btn.className = "load-more-btn";
    btn.textContent = `Load ${Math.min(100, total - shown.length)} more  (${total - shown.length} remaining)`;
    btn.addEventListener("click", () => {
      archiveDisplayCount += 100;
      renderArchive();
    });
    list.appendChild(btn);
  }
}

// ── Name matching ─────────────────────────────────────────────────────────────

const NAME_SUFFIXES = new Set(["iii", "ii", "iv", "jr.", "jr", "sr.", "sr"]);
const NAME_TITLES   = new Set(["sir", "dr.", "dr", "prof.", "prof"]);

function parseNameParts(name) {
  if (name.includes(",")) {
    const comma = name.indexOf(",");
    const last   = name.slice(0, comma).trim().toLowerCase();
    const rest   = name.slice(comma + 1).trim().split(/\s+/);
    const first  = rest[0].replace(/\./g, "").toLowerCase();
    const middleInitial = rest.length > 1 ? rest[1].replace(/\./g, "").toLowerCase()[0] : null;
    return { first, last, middleInitial };
  }
  let tokens = name.trim().split(/\s+/);
  while (tokens.length > 1 && NAME_TITLES.has(tokens[0].toLowerCase()))
    tokens = tokens.slice(1);
  while (tokens.length > 1 && NAME_SUFFIXES.has(tokens[tokens.length - 1].toLowerCase()))
    tokens = tokens.slice(0, -1);
  const last  = tokens[tokens.length - 1].toLowerCase();
  const first = tokens[0].replace(/\./g, "").toLowerCase();
  const middleInitial = tokens.length > 2 ? tokens[1].replace(/\./g, "").toLowerCase()[0] : null;
  return { first, last, middleInitial };
}

function matchAuthor(favName, arxivName) {
  const fav = parseNameParts(favName);
  const arx = parseNameParts(arxivName);
  if (fav.last !== arx.last) return null;
  if (fav.first === arx.first) return "strong";
  if (fav.first[0] === arx.first[0]) {
    if (fav.middleInitial && arx.middleInitial && fav.middleInitial === arx.middleInitial)
      return "strong";
    return "weak";
  }
  return null;
}

function bestMatchStrength(paper) {
  let best = null;
  for (const author of paper.authors) {
    for (const fav of favoriteAuthors) {
      const s = matchAuthor(fav, author);
      if (s === "strong") return "strong";
      if (s === "weak") best = "weak";
    }
  }
  return best;
}

function sortPapers(papers, mode) {
  const copy = [...papers];
  if (mode === "arxiv") {
    copy.sort((a, b) => (a._arxivIndex || 0) - (b._arxivIndex || 0));
  } else if (mode === "arxiv-rev") {
    copy.sort((a, b) => (b._arxivIndex || 0) - (a._arxivIndex || 0));
  } else if (mode === "title") {
    copy.sort((a, b) => a.title.localeCompare(b.title));
  } else if (mode === "author") {
    copy.sort((a, b) => (a.authors[0] || "").localeCompare(b.authors[0] || ""));
  } else if (mode === "category") {
    copy.sort((a, b) => (a.primary_category || "").localeCompare(b.primary_category || ""));
  } else if (mode === "local") {
    const rank = { "strong": 0, "weak": 1, null: 2 };
    copy.sort((a, b) =>
      rank[a._matchStrength ?? bestMatchStrength(a)] - rank[b._matchStrength ?? bestMatchStrength(b)] ||
      (a._arxivIndex || 0) - (b._arxivIndex || 0)
    );
  }
  return copy;
}

function makeSectionHeader(text) {
  const div = document.createElement("div");
  div.className = "section-header";
  div.textContent = text;
  return div;
}

function buildCard(paper) {
  const card = document.createElement("div");
  card.className = "paper-card";

  const strength = bestMatchStrength(paper);
  if (strength === "strong") card.classList.add("highlighted-strong");
  else if (strength === "weak") card.classList.add("highlighted-weak");

  const meta = document.createElement("div");
  meta.className = "paper-meta";

  if (paper._arxivNum != null) {
    const numSpan = document.createElement("span");
    numSpan.className = "arxiv-num" + (paper._isCrossListing ? " arxiv-num-cross" : "");
    numSpan.textContent = `[${paper._arxivNum}]`;
    meta.appendChild(numSpan);
  }

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

  const secondaryCats = paper.categories.filter((c) => c !== paper.primary_category);
  const secSpan = document.createElement("span");
  secSpan.className = "secondary-cats";
  if (secondaryCats.length) secSpan.textContent = "+ " + secondaryCats.join(", ");

  meta.append(idSpan, pdfLink, primaryBadge, secSpan);

  const titleDiv = document.createElement("div");
  titleDiv.className = "paper-title";
  const titleLink = document.createElement("a");
  titleLink.href = paper.arxiv_url;
  titleLink.target = "_blank";
  titleLink.rel = "noopener";
  titleLink.textContent = paper.title;
  titleDiv.appendChild(titleLink);

  const authorsDiv = document.createElement("div");
  authorsDiv.className = "paper-authors";
  authorsDiv.innerHTML = paper.authors.map((a) => highlightAuthor(a)).join(", ");

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
  badge.textContent = cat ? (cat.split(".")[1] || cat) : "other";
  badge.title = cat || "";
  const style = cat && CAT_COLORS[cat];
  if (style) {
    badge.style.background = style.bg;
    badge.style.color = style.color;
  } else {
    badge.classList.add("other");
  }
  return badge;
}

function highlightAuthor(name) {
  let best = null;
  for (const fav of favoriteAuthors) {
    const s = matchAuthor(fav, name);
    if (s === "strong") { best = "strong"; break; }
    if (s === "weak") best = "weak";
  }
  if (best === "strong") return `<span class="author-highlight-strong">${escHtml(name)}</span>`;
  if (best === "weak")   return `<span class="author-highlight-weak">${escHtml(name)}</span>`;
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
  // ── Announcement banner ──
  const annToggle = document.getElementById("announcement-toggle");
  const annBody   = document.getElementById("announcement-body");
  const ANN_KEY   = "announcement-open";

  function setAnnouncement(open) {
    annBody.hidden = !open;
    annToggle.setAttribute("aria-expanded", String(open));
    localStorage.setItem(ANN_KEY, open ? "1" : "0");
  }

  setAnnouncement(localStorage.getItem(ANN_KEY) === "1");
  annToggle.addEventListener("click", () => setAnnouncement(annBody.hidden));

  // ── Sort ──
  document.getElementById("sort-select").addEventListener("change", (e) => {
    currentSort = e.target.value;
    if (archiveMode) renderArchive(); else render();
  });

  // ── Archive toggle ──
  document.getElementById("btn-archive").addEventListener("click", async () => {
    archiveMode = !archiveMode;
    const btn = document.getElementById("btn-archive");
    const searchContainer = document.getElementById("search-container");

    if (archiveMode) {
      btn.classList.add("active");
      searchContainer.style.display = "";
      updateDateLabel("archive");
      await loadArchive();
    } else {
      btn.classList.remove("active");
      searchContainer.style.display = "none";
      archiveSearchQuery = "";
      document.getElementById("search-input").value = "";
      archiveDisplayCount = 100;
      updateDateLabel(currentDate);
      await loadDay(currentDate);
    }
  });

  // ── Archive search ──
  document.getElementById("search-input").addEventListener("input", (e) => {
    archiveSearchQuery = e.target.value.trim();
    archiveDisplayCount = 100;
    renderArchive();
  });

  init();
});
