#!/usr/bin/env python3
"""Command-line entrypoint for the arXiv astro-ph scraper.

Normal runs fetch the latest 200 papers and update data/today.json. Older
listing days are kept in data/today-1.json through data/today-5.json.

Usage:
  python scripts/scrape.py [YYYY-MM-DD]
  python scripts/scrape.py --bootstrap N [YYYY-MM-DD]   # first-run seed for today.json
  python scripts/scrape.py --bootstrap-history          # seed today.json through today-5.json
  python scripts/scrape.py --bootstrap-history --api-enrich
  python scripts/scrape.py --reannotate                 # re-tag today*.json in-place
"""

import sys
from pathlib import Path

from scraper.dates import get_target_date
from scraper.workflows import bootstrap_history, reannotate, run_scrape


def main():
    """Scrape latest papers, update rolling day files, and refresh index.json."""
    repo_root = Path(__file__).parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)

    args = sys.argv[1:]
    api_enrich = "--api-enrich" in args
    if api_enrich:
        args.remove("--api-enrich")

    if "--reannotate" in args:
        reannotate(data_dir, repo_root)
        return
    if "--bootstrap-history" in args:
        bootstrap_history(data_dir, repo_root, api_enrich=api_enrich)
        return

    bootstrap_n = None
    if "--bootstrap" in args:
        idx = args.index("--bootstrap")
        bootstrap_n = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    explicit_date = bool(args)
    arxiv_date = args[0] if explicit_date else get_target_date()
    print(f"arXiv date: {arxiv_date}")

    run_scrape(
        data_dir=data_dir,
        repo_root=repo_root,
        arxiv_date=arxiv_date,
        explicit_date=explicit_date,
        bootstrap_n=bootstrap_n,
        api_enrich=api_enrich,
    )


if __name__ == "__main__":
    main()
