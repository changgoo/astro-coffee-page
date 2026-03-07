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
let currentSort = "local";
let availableDates = [];
let currentDate = null;
let localTenDayMode = false;

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
  // Merge, deduplicating by name (manual entries take precedence / come first)
  const seen = new Set();
  favoriteAuthors = [...manual, ...auto].filter((name) => {
    if (seen.has(name)) return false;
    seen.add(name);
    return true;
  });
}

async function loadAllDays() {
  document.getElementById("loading").style.display = "block";
  document.getElementById("paper-list").innerHTML = "";
  document.getElementById("stats").textContent = "";
  document.getElementById("fetched-at").textContent = "";

  try {
    // Load live days (filter to strong matches)
    const liveResults = await Promise.all(
      availableDates.map(async (d) => {
        const res = await fetch(`data/${d}.json`);
        if (!res.ok) return { date: d, papers: [] };
        const data = await res.json();
        const raw = data.papers || [];
        return { date: d, papers: raw.map((p, i) => ({ ...p, _arxivIndex: raw.length - i })) };
      })
    );
    const livePapers = liveResults.flatMap(({ date, papers }) =>
      papers
        .filter((p) => bestMatchStrength(p) === "strong")
        .map((p) => ({ ...p, _date: date }))
    );

    // Load archived strong-match papers
    let archivedPapers = [];
    try {
      const archRes = await fetch("data/local-archive.json");
      if (archRes.ok) {
        const archData = await archRes.json();
        // archData is { "YYYY-MM-DD": [...papers], ... }
        for (const [date, papers] of Object.entries(archData)) {
          papers.forEach((p, i) => {
            archivedPapers.push({ ...p, _date: date, _arxivIndex: papers.length - i });
          });
        }
      }
    } catch { /* archive not yet created — ignore */ }

    // Merge: live dates take precedence; skip archived dates already in live index
    const liveDates = new Set(availableDates);
    archivedPapers = archivedPapers.filter((p) => !liveDates.has(p._date));

    allPapers = [...livePapers, ...archivedPapers];
  } catch (e) {
    allPapers = [];
    showEmptyState("Could not load data.");
  } finally {
    document.getElementById("loading").style.display = "none";
  }

  renderAllDays();
}

function renderAllDays() {
  const list = document.getElementById("paper-list");
  list.innerHTML = "";

  // Group by date
  const byDate = {};
  for (const paper of allPapers) {
    (byDate[paper._date] = byDate[paper._date] || []).push(paper);
  }

  // All dates across live + archive, sorted descending
  const allDates = Object.keys(byDate).sort((a, b) => b.localeCompare(a));

  let total = 0;
  for (const date of allDates) {
    const papers = byDate[date];
    if (!papers || papers.length === 0) continue;
    total += papers.length;

    const header = document.createElement("div");
    header.className = "date-section-header";
    header.textContent = formatDate(date);
    list.appendChild(header);

    papers.forEach((paper) => list.appendChild(buildCard(paper)));
  }

  document.getElementById("stats").textContent =
    total === 0 ? "No strong local author matches found."
                : `${total} papers with strong local author matches across ${allDates.length} days`;
}

async function loadDay(dateStr) {
  document.getElementById("loading").style.display = "block";
  document.getElementById("paper-list").innerHTML = "";
  document.getElementById("stats").textContent = "";


  try {
    const res = await fetch(`data/${dateStr}.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // Papers are stored newest-first; arXiv listing number 1 = earliest submission.
    const raw = data.papers || [];
    allPapers = raw.map((p, i) => ({ ...p, _arxivIndex: raw.length - i }));
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

// ── Name matching ─────────────────────────────────────────────────────────────

const NAME_SUFFIXES = new Set(["iii", "ii", "iv", "jr.", "jr", "sr.", "sr"]);
const NAME_TITLES   = new Set(["sir", "dr.", "dr", "prof.", "prof"]);

/**
 * Parse a name into {first, last, middleInitial} components, handling two formats:
 *   "Last, First [Middle]"  (arXiv)
 *   "[Title] First [Middle] Last [Suffix]"  (Princeton people page)
 * Returns lowercase, dot-stripped first name, lowercase last name, and the
 * first character of the middle token (or null if absent).
 */
function parseNameParts(name) {
  if (name.includes(",")) {
    // arXiv format: "Last, First [Middle...]"
    const comma = name.indexOf(",");
    const last   = name.slice(0, comma).trim().toLowerCase();
    const rest   = name.slice(comma + 1).trim().split(/\s+/);
    const first  = rest[0].replace(/\./g, "").toLowerCase();
    const middleInitial = rest.length > 1 ? rest[1].replace(/\./g, "").toLowerCase()[0] : null;
    return { first, last, middleInitial };
  }
  // Princeton format: strip leading titles and trailing suffixes, then
  // first token = first name, middle token (if any) = middle, last token = last name.
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

/**
 * Compare a favorite name (Princeton format) against an arXiv author name.
 * Returns "strong" (last + first match, or last + first & middle initial match),
 * "weak" (last + first initial match), or null (last name mismatch).
 */
function matchAuthor(favName, arxivName) {
  const fav = parseNameParts(favName);
  const arx = parseNameParts(arxivName);
  if (fav.last !== arx.last) return null;
  if (fav.first === arx.first) return "strong";
  if (fav.first[0] === arx.first[0]) {
    // Upgrade to strong when both names carry a middle initial and they agree
    if (fav.middleInitial && arx.middleInitial && fav.middleInitial === arx.middleInitial)
      return "strong";
    return "weak";
  }
  return null;
}

/** Return the best match strength ("strong" | "weak" | null) across all authors. */
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

function hasLocalAuthor(paper) {
  return bestMatchStrength(paper) !== null;
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
    copy.sort((a, b) => {
      const aFirst = a.authors[0] || "";
      const bFirst = b.authors[0] || "";
      return aFirst.localeCompare(bFirst);
    });
  } else if (mode === "category") {
    copy.sort((a, b) => (a.primary_category || "").localeCompare(b.primary_category || ""));
  } else if (mode === "local") {
    // strong matches first, then weak, then the rest; arXiv order as tiebreaker
    const rank = { "strong": 0, "weak": 1, null: 2 };
    copy.sort((a, b) =>
      rank[bestMatchStrength(a)] - rank[bestMatchStrength(b)] ||
      (a._arxivIndex || 0) - (b._arxivIndex || 0)
    );
  }
  return copy;
}

function buildCard(paper, idx) {
  const card = document.createElement("div");
  card.className = "paper-card";

  const strength = bestMatchStrength(paper);
  if (strength === "strong") card.classList.add("highlighted-strong");
  else if (strength === "weak") card.classList.add("highlighted-weak");

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

  // Restore saved state (default: collapsed)
  setAnnouncement(localStorage.getItem(ANN_KEY) === "1");

  annToggle.addEventListener("click", () => {
    setAnnouncement(annBody.hidden);
  });

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

  document.getElementById("btn-local-10").addEventListener("click", async () => {
    localTenDayMode = !localTenDayMode;
    const btn = document.getElementById("btn-local-10");
    const navEls = [
      document.getElementById("btn-prev"),
      document.getElementById("date-select"),
      document.getElementById("btn-next"),
      document.getElementById("btn-today"),
    ];
    if (localTenDayMode) {
      btn.classList.add("active");
      navEls.forEach((el) => { el.disabled = true; el.style.opacity = "0.4"; });
      await loadAllDays();
    } else {
      btn.classList.remove("active");
      navEls.forEach((el) => { el.disabled = false; el.style.opacity = ""; });
      // Restore nav button disabled state based on position
      updateNavButtons();
      await loadDay(currentDate);
    }
  });

  document.getElementById("btn-today").addEventListener("click", async () => {
    if (availableDates.length === 0) return;
    currentDate = availableDates[0];
    document.getElementById("date-select").value = currentDate;
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
