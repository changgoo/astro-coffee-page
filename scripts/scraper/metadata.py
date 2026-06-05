"""Metadata enrichment for papers scraped from arXiv HTML listings."""

import json
import sqlite3
import urllib.error

from .archive import archive_dir
from .arxiv_api import fetch_papers_by_ids
from .history import history_offsets, history_path

FILL_FIELDS = (
    "title",
    "authors",
    "abstract",
    "primary_category",
    "categories",
    "submitted",
    "arxiv_url",
    "pdf_url",
)
API_METADATA_TIMEOUT = 60


def _has_value(value):
    """Return True when value contains useful metadata."""
    return bool(value)


def merge_missing_metadata(paper, source):
    """Fill empty metadata fields on paper from source, preserving listing date."""
    for field in FILL_FIELDS:
        if not _has_value(paper.get(field)) and _has_value(source.get(field)):
            paper[field] = source[field]


def load_known_metadata(data_dir):
    """Load known paper metadata from retained JSON listings and archive DBs."""
    known = {}

    for offset in history_offsets():
        path = history_path(data_dir, offset)
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for paper in data.get("papers", []):
            paper_id = paper.get("id")
            if paper_id:
                known[paper_id] = paper

    directory = archive_dir(data_dir)
    for db_path in sorted(directory.glob("*.sqlite")):
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, listing_date, submitted, title, authors_json, abstract,
                       primary_category, categories_json, arxiv_url, pdf_url
                FROM papers
                """
            )
            for row in rows:
                known.setdefault(row[0], _paper_from_archive_row(row))

    return known


def _paper_from_archive_row(row):
    """Convert one archive DB row into the standard paper dict shape."""
    return {
        "id": row[0],
        "_listing_date": row[1],
        "submitted": row[2],
        "title": row[3],
        "authors": json.loads(row[4]),
        "abstract": row[5],
        "primary_category": row[6],
        "categories": json.loads(row[7]),
        "arxiv_url": row[8],
        "pdf_url": row[9],
    }


def enrich_from_known_metadata(papers, known):
    """Fill missing metadata on papers from a known-metadata map."""
    for paper in papers:
        source = known.get(paper.get("id"))
        if source:
            merge_missing_metadata(paper, source)


def papers_missing_abstract(papers):
    """Return papers whose abstract is still absent."""
    return [paper for paper in papers if not paper.get("abstract")]


def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def enrich_from_api(papers, chunk_size=100, fetch_timeout=API_METADATA_TIMEOUT):
    """Fill missing metadata by fetching explicit arXiv IDs from the API."""
    missing = papers_missing_abstract(papers)
    if not missing:
        return 0

    enriched = 0
    by_id = {paper["id"]: paper for paper in papers if paper.get("id")}
    ids = [paper["id"] for paper in missing if paper.get("id")]
    for chunk in _chunks(ids, chunk_size):
        try:
            fetched = fetch_papers_by_ids(chunk, include_listing_date=False, fetch_timeout=fetch_timeout)
        except (TimeoutError, urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"  API metadata enrichment failed after {enriched} papers: {type(e).__name__}.")
            return enriched
        for source in fetched:
            paper = by_id.get(source.get("id"))
            if paper is None:
                continue
            before = paper.get("abstract")
            merge_missing_metadata(paper, source)
            if not before and paper.get("abstract"):
                enriched += 1

    return enriched


def enrich_html_papers(papers, data_dir=None, use_api=False):
    """Enrich HTML-scraped papers from local metadata and optionally the API."""
    if data_dir is not None:
        enrich_from_known_metadata(papers, load_known_metadata(data_dir))
        known_filled = len(papers) - len(papers_missing_abstract(papers))
        print(f"  Metadata available for {known_filled}/{len(papers)} HTML papers after local enrichment.")

    if use_api:
        enriched = enrich_from_api(papers)
        if enriched:
            print(f"  Filled abstracts for {enriched} HTML papers from arXiv API metadata.")

    return papers
