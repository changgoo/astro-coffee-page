"""Discussed-paper loading and annotation."""

import json


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


def annotate_discussed_papers(papers, discussed_papers):
    """Add discussed_at to papers whose IDs appear in discussed_papers."""
    for paper in papers:
        discussed_at = discussed_papers.get(paper.get("id"))
        if discussed_at:
            paper["discussed_at"] = discussed_at
