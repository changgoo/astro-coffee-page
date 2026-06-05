"""Yearly SQLite archive storage for purged arXiv listings."""

import json
import sqlite3

from .config import ARCHIVE_DIR
from .paper import utc_now_iso


def archive_dir(data_dir):
    """Return the directory for long-term archive files."""
    return data_dir / ARCHIVE_DIR


def archive_db_path(data_dir, year):
    """Return the yearly SQLite archive path for year."""
    return archive_dir(data_dir) / f"{year}.sqlite"


def make_search_text(paper):
    """Build normalized text used for simple archive search."""
    authors = " ".join(paper.get("authors", []))
    parts = (paper.get("id", ""), paper.get("title", ""), authors, paper.get("abstract", ""))
    return " ".join(part for part in parts if part).lower()


def ensure_archive_schema(conn):
    """Create the archive papers table when needed."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            listing_date TEXT NOT NULL,
            submitted TEXT,
            title TEXT NOT NULL,
            authors_json TEXT NOT NULL,
            abstract TEXT,
            primary_category TEXT,
            categories_json TEXT NOT NULL,
            arxiv_url TEXT,
            pdf_url TEXT,
            local_match TEXT,
            local_authors_json TEXT NOT NULL,
            discussed_at TEXT,
            search_text TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_papers_listing_date ON papers(listing_date)")


def archive_papers(data_dir, listing_date, papers):
    """Upsert papers into the yearly SQLite archive for listing_date."""
    if not papers:
        return

    year = listing_date[:4]
    archive_dir(data_dir).mkdir(exist_ok=True)
    db_path = archive_db_path(data_dir, year)
    with sqlite3.connect(db_path) as conn:
        ensure_archive_schema(conn)
        conn.executemany(
            """
            INSERT INTO papers (
                id, listing_date, submitted, title, authors_json, abstract,
                primary_category, categories_json, arxiv_url, pdf_url,
                local_match, local_authors_json, discussed_at, search_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                listing_date=excluded.listing_date,
                submitted=excluded.submitted,
                title=excluded.title,
                authors_json=excluded.authors_json,
                abstract=excluded.abstract,
                primary_category=excluded.primary_category,
                categories_json=excluded.categories_json,
                arxiv_url=excluded.arxiv_url,
                pdf_url=excluded.pdf_url,
                local_match=excluded.local_match,
                local_authors_json=excluded.local_authors_json,
                discussed_at=excluded.discussed_at,
                search_text=excluded.search_text
            """,
            [
                (
                    paper["id"],
                    listing_date,
                    paper.get("submitted", ""),
                    paper.get("title", ""),
                    json.dumps(paper.get("authors", []), ensure_ascii=False),
                    paper.get("abstract", ""),
                    paper.get("primary_category", ""),
                    json.dumps(paper.get("categories", []), ensure_ascii=False),
                    paper.get("arxiv_url", ""),
                    paper.get("pdf_url", ""),
                    paper.get("local_match"),
                    json.dumps(paper.get("local_authors", {}), ensure_ascii=False),
                    paper.get("discussed_at"),
                    make_search_text(paper),
                )
                for paper in papers
                if paper.get("id")
            ],
        )
    update_archive_index(data_dir)
    print(f"  Archived {len(papers)} papers to {db_path}.")


def archive_listing(data_dir, listing):
    """Archive one listing JSON object into its yearly SQLite database."""
    listing_date = listing.get("date")
    papers = listing.get("papers", [])
    if listing_date and papers:
        archive_papers(data_dir, listing_date, papers)


def update_archive_index(data_dir):
    """Write manifest metadata for available yearly SQLite archives."""
    directory = archive_dir(data_dir)
    directory.mkdir(exist_ok=True)
    years = []
    for db_path in sorted(directory.glob("*.sqlite")):
        year = db_path.stem
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        years.append({
            "year": year,
            "file": f"{ARCHIVE_DIR}/{db_path.name}",
            "count": count,
        })

    index = {
        "generated_at": utc_now_iso(),
        "years": years,
    }
    with open(directory / "index.json", "w") as f:
        json.dump(index, f, indent=2)
