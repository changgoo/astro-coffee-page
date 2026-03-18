#!/usr/bin/env python3
"""
Scrape the latest arXiv astro-ph papers via the arXiv API using a diff approach.

Each run fetches the most recent 1000 papers. Papers not present in the previous
archive snapshot are treated as new for today's listing. The archive is then updated.

Usage:
  python scripts/scrape.py [YYYY-MM-DD]
  python scripts/scrape.py --bootstrap N [YYYY-MM-DD]   # first-run seed
  python scripts/scrape.py --reannotate                 # re-tag today.json in-place
"""

import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

BASE_URL = "http://export.arxiv.org/api/query"
MAX_PER_REQUEST = 500
RATE_LIMIT_SECONDS = 3
ARCHIVE_SIZE = 1000


def prev_business_day(d):
    """Return the most recent weekday on or before date d."""
    while d.weekday() >= 5:
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


def build_query_url(start=0, max_results=MAX_PER_REQUEST):
    """Build the arXiv API query URL for the most recent astro-ph papers."""
    params = (
        f"search_query=cat:astro-ph.*"
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

    id_url = find_text("id")
    arxiv_id = id_url.rstrip("/").split("/abs/")[-1].split("v")[0]
    title = " ".join(find_text("title").split())
    abstract = " ".join(find_text("summary").split())
    submitted = find_text("published")[:10]

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


def fetch_latest_papers(n=ARCHIVE_SIZE):
    """Fetch the n most recently submitted astro-ph papers from the arXiv API."""
    papers = []
    start = 0
    total = None

    while start < n:
        max_results = min(MAX_PER_REQUEST, n - start)
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
            papers.append(parse_entry(entry))

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


def load_archive(data_dir):
    """Load data/archive.json; return (papers_list, ids_set) or ([], set())."""
    archive_path = data_dir / "archive.json"
    if not archive_path.exists():
        return [], set()
    with open(archive_path) as f:
        data = json.load(f)
    papers = data.get("papers", [])
    ids = {p["id"] for p in papers}
    return papers, ids


def save_archive(data_dir, papers):
    """Overwrite data/archive.json with the given papers list."""
    archive_path = data_dir / "archive.json"
    output = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(papers),
        "papers": papers,
    }
    with open(archive_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved archive.json with {len(papers)} papers.")


def update_index(data_dir):
    """Write data/index.json with today's UTC date (used for the header display)."""
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    index_path = data_dir / "index.json"
    with open(index_path, "w") as f:
        json.dump({"current": today_utc}, f, indent=2)
    print(f"  Updated index.json: current={today_utc}")


def reannotate(data_dir, repo_root):
    """Re-run author tagging on today.json and archive.json in-place without re-scraping."""
    fav_authors = load_favorite_authors(repo_root)
    print(f"  {len(fav_authors)} favorites loaded.")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for filename in ("today.json", "archive.json"):
        path = data_dir / filename
        if not path.exists():
            print(f"  {filename} not found, skipping.")
            continue
        with open(path) as f:
            data = json.load(f)
        papers = data.get("papers", [])
        print(f"  Re-annotating {len(papers)} papers in {filename} ...")
        annotate_papers(papers, fav_authors)
        data["papers"] = papers
        data["fetched_at"] = now
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Saved {filename}.")


def main():
    """Scrape latest papers, compute diff vs archive, save today's listing and update archive.

    --bootstrap N  First-run mode: use the top N fetched papers as today's listing
                   without requiring an existing archive.
    """
    repo_root = Path(__file__).parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)

    args = sys.argv[1:]
    if "--reannotate" in args:
        reannotate(data_dir, repo_root)
        return

    bootstrap_n = None
    if "--bootstrap" in args:
        idx = args.index("--bootstrap")
        bootstrap_n = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    arxiv_date = args[0] if args else get_target_date()
    print(f"arXiv date: {arxiv_date}")

    print(f"Fetching latest {ARCHIVE_SIZE} arXiv astro-ph papers ...")
    fetched = fetch_latest_papers(n=ARCHIVE_SIZE)
    if not fetched:
        print("  No papers fetched. Skipping.")
        return

    print(f"  Fetched {len(fetched)} papers.")

    fav_authors = load_favorite_authors(repo_root)
    print(f"  Annotating local author matches ({len(fav_authors)} favorites) ...")
    annotate_papers(fetched, fav_authors)

    _, archive_ids = load_archive(data_dir)

    if bootstrap_n is not None:
        sorted_by_id = sorted(fetched, key=lambda p: p["id"], reverse=True)
        new_papers = sorted_by_id[:bootstrap_n]
        print(f"  Bootstrap mode: using top {bootstrap_n} papers by arXiv ID desc as today's listing.")
    elif not archive_ids:
        print("  No archive found. Run with --bootstrap N to initialize.")
        return
    else:
        new_papers = [p for p in fetched if p["id"] not in archive_ids]
        print(f"  Diff: {len(new_papers)} new papers since last archive.")

    new_count = len(new_papers)
    if new_count == 0:
        print("  No new papers. Skipping.")
        return

    # Append to today.json if it already holds the same arXiv date; otherwise start fresh.
    out_path = data_dir / "today.json"
    existing_papers = []
    if bootstrap_n is None and out_path.exists():
        with open(out_path) as f:
            existing = json.load(f)
        if existing.get("date") == arxiv_date:
            existing_papers = existing.get("papers", [])
            print(f"  Appending {new_count} papers to existing {len(existing_papers)}.")
    all_papers = existing_papers + new_papers
    output = {
        "date": arxiv_date,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(all_papers),
        "papers": all_papers,
    }
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved {len(all_papers)} papers to {out_path} ({new_count} new).")

    save_archive(data_dir, fetched)
    update_index(data_dir)
    print("Done.")



if __name__ == "__main__":
    main()
