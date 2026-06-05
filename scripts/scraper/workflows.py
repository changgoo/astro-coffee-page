"""Top-level scraper workflows used by the CLI."""

import json

from .authors import annotate_papers, load_favorite_authors
from .arxiv_html import fetch_latest_papers_from_listing
from .config import BOOTSTRAP_FETCH_SIZE, FETCH_SIZE, HISTORY_DAYS
from .discussed import annotate_discussed_papers, load_discussed_papers
from .fetch import fetch_latest_papers_with_fallback
from .history import (
    group_papers_by_listing_date,
    history_path,
    save_listing,
    update_history_for_date,
    update_index,
)
from .metadata import enrich_html_papers, papers_missing_abstract
from .paper import utc_now_iso


def load_annotation_context(repo_root, data_dir):
    """Load author and discussed-paper context for annotation."""
    return load_favorite_authors(repo_root), load_discussed_papers(data_dir)


def annotate_all(papers, fav_authors, discussed_papers=None):
    """Annotate papers with local-author and optional discussed metadata."""
    annotate_papers(papers, fav_authors)
    if discussed_papers is not None:
        annotate_discussed_papers(papers, discussed_papers)


def reannotate(data_dir, repo_root):
    """Re-run author tagging on rolling today*.json files without re-scraping."""
    fav_authors, discussed_papers = load_annotation_context(repo_root, data_dir)
    print(f"  {len(fav_authors)} favorites loaded.")
    now = utc_now_iso()

    for offset in range(HISTORY_DAYS + 1):
        path = history_path(data_dir, offset)
        if not path.exists():
            print(f"  {path.name} not found, skipping.")
            continue
        with open(path) as f:
            data = json.load(f)
        papers = data.get("papers", [])
        print(f"  Re-annotating {len(papers)} papers in {path.name} ...")
        annotate_all(papers, fav_authors, discussed_papers)
        data["papers"] = papers
        data["fetched_at"] = now
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Saved {path.name}.")


def bootstrap_history(data_dir, repo_root, api_enrich=False):
    """Seed today.json through today-5.json from arXiv's recent HTML listing."""
    print(f"Fetching latest {BOOTSTRAP_FETCH_SIZE} arXiv astro-ph papers from recent listing ...")
    fetched = fetch_latest_papers_from_listing(
        n=BOOTSTRAP_FETCH_SIZE,
        include_listing_date=True,
        source="recent",
    )
    if not fetched:
        print("  No papers fetched. Skipping.")
        return
    if papers_missing_abstract(fetched):
        enrich_html_papers(fetched, data_dir=data_dir, use_api=api_enrich)

    fav_authors, discussed_papers = load_annotation_context(repo_root, data_dir)
    print(f"  Annotating local author matches ({len(fav_authors)} favorites) ...")
    annotate_all(fetched, fav_authors, discussed_papers)

    groups = group_papers_by_listing_date(fetched)
    listing_dates = sorted(groups.keys(), reverse=True)
    if len(listing_dates) < HISTORY_DAYS + 1:
        print(f"  Warning: only found {len(listing_dates)} listing days in bootstrap fetch.")

    for offset, listing_date in enumerate(listing_dates[:HISTORY_DAYS + 1]):
        papers = groups[listing_date]
        save_listing(history_path(data_dir, offset), listing_date, papers, skip_unchanged=True)

    for offset in range(len(listing_dates[:HISTORY_DAYS + 1]), HISTORY_DAYS + 1):
        path = history_path(data_dir, offset)
        if path.exists():
            path.unlink()

    update_index(data_dir)
    print("Done.")


def run_scrape(data_dir, repo_root, arxiv_date, explicit_date=False, bootstrap_n=None, api_enrich=False):
    """Run the normal scrape workflow for one target listing date."""
    print(f"Fetching latest {FETCH_SIZE} arXiv astro-ph papers ...")
    fetched = fetch_latest_papers_with_fallback(n=FETCH_SIZE, include_listing_date=True)
    if not fetched:
        print("  No papers fetched. Skipping.")
        return
    if papers_missing_abstract(fetched):
        enrich_html_papers(fetched, data_dir=data_dir, use_api=api_enrich)

    print(f"  Fetched {len(fetched)} papers.")

    fav_authors, discussed_papers = load_annotation_context(repo_root, data_dir)
    print(f"  Annotating local author matches ({len(fav_authors)} favorites) ...")
    annotate_papers(fetched, fav_authors)

    grouped = group_papers_by_listing_date(fetched)
    if not explicit_date and grouped:
        if arxiv_date not in grouped:
            fetched_date = max(grouped.keys())
            print(f"  Using fetched arXiv listing date {fetched_date} instead of clock estimate {arxiv_date}.")
            arxiv_date = fetched_date
    target_papers = grouped.get(arxiv_date, [])
    if not target_papers:
        print(f"  No fetched papers matched arXiv date {arxiv_date}. Skipping.")
        return

    new_count = update_history_for_date(
        data_dir,
        arxiv_date,
        target_papers,
        bootstrap_n=bootstrap_n,
        discussed_papers=discussed_papers,
    )
    if new_count == 0:
        return
    update_index(data_dir)
    print("Done.")
