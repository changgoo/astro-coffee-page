#!/usr/bin/env python3
"""
Scrape the Princeton Astronomy department people pages and update config/authors.json.

Usage:
    python scripts/scrape_authors.py [--dry-run]

Requirements:
    pip install requests beautifulsoup4

By default scrapes: Faculty, Postdocs/Researchers, Graduate Students, and Associated Faculty/Affiliates.
Edit PAGES below to customise which groups are included.
"""

import argparse
import json
from pathlib import Path

try:
    import cloudscraper
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit(
        "Missing dependencies. Install with:\n  pip install cloudscraper beautifulsoup4"
    )

# cloudscraper handles Cloudflare JS challenges automatically
_scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "darwin"})

BASE_URL = "https://web.astro.princeton.edu"

# Pages to scrape and their labels. Comment out any groups you want to exclude.
PAGES = [
    ("Faculty & Research Scholars",
     f"{BASE_URL}/people/astronomy-Faculty%20and%20Research%20Scholars"),
    ("Postdoctoral Researchers",
     f"{BASE_URL}/people/postdocs-researchers"),
    ("Graduate Students",
     f"{BASE_URL}/people/graduate-students"),
    ("Associated Faculty & Affiliates",
     f"{BASE_URL}/people/associated-faculty-department-affiliates"),
]

# CSS selectors (Princeton Astro site structure as of 2024)
PERSON_DIV_CLASS = "content-list-item feature-is-3x4 no-featured-video"
NAME_SPAN_CLASS = "field field--name-title field--type-string field--label-hidden"

def scrape_page(label, url):
    """Return list of names from a single people page."""
    print(f"  Fetching {label} ...", end=" ", flush=True)
    try:
        r = _scraper.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"FAILED ({e})")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    people = soup.find_all("div", class_=PERSON_DIV_CLASS)

    names = []
    for person in people:
        span = person.find("span", class_=NAME_SPAN_CLASS)
        if span:
            name = span.get_text(strip=True)
            if name:
                names.append(name)

    print(f"{len(names)} people found")
    return names


def main():
    """Parse arguments, scrape all configured pages, and write config/authors.json."""
    parser = argparse.ArgumentParser(description="Scrape Princeton Astro people list")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print names without writing to config/authors.json"
    )
    args = parser.parse_args()

    all_names = []
    for label, url in PAGES:
        all_names.extend(scrape_page(label, url))

    # Deduplicate while preserving order
    seen = set()
    unique_names = []
    for name in all_names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)

    print(f"\nTotal: {len(unique_names)} unique names")

    if args.dry_run:
        print("\nDry run — names that would be written:")
        for name in unique_names:
            print(f"  {name}")
        return

    config_path = Path(__file__).parent.parent / "config" / "authors.json"
    config_path.parent.mkdir(exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"authors": unique_names}, f, indent=2, ensure_ascii=False)

    print(f"Written to {config_path}")


if __name__ == "__main__":
    main()
