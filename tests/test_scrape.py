"""Unit tests for scripts/scrape.py."""

import io
import json
import sqlite3
import urllib.error
import urllib.request
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


def test_listing_date_for_published_weekday_before_cutoff():
    """Tuesday before 14:00 ET belongs to Tuesday's listing."""
    assert scrape.listing_date_for_published("2026-03-10T17:59:00Z") == "2026-03-10"


def test_listing_date_for_published_weekday_after_cutoff():
    """Tuesday after 14:00 ET belongs to Wednesday's listing."""
    assert scrape.listing_date_for_published("2026-03-10T18:01:00Z") == "2026-03-11"


def test_listing_date_for_published_friday_after_cutoff():
    """Friday after 14:00 ET belongs to Monday's listing."""
    assert scrape.listing_date_for_published("2026-03-06T19:01:00Z") == "2026-03-09"


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


def test_parse_entry_can_include_listing_date(sample_entry):
    paper = scrape.parse_entry(sample_entry, include_listing_date=True)
    assert paper["_listing_date"] == "2025-03-05"


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


def test_parse_name_parts_dot_only_middle_token():
    """Middle token that is only '.' must not raise IndexError."""
    # arXiv format: last, first .  (dot as middle token)
    first, last, mid = scrape.parse_name_parts("Smith, Jane .")
    assert last == "smith"
    assert first == "jane"
    assert mid is None

    # Princeton format: first . Last
    first, last, mid = scrape.parse_name_parts("Jane . Smith")
    assert last == "smith"
    assert first == "jane"
    assert mid is None


# ── match_author ──────────────────────────────────────────────────────────────

FAV_AUTHORS = ["Chang-Goo Kim", "Eve C. Ostriker"]


def test_match_author_strong_exact_first_name():
    assert scrape.match_author("Kim, Chang-Goo", FAV_AUTHORS) == "strong"


def test_match_author_strong_middle_initial():
    """First initial + matching middle initial → strong."""
    assert scrape.match_author("Ostriker, Eve C.", FAV_AUTHORS) == "strong"


FAV_AUTHORS_EXTENDED = ["Chang-Goo Kim", "Eve C. Ostriker", "Matthew W. Kunz", "George Livadiotis"]


# Chang-Goo Kim (hyphenated first name, no middle initial)
def test_match_author_hyphenated_exact_strong():
    assert scrape.match_author("Kim, Chang-Goo", FAV_AUTHORS_EXTENDED) == "strong"

def test_match_author_hyphenated_initials_strong():
    """C.-G. Kim → strong (hyphenated initials match hyphenated first name)."""
    assert scrape.match_author("Kim, C.-G.", FAV_AUTHORS_EXTENDED) == "strong"

def test_match_author_concatenated_initials_none():
    """C.G. Kim → None (parsed as 'cg', len>=2, conflicts with 'chang-goo')."""
    assert scrape.match_author("Kim, C.G.", FAV_AUTHORS_EXTENDED) is None

def test_match_author_single_initial_hyphenated_fav_none():
    """C. Kim → None (single initial vs hyphenated fav name is too ambiguous)."""
    assert scrape.match_author("Kim, C.", FAV_AUTHORS_EXTENDED) is None


# Matthew W. Kunz (non-hyphenated, has middle initial)
def test_match_author_first_and_middle_initial_strong():
    """M. W. Kunz → strong (first + middle initial both match)."""
    assert scrape.match_author("Kunz, M. W.", FAV_AUTHORS_EXTENDED) == "strong"

def test_match_author_exact_no_middle_strong():
    """Matthew Kunz → strong (exact first name, middle initial not required)."""
    assert scrape.match_author("Kunz, Matthew", FAV_AUTHORS_EXTENDED) == "strong"

def test_match_author_single_initial_fav_has_middle_none():
    """M. Kunz → None (fav has middle initial W. but arXiv omits it — can't confirm)."""
    assert scrape.match_author("Kunz, M.", FAV_AUTHORS_EXTENDED) is None

def test_match_author_conflicting_middle_initial_none():
    """M. A. Kunz vs Matthew W. Kunz → None (middle initials disagree)."""
    assert scrape.match_author("Kunz, M. A.", FAV_AUTHORS_EXTENDED) is None


# George Livadiotis (non-hyphenated, no middle initial)
def test_match_author_single_initial_weak():
    """Single bare initial against fav with no middle initial → weak."""
    assert scrape.match_author("Livadiotis, G.", FAV_AUTHORS_EXTENDED) == "weak"

def test_match_author_extra_middle_initial_none():
    """arXiv provides a middle initial the fav lacks → None (too ambiguous)."""
    assert scrape.match_author("Livadiotis, G. A.", FAV_AUTHORS_EXTENDED) is None


# Generic weak/none
def test_match_author_full_name_conflict_none():
    """Different full first names with same initial → None (unambiguously different person)."""
    assert scrape.match_author("Kim, Christopher", FAV_AUTHORS_EXTENDED) is None
    assert scrape.match_author("Chen, Yujie", ["Yixian Chen"]) is None

def test_match_author_last_name_mismatch():
    assert scrape.match_author("Lee, Chang-Goo", FAV_AUTHORS_EXTENDED) is None

def test_match_author_no_match():
    assert scrape.match_author("Nobody, Jane", FAV_AUTHORS_EXTENDED) is None


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


def test_annotate_papers_full_name_conflict_none():
    """Conflicting full first names → no match."""
    papers = [{"authors": ["Ostriker, Elaine"], "title": "Test"}]
    scrape.annotate_papers(papers, ["Eve C. Ostriker"])
    assert papers[0]["local_match"] is None
    assert papers[0]["local_authors"] == {}


def test_annotate_papers_single_initial_always_weak():
    """Single initial is always weak; add abbreviated form to manual list for strong."""
    papers = [{"authors": ["Livadiotis, G."], "title": "Test"}]
    scrape.annotate_papers(papers, ["George Livadiotis"])
    assert papers[0]["local_match"] == "weak"
    assert papers[0]["local_authors"] == {"Livadiotis, G.": "weak"}


def test_annotate_papers_manual_initial_name_strong():
    """Adding abbreviated form to fav list gives exact match → strong."""
    papers = [{"authors": ["Livadiotis, G."], "title": "Test"}]
    scrape.annotate_papers(papers, ["George Livadiotis", "G. Livadiotis"])
    assert papers[0]["local_match"] == "strong"
    assert papers[0]["local_authors"] == {"Livadiotis, G.": "strong"}


def test_annotate_papers_single_initial_fav_has_middle_none():
    """Single initial, fav has middle initial → None (can't confirm without middle)."""
    papers = [{"authors": ["Ostriker, E."], "title": "Test"}]
    scrape.annotate_papers(papers, ["Eve C. Ostriker"])
    assert papers[0]["local_match"] is None
    assert papers[0]["local_authors"] == {}


def test_annotate_papers_multiple_papers():
    papers = [dict(PAPER_KIM), dict(PAPER_NONE)]
    scrape.annotate_papers(papers, ["Chang-Goo Kim"])
    assert papers[0]["local_match"] == "strong"
    assert papers[1]["local_match"] is None


def test_annotate_discussed_papers_marks_matching_ids():
    papers = [{"id": "2503.00001"}, {"id": "2503.00002"}]
    discussed = {"2503.00002": "2026-05-28"}
    scrape.annotate_discussed_papers(papers, discussed)
    assert papers[0].get("discussed_at") is None
    assert papers[1]["discussed_at"] == "2026-05-28"


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


def test_load_discussed_papers_missing(tmp_path):
    discussed = scrape.load_discussed_papers(tmp_path)
    assert discussed == {}


def test_load_discussed_papers_reads_file(tmp_path):
    data = {
        "papers": [
            {"paper_id": "2503.00001", "discussed_at": "2026-05-28"},
            {"paper_id": "2503.00002", "discussed_at": "2026-05-27"},
        ]
    }
    (tmp_path / "discussed.json").write_text(json.dumps(data))
    discussed = scrape.load_discussed_papers(tmp_path)
    assert discussed == {
        "2503.00001": "2026-05-28",
        "2503.00002": "2026-05-27",
    }


def test_reannotate_applies_discussed_tags(tmp_path):
    data_dir = tmp_path
    repo_root = tmp_path
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "authors.json").write_text(json.dumps({"authors": []}))
    today = {
        "date": "2026-05-28",
        "papers": [
            {"id": "2503.00001", "authors": [], "title": "A"},
            {"id": "2503.00002", "authors": [], "title": "B"},
        ],
    }
    previous = {
        "date": "2026-05-27",
        "papers": [
            {"id": "2503.00001", "authors": [], "title": "A"},
        ]
    }
    discussed = {
        "papers": [
            {"paper_id": "2503.00002", "discussed_at": "2026-05-28"},
        ]
    }
    (tmp_path / "today.json").write_text(json.dumps(today))
    (tmp_path / "today-1.json").write_text(json.dumps(previous))
    (tmp_path / "discussed.json").write_text(json.dumps(discussed))

    scrape.reannotate(data_dir, repo_root)

    updated_today = json.loads((tmp_path / "today.json").read_text())
    updated_previous = json.loads((tmp_path / "today-1.json").read_text())
    assert updated_today["papers"][1]["discussed_at"] == "2026-05-28"
    assert "discussed_at" not in updated_today["papers"][0]
    assert "discussed_at" not in updated_previous["papers"][0]


# ── rolling history helpers ───────────────────────────────────────────────────

def make_paper(paper_id, listing_date="2026-03-09"):
    """Build a minimal paper dict for history tests."""
    return {
        "id": paper_id,
        "authors": [],
        "title": paper_id,
        "abstract": "",
        "primary_category": "astro-ph.GA",
        "categories": ["astro-ph.GA"],
        "arxiv_url": "",
        "pdf_url": "",
        "submitted": listing_date,
        "_listing_date": listing_date,
    }


def test_history_filename():
    assert scrape.history_filename(0) == "today.json"
    assert scrape.history_filename(3) == "today-3.json"


def test_save_listing_writes_file_and_strips_internal_fields(tmp_path):
    papers = [make_paper("2503.00001")]
    scrape.save_listing(tmp_path / "today.json", "2026-03-09", papers)
    data = json.loads((tmp_path / "today.json").read_text())
    assert data["total"] == 1
    assert data["date"] == "2026-03-09"
    assert data["papers"][0]["id"] == "2503.00001"
    assert "_listing_date" not in data["papers"][0]
    assert "fetched_at" in data


def test_load_history_reads_existing_files(tmp_path):
    scrape.save_listing(tmp_path / "today.json", "2026-03-10", [make_paper("A")])
    scrape.save_listing(tmp_path / "today-2.json", "2026-03-06", [make_paper("B")])
    history = scrape.load_history(tmp_path)
    assert set(history) == {0, 2}
    assert scrape.collect_history_ids(history) == {"A", "B"}


def test_rotate_history_drops_oldest(tmp_path):
    for offset in range(6):
        scrape.save_listing(
            tmp_path / scrape.history_filename(offset),
            f"2026-03-0{offset + 1}",
            [make_paper(f"P{offset}")],
        )

    scrape.rotate_history(tmp_path)

    assert not (tmp_path / "today.json").exists()
    assert json.loads((tmp_path / "today-1.json").read_text())["papers"][0]["id"] == "P0"
    assert json.loads((tmp_path / "today-5.json").read_text())["papers"][0]["id"] == "P4"
    archive_db = tmp_path / "archive" / "2026.sqlite"
    with sqlite3.connect(archive_db) as conn:
        archived = conn.execute("SELECT id, listing_date FROM papers").fetchall()
    assert archived == [("P5", "2026-03-06")]


def test_archive_papers_writes_yearly_sqlite_and_manifest(tmp_path):
    paper = make_paper("2503.00001", "2026-03-09")
    paper["authors"] = ["Kim, Chang-Goo"]
    paper["local_match"] = "strong"
    paper["local_authors"] = {"Kim, Chang-Goo": "strong"}
    paper["discussed_at"] = "2026-03-10"

    scrape.archive_papers(tmp_path, "2026-03-09", [paper])

    with sqlite3.connect(tmp_path / "archive" / "2026.sqlite") as conn:
        row = conn.execute(
            """
            SELECT id, listing_date, authors_json, local_match,
                   local_authors_json, discussed_at, search_text
            FROM papers
            """
        ).fetchone()

    assert row[0] == "2503.00001"
    assert row[1] == "2026-03-09"
    assert json.loads(row[2]) == ["Kim, Chang-Goo"]
    assert row[3] == "strong"
    assert json.loads(row[4]) == {"Kim, Chang-Goo": "strong"}
    assert row[5] == "2026-03-10"
    assert "2503.00001" in row[6]

    index = json.loads((tmp_path / "archive" / "index.json").read_text())
    assert index["years"] == [{"year": "2026", "file": "archive/2026.sqlite", "count": 1}]


def test_archive_papers_upserts_duplicate_ids(tmp_path):
    first = make_paper("2503.00001", "2026-03-09")
    second = make_paper("2503.00001", "2026-03-09")
    second["title"] = "Updated title"

    scrape.archive_papers(tmp_path, "2026-03-09", [first])
    scrape.archive_papers(tmp_path, "2026-03-09", [second])

    with sqlite3.connect(tmp_path / "archive" / "2026.sqlite") as conn:
        rows = conn.execute("SELECT id, title FROM papers").fetchall()

    assert rows == [("2503.00001", "Updated title")]


def test_select_new_papers_dedupes_in_order():
    seen = {"A"}
    selected = scrape.select_new_papers([make_paper("A"), make_paper("B"), make_paper("B")], seen)
    assert [paper["id"] for paper in selected] == ["B"]
    assert seen == {"A", "B"}


def test_group_papers_by_listing_date():
    papers = [make_paper("A", "2026-03-09"), make_paper("B", "2026-03-10")]
    groups = scrape.group_papers_by_listing_date(papers)
    assert [paper["id"] for paper in groups["2026-03-09"]] == ["A"]
    assert [paper["id"] for paper in groups["2026-03-10"]] == ["B"]


# ── update_index ──────────────────────────────────────────────────────────────

def test_update_index_writes_current(tmp_path):
    scrape.update_index(tmp_path)
    index = json.loads((tmp_path / "index.json").read_text())
    datetime.strptime(index["current"], "%Y-%m-%d")  # valid YYYY-MM-DD


def test_update_index_overwrites(tmp_path):
    scrape.update_index(tmp_path)
    scrape.update_index(tmp_path)
    index = json.loads((tmp_path / "index.json").read_text())
    assert "current" in index


# ── rolling today.json write logic ────────────────────────────────────────────

def test_appends_when_same_arxiv_date(tmp_path):
    """Second scrape on the same arXiv date appends new papers to today.json."""
    scrape.save_listing(tmp_path / "today.json", "2026-03-09", [make_paper("A")])

    new_count = scrape.update_history_for_date(
        tmp_path,
        "2026-03-09",
        [make_paper("A"), make_paper("B"), make_paper("C")],
    )

    data = json.loads((tmp_path / "today.json").read_text())
    assert new_count == 2
    assert [paper["id"] for paper in data["papers"]] == ["A", "B", "C"]


def test_replaces_when_new_arxiv_date(tmp_path):
    """Scrape for a new arXiv date rotates old today into today-1."""
    scrape.save_listing(tmp_path / "today.json", "2026-03-06", [make_paper("A", "2026-03-06")])

    new_count = scrape.update_history_for_date(tmp_path, "2026-03-09", [make_paper("B")])

    today = json.loads((tmp_path / "today.json").read_text())
    previous = json.loads((tmp_path / "today-1.json").read_text())
    assert new_count == 1
    assert [paper["id"] for paper in today["papers"]] == ["B"]
    assert [paper["id"] for paper in previous["papers"]] == ["A"]


def test_new_date_dedupes_against_rotated_history(tmp_path):
    """A new listing does not duplicate IDs already present in previous days."""
    scrape.save_listing(tmp_path / "today.json", "2026-03-06", [make_paper("A", "2026-03-06")])

    new_count = scrape.update_history_for_date(tmp_path, "2026-03-09", [make_paper("A"), make_paper("B")])

    today = json.loads((tmp_path / "today.json").read_text())
    assert new_count == 1
    assert [paper["id"] for paper in today["papers"]] == ["B"]


# ── fetch_xml retry logic ─────────────────────────────────────────────────────

def _make_urlopen(responses):
    """Build a fake urlopen that yields responses in order (HTTPError or bytes)."""
    call_count = [0]

    def fake_urlopen(req, timeout=None):
        idx = call_count[0]
        call_count[0] += 1
        resp = responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return io.BytesIO(resp)

    return fake_urlopen


def test_fetch_xml_succeeds_immediately(monkeypatch):
    """fetch_xml returns bytes when the first attempt succeeds."""
    monkeypatch.setattr(urllib.request, "urlopen", _make_urlopen([b"<xml/>"]))
    assert scrape.fetch_xml("http://example.com") == b"<xml/>"


def test_fetch_xml_retries_on_503(monkeypatch):
    """fetch_xml retries on HTTP 503 and succeeds on the second attempt."""
    err503 = urllib.error.HTTPError("", 503, "Service Unavailable", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", _make_urlopen([err503, b"<xml/>"]))
    monkeypatch.setattr(scrape.time, "sleep", lambda s: None)
    assert scrape.fetch_xml("http://example.com") == b"<xml/>"


def test_fetch_xml_raises_immediately_on_429(monkeypatch):
    """fetch_xml does not retry on HTTP 429."""
    slept = []
    err429 = urllib.error.HTTPError("", 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", _make_urlopen([err429, b"<xml/>"]))
    monkeypatch.setattr(scrape.time, "sleep", lambda s: slept.append(s))
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        scrape.fetch_xml("http://example.com")
    assert exc_info.value.code == 429
    assert slept == []


def test_fetch_xml_retries_on_timeout(monkeypatch):
    """fetch_xml retries on TimeoutError and succeeds on the second attempt."""
    monkeypatch.setattr(urllib.request, "urlopen", _make_urlopen([TimeoutError("timed out"), b"<xml/>"]))
    monkeypatch.setattr(scrape.time, "sleep", lambda s: None)
    assert scrape.fetch_xml("http://example.com") == b"<xml/>"


def test_fetch_xml_raises_after_max_retries(monkeypatch):
    """fetch_xml raises after exhausting all retries."""
    err503 = urllib.error.HTTPError("", 503, "Service Unavailable", {}, None)
    responses = [err503] * 6  # more than max_retries=5
    monkeypatch.setattr(urllib.request, "urlopen", _make_urlopen(responses))
    monkeypatch.setattr(scrape.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        scrape.fetch_xml("http://example.com")
    assert exc_info.value.code == 503


def test_fetch_xml_raises_immediately_on_404(monkeypatch):
    """fetch_xml does not retry on non-transient HTTP errors like 404."""
    err404 = urllib.error.HTTPError("", 404, "Not Found", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", _make_urlopen([err404]))
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        scrape.fetch_xml("http://example.com")
    assert exc_info.value.code == 404


def test_fetch_xml_ignores_retry_after_header_on_429(monkeypatch):
    """fetch_xml does not sleep on 429 even when Retry-After is present."""
    slept = []
    headers = {"Retry-After": "30"}
    err429 = urllib.error.HTTPError("", 429, "Too Many Requests", headers, None)
    monkeypatch.setattr(urllib.request, "urlopen", _make_urlopen([err429, b"<xml/>"]))
    monkeypatch.setattr(scrape.time, "sleep", lambda s: slept.append(s))
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        scrape.fetch_xml("http://example.com")
    assert exc_info.value.code == 429
    assert slept == []


def test_fetch_latest_papers_default_uses_200_results(monkeypatch):
    """Normal fetches request the configured 200-paper page size."""
    feed = f"""
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <opensearch:totalResults>1</opensearch:totalResults>
      {SAMPLE_ENTRY_XML}
    </feed>
    """.encode()
    requested_urls = []

    def fake_urlopen(req, timeout=None):
        requested_urls.append(req.full_url)
        return io.BytesIO(feed)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    papers = scrape.fetch_latest_papers()

    assert len(papers) == 1
    assert len(requested_urls) == 1
    assert "max_results=200" in requested_urls[0]


def test_bootstrap_history_writes_six_listing_files(tmp_path, monkeypatch):
    """bootstrap_history seeds today.json through today-5.json from grouped papers."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "authors.json").write_text(json.dumps({"authors": []}))
    listing_dates = ["2026-03-10", "2026-03-09", "2026-03-06", "2026-03-05", "2026-03-04", "2026-03-03"]
    fetched = [make_paper(f"P{i}", listing_date) for i, listing_date in enumerate(listing_dates)]

    def fake_fetch(n, include_listing_date=False, max_per_request=scrape.MAX_PER_REQUEST):
        assert n == scrape.BOOTSTRAP_FETCH_SIZE
        assert include_listing_date is True
        assert max_per_request == scrape.BOOTSTRAP_FETCH_SIZE
        return fetched

    monkeypatch.setattr(scrape, "fetch_latest_papers", fake_fetch)

    scrape.bootstrap_history(tmp_path, tmp_path)

    assert json.loads((tmp_path / "today.json").read_text())["date"] == "2026-03-10"
    assert json.loads((tmp_path / "today-5.json").read_text())["date"] == "2026-03-03"
    assert json.loads((tmp_path / "today.json").read_text())["papers"][0]["id"] == "P0"
