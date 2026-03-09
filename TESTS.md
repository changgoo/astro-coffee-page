# Test Suite

Run all tests with:

```bash
python -m pytest tests/ -v
```

No network access is required — all HTTP calls are mocked.

---

## `tests/test_scrape.py` — arXiv scraper (62 tests)

Tests for `scripts/scrape.py`. Uses a minimal Atom XML fixture that mirrors the
structure returned by the arXiv API.

### `build_query_url`

| Test | What it checks |
|------|----------------|
| `test_build_query_url_contains_category` | The query targets `cat:astro-ph.*` |
| `test_build_query_url_sort_by_submitted_date` | The URL includes `sortBy=submittedDate` |
| `test_build_query_url_descending` | The URL includes `sortOrder=descending` |
| `test_build_query_url_pagination` | A non-zero `start` offset appears in the URL |
| `test_build_query_url_max_results` | The `max_results` parameter is reflected in the URL |
| `test_build_query_url_no_date_window` | The URL does not contain a `submittedDate:[` range filter (date filtering is done post-fetch) |

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

### `match_author`

Returns `"strong"`, `"weak"`, or `None` for a single arXiv author string against
the favorite-authors list. Tests are grouped by the fav-author name pattern being exercised.

**Chang-Goo Kim** (hyphenated first name, no middle initial)

| Test | What it checks |
|------|----------------|
| `test_match_author_strong_exact_first_name` | Last + exact first name is a strong match |
| `test_match_author_strong_middle_initial` | Last + first initial + agreeing middle initial is a strong match |
| `test_match_author_hyphenated_exact_strong` | Exact hyphenated first name is a strong match |
| `test_match_author_hyphenated_initials_strong` | Hyphenated initials (C.-G.) match a hyphenated first name → strong |
| `test_match_author_concatenated_initials_weak` | Concatenated initials (C.G.) are not strong → weak |
| `test_match_author_single_initial_hyphenated_fav_none` | Single initial (C.) when fav has a hyphenated first name → None (no match) |

**Matthew W. Kunz** (non-hyphenated, has middle initial)

| Test | What it checks |
|------|----------------|
| `test_match_author_first_and_middle_initial_strong` | First initial + matching middle initial → strong |
| `test_match_author_exact_no_middle_strong` | Exact first name without middle initial → strong |
| `test_match_author_single_initial_fav_has_middle_none` | M. Kunz → None (fav has middle initial W. but arXiv omits it — can't confirm) |
| `test_match_author_conflicting_middle_initial_none` | M. A. Kunz vs Matthew W. Kunz → None (middle initials disagree) |

**George Livadiotis** (non-hyphenated, no middle initial)

| Test | What it checks |
|------|----------------|
| `test_match_author_single_initial_weak` | G. Livadiotis → weak (bare initial, fav has no middle initial) |
| `test_match_author_extra_middle_initial_none` | G. A. Livadiotis → None (arXiv has middle initial the fav lacks — too ambiguous) |

**Generic cases**

| Test | What it checks |
|------|----------------|
| `test_match_author_full_name_conflict_none` | Different full first names sharing only the first letter → None (e.g. Christopher Kim vs Chang-Goo Kim; Yujie Chen vs Yixian Chen) |
| `test_match_author_last_name_mismatch` | Last name mismatch returns `None` |
| `test_match_author_no_match` | Completely unknown author returns `None` |

### `annotate_papers`

Calls `annotate_papers(papers, fav_authors)` and checks the `local_match` and
`local_authors` fields written onto each paper dict.

| Test | What it checks |
|------|----------------|
| `test_annotate_papers_strong_match` | A strong-match paper gets `local_match == "strong"` |
| `test_annotate_papers_local_authors_dict` | The `local_authors` dict maps the matched author string to its match level |
| `test_annotate_papers_no_match` | No fav author in paper → `local_match` is `None` and `local_authors` is `{}` |
| `test_annotate_papers_full_name_conflict_none` | Conflicting full first names (Elaine vs Eve) → `local_match` is `None` |
| `test_annotate_papers_single_initial_always_weak` | Single initial (G.) against a full-name fav → `local_match == "weak"` |
| `test_annotate_papers_manual_initial_name_strong` | Adding the abbreviated form (G. Livadiotis) to the fav list gives `local_match == "strong"` |
| `test_annotate_papers_single_initial_fav_has_middle_none` | Single initial when fav has a middle initial → `local_match` is `None` |
| `test_annotate_papers_multiple_papers` | Strong match and no-match papers in the same list are annotated correctly |

### `load_favorite_authors`

| Test | What it checks |
|------|----------------|
| `test_load_favorite_authors_merges_both_files` | Both `authors.json` and `authors_manual.json` are loaded |
| `test_load_favorite_authors_manual_first` | Manual entries appear before auto-scraped entries |
| `test_load_favorite_authors_deduplicates` | Duplicate names across both files appear only once |
| `test_load_favorite_authors_missing_files` | Missing config files return an empty list without error |

### `load_archive` / `save_archive`

| Test | What it checks |
|------|----------------|
| `test_load_archive_missing` | Missing `archive.json` returns empty list and empty set without error |
| `test_load_archive_returns_ids` | Existing archive returns all papers and their IDs as a set |
| `test_save_archive_writes_file` | `save_archive` creates `archive.json` with correct structure (`total`, `papers`, `fetched_at`) |

### `update_index`

Uses pytest's `tmp_path` fixture for isolated file I/O; no real `data/` directory
is touched.

| Test | What it checks |
|------|----------------|
| `test_update_index_writes_current` | `index.json` is created with a valid `YYYY-MM-DD` string in `current` (today's UTC date) |
| `test_update_index_overwrites` | A second call overwrites `index.json` and `current` is still present |

### `today.json` write logic

| Test | What it checks |
|------|----------------|
| `test_appends_when_same_arxiv_date` | A second scrape for the same `arxiv_date` appends new papers to the existing 82, yielding 85 total |
| `test_replaces_when_new_arxiv_date` | A scrape for a different `arxiv_date` starts fresh, discarding the previous day's papers |

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
