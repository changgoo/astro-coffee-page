"""Shared paper-shape helpers for API and HTML arXiv sources."""

from datetime import datetime, timezone


def normalize_text(value):
    """Collapse runs of whitespace in scraped text."""
    return " ".join(value.split())


def utc_now_iso():
    """Return the current UTC time in scraper JSON timestamp format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_today():
    """Return today's UTC date in YYYY-MM-DD format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sort_categories(primary_category, categories):
    """Return unique categories with the primary category first."""
    unique = {category for category in categories if category}
    return sorted(unique, key=lambda c: (c != primary_category, c))


def make_paper(
    arxiv_id,
    title,
    authors,
    abstract,
    primary_category,
    categories,
    submitted,
    listing_date=None,
    pdf_url=None,
):
    """Build the standard paper dictionary used by the scraper."""
    paper = {
        "id": arxiv_id,
        "title": normalize_text(title),
        "authors": authors,
        "abstract": normalize_text(abstract),
        "primary_category": primary_category,
        "categories": sort_categories(primary_category, categories),
        "submitted": submitted,
        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
    }
    if listing_date:
        paper["_listing_date"] = listing_date
    return paper
