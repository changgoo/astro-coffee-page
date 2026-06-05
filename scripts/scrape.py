#!/usr/bin/env python3
# ruff: noqa: F401
"""Compatibility entrypoint for the arXiv astro-ph scraper."""

from scraper import arxiv_api as _arxiv_api
from scraper.archive import (
    archive_db_path,
    archive_dir,
    archive_listing,
    archive_papers,
    ensure_archive_schema,
    make_search_text,
    update_archive_index,
)
from scraper.arxiv_api import build_query_url, fetch_latest_papers, fetch_xml, parse_entry
from scraper.arxiv_html import (
    ArxivListingParser,
    build_listing_url,
    fetch_html,
    fetch_latest_papers_from_listing,
    listing_show_size,
    parse_listing_date_heading,
    parse_listing_html,
)
from scraper.authors import annotate_papers, load_favorite_authors, match_author, parse_name_parts
from scraper.cli import main
from scraper.config import (
    ARCHIVE_DIR,
    BASE_URL,
    BOOTSTRAP_FETCH_SIZE,
    FETCH_SIZE,
    HISTORY_DAYS,
    LISTING_SHOW_SIZES,
    MAX_PER_REQUEST,
    NEW_LISTING_URL,
    NS,
    NY_TZ,
    RATE_LIMIT_SECONDS,
    RECENT_LISTING_URL,
)
from scraper.dates import get_target_date, listing_date_for_published, next_business_day, prev_business_day
from scraper.discussed import annotate_discussed_papers, load_discussed_papers
from scraper.fetch import fallback_listing_source, fetch_latest_papers_with_fallback
from scraper.history import (
    collect_history_ids,
    group_papers_by_listing_date,
    history_filename,
    history_offsets,
    history_path,
    load_history,
    load_listing,
    rotate_history,
    save_listing,
    select_new_papers,
    strip_internal_fields,
    update_history_for_date,
    update_index,
)
from scraper.paper import make_paper, normalize_text, sort_categories, utc_now_iso, utc_today
from scraper.workflows import annotate_all, bootstrap_history, load_annotation_context, reannotate, run_scrape

# Backward-compatible test monkeypatch target: fetch_xml uses this same module object.
time = _arxiv_api.time


if __name__ == "__main__":
    main()
