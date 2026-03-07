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

### 4. Add favorite authors

Edit `config/authors.json`:

```json
{
  "authors": [
    "Chang-Goo Kim",
    "Eve Ostriker"
  ]
}
```

Names are matched case-insensitively as substrings of the full author name.

## Local development

```bash
# Scrape a specific date
python scripts/scrape.py 2025-03-05

# Serve locally
python -m http.server 8000
# Open http://localhost:8000
```

## Acknowledgment

Thank you to arXiv for use of its open access interoperability.
