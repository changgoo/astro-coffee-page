"""Command-line entrypoint for the arXiv scraper."""

import sys
from pathlib import Path

from .dates import get_target_date
from .workflows import bootstrap_history, reannotate, run_scrape


def main():
    """Scrape latest papers, update rolling day files, and refresh index.json."""
    repo_root = Path(__file__).parent.parent.parent
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

    explicit_date = bool(args)
    arxiv_date = args[0] if explicit_date else get_target_date()
    print(f"arXiv date: {arxiv_date}")

    run_scrape(
        data_dir=data_dir,
        repo_root=repo_root,
        arxiv_date=arxiv_date,
        explicit_date=explicit_date,
        bootstrap_n=bootstrap_n,
    )
