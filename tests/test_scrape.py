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

def test_build_query_url_contains_date():
    url = scrape.build_query_url("2025-03-05")
    assert "20250305" in url


def test_build_query_url_contains_category():
    url = scrape.build_query_url("2025-03-05")
    assert "cat:astro-ph.*" in url


def test_build_query_url_pagination():
    url = scrape.build_query_url("2025-03-05", start=500)
    assert "start=500" in url


def test_build_query_url_max_results():
    url = scrape.build_query_url("2025-03-05", max_results=100)
    assert "max_results=100" in url


# ── get_target_date ───────────────────────────────────────────────────────────

def test_get_target_date_passthrough():
    assert scrape.get_target_date("2025-01-15") == "2025-01-15"


def test_get_target_date_format():
    date = scrape.get_target_date()
    # Should be YYYY-MM-DD
    datetime.strptime(date, "%Y-%m-%d")


def test_get_target_date_is_yesterday():
    """Default date should be yesterday relative to ET."""
    et_now = datetime.now(timezone(timedelta(hours=-5)))
    yesterday = (et_now - timedelta(days=1)).strftime("%Y-%m-%d")
    assert scrape.get_target_date() == yesterday


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
