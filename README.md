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

The workflow in `.github/workflows/daily-scrape.yml` runs automatically Mon–Fri at 15:30 UTC.

To run it manually: **Actions → Daily arXiv scrape → Run workflow**.

The Action needs write permission to commit data files. Go to:
**Settings → Actions → General → Workflow permissions** → select **Read and write permissions**.

### 4. Populate the author list

Run the Princeton Astronomy people scraper to populate `config/authors.json` automatically:

```bash
pip install -r requirements.txt
python scripts/scrape_authors.py
```

This scrapes Faculty & Research Scholars, Postdoctoral Researchers, and Graduate Students
from `web.astro.princeton.edu/people`. To preview without writing, use `--dry-run`:

```bash
python scripts/scrape_authors.py --dry-run
```

To adapt for a different institution, edit the `PAGES` list and CSS selectors in
`scripts/scrape_authors.py`.

You can also edit `config/authors.json` directly. Names are matched case-insensitively
as substrings of the full author name as it appears on arXiv.

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
