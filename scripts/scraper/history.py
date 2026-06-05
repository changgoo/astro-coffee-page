"""Rolling JSON history file management."""

import json

from .archive import archive_listing
from .config import FETCH_SIZE, HISTORY_DAYS
from .discussed import annotate_discussed_papers
from .paper import utc_now_iso, utc_today


def history_filename(offset):
    """Return the rolling history filename for offset 0..HISTORY_DAYS."""
    if offset == 0:
        return "today.json"
    return f"today-{offset}.json"


def history_path(data_dir, offset):
    """Return the path for one rolling history file."""
    return data_dir / history_filename(offset)


def history_offsets():
    """Return all rolling history offsets."""
    return range(HISTORY_DAYS + 1)


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
        "fetched_at": utc_now_iso(),
        "date": date,
        "total": len(papers),
        "papers": papers,
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved {path.name} with {len(papers)} papers.")


def load_history(data_dir):
    """Load all existing rolling history files keyed by offset."""
    history = {}
    for offset in history_offsets():
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
    """Write data/index.json with today's UTC date."""
    today_utc = utc_today()
    index_path = data_dir / "index.json"
    with open(index_path, "w") as f:
        json.dump({"current": today_utc}, f, indent=2)
    print(f"  Updated index.json: current={today_utc}")


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
