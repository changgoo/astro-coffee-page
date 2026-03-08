# Test Suite

Run all tests with:

```bash
python -m pytest tests/ -v
```

No network access is required — all HTTP calls are mocked.

---

## `tests/test_scrape.py` — arXiv scraper (54 tests)

Tests for `scripts/scrape.py`. Uses a minimal Atom XML fixture that mirrors the
structure returned by the arXiv API.

### `build_query_url`

| Test | What it checks |
|------|----------------|
| `test_build_query_url_contains_start_date` | The start datetime string appears in the URL |
| `test_build_query_url_contains_end_date` | The end datetime string appears in the URL |
| `test_build_query_url_contains_category` | The query targets `cat:astro-ph.*` |
| `test_build_query_url_pagination` | A non-zero `start` offset appears in the URL |
| `test_build_query_url_max_results` | The `max_results` parameter is reflected in the URL |

### `get_target_date`

| Test | What it checks |
|------|----------------|
| `test_get_target_date_passthrough` | An explicit date string is returned unchanged |
| `test_get_target_date_format` | The default date is a valid `YYYY-MM-DD` string |
| `test_get_target_date_weekday_evening` | Tue 21:00 ET → Tuesday (nightly run catches Tue announcement) |
| `test_get_target_date_sunday_evening` | Sun 21:00 ET → Friday (Thu–Fri batch announced Sunday) |
| `test_get_target_date_monday_evening` | Mon 21:00 ET → Monday (Fri–Mon batch announced Monday) |
| `test_get_target_date_monday_morning` | Mon 06:00 ET → Friday (morning catch-up for Fri–Mon batch) |
| `test_get_target_date_tuesday_morning` | Tue 06:00 ET → Monday (morning catch-up) |
| `test_get_target_date_saturday_morning` | Sat 10:00 ET → Friday (matches arXiv showing Fri papers on Saturday) |

### `get_submission_window`

The arXiv API `submittedDate` is in UTC. arXiv's 14:00 ET cutoff = 19:00 UTC (EST = UTC−5, no DST).

| Test | What it checks |
|------|----------------|
| `test_get_submission_window_friday` | Friday listing → Wed 19:00 UTC – Thu 18:59:59 UTC |
| `test_get_submission_window_monday` | Monday listing → Thu 19:00 UTC – Fri 18:59:59 UTC |
| `test_get_submission_window_tuesday` | Tuesday listing → Fri 19:00 UTC – Mon 18:59:59 UTC (spans weekend) |
| `test_get_submission_window_wednesday` | Wednesday listing → Mon 19:00 UTC – Tue 18:59:59 UTC |
| `test_get_submission_window_thursday` | Thursday listing → Tue 19:00 UTC – Wed 18:59:59 UTC |

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

### `parse_name_parts`

| Test | What it checks |
|------|----------------|
| `test_parse_name_parts_arxiv_format` | arXiv `"Last, First"` format is split correctly |
| `test_parse_name_parts_arxiv_with_middle` | Middle initial is extracted from arXiv format |
| `test_parse_name_parts_princeton_format` | Princeton `"First Last"` format is split correctly |
| `test_parse_name_parts_princeton_with_middle` | Middle initial is extracted from Princeton format |
| `test_parse_name_parts_strips_title` | Honorific titles (Dr., Prof.) are removed |
| `test_parse_name_parts_strips_suffix` | Name suffixes (Jr., III) are removed |

### `has_strong_local_author`

| Test | What it checks |
|------|----------------|
| `test_has_strong_local_author_exact_first_name` | Last + exact first name is a strong match |
| `test_has_strong_local_author_matching_middle_initial` | Last + first initial + agreeing middle initial is a strong match |
| `test_has_strong_local_author_first_initial_only_is_not_strong` | Last + first initial alone is not a strong match (only weak) |
| `test_has_strong_local_author_last_name_mismatch` | Last name mismatch returns no match |
| `test_has_strong_local_author_no_authors` | Paper with empty author list returns no match |

### `load_favorite_authors`

| Test | What it checks |
|------|----------------|
| `test_load_favorite_authors_merges_both_files` | Both `authors.json` and `authors_manual.json` are loaded |
| `test_load_favorite_authors_manual_first` | Manual entries appear before auto-scraped entries |
| `test_load_favorite_authors_deduplicates` | Duplicate names across both files appear only once |
| `test_load_favorite_authors_missing_files` | Missing config files return an empty list without error |

### `archive_strong_papers`

| Test | What it checks |
|------|----------------|
| `test_archive_strong_papers_creates_file` | `local-archive.json` is created with the matching papers keyed by date |
| `test_archive_strong_papers_only_strong_matches` | Only strong-match papers are archived; others are excluded |
| `test_archive_strong_papers_no_matches_skips` | No file is created when there are no strong matches |
| `test_archive_strong_papers_appends_existing` | A second call for a different date adds to the existing archive |

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
| `test_update_index_archives_strong_match_before_delete` | Strong local author matches are saved to `local-archive.json` before the day file is deleted |
| `test_update_index_no_archive_when_no_strong_match` | Day files with no strong matches are deleted without creating an archive entry |

### Skip-unchanged logic

| Test | What it checks |
|------|----------------|
| `test_main_skips_when_count_unchanged` | When the fetched paper count does not exceed the existing count, the file is not rewritten |
| `test_main_writes_when_count_increases` | When the fetched count exceeds the existing count, the file is updated |

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
