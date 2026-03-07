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


def get_target_date(date_str=None):
    """Return the target submission date as YYYY-MM-DD string.

    arXiv cutoff is 14:00 US Eastern Time. Papers submitted before that
    appear in the *next* day's mailing. We query for papers submitted on
    the calendar date that would have appeared in today's new listing.

    If a date string is provided, use that directly.
    """
    if date_str:
        return date_str

    # Current time in US Eastern (UTC-5 standard / UTC-4 daylight)
    # Use a fixed offset of UTC-5 (EST) as a conservative estimate.
    et_now = datetime.now(timezone(timedelta(hours=-5)))
    # arXiv announces papers submitted the *previous* business day
    # For simplicity: use yesterday's date when it's before 15:00 ET,
    # otherwise use today's date (the current day's submissions won't be
    # announced until tomorrow, but we fetch what's available).
    # The GitHub Action runs after 15:30 UTC (10:30 ET) which is well before
    # the 14:00 ET cutoff — so we query the previous calendar day.
    target = et_now - timedelta(days=1)
    return target.strftime("%Y-%m-%d")


def build_query_url(date_str, start=0, max_results=MAX_PER_REQUEST):
    date_compact = date_str.replace("-", "")
    search_query = f"cat:astro-ph.*+AND+submittedDate:[{date_compact}0000+TO+{date_compact}2359]"
    params = (
        f"search_query={search_query}"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&start={start}&max_results={max_results}"
    )
    return f"{BASE_URL}?{params}"


def fetch_xml(url):
    req = urllib.request.Request(url, headers={"User-Agent": "coffee-page/1.0 (arxiv paper browser)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_entry(entry):
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


def fetch_all_papers(date_str):
    papers = []
    start = 0
    total = None

    while True:
        url = build_query_url(date_str, start=start)
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


def update_index(data_dir, date_str, max_days=10):
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

    # Remove JSON files for dates no longer in the index
    for json_file in data_dir.glob("????-??-??.json"):
        if json_file.stem not in dates:
            print(f"  Removing old data file: {json_file.name}")
            json_file.unlink()

    index["dates"] = dates
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"  Updated index.json: {dates}")


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else get_target_date()
    print(f"Fetching arXiv astro-ph papers for {date_str}")

    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    papers = fetch_all_papers(date_str)

    output = {
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(papers),
        "papers": papers,
    }

    out_path = data_dir / f"{date_str}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved {len(papers)} papers to {out_path}")

    update_index(data_dir, date_str)
    print("Done.")


if __name__ == "__main__":
    main()
