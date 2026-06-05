"""Shared scraper configuration constants."""

from zoneinfo import ZoneInfo

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

BASE_URL = "https://export.arxiv.org/api/query"
NEW_LISTING_URL = "https://arxiv.org/list/astro-ph/new"
RECENT_LISTING_URL = "https://arxiv.org/list/astro-ph/recent"
LISTING_SHOW_SIZES = (25, 50, 100, 250, 500, 1000, 2000)
USER_AGENT = "coffee-page/1.0 (arxiv paper browser)"

MAX_PER_REQUEST = 200
RATE_LIMIT_SECONDS = 3
FETCH_SIZE = 200
BOOTSTRAP_FETCH_SIZE = 1000
HISTORY_DAYS = 5
ARCHIVE_DIR = "archive"
NY_TZ = ZoneInfo("America/New_York")
