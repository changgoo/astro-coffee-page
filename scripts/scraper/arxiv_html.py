"""arXiv HTML listing fetching and parsing."""

import re
from datetime import datetime
from html.parser import HTMLParser

from .config import FETCH_SIZE, LISTING_SHOW_SIZES, NEW_LISTING_URL, RECENT_LISTING_URL
from .http import fetch_text
from .paper import make_paper, normalize_text


def listing_show_size(show):
    """Return an arXiv HTML listing size accepted by the website."""
    for size in LISTING_SHOW_SIZES:
        if show <= size:
            return size
    return LISTING_SHOW_SIZES[-1]


def build_listing_url(show=FETCH_SIZE, source="new"):
    """Build the arXiv HTML listing URL."""
    if source == "new":
        return NEW_LISTING_URL
    return f"{RECENT_LISTING_URL}?show={listing_show_size(show)}"


def fetch_html(url):
    """Fetch an HTML page from arXiv and return decoded text."""
    return fetch_text(url)


def parse_listing_date_heading(text):
    """Parse an arXiv listing heading into YYYY-MM-DD, returning None if it fails."""
    heading = re.sub(r"\s*\(.*\)$", "", normalize_text(text))
    heading = heading.removeprefix("Showing new listings for ")
    for fmt in ("%A, %d %B %Y", "%A, %d %B %y", "%a, %d %b %Y", "%a, %d %b %y"):
        try:
            return datetime.strptime(heading, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


class ArxivListingParser(HTMLParser):
    """Parse arXiv astro-ph listing HTML into paper dictionaries."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.papers = []
        self.current_date = ""
        self._tag_stack = []
        self._current_dt = None
        self._current_paper = None
        self._capture = None
        self._capture_parts = []
        self._links = []
        self._current_section = "papers"

    def handle_starttag(self, tag, attrs):
        """Handle the start of relevant arXiv listing tags."""
        attrs = dict(attrs)
        self._tag_stack.append(tag)

        if tag == "h3":
            self._start_capture("heading")
            return

        if tag == "dt":
            self._current_dt = {"links": [], "text": []}
            self._links = []
            self._start_capture("dt")
            return

        if tag == "dd":
            self._current_paper = {
                "listing_date": self.current_date,
                "dt_text": normalize_text(" ".join(self._current_dt.get("text", []))) if self._current_dt else "",
                "links": list(self._links),
                "title": "",
                "authors": [],
                "abstract": "",
                "categories": [],
                "primary_category": "",
            }
            return

        if tag == "a" and self._current_dt is not None:
            self._current_dt["links"].append({"href": attrs.get("href", ""), "text": ""})

        if tag == "div" and self._current_paper is not None:
            classes = set(attrs.get("class", "").split())
            if "list-title" in classes:
                self._start_capture("title")
            elif "list-authors" in classes:
                self._start_capture("authors")
            elif "list-subjects" in classes:
                self._start_capture("subjects")

        if tag == "p" and self._current_paper is not None:
            self._start_capture("abstract")

    def handle_endtag(self, tag):
        """Handle the end of relevant arXiv listing tags."""
        text = normalize_text(" ".join(self._capture_parts)) if self._capture else ""

        if tag == "h3" and self._capture == "heading":
            self._update_section(text)
            parsed = parse_listing_date_heading(text)
            if parsed:
                self.current_date = parsed
            self._stop_capture()
        elif tag == "dt" and self._capture == "dt":
            if self._current_dt is not None:
                self._current_dt["text"].append(text)
                self._links = self._current_dt["links"]
            self._stop_capture()
        elif tag == "div" and self._capture in {"title", "authors", "subjects"}:
            self._apply_captured_div(self._capture, text)
            self._stop_capture()
        elif tag == "p" and self._capture == "abstract":
            if self._current_paper is not None:
                self._current_paper["abstract"] = text
            self._stop_capture()
        elif tag == "dd" and self._current_paper is not None:
            paper = self._finish_paper(self._current_paper)
            if paper is not None and self._current_section != "replacement":
                self.papers.append(paper)
            self._current_paper = None
            self._current_dt = None
            self._links = []

        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data):
        """Collect text for the active listing field."""
        if self._capture:
            self._capture_parts.append(data)
        if self._tag_stack and self._tag_stack[-1] == "a" and self._current_dt is not None:
            if self._current_dt["links"]:
                self._current_dt["links"][-1]["text"] += data

    def _start_capture(self, name):
        self._capture = name
        self._capture_parts = []

    def _stop_capture(self):
        self._capture = None
        self._capture_parts = []

    def _update_section(self, text):
        heading = normalize_text(text).lower()
        if heading.startswith("new submissions"):
            self._current_section = "new"
        elif heading.startswith("cross submissions"):
            self._current_section = "cross"
        elif heading.startswith("replacement submissions"):
            self._current_section = "replacement"

    def _apply_captured_div(self, field, text):
        if self._current_paper is None:
            return
        if field == "title":
            self._current_paper["title"] = normalize_text(text.removeprefix("Title:"))
        elif field == "authors":
            author_text = normalize_text(text.removeprefix("Authors:"))
            self._current_paper["authors"] = [a.strip() for a in author_text.split(", ") if a.strip()]
        elif field == "subjects":
            subject_text = normalize_text(text.removeprefix("Subjects:"))
            categories = re.findall(r"\(([^()]+)\)", subject_text)
            self._current_paper["categories"] = categories
            self._current_paper["primary_category"] = categories[0] if categories else ""

    def _finish_paper(self, paper):
        abs_link = next((link for link in paper["links"] if "/abs/" in link["href"]), None)
        if abs_link is None:
            return None

        id_text = normalize_text(abs_link["text"] or abs_link["href"].rstrip("/").split("/abs/")[-1])
        match = re.search(r"(\d{4}\.\d{4,5}|[a-z.-]+/\d{7})", id_text)
        arxiv_id = match.group(1) if match else id_text.replace("arXiv:", "")
        arxiv_id = arxiv_id.split("v")[0]
        pdf_link = next((link for link in paper["links"] if "/pdf/" in link["href"]), None)
        pdf_href = pdf_link["href"] if pdf_link else f"/pdf/{arxiv_id}"
        pdf_url = f"https://arxiv.org{pdf_href}" if pdf_href.startswith("/") else pdf_href

        return make_paper(
            arxiv_id=arxiv_id,
            title=paper["title"],
            authors=paper["authors"],
            abstract=paper["abstract"],
            primary_category=paper["primary_category"],
            categories=paper["categories"],
            submitted=paper["listing_date"],
            listing_date=paper["listing_date"],
            pdf_url=pdf_url,
        )


def parse_listing_html(html, include_listing_date=False):
    """Parse arXiv listing HTML and return paper dictionaries."""
    parser = ArxivListingParser()
    parser.feed(html)
    papers = parser.papers
    if not include_listing_date:
        for paper in papers:
            paper.pop("_listing_date", None)
    return papers


def fetch_latest_papers_from_listing(n=FETCH_SIZE, include_listing_date=False, source="new"):
    """Fetch recent astro-ph papers from arXiv's HTML listing page."""
    url = build_listing_url(show=n, source=source)
    if source == "new":
        print("  Fetching arXiv HTML new listing ...", flush=True)
    else:
        print(f"  Fetching arXiv HTML recent listing show={listing_show_size(n)} ...", flush=True)
    html = fetch_html(url)
    papers = parse_listing_html(html, include_listing_date=include_listing_date)
    return papers[:n]
