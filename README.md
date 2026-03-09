# astro-ph Coffee Page

A daily arXiv astro-ph paper browser hosted on GitHub Pages.

## Features

- Daily arXiv astro-ph listings (all subcategories: GA, CO, EP, HE, IM, SR)
- Sequential arXiv listing numbers [1]…[N] matching `arxiv.org/list/astro-ph/new`, with cross-listings labelled and numbered continuously
- Sort by local authors first, arXiv order, first author, title, or category
- Filter by sub-category
- Highlight Princeton authors (strong: bold amber; weak: italic pale yellow)
- **Archive view** — browse the 1000 most recent astro-ph papers with full-text search (title + author) and 100-paper paginated loading
- Author match strength (`local_match`, `local_authors`) precomputed during scraping — no client-side name matching
- **Font size control** — S / M / L buttons scale all paper content; persisted across sessions
- **Abstract expand mode** — collapsed (default), local strong authors open, or all open; persisted across sessions
- **Author truncation** — long author lists collapsed to 5 with expand toggle; strong-match papers always show full list

## Setup

### 1. Create a GitHub repository and push this code

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/coffee-page.git
git push -u origin main
```

### 2. Enable GitHub Pages

In your repository → **Settings → Pages**:
- Source: **Deploy from a branch**
- Branch: `main`, folder: `/ (root)`

### 3. Enable the GitHub Action

The workflow in `.github/workflows/daily-scrape.yml` runs on the following schedule,
timed around arXiv's ~8 PM ET daily announcement:

| Runs | ET time | Days |
|------|---------|------|
| Hourly ×4 | 9 PM, 10 PM, 11 PM, midnight | Sun–Thu nights |
| Once | 6 AM | Mon–Fri mornings |

> **Note:** Times above assume EST (UTC−5). During EDT (UTC−4, mid-March to early
> November) all night runs fire 1 hour earlier ET (8 PM–11 PM).

To run it manually: **Actions → Daily arXiv scrape → Run workflow** (no inputs required).

The Action pushes data commits directly to the protected `main` branch using an SSH deploy key. Set it up once:

1. Generate a key pair (no passphrase): `ssh-keygen -t ed25519 -C "astro-coffee-scraper" -f deploy_key -N ""`
2. Add `deploy_key.pub` as a deploy key with **write access** — repo **Settings → Deploy keys → Add deploy key**
3. Add the private key `deploy_key` as a repository secret named `SCRAPER_DEPLOY_KEY` — repo **Settings → Secrets → Actions → New repository secret**
4. Delete both local key files
5. Add **Deploy keys** as a bypass actor in your branch ruleset — repo **Settings → Rules → (ruleset) → Bypass list**

### 4. Populate the author list

There are two author list files:

| File | Purpose |
|------|---------|
| `config/authors.json` | Auto-populated by scraping the department people page. **Do not edit by hand** — it is overwritten monthly by the GitHub Action. |
| `config/authors_manual.json` | Hand-curated additions (collaborators, alumni, etc.). Never overwritten automatically. |

Both files are loaded at page load and merged (manual entries take precedence).

**Automatic updates** — the workflow in `.github/workflows/monthly-authors.yml` re-scrapes
the Princeton Astronomy people page on the 1st of every month and commits the result to
`config/authors.json`. It can also be triggered manually via **Actions → Monthly author
list update → Run workflow**.

**Manual additions** — edit `config/authors_manual.json` directly:

```json
{
  "authors": [
    "Vera Rubin",
    "Jan Oort"
  ]
}
```

**Initial setup** — run the scraper locally to seed `config/authors.json` before the
first monthly Action fires:

```bash
pip install -r requirements.txt
python scripts/scrape_authors.py
```

To adapt for a different institution, edit the `PAGES` list and CSS selectors in
`scripts/scrape_authors.py`. Use `--dry-run` to preview without writing.

Names are matched by last name (exact) then first name. **Strong** match (bold amber): exact first name, hyphenated initials matching a hyphenated first name (`C.-G.` == `Chang-Goo`), or first + middle initial both match (`M. W.` == `Matthew W.`). **Weak** match (italic grey): first initial only against a non-hyphenated fav name. **No match**: single initial against a hyphenated fav name (`C. Kim` vs `Chang-Goo Kim`), arXiv provides a middle initial the fav lacks (`G. A. Livadiotis` vs `George Livadiotis`), or conflicting middle initials (`M. A. Kunz` vs `Matthew W. Kunz`). To get a strong match for someone who publishes under an abbreviated name, add that form to `config/authors_manual.json` (e.g. `"G. Livadiotis"`). Titles (Dr., Sir) and suffixes (Jr., III) are ignored.

## Local development

```bash
# Install dependencies for the author scraper
pip install -r requirements.txt

# First-time setup: seed archive.json and today's listing
# N = number of papers in today's arXiv listing (check arxiv.org/list/astro-ph/new)
python scripts/scrape.py --bootstrap N

# Subsequent runs (automated by GitHub Action): diff vs archive
python scripts/scrape.py

# Scrape a specific date manually
python scripts/scrape.py 2026-03-06

# Update the author list from the Princeton Astro people page
python scripts/scrape_authors.py

# Serve locally
python -m http.server 8000
# Open http://localhost:8000
```

## Acknowledgment

Thank you to arXiv for use of its open access interoperability.
