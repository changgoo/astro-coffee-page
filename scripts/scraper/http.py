"""HTTP helpers shared by arXiv API and HTML listing fetchers."""

import urllib.request

from .config import USER_AGENT


def build_request(url):
    """Build an arXiv request with the scraper User-Agent."""
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def fetch_bytes(url, timeout=60):
    """Fetch a URL and return raw response bytes."""
    req = build_request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url, timeout=60):
    """Fetch a URL and return decoded text."""
    req = build_request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")
