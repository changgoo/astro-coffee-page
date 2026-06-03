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
  "astro-ph.CO": { bg: "var(--cat-co)", color: "#fff" },
  "astro-ph.EP": { bg: "var(--cat-ep)", color: "#fff" },
  "astro-ph.HE": { bg: "var(--cat-he)", color: "#fff" },
  "astro-ph.IM": { bg: "var(--cat-im)", color: "#fff" },
  "astro-ph.SR": { bg: "var(--cat-sr)", color: "#fff" },
};

let allPapers = [];
let activeCats = new Set(ASTRO_CATS);
const PAGE_MODE = document.body.dataset.page ||
  (location.pathname.endsWith("discussed.html") ? "discussed" : "today");
const DISCUSSED_ISSUE_LABEL = "discussed-paper";
// ── Sorting state (three independent axes) ────────────────────────────────────
let sortOrder  = localStorage.getItem("sort-order")   || "asc";       // "asc" | "desc"
let localFirst = localStorage.getItem("local-first")  || "strong";    // "none" | "strong" | "strong+weak"
let historyOffset = 0;                                                   // 0..5, not persisted
// ─────────────────────────────────────────────────────────────────────────────
let currentDate = null;
let discussedPapers = [];
let searchQuery = "";
let currentFontSize = localStorage.getItem("font-size") || "medium";
let abstractMode = localStorage.getItem("abstract-mode") || "none";
const HISTORY_OFFSETS = [0, 1, 2, 3, 4, 5];
const historyData = new Map();

// ── Initialise ────────────────────────────────────────────────────────────────

function applyFontSize(size) {
  currentFontSize = size;
  document.body.dataset.font = size;
  localStorage.setItem("font-size", size);
  document.querySelectorAll(".btn-font").forEach((b) => {
    b.classList.toggle("active", b.dataset.size === size);
  });
}

/** Sync active class on all button groups from current state variables. */
function syncSortUI() {
  document.querySelectorAll(".sort-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.sortOrder === sortOrder));
  document.querySelectorAll(".local-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.local === localFirst));
  document.querySelectorAll(".source-btn").forEach((b) =>
    b.classList.toggle("active", Number(b.dataset.historyOffset) === historyOffset));
  document.querySelectorAll(".abstract-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.abstract === abstractMode));
}

async function init() {
  applyFontSize(currentFontSize);
  syncSortUI();

  if (PAGE_MODE === "discussed") {
    await loadDiscussed();
    return;
  }

  await loadIndex();
  buildCatFilter();
  await loadHistoryData();

  if (!currentDate) {
    showEmptyState("No data available yet. The GitHub Action will populate data daily.");
    return;
  }

  await loadDay(0);
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadIndex() {
  const res = await fetch("data/index.json");
  const data = await res.json();
  currentDate = data.current || null;
}

function historyFilename(offset) {
  return offset === 0 ? "today.json" : `today-${offset}.json`;
}

async function fetchHistoryFile(offset) {
  const res = await fetch(`data/${historyFilename(offset)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadHistoryData() {
  const loads = HISTORY_OFFSETS.map(async (offset) => {
    const btn = document.querySelector(`.source-btn[data-history-offset="${offset}"]`);
    try {
      const data = await fetchHistoryFile(offset);
      historyData.set(offset, data);
      if (btn) {
        btn.hidden = false;
        btn.disabled = false;
        btn.title = data.date ? formatDate(data.date) : btn.title;
      }
    } catch (e) {
      if (btn && offset > 0) {
        btn.hidden = true;
        btn.disabled = true;
      }
    }
  });
  await Promise.all(loads);
}

async function loadDay(offset) {
  document.getElementById("loading").style.display = "block";
  document.getElementById("paper-list").innerHTML = "";
  document.getElementById("stats").textContent = "";

  try {
    const data = historyData.get(offset) || await fetchHistoryFile(offset);
    historyData.set(offset, data);
    const raw = data.papers || [];

    // Assign arXiv listing numbers by ascending ID within each group
    const newSubs = raw.filter((p) => (p.primary_category || "").startsWith("astro-ph"))
                       .sort((a, b) => a.id.localeCompare(b.id));
    const crossList = raw.filter((p) => !(p.primary_category || "").startsWith("astro-ph"))
                         .sort((a, b) => a.id.localeCompare(b.id));
    const newNums  = new Map(newSubs.map((p, i)  => [p.id, i + 1]));
    const crossNums = new Map(crossList.map((p, i) => [p.id, newSubs.length + i + 1]));

    allPapers = raw.map((p) => ({
      ...p,
      _arxivNum: newNums.get(p.id) ?? crossNums.get(p.id),
      _isCrossListing: !(p.primary_category || "").startsWith("astro-ph"),
    }));

    const fetchedText = data.fetched_at
      ? `fetched ${data.fetched_at.slice(0, 16).replace("T", " ")} UTC`
      : "";
    const listingText = data.date ? `arXiv listing: ${formatDate(data.date)}` : "";
    document.getElementById("fetched-at").textContent =
      [listingText, fetchedText].filter(Boolean).join(" · ");
    updateDateLabel(offset === 0 ? currentDate : data.date || currentDate);
  } catch (e) {
    allPapers = [];
    showEmptyState(`Could not load data for ${historyFilename(offset)}.`);
  } finally {
    document.getElementById("loading").style.display = "none";
  }

  render();
}

// ── UI builders ───────────────────────────────────────────────────────────────

function updateDateLabel(dateStr) {
  const label = document.getElementById("current-date-label");
  if (!label) return;
  if (dateStr === "discussed") {
    label.textContent = "Discussed papers";
  } else {
    label.textContent = formatDate(dateStr);
  }
}

async function loadDiscussed() {
  document.getElementById("loading").style.display = "block";
  document.getElementById("loading").textContent = "Loading discussed papers…";
  document.getElementById("paper-list").innerHTML = "";
  document.getElementById("stats").textContent = "";

  let loaded = false;
  try {
    const res = await fetch("data/discussed.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    discussedPapers = (data.papers || []).map((p) => ({
      ...p,
      id: p.paper_id,
    }));
    document.getElementById("fetched-at").textContent =
      data.generated_at ? `updated ${data.generated_at.slice(0, 16).replace("T", " ")} UTC` : "";
    updateDateLabel("discussed");
    loaded = true;
  } catch (e) {
    discussedPapers = [];
    showEmptyState("Could not load discussed papers.");
  } finally {
    document.getElementById("loading").style.display = "none";
    document.getElementById("loading").textContent = "Loading…";
  }

  if (loaded) {
    renderDiscussed();
  }
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
    renderCurrent();
  });

  const none = document.createElement("button");
  none.className = "cat-toggle";
  none.textContent = "None";
  none.addEventListener("click", () => {
    activeCats.clear();
    document.querySelectorAll(".cat-toggle[data-cat]").forEach((b) => b.classList.remove("active"));
    renderCurrent();
  });

  container.appendChild(all);
  container.appendChild(none);

  // Font size controls — appended last so they sit at the end of the filter row
  const fontLabel = document.createElement("span");
  fontLabel.className = "sort-label";
  fontLabel.textContent = "Font size:";
  fontLabel.style.marginLeft = "8px";

  const fontGroup = document.createElement("div");
  fontGroup.className = "btn-group";
  ["small", "medium", "large"].forEach((size) => {
    const btn = document.createElement("button");
    btn.className = "btn-font";
    btn.dataset.size = size;
    btn.textContent = size[0].toUpperCase();
    btn.addEventListener("click", () => applyFontSize(size));
    fontGroup.appendChild(btn);
  });

  container.appendChild(fontLabel);
  container.appendChild(fontGroup);
}

function toggleCat(cat, btn) {
  if (activeCats.has(cat)) {
    activeCats.delete(cat);
    btn.classList.remove("active");
  } else {
    activeCats.add(cat);
    btn.classList.add("active");
  }
  renderCurrent();
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderCurrent() {
  render();
}

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

/**
 * Sort papers by the current sortOrder and localFirst axes.
 *
 * localFirst groupings (each group is internally sorted by arXiv ID):
 *   "none"        → plain arXiv ID order (asc or desc)
 *   "strong"      → strong-match papers first, then all others
 *   "strong+weak" → strong first, then weak, then the rest
 */
function sortPapers(papers) {
  const copy = [...papers];
  const idCmp = sortOrder === "asc"
    ? (a, b) => a.id.localeCompare(b.id)
    : (a, b) => b.id.localeCompare(a.id);

  // Cross-listings sort after new submissions within each group
  const crossCmp = (a, b) =>
    (isNewSubmission(a) ? 0 : 1) - (isNewSubmission(b) ? 0 : 1);

  if (localFirst === "none") {
    copy.sort((a, b) => crossCmp(a, b) || idCmp(a, b));
  } else if (localFirst === "strong") {
    copy.sort((a, b) => {
      const ra = a.local_match === "strong" ? 0 : 1;
      const rb = b.local_match === "strong" ? 0 : 1;
      return ra - rb || crossCmp(a, b) || idCmp(a, b);
    });
  } else { // "strong+weak"
    const rank = { strong: 0, weak: 1 };
    copy.sort((a, b) => {
      const ra = rank[a.local_match] ?? 2;
      const rb = rank[b.local_match] ?? 2;
      return ra - rb || crossCmp(a, b) || idCmp(a, b);
    });
  }
  return copy;
}

/**
 * Append paper cards to list, grouped by local-match strength or by
 * new-submission vs cross-listing, with section dividers.
 *
 * @param {HTMLElement} list    - container element
 * @param {object[]}    papers  - already sorted slice to render
 * @param {boolean}     partial - true when more papers remain
 */
/**
 * Render the "others" group, splitting new submissions from cross-listings.
 */
function appendOthersWithCrossListSplit(list, others, partial) {
  const newSubs   = others.filter(isNewSubmission);
  const crossList = others.filter((p) => !isNewSubmission(p));
  newSubs.forEach((p) => list.appendChild(buildCard(p)));
  if (crossList.length) {
    list.appendChild(makeSectionHeader(
      `Cross-listings (${crossList.length}${partial ? "+" : ""})`));
    crossList.forEach((p) => list.appendChild(buildCard(p)));
  }
}

function appendPaperGroups(list, papers, partial = false) {
  if (localFirst === "none") {
    // Pure arXiv order: split new submissions and cross-listings
    const newSubs   = papers.filter(isNewSubmission);
    const crossList = papers.filter((p) => !isNewSubmission(p));
    newSubs.forEach((p) => list.appendChild(buildCard(p)));
    if (crossList.length > 0) {
      list.appendChild(makeSectionHeader(
        `Cross-listings (${crossList.length}${partial ? "+" : ""})`));
      crossList.forEach((p) => list.appendChild(buildCard(p)));
    }
  } else if (localFirst === "strong") {
    const strong = papers.filter((p) => p.local_match === "strong");
    const others  = papers.filter((p) => p.local_match !== "strong");
    if (strong.length) {
      list.appendChild(makeSectionHeader(`Local authors – strong (${strong.length})`));
      strong.forEach((p) => list.appendChild(buildCard(p)));
    }
    appendOthersWithCrossListSplit(list, others, partial);
  } else { // "strong+weak"
    const strong = papers.filter((p) => p.local_match === "strong");
    const weak   = papers.filter((p) => p.local_match === "weak");
    const others = papers.filter((p) => !p.local_match);
    if (strong.length) {
      list.appendChild(makeSectionHeader(`Local authors – strong (${strong.length})`));
      strong.forEach((p) => list.appendChild(buildCard(p)));
    }
    if (weak.length) {
      list.appendChild(makeSectionHeader(`Local authors – weak (${weak.length})`));
      weak.forEach((p) => list.appendChild(buildCard(p)));
    }
    appendOthersWithCrossListSplit(list, others, partial);
  }
}

function render() {
  const list = document.getElementById("paper-list");
  list.innerHTML = "";

  let papers = allPapers;
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    papers = papers.filter((p) =>
      p.title.toLowerCase().includes(q) ||
      p.authors.some((a) => a.toLowerCase().includes(q))
    );
  }
  papers = applyFilters(papers);
  papers = sortPapers(papers);

  if (papers.length === 0) {
    document.getElementById("stats").textContent = `0 of ${allPapers.length} papers`;
    list.innerHTML = `<div id="empty-state">No papers match the current filters.</div>`;
    return;
  }

  const newSubs   = papers.filter(isNewSubmission);
  const crossList = papers.filter((p) => !isNewSubmission(p));
  let statsText = "";
  if (localFirst !== "none") {
    const localCount = papers.filter((p) => p.local_match).length;
    statsText += `${localCount} local author paper${localCount !== 1 ? "s" : ""}, `;
  }
  statsText +=
    `${newSubs.length} new submission${newSubs.length !== 1 ? "s" : ""}` +
    (crossList.length ? `, ${crossList.length} cross-listing${crossList.length !== 1 ? "s" : ""}` : "") +
    ` (${papers.length} of ${allPapers.length} papers)`;
  document.getElementById("stats").textContent = statsText;

  appendPaperGroups(list, papers);
}

// ── Name matching ─────────────────────────────────────────────────────────────
// Match strength is precomputed during scraping and stored in paper.local_match
// and paper.local_authors — no client-side name matching needed.

function makeSectionHeader(text) {
  const div = document.createElement("div");
  div.className = "section-header";
  div.textContent = text;
  return div;
}

const MAX_AUTHORS_SHOWN = 5;

function buildAuthorsDiv(paper) {
  const div = document.createElement("div");
  div.className = "paper-authors";
  const authors = paper.authors;
  const truncate = paper.local_match !== "strong" && authors.length > MAX_AUTHORS_SHOWN;

  if (!truncate) {
    div.innerHTML = authors.map((a) => highlightAuthor(a, paper.local_authors)).join(", ");
    return div;
  }

  const shownSpan = document.createElement("span");
  shownSpan.innerHTML = authors.slice(0, MAX_AUTHORS_SHOWN)
    .map((a) => highlightAuthor(a, paper.local_authors)).join(", ");

  const hiddenSpan = document.createElement("span");
  hiddenSpan.innerHTML = ", " + authors.slice(MAX_AUTHORS_SHOWN)
    .map((a) => highlightAuthor(a, paper.local_authors)).join(", ");
  hiddenSpan.hidden = true;

  const expandBtn = document.createElement("button");
  expandBtn.className = "author-expand-btn";
  expandBtn.textContent = ` … and ${authors.length - MAX_AUTHORS_SHOWN} more`;

  const collapseBtn = document.createElement("button");
  collapseBtn.className = "author-expand-btn";
  collapseBtn.textContent = " (collapse)";
  collapseBtn.hidden = true;

  expandBtn.addEventListener("click", () => {
    expandBtn.hidden = true;
    hiddenSpan.hidden = false;
    collapseBtn.hidden = false;
  });
  collapseBtn.addEventListener("click", () => {
    expandBtn.hidden = false;
    hiddenSpan.hidden = true;
    collapseBtn.hidden = true;
  });

  div.append(shownSpan, expandBtn, hiddenSpan, collapseBtn);
  return div;
}

function buildCard(paper) {
  const card = document.createElement("div");
  card.className = "paper-card";

  if (paper.local_match === "strong") card.classList.add("highlighted-strong");
  else if (paper.local_match === "weak") card.classList.add("highlighted-weak");
  if (paper.discussed_at) card.classList.add("discussed-paper");

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

  const discussedControl = buildDiscussedControl(paper);

  meta.append(idSpan, pdfLink, primaryBadge, secSpan, discussedControl);

  const titleDiv = document.createElement("div");
  titleDiv.className = "paper-title";
  const titleSpan = document.createElement("span");
  titleSpan.textContent = paper.title;
  titleDiv.appendChild(titleSpan);

  const authorsDiv = buildAuthorsDiv(paper);

  const toggleBtn = document.createElement("button");
  toggleBtn.className = "abstract-toggle";
  const startOpen = abstractMode === "all" ||
    (abstractMode === "strong" && paper.local_match === "strong");
  toggleBtn.textContent = startOpen ? "Hide abstract" : "Show abstract";

  function toggleAbstract() {
    const abs = card.querySelector(".paper-abstract");
    const open = abs.classList.toggle("open");
    toggleBtn.textContent = open ? "Hide abstract" : "Show abstract";
  }

  titleSpan.addEventListener("click", toggleAbstract);
  toggleBtn.addEventListener("click", toggleAbstract);

  const abstractDiv = document.createElement("div");
  abstractDiv.className = "paper-abstract" + (startOpen ? " open" : "");
  abstractDiv.textContent = paper.abstract;

  card.append(meta, titleDiv, authorsDiv, toggleBtn, abstractDiv);
  return card;
}

function buildDiscussedIssueUrl(paper) {
  const paperId = paper.id || paper.paper_id || "";
  const authors = Array.isArray(paper.authors) ? paper.authors.join("; ") : "";
  const title = `Discussed paper: ${paperId}`;
  const body = [
    `paper_id: ${paperId}`,
    `title: ${paper.title || ""}`,
    `arxiv_url: ${paper.arxiv_url || ""}`,
    `authors: ${authors}`,
  ].join("\n");

  const params = new URLSearchParams({
    title,
    body,
    labels: DISCUSSED_ISSUE_LABEL,
  });
  return `https://github.com/changgoo/astro-coffee-page/issues/new?${params.toString()}`;
}

function buildDiscussedControl(paper) {
  if (paper.discussed_at) {
    const badge = document.createElement("span");
    badge.className = "discussed-badge discussed-control";
    badge.textContent = "Discussed";
    badge.title = `Discussed on ${formatDate(paper.discussed_at)}`;
    return badge;
  }

  const button = document.createElement("button");
  button.className = "discussed-btn discussed-control";
  button.type = "button";
  button.textContent = "Mark as discussed";
  button.title = "Open a prefilled GitHub issue for this paper";
  button.addEventListener("click", () => {
    window.open(buildDiscussedIssueUrl(paper), "_blank", "noopener");
  });
  return button;
}

function buildDiscussedCard(paper) {
  const card = document.createElement("div");
  card.className = "paper-card";

  const meta = document.createElement("div");
  meta.className = "paper-meta";

  const idSpan = document.createElement("span");
  idSpan.className = "paper-id";
  idSpan.innerHTML = `[<a href="${paper.arxiv_url}" target="_blank" rel="noopener">${paper.paper_id}</a>]`;

  const pdfLink = document.createElement("a");
  pdfLink.className = "pdf-link";
  pdfLink.href = paper.arxiv_url ? paper.arxiv_url.replace("/abs/", "/pdf/") : "#";
  pdfLink.target = "_blank";
  pdfLink.rel = "noopener";
  pdfLink.textContent = "[PDF]";

  const discussed = document.createElement("span");
  discussed.className = "discussed-date";
  discussed.textContent = paper.discussed_at ? `Discussed ${formatUtcDate(paper.discussed_at)}` : "Discussed";

  meta.append(idSpan, pdfLink, discussed);

  const titleDiv = document.createElement("div");
  titleDiv.className = "paper-title";
  const titleSpan = document.createElement("span");
  titleSpan.textContent = paper.title || "";
  titleSpan.addEventListener("click", () => window.open(paper.arxiv_url, "_blank", "noopener"));
  titleDiv.appendChild(titleSpan);

  const authorsDiv = document.createElement("div");
  authorsDiv.className = "paper-authors";
  authorsDiv.textContent = Array.isArray(paper.authors) ? paper.authors.join(", ") : "";

  card.append(meta, titleDiv, authorsDiv);
  return card;
}

function formatUtcDate(ts) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function renderDiscussed() {
  const list = document.getElementById("paper-list");
  list.innerHTML = "";

  const papers = [...discussedPapers].sort((a, b) => {
    const dateCmp = (b.discussed_at || "").localeCompare(a.discussed_at || "");
    return dateCmp || (b.issue_number || 0) - (a.issue_number || 0);
  });

  document.getElementById("stats").textContent =
    `${papers.length} discussed paper${papers.length !== 1 ? "s" : ""}`;

  if (papers.length === 0) {
    list.innerHTML = `<div id="empty-state">No discussed papers yet.</div>`;
    return;
  }

  let currentDate = null;
  for (const paper of papers) {
    if (paper.discussed_at !== currentDate) {
      currentDate = paper.discussed_at;
      list.appendChild(makeSectionHeader(formatUtcDate(currentDate)));
    }
    list.appendChild(buildDiscussedCard(paper));
  }
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

function highlightAuthor(name, localAuthors) {
  const strength = localAuthors && localAuthors[name];
  if (strength === "strong") return `<span class="author-highlight-strong">${escHtml(name)}</span>`;
  if (strength === "weak")   return `<span class="author-highlight-weak">${escHtml(name)}</span>`;
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

  if (PAGE_MODE !== "discussed") {
    // ── Abstract mode ──
    document.querySelectorAll(".abstract-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        abstractMode = btn.dataset.abstract;
        localStorage.setItem("abstract-mode", abstractMode);
        syncSortUI();
        renderCurrent();
      });
    });

    // ── Sort order (asc / desc) ──
    document.querySelectorAll(".sort-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        sortOrder = btn.dataset.sortOrder;
        localStorage.setItem("sort-order", sortOrder);
        syncSortUI();
        renderCurrent();
      });
    });

    // ── Local-first axis (none / strong / strong+weak) ──
    document.querySelectorAll(".local-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        localFirst = btn.dataset.local;
        localStorage.setItem("local-first", localFirst);
        syncSortUI();
        renderCurrent();
      });
    });

    // ── Data source (today / previous listings) ──
    document.querySelectorAll(".source-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const newOffset = Number(btn.dataset.historyOffset);
        if (newOffset === historyOffset) return;
        historyOffset = newOffset;
        syncSortUI();

        searchQuery = "";
        document.getElementById("search-input").value = "";
        await loadDay(historyOffset);
      });
    });

    // ── Search ──
    const searchInput = document.getElementById("search-input");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        searchQuery = e.target.value.trim();
        renderCurrent();
      });
    }
  }

  init();
});
