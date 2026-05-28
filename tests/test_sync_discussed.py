"""Unit tests for scripts/sync_discussed.py."""

import json
import sys
from pathlib import Path

import pytest

# Add scripts/ to path so we can import without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import sync_discussed


def test_parse_issue_body_discussed_fields():
    body = """paper_id: 2605.12345
title: Example Paper
arxiv_url: https://arxiv.org/abs/2605.12345
authors: Alice A; Bob B
"""
    parsed = sync_discussed.parse_issue_body(body)
    assert parsed == {
        "paper_id": "2605.12345",
        "title": "Example Paper",
        "arxiv_url": "https://arxiv.org/abs/2605.12345",
        "authors": ["Alice A", "Bob B"],
    }


def test_parse_issue_body_missing_field_returns_none():
    body = """paper_id: 2605.12345
title: Example Paper
authors: Alice A
"""
    assert sync_discussed.parse_issue_body(body) is None


def test_sync_discussed_writes_file_and_closes_issues(tmp_path, monkeypatch):
    issues = [
        {
            "number": 10,
            "title": "Discussed paper: 2605.00001",
            "body": (
                "paper_id: 2605.00001\n"
                "title: First Paper\n"
                "arxiv_url: https://arxiv.org/abs/2605.00001\n"
                "authors: Alice A; Bob B\n"
            ),
            "created_at": "2026-05-28T19:00:25Z",
        },
        {
            "number": 11,
            "title": "Discussed paper: 2605.00001",
            "body": (
                "paper_id: 2605.00001\n"
                "title: First Paper Updated\n"
                "arxiv_url: https://arxiv.org/abs/2605.00001\n"
                "authors: Alice A; Bob B\n"
            ),
            "created_at": "2026-05-28T19:01:25Z",
        },
        {
            "number": 12,
            "title": "Not discussed",
            "body": "",
            "created_at": "2026-05-28T19:02:25Z",
        },
    ]
    closed = []
    data_path = tmp_path / "discussed.json"

    monkeypatch.setattr(sync_discussed, "list_open_issues", lambda owner, repo, token: issues)
    monkeypatch.setattr(sync_discussed, "close_issue", lambda owner, repo, token, issue_number: closed.append(issue_number))

    processed = sync_discussed.sync_discussed("owner", "repo", "token", data_path)

    assert processed == 2
    assert closed == [10, 11]

    payload = json.loads(data_path.read_text())
    assert len(payload["papers"]) == 1
    assert payload["papers"][0]["issue_number"] == 11
    assert payload["papers"][0]["discussed_at"] == "2026-05-28"
    assert payload["papers"][0]["title"] == "First Paper Updated"


def test_sync_discussed_no_matches_does_not_write(tmp_path, monkeypatch):
    issues = [{"number": 12, "title": "Unrelated", "body": "", "created_at": "2026-05-28T19:02:25Z"}]
    data_path = tmp_path / "discussed.json"

    monkeypatch.setattr(sync_discussed, "list_open_issues", lambda owner, repo, token: issues)
    monkeypatch.setattr(sync_discussed, "close_issue", lambda *args, **kwargs: pytest.fail("should not close"))

    processed = sync_discussed.sync_discussed("owner", "repo", "token", data_path)

    assert processed == 0
    assert not data_path.exists()
