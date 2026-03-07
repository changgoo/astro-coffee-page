# astro-ph Coffee Page

A daily arXiv astro-ph paper browser hosted on GitHub Pages.

## Features

- Daily arXiv astro-ph listings (all subcategories: GA, CO, EP, HE, IM, SR)
- Browse papers from the last 10 days
- Sort by arXiv order, first author, title, or category
- Filter by sub-category
- Highlight favorite authors

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

To run it manually: **Actions → Daily arXiv scrape → Run workflow**.

The Action needs write permission to commit data files. Go to:
**Settings → Actions → General → Workflow permissions** → select **Read and write permissions**.

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

Names are matched by last name (exact) then first name: an exact first-name match is a
**strong** match (bold amber highlight); a matching first initial only is a **weak**
match (italic grey highlight). Titles (Dr., Sir) and suffixes (Jr., III) are ignored.

## Local development

```bash
# Install dependencies for the author scraper
pip install -r requirements.txt

# Scrape a specific date (scrape.py has no pip dependencies)
python scripts/scrape.py 2025-03-05

# Update the author list from the Princeton Astro people page
python scripts/scrape_authors.py

# Serve locally
python -m http.server 8000
# Open http://localhost:8000
```

## Acknowledgment

Thank you to arXiv for use of its open access interoperability.
