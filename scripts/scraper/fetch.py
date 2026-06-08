"""API-first paper fetch orchestration with HTML fallback."""

import urllib.error

from .arxiv_api import fetch_latest_papers
from .arxiv_html import fetch_latest_papers_from_listing
from .config import FETCH_SIZE, MAX_PER_REQUEST


def fallback_listing_source(n):
    """Return the HTML listing source to use for fallback requests."""
    return "recent" if n > FETCH_SIZE else "new"


def fetch_latest_papers_with_fallback(n=FETCH_SIZE, include_listing_date=False, max_per_request=MAX_PER_REQUEST):
    """Fetch recent papers from the API, falling back to HTML listing on API throttling/errors."""
    try:
        return fetch_latest_papers(
            n=n,
            include_listing_date=include_listing_date,
            max_per_request=max_per_request,
            fetch_max_retries=0,
            fetch_timeout=10,
        )
    except urllib.error.HTTPError as e:
        if e.code not in {406, 429, 503}:
            raise
        print(f"  Falling back to arXiv HTML listing scrape after API HTTP {e.code}.", flush=True)
        return fetch_latest_papers_from_listing(
            n=n,
            include_listing_date=include_listing_date,
            source=fallback_listing_source(n),
        )
    except (TimeoutError, urllib.error.URLError) as e:
        print(f"  Falling back to arXiv HTML listing scrape after API {type(e).__name__}.", flush=True)
        return fetch_latest_papers_from_listing(
            n=n,
            include_listing_date=include_listing_date,
            source=fallback_listing_source(n),
        )
