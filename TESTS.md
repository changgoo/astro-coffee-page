# Test Suite

Run all tests with:

```bash
python -m pytest tests/ -v
```

No network access is required — all HTTP calls are mocked.

---

## `tests/test_scrape.py` — arXiv scraper (20 tests)

Tests for `scripts/scrape.py`. Uses a minimal Atom XML fixture that mirrors the
structure returned by the arXiv API.

### `build_query_url`

| Test | What it checks |
|------|----------------|
| `test_build_query_url_contains_date` | The date `2025-03-05` is compacted to `20250305` in the URL |
| `test_build_query_url_contains_category` | The query targets `cat:astro-ph.*` |
| `test_build_query_url_pagination` | A non-zero `start` offset appears in the URL |
| `test_build_query_url_max_results` | The `max_results` parameter is reflected in the URL |

### `get_target_date`

| Test | What it checks |
|------|----------------|
| `test_get_target_date_passthrough` | An explicit date string is returned unchanged |
| `test_get_target_date_format` | The default date is a valid `YYYY-MM-DD` string |
| `test_get_target_date_is_yesterday` | The default date is yesterday relative to US Eastern time, matching arXiv's announcement schedule |

### `parse_entry`

Uses a single Atom `<entry>` with known values (ID `2503.12345`, two authors,
two categories, extra whitespace in title and abstract).

| Test | What it checks |
|------|----------------|
| `test_parse_entry_id` | arXiv ID is extracted from the `<id>` URL and version suffix is stripped |
| `test_parse_entry_title_normalized` | Extra internal whitespace in the title is collapsed to single spaces |
| `test_parse_entry_authors` | All author names are extracted in order |
| `test_parse_entry_abstract_normalized` | Leading/trailing whitespace in the abstract is stripped |
| `test_parse_entry_primary_category` | The `arxiv:primary_category` attribute is read correctly |
| `test_parse_entry_categories_primary_first` | The primary category appears first in the `categories` list; secondary categories are included |
| `test_parse_entry_urls` | Abstract and PDF URLs are constructed correctly from the arXiv ID |
| `test_parse_entry_submitted_date` | The `published` timestamp is truncated to `YYYY-MM-DD` |

### `update_index`

Uses pytest's `tmp_path` fixture for isolated file I/O; no real `data/` directory
is touched.

| Test | What it checks |
|------|----------------|
| `test_update_index_creates_index` | `index.json` is created and contains the new date |
| `test_update_index_no_duplicates` | Calling with the same date twice leaves only one entry |
| `test_update_index_sorted_descending` | Dates added out of order are sorted newest-first |
| `test_update_index_max_days` | After 15 insertions with `max_days=10`, only 10 entries remain |
| `test_update_index_removes_old_files` | A `.json` data file for a pruned date is deleted from disk |

---

## `tests/test_scrape_authors.py` — Princeton Astro people scraper (7 tests)

Tests for `scripts/scrape_authors.py`. All HTTP requests are mocked via
`unittest.mock.patch` on the `cloudscraper` session; no real network traffic is
generated. The helper `make_html(names)` builds minimal HTML that matches the
Princeton site's CSS class structure.

### `scrape_page`

| Test | What it checks |
|------|----------------|
| `test_scrape_page_returns_names` | Names inside the expected `<div>`/`<span>` structure are returned |
| `test_scrape_page_strips_whitespace` | Leading and trailing whitespace around names is stripped |
| `test_scrape_page_returns_empty_on_http_error` | An HTTP error (e.g. 403) from `raise_for_status` returns an empty list instead of raising |
| `test_scrape_page_returns_empty_on_network_error` | A network-level exception (e.g. timeout) returns an empty list |
| `test_scrape_page_skips_entries_without_name_span` | Person `<div>`s that lack the expected `<span>` are silently skipped |

### `main` (file writing and deduplication)

| Test | What it checks |
|------|----------------|
| `test_main_writes_authors_json` | `main()` creates a valid `config/authors.json` with the correct `{"authors": [...]}` structure; the output path is redirected to `tmp_path` so the real config file is not modified |
| `test_main_deduplicates_names` | Names returned by multiple pages are deduplicated while preserving order |
