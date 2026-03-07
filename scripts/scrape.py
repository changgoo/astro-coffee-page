#!/usr/bin/env python3
"""
Scrape arXiv astro-ph new papers via the arXiv API and save as JSON.
Usage: python scripts/scrape.py [YYYY-MM-DD]
Default date: today in ET (adjusted for arXiv's 14:00 ET submission cutoff)
"""

import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# arXiv API namespace
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

BASE_URL = "http://export.arxiv.org/api/query"
MAX_PER_REQUEST = 500
RATE_LIMIT_SECONDS = 3


def prev_business_day(d):
    """Return the most recent weekday on or before date d."""
    while d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        d -= timedelta(days=1)
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

    Examples:
      Tue 21:00 ET  →  Tuesday   (Tue nightly run, catches Tue announcement)
      Sun 21:00 ET  →  Friday    (Sun nightly run, catches Thu–Fri batch)
      Mon 21:00 ET  →  Monday    (Mon nightly run, catches Fri–Mon batch)
      Mon 06:00 ET  →  Friday    (Mon morning catch-up for Fri–Mon batch)
      Sat 10:00 ET  →  Friday    (matches arXiv showing Fri papers on Saturday)

    If date_str is provided, use that directly.
    _et_now may be injected for testing.
    """
    if date_str:
        return date_str

    if _et_now is None:
        _et_now = datetime.now(timezone(timedelta(hours=-5)))

    if _et_now.hour >= 14:
        target = _et_now.date()
    else:
        target = _et_now.date() - timedelta(days=1)

    return prev_business_day(target).strftime("%Y-%m-%d")


ET_CUTOFF_HOUR = 14  # arXiv submission cutoff: 14:00 Eastern (EST, UTC-5)


def get_submission_window(listing_date_str):
    """Return (start_dt, end_dt) arXiv submittedDate strings for a listing date.

    arXiv uses Eastern Time (EST, UTC-5) for its 14:00 submission cutoff.
    The window spans from the previous business day's cutoff to the cutoff
    day's cutoff (exclusive), i.e.:
      prev_biz_day(cutoff_day - 1) 14:00 ET  →  cutoff_day 13:59:59 ET
    where cutoff_day = prev_business_day(listing - 1 day).

    Strings are formatted as YYYYMMDDHHMMSS for the arXiv API.

    Examples:
      Friday   (2026-03-06) → cutoff=Thu 03-05; window: Wed 14:00–Thu 13:59:59 ET
      Monday   (2026-03-09) → cutoff=Fri 03-06; window: Thu 14:00–Fri 13:59:59 ET
      Tuesday  (2026-03-10) → cutoff=Mon 03-09; window: Fri 14:00–Mon 13:59:59 ET
    """
    listing = datetime.strptime(listing_date_str, "%Y-%m-%d").date()
    cutoff_day = prev_business_day(listing - timedelta(days=1))
    window_start_day = prev_business_day(cutoff_day - timedelta(days=1))
    start = f"{window_start_day.strftime('%Y%m%d')}{ET_CUTOFF_HOUR:02d}0000"
    end = f"{cutoff_day.strftime('%Y%m%d')}{ET_CUTOFF_HOUR - 1:02d}5959"
    return start, end


def build_query_url(start_dt, end_dt, start=0, max_results=MAX_PER_REQUEST):
    """Build the arXiv API query URL for a submittedDate range and pagination offset."""
    search_query = f"cat:astro-ph.*+AND+submittedDate:[{start_dt}+TO+{end_dt}]"
    params = (
        f"search_query={search_query}"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&start={start}&max_results={max_results}"
    )
    return f"{BASE_URL}?{params}"


def fetch_xml(url):
    """Fetch a URL and return raw bytes, sending a descriptive User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": "coffee-page/1.0 (arxiv paper browser)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_entry(entry):
    """Parse a single Atom <entry> element into a paper dict."""
    def find_text(tag, ns_key="atom"):
        el = entry.find(f"{ns_key}:{tag}", NS)
        return el.text.strip() if el is not None and el.text else ""

    # arXiv ID from <id> URL like https://arxiv.org/abs/2603.12345v1
    id_url = find_text("id")
    arxiv_id = id_url.rstrip("/").split("/abs/")[-1].split("v")[0]

    title = " ".join(find_text("title").split())  # normalize whitespace
    abstract = " ".join(find_text("summary").split())
    submitted = find_text("published")[:10]  # YYYY-MM-DD

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

    # Keep only astro-ph and known physics categories; sort with primary first
    categories = sorted(categories, key=lambda c: (c != primary_category, c))

    return {
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


def fetch_all_papers(listing_date_str):
    """Fetch all papers for the given listing date, paginating as needed."""
    start_dt, end_dt = get_submission_window(listing_date_str)
    print(f"  Submission window: {start_dt[:8]} {start_dt[8:10]}:00 ET → "
          f"{end_dt[:8]} {end_dt[8:10]}:59 ET")
    papers = []
    start = 0
    total = None

    while True:
        url = build_query_url(start_dt, end_dt, start=start)
        print(f"  Fetching start={start} ...", flush=True)
        raw = fetch_xml(url)
        root = ET.fromstring(raw)

        if total is None:
            total_el = root.find("opensearch:totalResults", NS)
            total = int(total_el.text) if total_el is not None else 0
            print(f"  Total results: {total}")

        entries = root.findall("atom:entry", NS)
        if not entries:
            break

        for entry in entries:
            papers.append(parse_entry(entry))

        start += len(entries)
        if start >= total:
            break

        time.sleep(RATE_LIMIT_SECONDS)

    return papers


def load_favorite_authors(repo_root):
    """Load and merge favorite authors from both config files.

    Returns a list of name strings (manual entries first, deduped).
    """
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
        middle_initial = rest[1].replace(".", "").lower()[0] if len(rest) > 1 else None
        return first, last, middle_initial

    tokens = name.strip().split()
    while len(tokens) > 1 and tokens[0].lower() in titles:
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1].lower() in suffixes:
        tokens = tokens[:-1]
    last = tokens[-1].lower() if tokens else ""
    first = tokens[0].replace(".", "").lower() if tokens else ""
    middle_initial = tokens[1].replace(".", "").lower()[0] if len(tokens) > 2 else None
    return first, last, middle_initial


def has_strong_local_author(paper, fav_authors):
    """Return True if any paper author is a strong match against fav_authors.

    Strong match: last name exact AND (first name exact, or both sides have
    a matching middle initial when only first initials agree).
    """
    for arxiv_name in paper.get("authors", []):
        arx_first, arx_last, arx_mid = parse_name_parts(arxiv_name)
        for fav_name in fav_authors:
            fav_first, fav_last, fav_mid = parse_name_parts(fav_name)
            if fav_last != arx_last:
                continue
            if fav_first == arx_first:
                return True
            if fav_first and arx_first and fav_first[0] == arx_first[0]:
                if fav_mid and arx_mid and fav_mid == arx_mid:
                    return True
    return False


def archive_strong_papers(data_dir, date_str, papers, fav_authors):
    """Append strong local author matches from papers to data/local-archive.json.

    The archive is a JSON object mapping date strings to lists of paper dicts,
    keeping only strong-match papers. Existing entries for date_str are replaced.
    """
    archive_path = data_dir / "local-archive.json"
    archive = {}
    if archive_path.exists():
        with open(archive_path) as f:
            archive = json.load(f)

    strong = [p for p in papers if has_strong_local_author(p, fav_authors)]
    if strong:
        archive[date_str] = strong
        with open(archive_path, "w") as f:
            json.dump(archive, f, indent=2)
        print(f"  Archived {len(strong)} strong-match papers from {date_str} to local-archive.json")
    else:
        print(f"  No strong matches in {date_str}; nothing archived.")


def update_index(data_dir, date_str, fav_authors=None, max_days=10):
    """Add date_str to data/index.json and prune entries beyond max_days.

    When pruning an old date, extracts strong local author matches into
    data/local-archive.json before deleting the full day file.
    """
    index_path = data_dir / "index.json"
    if index_path.exists():
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {"dates": []}

    dates = index["dates"]
    if date_str not in dates:
        dates.insert(0, date_str)

    # Sort descending and keep only max_days
    dates = sorted(set(dates), reverse=True)[:max_days]

    # Prune files for dates no longer in the index
    for json_file in data_dir.glob("????-??-??.json"):
        stem = json_file.stem
        if stem in dates:
            continue
        if fav_authors:
            with open(json_file) as f:
                day_data = json.load(f)
            archive_strong_papers(data_dir, stem, day_data.get("papers", []), fav_authors)
        print(f"  Removing old data file: {json_file.name}")
        json_file.unlink()

    index["dates"] = dates
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"  Updated index.json: {dates}")


def main():
    """Entry point: scrape papers for the target date and save to data/.

    Skips writing if the fetched paper count is no greater than what is
    already stored, so repeated nightly runs only commit when arXiv has
    added more papers since the last run.
    """
    listing_date = sys.argv[1] if len(sys.argv) > 1 else get_target_date()
    print(f"Fetching arXiv astro-ph papers for listing {listing_date}")

    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    papers = fetch_all_papers(listing_date)
    new_count = len(papers)

    if new_count == 0:
        print(f"  No papers found for {listing_date} — arXiv may not have announced this batch yet. Skipping.")
        return

    # Check existing file to avoid redundant writes and commits
    out_path = data_dir / f"{listing_date}.json"
    if out_path.exists():
        with open(out_path) as f:
            existing = json.load(f)
        existing_count = existing.get("total", 0)
        if new_count <= existing_count:
            print(f"  No update: fetched {new_count} papers, existing {existing_count}. Skipping.")
            return
        print(f"  Update detected: {existing_count} -> {new_count} papers.")

    output = {
        "date": listing_date,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": new_count,
        "papers": papers,
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved {new_count} papers to {out_path}")

    repo_root = Path(__file__).parent.parent
    fav_authors = load_favorite_authors(repo_root)
    update_index(data_dir, listing_date, fav_authors=fav_authors)
    print("Done.")


if __name__ == "__main__":
    main()
