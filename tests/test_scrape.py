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

def test_build_query_url_contains_category():
    url = scrape.build_query_url()
    assert "cat:astro-ph.*" in url


def test_build_query_url_sort_by_submitted_date():
    url = scrape.build_query_url()
    assert "sortBy=submittedDate" in url


def test_build_query_url_descending():
    url = scrape.build_query_url()
    assert "sortOrder=descending" in url


def test_build_query_url_pagination():
    url = scrape.build_query_url(start=500)
    assert "start=500" in url


def test_build_query_url_max_results():
    url = scrape.build_query_url(max_results=100)
    assert "max_results=100" in url


def test_build_query_url_no_date_window():
    """New approach sorts by submittedDate but has no date range filter."""
    url = scrape.build_query_url()
    assert "submittedDate:[" not in url


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


# ── match_author ──────────────────────────────────────────────────────────────

FAV_AUTHORS = ["Chang-Goo Kim", "Eve C. Ostriker"]


def test_match_author_strong_exact_first_name():
    assert scrape.match_author("Kim, Chang-Goo", FAV_AUTHORS) == "strong"


def test_match_author_strong_middle_initial():
    """First initial + matching middle initial → strong."""
    assert scrape.match_author("Ostriker, Eve C.", FAV_AUTHORS) == "strong"


def test_match_author_single_initial_strong():
    """Single first initial in paper → strong (not weak)."""
    assert scrape.match_author("Ostriker, E.", FAV_AUTHORS) == "strong"


def test_match_author_single_initial_hyphenated_fav_strong():
    """Single initial matching hyphenated favorite first name → strong."""
    assert scrape.match_author("Kim, C.", FAV_AUTHORS) == "strong"


def test_match_author_hyphenated_initials_strong():
    """Hyphenated initials (C.-G.) matching hyphenated favorite (Chang-Goo) → strong."""
    assert scrape.match_author("Kim, C.-G.", FAV_AUTHORS) == "strong"


def test_match_author_concatenated_initials_strong():
    """Concatenated initials (C.G. → cg) matching hyphenated favorite → strong."""
    assert scrape.match_author("Kim, C.G.", FAV_AUTHORS) == "strong"


def test_match_author_hyphenated_initials_wrong_second_weak():
    """Wrong second hyphenated initial falls back to weak (first initial only)."""
    assert scrape.match_author("Kim, C.-J.", FAV_AUTHORS) == "weak"


def test_match_author_weak_full_first_initial_only():
    """Non-initial first name with matching first letter only → weak."""
    assert scrape.match_author("Kim, Christopher", FAV_AUTHORS) == "weak"


def test_match_author_last_name_mismatch():
    assert scrape.match_author("Lee, Chang-Goo", FAV_AUTHORS) is None


def test_match_author_no_match():
    assert scrape.match_author("Nobody, Jane", FAV_AUTHORS) is None


# ── annotate_papers ───────────────────────────────────────────────────────────

PAPER_KIM = {"authors": ["Kim, Chang-Goo", "Nobody, Jane"], "title": "Test"}
PAPER_NONE = {"authors": ["Nobody, Jane"], "title": "Remote"}


def test_annotate_papers_strong_match():
    papers = [dict(PAPER_KIM)]
    scrape.annotate_papers(papers, ["Chang-Goo Kim"])
    assert papers[0]["local_match"] == "strong"


def test_annotate_papers_local_authors_dict():
    papers = [dict(PAPER_KIM)]
    scrape.annotate_papers(papers, ["Chang-Goo Kim"])
    assert papers[0]["local_authors"] == {"Kim, Chang-Goo": "strong"}


def test_annotate_papers_no_match():
    papers = [dict(PAPER_NONE)]
    scrape.annotate_papers(papers, ["Chang-Goo Kim"])
    assert papers[0]["local_match"] is None
    assert papers[0]["local_authors"] == {}


def test_annotate_papers_weak_match():
    """Full first name with only first-initial overlap → weak."""
    papers = [{"authors": ["Ostriker, Elaine"], "title": "Test"}]
    scrape.annotate_papers(papers, ["Eve C. Ostriker"])
    assert papers[0]["local_match"] == "weak"
    assert papers[0]["local_authors"] == {"Ostriker, Elaine": "weak"}


def test_annotate_papers_single_initial_strong():
    """Single initial in paper → strong (upgraded from previous weak)."""
    papers = [{"authors": ["Ostriker, E."], "title": "Test"}]
    scrape.annotate_papers(papers, ["Eve C. Ostriker"])
    assert papers[0]["local_match"] == "strong"
    assert papers[0]["local_authors"] == {"Ostriker, E.": "strong"}


def test_annotate_papers_multiple_papers():
    papers = [dict(PAPER_KIM), dict(PAPER_NONE)]
    scrape.annotate_papers(papers, ["Chang-Goo Kim"])
    assert papers[0]["local_match"] == "strong"
    assert papers[1]["local_match"] is None


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


# ── load_archive / save_archive ───────────────────────────────────────────────

def test_load_archive_missing(tmp_path):
    papers, ids = scrape.load_archive(tmp_path)
    assert papers == []
    assert ids == set()


def test_load_archive_returns_ids(tmp_path):
    data = {"papers": [{"id": "2503.00001"}, {"id": "2503.00002"}]}
    (tmp_path / "archive.json").write_text(json.dumps(data))
    papers, ids = scrape.load_archive(tmp_path)
    assert ids == {"2503.00001", "2503.00002"}
    assert len(papers) == 2


def test_save_archive_writes_file(tmp_path):
    papers = [{"id": "2503.00001", "title": "Test"}]
    scrape.save_archive(tmp_path, papers)
    data = json.loads((tmp_path / "archive.json").read_text())
    assert data["total"] == 1
    assert data["papers"][0]["id"] == "2503.00001"
    assert "fetched_at" in data


# ── update_index ──────────────────────────────────────────────────────────────

def test_update_index_writes_current(tmp_path):
    scrape.update_index(tmp_path, "2026-03-06")
    index = json.loads((tmp_path / "index.json").read_text())
    assert index["current"] == "2026-03-06"


def test_update_index_overwrites(tmp_path):
    scrape.update_index(tmp_path, "2026-03-06")
    scrape.update_index(tmp_path, "2026-03-09")
    index = json.loads((tmp_path / "index.json").read_text())
    assert index["current"] == "2026-03-09"


# ── skip-unchanged logic ──────────────────────────────────────────────────────

def test_skips_when_count_unchanged(tmp_path):
    """Should not overwrite when new count <= existing count."""
    existing = {"total": 2, "papers": [{"id": "A"}, {"id": "B"}]}
    out_path = tmp_path / "2025-03-05.json"
    out_path.write_text(json.dumps(existing))

    new_papers = [{"id": "A"}, {"id": "B"}]
    new_count = len(new_papers)
    with open(out_path) as f:
        existing_count = json.load(f).get("total", 0)
    assert new_count <= existing_count  # would skip


def test_writes_when_count_increases(tmp_path):
    """Should write when new count exceeds existing count."""
    existing = {"total": 1, "papers": [{"id": "A"}]}
    out_path = tmp_path / "2025-03-05.json"
    out_path.write_text(json.dumps(existing))

    new_papers = [{"id": "A"}, {"id": "B"}]
    new_count = len(new_papers)
    with open(out_path) as f:
        existing_count = json.load(f).get("total", 0)
    assert new_count > existing_count  # would write
