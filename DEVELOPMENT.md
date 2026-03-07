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

## Planned / open issues

| # | Title |
|---|-------|
| [#7](https://github.com/changgoo/astro-coffee-page/issues/7) | Globally persistent discussed papers list |

Ideas under consideration:
- **Search bar** — real-time filter across title, authors, and abstract
- **Discussed papers** — per-session marking via `localStorage` as a first step; global persistence (shared across all users) requires a write mechanism (options: manual `data/discussed.json` in the repo, GitHub Actions `workflow_dispatch`, or an external free-tier backend such as Supabase)
