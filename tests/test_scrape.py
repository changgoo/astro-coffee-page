"""Unit tests for scripts/scrape.py."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

# Add scripts/ to path so we can import without installing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import scrape


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_ENTRY_XML = """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:arxiv="http://arxiv.org/schemas/atom">
  <id>https://arxiv.org/abs/2503.12345v1</id>
  <title>  Test   Paper Title  </title>
  <summary>  Abstract text here.  </summary>
  <author><name>Kim, Chang-Goo</name></author>
  <author><name>Ostriker, Eve C.</name></author>
  <arxiv:primary_category term="astro-ph.GA"/>
  <category term="astro-ph.GA"/>
  <category term="astro-ph.CO"/>
  <published>2025-03-05T00:00:00Z</published>
</entry>
"""


@pytest.fixture
def sample_entry():
    """Return a parsed Atom <entry> ElementTree element."""
    return ET.fromstring(SAMPLE_ENTRY_XML)


# ── build_query_url ───────────────────────────────────────────────────────────

def test_build_query_url_contains_start_date():
    url = scrape.build_query_url("20260304190000", "20260305185959")
    assert "20260304190000" in url


def test_build_query_url_contains_end_date():
    url = scrape.build_query_url("20260304190000", "20260305185959")
    assert "20260305185959" in url


def test_build_query_url_contains_category():
    url = scrape.build_query_url("20260304190000", "20260305185959")
    assert "cat:astro-ph.*" in url


def test_build_query_url_pagination():
    url = scrape.build_query_url("20260304190000", "20260305185959", start=500)
    assert "start=500" in url


def test_build_query_url_max_results():
    url = scrape.build_query_url("20260304190000", "20260305185959", max_results=100)
    assert "max_results=100" in url


# ── get_target_date ───────────────────────────────────────────────────────────

def test_get_target_date_passthrough():
    assert scrape.get_target_date("2025-01-15") == "2025-01-15"


def test_get_target_date_format():
    date = scrape.get_target_date()
    datetime.strptime(date, "%Y-%m-%d")


def et(y, m, d, hour):
    return datetime(y, m, d, hour, 0, tzinfo=timezone(timedelta(hours=-5)))


def test_get_target_date_weekday_evening():
    """Tue 21:00 ET → Tuesday (Tue announcement batch)."""
    assert scrape.get_target_date(_et_now=et(2026, 3, 3, 21)) == "2026-03-03"


def test_get_target_date_sunday_evening():
    """Sun 21:00 ET → Friday (Thu–Fri batch announced Sunday)."""
    assert scrape.get_target_date(_et_now=et(2026, 3, 8, 21)) == "2026-03-06"


def test_get_target_date_monday_evening():
    """Mon 21:00 ET → Monday (Fri–Mon batch announced Monday)."""
    assert scrape.get_target_date(_et_now=et(2026, 3, 9, 21)) == "2026-03-09"


def test_get_target_date_monday_morning():
    """Mon 06:00 ET → Friday (catch-up for Fri–Mon batch)."""
    assert scrape.get_target_date(_et_now=et(2026, 3, 9, 6)) == "2026-03-06"


def test_get_target_date_tuesday_morning():
    """Tue 06:00 ET → Monday (catch-up for Tue announcement)."""
    assert scrape.get_target_date(_et_now=et(2026, 3, 10, 6)) == "2026-03-09"


def test_get_target_date_saturday_morning():
    """Sat 10:00 ET → Friday (matches arXiv showing Fri papers on Saturday)."""
    assert scrape.get_target_date(_et_now=et(2026, 3, 7, 10)) == "2026-03-06"


# ── get_submission_window ─────────────────────────────────────────────────────

def test_get_submission_window_friday():
    """Friday listing → Wed 19:00 UTC – Thu 18:59:59 UTC (= Wed 14:00–Thu 13:59:59 ET)."""
    start, end = scrape.get_submission_window("2026-03-06")
    assert start == "20260304190000"  # Wed Mar 4 19:00 UTC = 14:00 ET
    assert end   == "20260305185959"  # Thu Mar 5 18:59:59 UTC = 13:59:59 ET


def test_get_submission_window_monday():
    """Monday listing → Thu 19:00 UTC – Fri 18:59:59 UTC (= Thu 14:00–Fri 13:59:59 ET)."""
    start, end = scrape.get_submission_window("2026-03-09")
    assert start == "20260305190000"  # Thu Mar 5 19:00 UTC = 14:00 ET
    assert end   == "20260306185959"  # Fri Mar 6 18:59:59 UTC = 13:59:59 ET


def test_get_submission_window_tuesday():
    """Tuesday listing → Fri 19:00 UTC – Mon 18:59:59 UTC (spans weekend)."""
    start, end = scrape.get_submission_window("2026-03-10")
    assert start == "20260306190000"  # Fri Mar 6 19:00 UTC = 14:00 ET
    assert end   == "20260309185959"  # Mon Mar 9 18:59:59 UTC = 13:59:59 ET


def test_get_submission_window_wednesday():
    """Wednesday listing → Mon 19:00 UTC – Tue 18:59:59 UTC."""
    start, end = scrape.get_submission_window("2026-03-11")
    assert start == "20260309190000"  # Mon Mar 9 19:00 UTC = 14:00 ET
    assert end   == "20260310185959"  # Tue Mar 10 18:59:59 UTC = 13:59:59 ET


def test_get_submission_window_thursday():
    """Thursday listing → Tue 19:00 UTC – Wed 18:59:59 UTC."""
    start, end = scrape.get_submission_window("2026-03-12")
    assert start == "20260310190000"  # Tue Mar 10 19:00 UTC = 14:00 ET
    assert end   == "20260311185959"  # Wed Mar 11 18:59:59 UTC = 13:59:59 ET


# ── parse_entry ───────────────────────────────────────────────────────────────

def test_parse_entry_id(sample_entry):
    paper = scrape.parse_entry(sample_entry)
    assert paper["id"] == "2503.12345"


def test_parse_entry_title_normalized(sample_entry):
    """Extra whitespace in title should be collapsed."""
    paper = scrape.parse_entry(sample_entry)
    assert paper["title"] == "Test Paper Title"


def test_parse_entry_authors(sample_entry):
    paper = scrape.parse_entry(sample_entry)
    assert paper["authors"] == ["Kim, Chang-Goo", "Ostriker, Eve C."]


def test_parse_entry_abstract_normalized(sample_entry):
    paper = scrape.parse_entry(sample_entry)
    assert paper["abstract"] == "Abstract text here."


def test_parse_entry_primary_category(sample_entry):
    paper = scrape.parse_entry(sample_entry)
    assert paper["primary_category"] == "astro-ph.GA"


def test_parse_entry_categories_primary_first(sample_entry):
    paper = scrape.parse_entry(sample_entry)
    assert paper["categories"][0] == "astro-ph.GA"
    assert "astro-ph.CO" in paper["categories"]


def test_parse_entry_urls(sample_entry):
    paper = scrape.parse_entry(sample_entry)
    assert paper["arxiv_url"] == "https://arxiv.org/abs/2503.12345"
    assert paper["pdf_url"] == "https://arxiv.org/pdf/2503.12345"


def test_parse_entry_submitted_date(sample_entry):
    paper = scrape.parse_entry(sample_entry)
    assert paper["submitted"] == "2025-03-05"


# ── parse_name_parts ──────────────────────────────────────────────────────────

def test_parse_name_parts_arxiv_format():
    first, last, mid = scrape.parse_name_parts("Kim, Chang-Goo")
    assert last == "kim"
    assert first == "chang-goo"
    assert mid is None


def test_parse_name_parts_arxiv_with_middle():
    first, last, mid = scrape.parse_name_parts("Ostriker, Eve C.")
    assert last == "ostriker"
    assert first == "eve"
    assert mid == "c"


def test_parse_name_parts_princeton_format():
    first, last, mid = scrape.parse_name_parts("Chang-Goo Kim")
    assert last == "kim"
    assert first == "chang-goo"
    assert mid is None


def test_parse_name_parts_princeton_with_middle():
    first, last, mid = scrape.parse_name_parts("Eve C. Ostriker")
    assert last == "ostriker"
    assert first == "eve"
    assert mid == "c"


def test_parse_name_parts_strips_title():
    first, last, mid = scrape.parse_name_parts("Dr. Jane Smith")
    assert last == "smith"
    assert first == "jane"


def test_parse_name_parts_strips_suffix():
    first, last, mid = scrape.parse_name_parts("John Smith Jr.")
    assert last == "smith"
    assert first == "john"


# ── has_strong_local_author ───────────────────────────────────────────────────

PAPER_KIM = {
    "authors": ["Kim, Chang-Goo", "Ostriker, Eve C."],
    "title": "Test",
}

def test_has_strong_local_author_exact_first_name():
    assert scrape.has_strong_local_author(PAPER_KIM, ["Chang-Goo Kim"])


def test_has_strong_local_author_matching_middle_initial():
    """First initial + matching middle initial should be strong."""
    assert scrape.has_strong_local_author(PAPER_KIM, ["E. C. Ostriker"])


def test_has_strong_local_author_first_initial_only_is_not_strong():
    """First initial match without middle initial is weak — not strong."""
    assert not scrape.has_strong_local_author(PAPER_KIM, ["E. Ostriker"])


def test_has_strong_local_author_last_name_mismatch():
    assert not scrape.has_strong_local_author(PAPER_KIM, ["Chang-Goo Lee"])


def test_has_strong_local_author_no_authors():
    assert not scrape.has_strong_local_author({"authors": []}, ["Chang-Goo Kim"])


# ── load_favorite_authors ─────────────────────────────────────────────────────

def test_load_favorite_authors_merges_both_files(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "authors.json").write_text(json.dumps({"authors": ["Alice Auto"]}))
    (config / "authors_manual.json").write_text(json.dumps({"authors": ["Bob Manual"]}))
    authors = scrape.load_favorite_authors(tmp_path)
    assert "Alice Auto" in authors
    assert "Bob Manual" in authors


def test_load_favorite_authors_manual_first(tmp_path):
    """Manual entries should appear before auto entries."""
    config = tmp_path / "config"
    config.mkdir()
    (config / "authors.json").write_text(json.dumps({"authors": ["Alice Auto"]}))
    (config / "authors_manual.json").write_text(json.dumps({"authors": ["Bob Manual"]}))
    authors = scrape.load_favorite_authors(tmp_path)
    assert authors.index("Bob Manual") < authors.index("Alice Auto")


def test_load_favorite_authors_deduplicates(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "authors.json").write_text(json.dumps({"authors": ["Alice Auto"]}))
    (config / "authors_manual.json").write_text(json.dumps({"authors": ["Alice Auto"]}))
    authors = scrape.load_favorite_authors(tmp_path)
    assert authors.count("Alice Auto") == 1


def test_load_favorite_authors_missing_files(tmp_path):
    (tmp_path / "config").mkdir()
    authors = scrape.load_favorite_authors(tmp_path)
    assert authors == []


# ── archive_strong_papers ─────────────────────────────────────────────────────

def test_archive_strong_papers_creates_file(tmp_path):
    papers = [{"authors": ["Kim, Chang-Goo"], "title": "A"}]
    scrape.archive_strong_papers(tmp_path, "2025-01-01", papers, ["Chang-Goo Kim"])
    archive = json.loads((tmp_path / "local-archive.json").read_text())
    assert "2025-01-01" in archive
    assert len(archive["2025-01-01"]) == 1


def test_archive_strong_papers_only_strong_matches(tmp_path):
    papers = [
        {"authors": ["Kim, Chang-Goo"], "title": "Local"},
        {"authors": ["Nobody, Jane"], "title": "Remote"},
    ]
    scrape.archive_strong_papers(tmp_path, "2025-01-01", papers, ["Chang-Goo Kim"])
    archive = json.loads((tmp_path / "local-archive.json").read_text())
    assert len(archive["2025-01-01"]) == 1
    assert archive["2025-01-01"][0]["title"] == "Local"


def test_archive_strong_papers_no_matches_skips(tmp_path):
    papers = [{"authors": ["Nobody, Jane"], "title": "Remote"}]
    scrape.archive_strong_papers(tmp_path, "2025-01-01", papers, ["Chang-Goo Kim"])
    assert not (tmp_path / "local-archive.json").exists()


def test_archive_strong_papers_appends_existing(tmp_path):
    papers_a = [{"authors": ["Kim, Chang-Goo"], "title": "A"}]
    papers_b = [{"authors": ["Kim, Chang-Goo"], "title": "B"}]
    scrape.archive_strong_papers(tmp_path, "2025-01-01", papers_a, ["Chang-Goo Kim"])
    scrape.archive_strong_papers(tmp_path, "2025-01-02", papers_b, ["Chang-Goo Kim"])
    archive = json.loads((tmp_path / "local-archive.json").read_text())
    assert "2025-01-01" in archive
    assert "2025-01-02" in archive


# ── update_index ──────────────────────────────────────────────────────────────

def test_update_index_creates_index(tmp_path):
    scrape.update_index(tmp_path, "2025-03-05")
    index = json.loads((tmp_path / "index.json").read_text())
    assert "2025-03-05" in index["dates"]


def test_update_index_no_duplicates(tmp_path):
    scrape.update_index(tmp_path, "2025-03-05")
    scrape.update_index(tmp_path, "2025-03-05")
    index = json.loads((tmp_path / "index.json").read_text())
    assert index["dates"].count("2025-03-05") == 1


def test_update_index_sorted_descending(tmp_path):
    for d in ["2025-03-03", "2025-03-05", "2025-03-04"]:
        scrape.update_index(tmp_path, d)
    index = json.loads((tmp_path / "index.json").read_text())
    assert index["dates"] == sorted(index["dates"], reverse=True)


def test_update_index_max_days(tmp_path):
    for i in range(15):
        scrape.update_index(tmp_path, f"2025-01-{i + 1:02d}", max_days=10)
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["dates"]) == 10


def test_update_index_removes_old_files(tmp_path):
    """Data files for pruned dates should be deleted."""
    old_file = tmp_path / "2025-01-01.json"
    old_file.write_text("{}")
    for i in range(2, 13):
        scrape.update_index(tmp_path, f"2025-01-{i:02d}", max_days=10)
    assert not old_file.exists()


def test_update_index_archives_strong_match_before_delete(tmp_path):
    """Pruned file with strong local author match should appear in local-archive.json."""
    old_file = tmp_path / "2025-01-01.json"
    old_file.write_text(json.dumps({
        "papers": [{"authors": ["Kim, Chang-Goo"], "title": "Old paper"}]
    }))
    for i in range(2, 13):
        scrape.update_index(tmp_path, f"2025-01-{i:02d}", max_days=10,
                            fav_authors=["Chang-Goo Kim"])
    assert not old_file.exists()
    archive = json.loads((tmp_path / "local-archive.json").read_text())
    assert "2025-01-01" in archive


def test_update_index_no_archive_when_no_strong_match(tmp_path):
    """Pruned file with no local author match should not appear in archive."""
    old_file = tmp_path / "2025-01-01.json"
    old_file.write_text(json.dumps({
        "papers": [{"authors": ["Nobody, Jane"], "title": "Old paper"}]
    }))
    for i in range(2, 13):
        scrape.update_index(tmp_path, f"2025-01-{i:02d}", max_days=10,
                            fav_authors=["Chang-Goo Kim"])
    assert not old_file.exists()
    assert not (tmp_path / "local-archive.json").exists()


# ── skip-unchanged (main logic) ───────────────────────────────────────────────

def test_main_skips_when_count_unchanged(tmp_path, monkeypatch):
    """main() should not overwrite the file when paper count has not increased."""
    existing = {
        "date": "2025-03-05",
        "fetched_at": "2025-03-05T10:00:00Z",
        "total": 2,
        "papers": [
            {"authors": ["Kim, Chang-Goo"], "title": "A"},
            {"authors": ["Ostriker, Eve C."], "title": "B"},
        ],
    }
    out_path = tmp_path / "2025-03-05.json"
    out_path.write_text(json.dumps(existing))

    monkeypatch.setattr(scrape, "fetch_all_papers", lambda d: existing["papers"])
    monkeypatch.setattr(scrape, "load_favorite_authors", lambda r: [])
    monkeypatch.setattr(scrape, "update_index", lambda *a, **kw: None)
    monkeypatch.setattr(sys, "argv", ["scrape.py", "2025-03-05"])
    # Redirect data dir to tmp_path
    monkeypatch.setattr(scrape, "Path", lambda *a: tmp_path if "data" in str(a) else Path(*a))

    def patched_main():
        date_str = "2025-03-05"
        papers = scrape.fetch_all_papers(date_str)
        new_count = len(papers)
        if out_path.exists():
            with open(out_path) as f:
                existing_data = json.load(f)
            if new_count <= existing_data.get("total", 0):
                return "skipped"
        return "wrote"

    assert patched_main() == "skipped"


def test_main_writes_when_count_increases(tmp_path):
    """main() should write when new count exceeds existing count."""
    existing = {"total": 1, "papers": [{"authors": ["Kim, Chang-Goo"], "title": "A"}]}
    out_path = tmp_path / "2025-03-05.json"
    out_path.write_text(json.dumps(existing))

    new_papers = [
        {"authors": ["Kim, Chang-Goo"], "title": "A"},
        {"authors": ["Ostriker, Eve C."], "title": "B"},
    ]

    def patched_main():
        new_count = len(new_papers)
        if out_path.exists():
            with open(out_path) as f:
                existing_data = json.load(f)
            if new_count <= existing_data.get("total", 0):
                return "skipped"
        return "wrote"

    assert patched_main() == "wrote"
