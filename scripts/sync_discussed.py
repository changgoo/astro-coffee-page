#!/usr/bin/env python3
"""Sync discussed-paper GitHub issues into data/discussed.json."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ISSUE_TITLE_PREFIX = "Discussed paper: "
ISSUES_PER_PAGE = 100


def parse_issue_body(body: str) -> dict[str, object] | None:
    """Parse the machine-readable paper fields from an issue body."""
    result: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([a-z_]+):\s*(.*)$", line, flags=re.IGNORECASE)
        if not match:
            continue
        result[match.group(1).lower()] = match.group(2).strip()

    required = ("paper_id", "title", "arxiv_url", "authors")
    if any(not result.get(field) for field in required):
        return None

    return {
        "paper_id": result["paper_id"],
        "title": result["title"],
        "arxiv_url": result["arxiv_url"],
        "authors": [a for a in re.split(r"\s*;\s*", result["authors"]) if a],
    }


def github_request(method: str, url: str, token: str, payload: dict | None = None) -> object:
    """Make an authenticated GitHub API request and return decoded JSON."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method.upper(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "astro-coffee-page",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def list_open_issues(owner: str, repo: str, token: str) -> list[dict]:
    """List open issues in the repository, handling pagination."""
    issues: list[dict] = []
    page = 1
    while True:
        params = urllib.parse.urlencode(
            {
                "state": "open",
                "per_page": ISSUES_PER_PAGE,
                "page": page,
            }
        )
        url = f"https://api.github.com/repos/{owner}/{repo}/issues?{params}"
        batch = github_request("GET", url, token) or []
        if not batch:
            break
        issues.extend(batch)
        if len(batch) < ISSUES_PER_PAGE:
            break
        page += 1
    return issues


def close_issue(owner: str, repo: str, token: str, issue_number: int) -> None:
    """Close a GitHub issue."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    github_request("PATCH", url, token, {"state": "closed"})


def load_existing_discussed(data_path: Path) -> dict:
    """Load the existing discussed.json payload or a default empty structure."""
    if not data_path.exists():
        return {"generated_at": None, "papers": []}
    with data_path.open() as f:
        data = json.load(f)
    if "papers" not in data:
        data["papers"] = []
    if "generated_at" not in data:
        data["generated_at"] = None
    return data


def sync_discussed(owner: str, repo: str, token: str, data_path: Path) -> int:
    """Sync discussed issues into discussed.json and close processed issues."""
    open_issues = list_open_issues(owner, repo, token)
    open_issues.sort(key=lambda issue: issue.get("created_at", ""))

    existing = load_existing_discussed(data_path)
    by_paper_id = {
        paper["paper_id"]: paper
        for paper in existing.get("papers", [])
        if paper.get("paper_id")
    }

    processed_issue_numbers: list[int] = []
    for issue in open_issues:
        if issue.get("pull_request"):
            continue
        if not (issue.get("title") or "").startswith(ISSUE_TITLE_PREFIX):
            continue

        parsed = parse_issue_body(issue.get("body") or "")
        if not parsed:
            continue

        discussed_at = (issue.get("created_at") or "")[:10]
        paper_id = str(parsed["paper_id"])
        by_paper_id[paper_id] = {
            **parsed,
            "discussed_at": discussed_at,
            "issue_number": issue["number"],
        }
        processed_issue_numbers.append(issue["number"])

    if not processed_issue_numbers:
        return 0

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "papers": sorted(
            by_paper_id.values(),
            key=lambda paper: (paper.get("discussed_at", ""), paper.get("issue_number", 0)),
            reverse=True,
        ),
    }

    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, indent=2) + "\n")

    for issue_number in processed_issue_numbers:
        close_issue(owner, repo, token, issue_number)

    return len(processed_issue_numbers)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo:
        print("GITHUB_REPOSITORY is required", file=sys.stderr)
        return 1
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 1

    owner, repo_name = repo.split("/", 1)
    repo_root = Path(__file__).resolve().parent.parent
    data_path = repo_root / "data" / "discussed.json"
    processed = sync_discussed(owner, repo_name, token, data_path)
    print(f"Processed {processed} discussed issue(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
