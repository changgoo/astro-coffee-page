# Development History

This document summarizes the features built for the astro coffee page, in the order they were added.

---

## 1. Initial setup

**Branch:** `main` (initial commit)

- `scripts/scrape.py` — queries the arXiv Atom XML API for all `astro-ph.*` papers on a given date, paginates with a 3 s rate-limit delay, and writes `data/YYYY-MM-DD.json`
- `data/index.json` — manifest of available dates (max 10 days); older files are pruned automatically
- `index.html` + `app.js` + `style.css` — static frontend served by GitHub Pages
  - Date navigator (prev/next/dropdown)
  - Sort by arXiv order, first author, title, or category
  - Category filter buttons (GA, CO, EP, HE, IM, SR)
  - Collapsible abstracts
- `.github/workflows/daily-scrape.yml` — GitHub Action that runs the scraper and commits updated data

---

## 2. Local author highlighting

- `scripts/scrape_authors.py` — scrapes the Princeton Astronomy people page (Faculty, Postdocs, Grad Students) using `cloudscraper` + `beautifulsoup4` to bypass Cloudflare; writes `config/authors.json`
- Smart name matching in `app.js`:
  - Handles both arXiv format (`"Last, First"`) and Princeton format (`"First Last"`)
  - Strips honorific titles (Dr., Prof.) and name suffixes (Jr., III)
  - **Strong match**: last name + exact first name, or last name + first initial + agreeing middle initial
  - **Weak match**: last name + first initial only
- Strong matches: bold amber highlight; weak matches: italic pale yellow
- Default sort order: strong matches first, then weak, then arXiv order

---

## 3. Unit tests and CI

- `tests/test_scrape.py` — 43 tests covering `build_query_url`, `get_target_date`, `parse_entry`, `update_index`, `parse_name_parts`, `has_strong_local_author`, `load_favorite_authors`, `archive_strong_papers`, and skip-unchanged logic
- `tests/test_scrape_authors.py` — 7 tests covering the Princeton people scraper
- `TESTS.md` — describes the test suite
- `.github/workflows/tests.yml` — runs `ruff check` + `pytest` on every PR and push to `main`

---

## 4. Scrape schedule

`.github/workflows/daily-scrape.yml` schedule:

| Runs | ET time | Days |
|------|---------|------|
| Hourly x4 | 9 PM, 10 PM, 11 PM, midnight | Sun–Thu nights |
| Once | 6 AM | Mon–Fri mornings |

The nightly runs catch arXiv's ~8 PM ET announcement; the morning run picks up any delayed updates.

---

## 5. Header navigation

- Princeton shield linking to `web.astro.princeton.edu`
- AstroCoffee calendar link (`changgoo.github.io/AstroCoffee/intro.html`)
- arXiv favicon linking to `/list/astro-ph/new`
- GitHub icon linking to the repository
- Date navigator: Older / dropdown / **Today** / Newer

---

## 6. Dual author lists (PR #2)

| File | Purpose |
|------|---------|
| `config/authors.json` | Auto-scraped monthly from the Princeton people page. Never edit by hand. |
| `config/authors_manual.json` | Hand-curated additions (collaborators, alumni, visitors). Never overwritten. |

Both files are fetched at page load and merged (manual entries take precedence). The monthly update is handled by `.github/workflows/monthly-authors.yml`.

---

## 7. Data backfill (PR #1)

- Ran `scripts/scrape.py` for each of the last 10 weekdays to seed `data/` before the first scheduled Action fired.

---

## 8. 10-day local author view (PR #3)

- **"Local authors (10 days)"** toolbar button fetches all available day files in parallel, filters for strong local author matches, and renders them grouped by date section headers.
- Date nav controls are disabled while this view is active.
- Expanded in PR #5 to also include archived strong-match papers (see below).

---

## 9. Today button (PR #4)

- **"Today"** button in the date navigator jumps directly to the most recent available date.

---

## 10. Smarter scraping (PR #5)

Two improvements to `scripts/scrape.py`:

**Skip unchanged runs** — after fetching, compare the new paper count against the existing file. If the count has not increased, skip writing and exit early. The workflow's existing `git diff --cached --quiet` guard prevents an empty commit either way.

**Archive strong matches on prune** — when a date ages out of the 10-day window, strong local author match papers are extracted into `data/local-archive.json` (keyed by date) before the full day file is deleted. Dates with no strong matches are deleted without archiving.

The frontend's local author view loads from both `data/index.json` and `data/local-archive.json`, so strong matches accumulate indefinitely.

---

## 11. Announcement banner (PR #6)

- Collapsible **"Welcome to Astro-Coffee@Princeton!"** card at the top of the main content column.
- Contains the department meeting description, expectations list, community conduct link, contact email, and a GitHub issue link.
- Collapsed by default; open/closed state persisted in `localStorage`.

---

## 12. Correct arXiv listing date and submission window (PR #9)

Three interrelated fixes to `scripts/scrape.py`:

**Correct listing date** — `get_target_date()` now returns the arXiv announcement date (e.g. Friday for papers announced Thursday night). Rule: `prev_business_day(today ET)` after 14:00 ET, else `prev_business_day(yesterday ET)`.

**Separate listing date from query date** — the filename/index use the listing date (what users see on arXiv), while the API query uses the submission window.

**Exact UTC submission window** — replaces the single-day date query with `get_submission_window()`, which returns the precise window in UTC:

| Listing date | Submission window (ET) | Submission window (UTC) |
|---|---|---|
| Tuesday | Fri 14:00 – Mon 14:00 | Fri 19:00 – Mon 18:59:59 |
| Wednesday | Mon 14:00 – Tue 14:00 | Mon 19:00 – Tue 18:59:59 |
| Thursday | Tue 14:00 – Wed 14:00 | Tue 19:00 – Wed 18:59:59 |
| Friday | Wed 14:00 – Thu 14:00 | Wed 19:00 – Thu 18:59:59 |
| Monday | Thu 14:00 – Fri 14:00 | Thu 19:00 – Fri 18:59:59 |

The arXiv API's `submittedDate` field is in UTC; arXiv uses EST (UTC−5) year-round with no DST adjustment for its 14:00 ET cutoff.

Two new sort options replace the old ambiguous "Default (arXiv order)":
- **arXiv order (earliest first)** — earliest submissions at top
- **Reverse arXiv order (latest first)** — newest submissions at top

---

## 13. Diff-based listing, archive view, and arXiv numbering (PR #12, closes #10)

**Motivation:** The date-window API query from PR #9 still caused mismatches with arXiv's published listing — wrong paper set and no separation of new submissions vs. cross-listings.

### Scraping — diff-based approach

`scripts/scrape.py` now uses a snapshot-diff strategy instead of a date-window query:

1. **Fetch** the 1000 most recently submitted `astro-ph.*` papers from the arXiv API (no date filter, sorted by `submittedDate` descending).
2. **Diff** against `data/archive.json` (the previous 1000-paper snapshot). Papers in the new fetch but not in the archive are the day's new listings.
3. **Save** new papers to `data/YYYY-MM-DD.json` and update `data/archive.json`.
4. **`data/index.json`** simplified to `{"current": "YYYY-MM-DD"}` — no more 10-date array.

**Bootstrap mode** (`--bootstrap N`): for the first run, seeds today's listing with the top N papers sorted by arXiv ID descending (more stable than `submittedDate` for window alignment). Used when `archive.json` does not yet exist.

### Author matching precomputed in scraper

Name matching against the favorites list is now done entirely in Python at scrape time. Each paper in the JSON carries:

- `local_match`: `"strong"` | `"weak"` | `null` — best match strength across all authors
- `local_authors`: `{arxiv_name: "strong"|"weak"}` — per-author match results

The frontend reads these fields directly, eliminating all client-side string comparison against 179 favorites. Sorting, highlighting, and archive search are now O(1) lookups.

### Frontend changes

- **Removed:** date dropdown, Older/Newer/Today navigation, "Local authors (10 days)" button, all JS name-matching code (`parseNameParts`, `matchAuthor`, `bestMatchStrength`, `loadAuthors`).
- **Added:** Archive button — loads `data/archive.json` (1000 papers) with a text search bar (searches title + author across all 1000), 100-paper paginated "Load more", and sort/filter controls.
- **arXiv numbering:** today's listing shows `[1]…[N]` matching `arxiv.org/list/astro-ph/new`. New submissions are numbered sequentially by arXiv ID ascending; cross-listings continue the count.
- **Cross-listings:** in arXiv order sort, a "Cross-listings (N)" section divider separates papers whose primary category is not `astro-ph.*`.
- **Category badge colors** applied via a JS `CAT_COLORS` map (inline style) — avoids unreliable CSS class-name-with-dots escaping.

### Author scraper

Added `Associated Faculty & Department Affiliates` page to `scripts/scrape_authors.py`. Author list grew from 146 to 168 names.

---

## 14. Reader preferences: font size, abstract mode, author truncation (PR #13)

Three UI quality-of-life improvements to `app.js`, `index.html`, and `style.css`:

**Font size buttons (S / M / L)** — three buttons in the toolbar cycle the base font size between 13 px (S), 15 px (M, default), and 17 px (L). Paper card content (`paper-title`, `paper-authors`, `paper-abstract`, and all meta spans) uses `em` units so it scales with the body font size. The active size is highlighted and persisted in `localStorage`.

**Abstract expand mode** — a select next to the sort control offers three modes:
- *Collapsed* (default) — all abstracts hidden, click to open individually
- *Local (strong) open* — abstracts for strong-match Princeton author papers open automatically
- *All open* — every abstract expanded on page load

The selected mode is persisted in `localStorage` and applied on every render.

**Author list truncation** — papers with more than 5 authors show the first 5 followed by a "… and N more" link; clicking expands to the full list, with a "(collapse)" link to shrink it back. Strong-match papers always show the full author list so no highlighted name is hidden.

**Stronger author matching** — two additional cases now qualify as strong matches in `scripts/scrape.py`:
- *Single first initial in paper* — `"Kim, C."` matches `"Chang-Goo Kim"` as strong (previously weak)
- *Hyphenated first name initials* — `"Kim, C.-G."` and `"Kim, C.G."` both match `"Chang-Goo Kim"` as strong

---

## Planned / open issues

| # | Title |
|---|-------|
| [#7](https://github.com/changgoo/astro-coffee-page/issues/7) | Globally persistent discussed papers list |

Ideas under consideration:
- **Discussed papers** — per-session marking via `localStorage` as a first step; global persistence (shared across all users) requires a write mechanism (options: manual `data/discussed.json` in the repo, GitHub Actions `workflow_dispatch`, or an external free-tier backend such as Supabase)
