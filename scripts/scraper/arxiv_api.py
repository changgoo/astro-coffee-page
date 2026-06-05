"""arXiv Atom API fetching and parsing."""

import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET

from .config import BASE_URL, FETCH_SIZE, MAX_PER_REQUEST, NS, RATE_LIMIT_SECONDS
from .dates import listing_date_for_published
from .http import fetch_bytes
from .paper import make_paper


def build_query_url(start=0, max_results=MAX_PER_REQUEST):
    """Build the arXiv API query URL for the most recent astro-ph papers."""
    params = (
        f"search_query=cat:astro-ph.*"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&start={start}&max_results={max_results}"
    )
    return f"{BASE_URL}?{params}"


def build_id_list_url(ids):
    """Build an arXiv API URL for an explicit list of arXiv IDs."""
    params = urllib.parse.urlencode({
        "id_list": ",".join(ids),
        "max_results": len(ids),
    })
    return f"{BASE_URL}?{params}"


def fetch_xml(url, max_retries=5, base_delay=10, timeout=60):
    """Fetch a URL and return raw bytes, retrying on transient errors."""
    for attempt in range(max_retries + 1):
        try:
            return fetch_bytes(url, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("  HTTP 429 Too Many Requests from arXiv; not retrying.", flush=True)
                raise
            if e.code == 503 and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"  HTTP {e.code}, retrying in {delay}s (attempt {attempt + 1}/{max_retries}) ...", flush=True)
                time.sleep(delay)
            else:
                raise
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"  {type(e).__name__}: {e}, retrying in {delay}s (attempt {attempt + 1}/{max_retries}) ...", flush=True)
                time.sleep(delay)
            else:
                raise


def parse_entry(entry, include_listing_date=False):
    """Parse a single Atom <entry> element into a paper dict."""
    def find_text(tag, ns_key="atom"):
        el = entry.find(f"{ns_key}:{tag}", NS)
        return el.text.strip() if el is not None and el.text else ""

    id_url = find_text("id")
    arxiv_id = id_url.rstrip("/").split("/abs/")[-1].split("v")[0]
    published = find_text("published")

    authors = [
        author.find("atom:name", NS).text.strip()
        for author in entry.findall("atom:author", NS)
        if author.find("atom:name", NS) is not None
    ]

    primary_cat_el = entry.find("arxiv:primary_category", NS)
    primary_category = primary_cat_el.get("term", "") if primary_cat_el is not None else ""
    categories = [cat.get("term", "") for cat in entry.findall("atom:category", NS)]
    listing_date = listing_date_for_published(published) if include_listing_date else None

    return make_paper(
        arxiv_id=arxiv_id,
        title=find_text("title"),
        authors=authors,
        abstract=find_text("summary"),
        primary_category=primary_category,
        categories=categories,
        submitted=published[:10],
        listing_date=listing_date,
    )


def fetch_latest_papers(
    n=FETCH_SIZE,
    include_listing_date=False,
    max_per_request=MAX_PER_REQUEST,
    fetch_max_retries=5,
    fetch_timeout=60,
):
    """Fetch the n most recently submitted astro-ph papers from the arXiv API."""
    papers = []
    start = 0
    total = None

    while start < n:
        max_results = min(max_per_request, n - start)
        url = build_query_url(start=start, max_results=max_results)
        print(f"  Fetching start={start} ...", flush=True)
        raw = fetch_xml(url, max_retries=fetch_max_retries, timeout=fetch_timeout)
        root = ET.fromstring(raw)

        if total is None:
            total_el = root.find("opensearch:totalResults", NS)
            total = int(total_el.text) if total_el is not None else 0
            print(f"  Total available: {total}")

        entries = root.findall("atom:entry", NS)
        if not entries:
            break

        for entry in entries:
            papers.append(parse_entry(entry, include_listing_date=include_listing_date))

        start += len(entries)
        if start >= min(total, n):
            break

        time.sleep(RATE_LIMIT_SECONDS)

    return papers


def fetch_papers_by_ids(ids, include_listing_date=False, fetch_max_retries=0, fetch_timeout=10):
    """Fetch paper metadata for explicit arXiv IDs from the arXiv API."""
    if not ids:
        return []

    url = build_id_list_url(ids)
    raw = fetch_xml(url, max_retries=fetch_max_retries, timeout=fetch_timeout)
    root = ET.fromstring(raw)
    entries = root.findall("atom:entry", NS)
    return [parse_entry(entry, include_listing_date=include_listing_date) for entry in entries]
