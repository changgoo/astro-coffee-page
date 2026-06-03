#!/usr/bin/env python3
"""Scrape the latest arXiv astro-ph papers into rolling day files.

Normal runs fetch the latest 200 papers and update data/today.json. Older
listing days are kept in data/today-1.json through data/today-5.json.

Usage:
  python scripts/scrape.py [YYYY-MM-DD]
  python scripts/scrape.py --bootstrap N [YYYY-MM-DD]   # first-run seed for today.json
  python scripts/scrape.py --bootstrap-history          # seed today.json through today-5.json
  python scripts/scrape.py --reannotate                 # re-tag today*.json in-place
"""

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

BASE_URL = "https://export.arxiv.org/api/query"
MAX_PER_REQUEST = 200
RATE_LIMIT_SECONDS = 3
FETCH_SIZE = 200
BOOTSTRAP_FETCH_SIZE = 1000
HISTORY_DAYS = 5
ARCHIVE_DIR = "archive"
NY_TZ = ZoneInfo("America/New_York")


def prev_business_day(d):
    """Return the most recent weekday on or before date d."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_business_day(d):
    """Return the next weekday on or after date d."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def get_target_date(date_str=None, _et_now=None):
    """Return the arXiv listing date to scrape as YYYY-MM-DD.

    arXiv's submission windows and announcement schedule:
      Mon 14:00 – Tue 14:00  →  announced Tue 20:00  →  listing date: Tuesday
      Tue 14:00 – Wed 14:00  →  announced Wed 20:00  →  listing date: Wednesday
      Wed 14:00 – Thu 14:00  →  announced Thu 20:00  →  listing date: Thursday
      Thu 14:00 – Fri 14:00  →  announced Sun 20:00  →  listing date: Friday
      Fri 14:00 – Mon 14:00  →  announced Mon 20:00  →  listing date: Monday

    The listing date is the last business day of the submission window.
    This equals prev_business_day(today ET) after 14:00, or
    prev_business_day(yesterday ET) before 14:00.
    """
    if date_str:
        return date_str

    if _et_now is None:
        _et_now = datetime.now(NY_TZ)

    if _et_now.hour >= 14:
        target = _et_now.date()
    else:
        target = _et_now.date() - timedelta(days=1)

    return prev_business_day(target).strftime("%Y-%m-%d")


def listing_date_for_published(published):
    """Return the arXiv listing date for an Atom published timestamp."""
    published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    et_dt = published_dt.astimezone(NY_TZ)
    target = et_dt.date() + timedelta(days=1) if et_dt.hour >= 14 else et_dt.date()
    return next_business_day(target).strftime("%Y-%m-%d")


def build_query_url(start=0, max_results=MAX_PER_REQUEST):
    """Build the arXiv API query URL for the most recent astro-ph papers."""
    params = (
        f"search_query=cat:astro-ph.*"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&start={start}&max_results={max_results}"
    )
    return f"{BASE_URL}?{params}"


def fetch_xml(url, max_retries=5, base_delay=10):
    """Fetch a URL and return raw bytes, retrying on transient errors with exponential backoff.

    Retries on HTTP 429/503 and network timeouts; raises immediately on other errors.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "coffee-page/1.0 (arxiv paper browser)"})
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < max_retries:
                retry_after = e.headers.get("Retry-After", "")
                delay = int(retry_after) if retry_after.isdigit() else base_delay * (2 ** attempt)
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
    title = " ".join(find_text("title").split())
    abstract = " ".join(find_text("summary").split())
    published = find_text("published")
    submitted = published[:10]

    authors = [
        author.find("atom:name", NS).text.strip()
        for author in entry.findall("atom:author", NS)
        if author.find("atom:name", NS) is not None
    ]

    primary_cat_el = entry.find("arxiv:primary_category", NS)
    primary_category = primary_cat_el.get("term", "") if primary_cat_el is not None else ""

    categories = list({
        cat.get("term", "")
        for cat in entry.findall("atom:category", NS)
        if cat.get("term", "")
    })
    categories = sorted(categories, key=lambda c: (c != primary_category, c))

    paper = {
        "id": arxiv_id,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "primary_category": primary_category,
        "categories": categories,
        "submitted": submitted,
        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
    }
    if include_listing_date:
        paper["_listing_date"] = listing_date_for_published(published)
    return paper


def fetch_latest_papers(n=FETCH_SIZE, include_listing_date=False, max_per_request=MAX_PER_REQUEST):
    """Fetch the n most recently submitted astro-ph papers from the arXiv API."""
    papers = []
    start = 0
    total = None

    while start < n:
        max_results = min(max_per_request, n - start)
        url = build_query_url(start=start, max_results=max_results)
        print(f"  Fetching start={start} ...", flush=True)
        raw = fetch_xml(url)
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


def load_favorite_authors(repo_root):
    """Load and merge favorite authors from both config files (manual first, deduped)."""
    names = []
    seen = set()
    for filename in ("authors_manual.json", "authors.json"):
        path = repo_root / "config" / filename
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for name in data.get("authors", []):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def load_discussed_papers(data_dir):
    """Load discussed paper IDs from data/discussed.json into a paper_id -> date map."""
    discussed_path = data_dir / "discussed.json"
    if not discussed_path.exists():
        return {}
    with open(discussed_path) as f:
        data = json.load(f)
    discussed = {}
    for paper in data.get("papers", []):
        paper_id = paper.get("paper_id")
        discussed_at = paper.get("discussed_at")
        if paper_id and discussed_at:
            discussed[paper_id] = discussed_at
    return discussed


def parse_name_parts(name):
    """Parse a name into (first, last, middle_initial) components.

    Handles arXiv format "Last, First [Middle]" and Princeton format
    "[Title] First [Middle] Last [Suffix]". Returns lowercase strings.
    """
    suffixes = {"iii", "ii", "iv", "jr.", "jr", "sr.", "sr"}
    titles = {"sir", "dr.", "dr", "prof.", "prof"}

    if "," in name:
        comma = name.index(",")
        last = name[:comma].strip().lower()
        rest = name[comma + 1:].strip().split()
        first = rest[0].replace(".", "").lower() if rest else ""
        mid_str = rest[1].replace(".", "").lower() if len(rest) > 1 else ""
        middle_initial = mid_str[0] if mid_str else None
        return first, last, middle_initial

    tokens = name.strip().split()
    while len(tokens) > 1 and tokens[0].lower() in titles:
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1].lower() in suffixes:
        tokens = tokens[:-1]
    last = tokens[-1].lower() if tokens else ""
    first = tokens[0].replace(".", "").lower() if tokens else ""
    mid_str = tokens[1].replace(".", "").lower() if len(tokens) > 2 else ""
    middle_initial = mid_str[0] if mid_str else None
    return first, last, middle_initial


def match_author(arxiv_name, fav_authors):
    """Return "strong", "weak", or None for one arXiv author against fav_authors.

    Strong match conditions (beyond exact first-name match):
      - Hyphenated first name matched by hyphenated initials only:
        "C.-G." == "Chang-Goo Kim" → strong; "C.G." is NOT strong
      - First initial + matching middle initial: "M. W." == "Matthew W." → strong
    A single bare initial against a hyphenated fav name returns None (no match).
    A single bare initial against a non-hyphenated fav name is weak.
    Add the abbreviated form to authors_manual.json to get a strong match (e.g. "G. Livadiotis").
    """
    arx_first, arx_last, arx_mid = parse_name_parts(arxiv_name)
    best = None
    for fav_name in fav_authors:
        fav_first, fav_last, fav_mid = parse_name_parts(fav_name)
        if fav_last != arx_last:
            continue
        if fav_first == arx_first:
            return "strong"
        if not fav_first or not arx_first:
            continue
        # Hyphenated favorite first name: only hyphenated initials are strong
        # (e.g. "C.-G." == "Chang-Goo"); concatenated "C.G." is NOT strong
        if "-" in fav_first and "-" in arx_first:
            fav_parts = fav_first.split("-")
            arx_parts = arx_first.split("-")
            if (len(fav_parts) == len(arx_parts) and
                    all(len(ap) == 1 and ap == fp[0]
                        for ap, fp in zip(arx_parts, fav_parts))):
                return "strong"

        # Single initial vs hyphenated fav name → no match (too ambiguous)
        if "-" in fav_first and len(arx_first) == 1:
            continue
        # First initial match with optional middle initial agreement
        if fav_first[0] == arx_first[0]:
            if fav_mid and arx_mid and fav_mid == arx_mid:
                return "strong"
            if fav_mid and arx_mid and fav_mid != arx_mid:
                continue  # conflicting middle initials → different person
            if arx_mid and not fav_mid:
                continue  # arXiv has extra middle initial fav lacks → too ambiguous
            if fav_mid and not arx_mid:
                continue  # fav has middle initial but arXiv omits it → can't confirm
            if len(arx_first) >= 2 and len(fav_first) >= 2:
                continue  # both full first names already failed equality → different person
            best = "weak"
    return best


def annotate_papers(papers, fav_authors):
    """Add local_match and local_authors fields to each paper dict in-place.

    local_match:   "strong" | "weak" | None  (best match across all authors)
    local_authors: {arxiv_name: "strong"|"weak"}  (matched authors only)
    """
    for paper in papers:
        local_authors = {}
        best = None
        for arxiv_name in paper.get("authors", []):
            strength = match_author(arxiv_name, fav_authors)
            if strength:
                local_authors[arxiv_name] = strength
                if strength == "strong":
                    best = "strong"
                elif best != "strong":
                    best = "weak"
        paper["local_match"] = best
        paper["local_authors"] = local_authors


def annotate_discussed_papers(papers, discussed_papers):
    """Add discussed_at to papers whose IDs appear in discussed_papers."""
    for paper in papers:
        discussed_at = discussed_papers.get(paper.get("id"))
        if discussed_at:
            paper["discussed_at"] = discussed_at


def history_filename(offset):
    """Return the rolling history filename for offset 0..HISTORY_DAYS."""
    if offset == 0:
        return "today.json"
    return f"today-{offset}.json"


def history_path(data_dir, offset):
    """Return the path for one rolling history file."""
    return data_dir / history_filename(offset)


def load_listing(path):
    """Load a listing JSON file, returning None when the file is absent."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def strip_internal_fields(papers):
    """Remove scraper-only fields before writing paper JSON."""
    for paper in papers:
        paper.pop("_listing_date", None)


def save_listing(path, date, papers):
    """Write one listing file with the standard data shape."""
    strip_internal_fields(papers)
    output = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": date,
        "total": len(papers),
        "papers": papers,
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved {path.name} with {len(papers)} papers.")


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
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "years": years,
    }
    with open(directory / "index.json", "w") as f:
        json.dump(index, f, indent=2)


def load_history(data_dir):
    """Load all existing rolling history files keyed by offset."""
    history = {}
    for offset in range(HISTORY_DAYS + 1):
        data = load_listing(history_path(data_dir, offset))
        if data is not None:
            history[offset] = data
    return history


def collect_history_ids(history):
    """Return all paper IDs present in loaded rolling history files."""
    return {
        paper["id"]
        for data in history.values()
        for paper in data.get("papers", [])
        if paper.get("id")
    }


def rotate_history(data_dir):
    """Rotate today.json through today-5.json, dropping the oldest file."""
    oldest = history_path(data_dir, HISTORY_DAYS)
    if oldest.exists():
        listing = load_listing(oldest)
        if listing:
            archive_listing(data_dir, listing)
        oldest.unlink()
    for offset in range(HISTORY_DAYS - 1, -1, -1):
        src = history_path(data_dir, offset)
        if src.exists():
            src.replace(history_path(data_dir, offset + 1))


def select_new_papers(candidates, seen_ids):
    """Return candidates whose IDs are not in seen_ids, updating seen_ids in order."""
    selected = []
    for paper in candidates:
        paper_id = paper.get("id")
        if paper_id and paper_id not in seen_ids:
            selected.append(paper)
            seen_ids.add(paper_id)
    return selected


def group_papers_by_listing_date(papers):
    """Group papers by scraper-computed arXiv listing date in input order."""
    groups = {}
    for paper in papers:
        listing_date = paper.get("_listing_date")
        if not listing_date:
            continue
        groups.setdefault(listing_date, []).append(paper)
    return groups


def update_index(data_dir):
    """Write data/index.json with today's UTC date (used for the header display)."""
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    index_path = data_dir / "index.json"
    with open(index_path, "w") as f:
        json.dump({"current": today_utc}, f, indent=2)
    print(f"  Updated index.json: current={today_utc}")


def reannotate(data_dir, repo_root):
    """Re-run author tagging on rolling today*.json files without re-scraping."""
    fav_authors = load_favorite_authors(repo_root)
    discussed_papers = load_discussed_papers(data_dir)
    print(f"  {len(fav_authors)} favorites loaded.")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for offset in range(HISTORY_DAYS + 1):
        path = history_path(data_dir, offset)
        if not path.exists():
            print(f"  {path.name} not found, skipping.")
            continue
        with open(path) as f:
            data = json.load(f)
        papers = data.get("papers", [])
        print(f"  Re-annotating {len(papers)} papers in {path.name} ...")
        annotate_papers(papers, fav_authors)
        annotate_discussed_papers(papers, discussed_papers)
        data["papers"] = papers
        data["fetched_at"] = now
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Saved {path.name}.")


def bootstrap_history(data_dir, repo_root):
    """Seed today.json through today-5.json from up to 1000 recent arXiv papers."""
    print(f"Fetching latest {BOOTSTRAP_FETCH_SIZE} arXiv astro-ph papers for history bootstrap ...")
    fetched = fetch_latest_papers(
        n=BOOTSTRAP_FETCH_SIZE,
        include_listing_date=True,
        max_per_request=BOOTSTRAP_FETCH_SIZE,
    )
    if not fetched:
        print("  No papers fetched. Skipping.")
        return

    fav_authors = load_favorite_authors(repo_root)
    discussed_papers = load_discussed_papers(data_dir)
    print(f"  Annotating local author matches ({len(fav_authors)} favorites) ...")
    annotate_papers(fetched, fav_authors)
    annotate_discussed_papers(fetched, discussed_papers)

    groups = group_papers_by_listing_date(fetched)
    listing_dates = sorted(groups.keys(), reverse=True)
    if len(listing_dates) < HISTORY_DAYS + 1:
        print(f"  Warning: only found {len(listing_dates)} listing days in bootstrap fetch.")

    for offset, listing_date in enumerate(listing_dates[:HISTORY_DAYS + 1]):
        papers = groups[listing_date]
        save_listing(history_path(data_dir, offset), listing_date, papers)

    for offset in range(len(listing_dates[:HISTORY_DAYS + 1]), HISTORY_DAYS + 1):
        path = history_path(data_dir, offset)
        if path.exists():
            path.unlink()

    update_index(data_dir)
    print("Done.")


def update_history_for_date(data_dir, arxiv_date, target_papers, bootstrap_n=None, discussed_papers=None):
    """Update rolling history for one arXiv listing date; return count of new papers."""
    discussed_papers = discussed_papers or {}

    if bootstrap_n is not None:
        sorted_by_id = sorted(target_papers, key=lambda p: p["id"], reverse=True)
        new_papers = sorted_by_id[:bootstrap_n]
        print(f"  Bootstrap mode: using top {bootstrap_n} papers by arXiv ID desc as today's listing.")
        annotate_discussed_papers(new_papers, discussed_papers)
        save_listing(history_path(data_dir, 0), arxiv_date, new_papers)
        return len(new_papers)

    history = load_history(data_dir)
    today = history.get(0)
    same_date = today and today.get("date") == arxiv_date

    if same_date:
        existing_papers = today.get("papers", [])
        seen_ids = collect_history_ids(history)
        new_papers = select_new_papers(target_papers, seen_ids)
        all_papers = existing_papers + new_papers
        print(f"  Appending {len(new_papers)} papers to existing {len(existing_papers)}.")
    else:
        if today:
            rotate_history(data_dir)
            history = load_history(data_dir)
        else:
            history = {}
        seen_ids = collect_history_ids(history)
        new_papers = select_new_papers(target_papers, seen_ids)
        all_papers = new_papers
        print(f"  Starting fresh listing with {len(new_papers)} papers.")

    if len(new_papers) >= int(FETCH_SIZE * 0.9):
        print("  Warning: new-paper count is close to fetch size; latest 200 papers may be insufficient.")

    if not new_papers and same_date:
        print("  No new papers. Skipping.")
        return 0

    annotate_discussed_papers(all_papers, discussed_papers)
    save_listing(history_path(data_dir, 0), arxiv_date, all_papers)
    return len(new_papers)


def main():
    """Scrape latest papers, update rolling day files, and refresh index.json.

    --bootstrap N  First-run mode: use the top N fetched papers as today's listing
                   without requiring existing history.
    """
    repo_root = Path(__file__).parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)

    args = sys.argv[1:]
    if "--reannotate" in args:
        reannotate(data_dir, repo_root)
        return
    if "--bootstrap-history" in args:
        bootstrap_history(data_dir, repo_root)
        return

    bootstrap_n = None
    if "--bootstrap" in args:
        idx = args.index("--bootstrap")
        bootstrap_n = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    arxiv_date = args[0] if args else get_target_date()
    print(f"arXiv date: {arxiv_date}")

    print(f"Fetching latest {FETCH_SIZE} arXiv astro-ph papers ...")
    fetched = fetch_latest_papers(n=FETCH_SIZE, include_listing_date=True)
    if not fetched:
        print("  No papers fetched. Skipping.")
        return

    print(f"  Fetched {len(fetched)} papers.")

    fav_authors = load_favorite_authors(repo_root)
    discussed_papers = load_discussed_papers(data_dir)
    print(f"  Annotating local author matches ({len(fav_authors)} favorites) ...")
    annotate_papers(fetched, fav_authors)
    annotate_discussed_papers(fetched, discussed_papers)

    grouped = group_papers_by_listing_date(fetched)
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



if __name__ == "__main__":
    main()
