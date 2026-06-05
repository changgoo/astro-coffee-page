"""Local-author loading, matching, and annotation."""

import json


def load_favorite_authors(repo_root):
    """Load and merge favorite authors from both config files."""
    names = []
    seen = set()
    for filename in ("authors_manual.json", "authors.json"):
        path = repo_root / "config" / filename
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for name in data.get("authors", []):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def parse_name_parts(name):
    """Parse a name into (first, last, middle_initial) components."""
    suffixes = {"iii", "ii", "iv", "jr.", "jr", "sr.", "sr"}
    titles = {"sir", "dr.", "dr", "prof.", "prof"}

    if "," in name:
        comma = name.index(",")
        last = name[:comma].strip().lower()
        rest = name[comma + 1:].strip().split()
        first = rest[0].replace(".", "").lower() if rest else ""
        mid_str = rest[1].replace(".", "").lower() if len(rest) > 1 else ""
        middle_initial = mid_str[0] if mid_str else None
        return first, last, middle_initial

    tokens = name.strip().split()
    while len(tokens) > 1 and tokens[0].lower() in titles:
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1].lower() in suffixes:
        tokens = tokens[:-1]
    last = tokens[-1].lower() if tokens else ""
    first = tokens[0].replace(".", "").lower() if tokens else ""
    mid_str = tokens[1].replace(".", "").lower() if len(tokens) > 2 else ""
    middle_initial = mid_str[0] if mid_str else None
    return first, last, middle_initial


def match_author(arxiv_name, fav_authors):
    """Return "strong", "weak", or None for one arXiv author against fav_authors."""
    arx_first, arx_last, arx_mid = parse_name_parts(arxiv_name)
    best = None
    for fav_name in fav_authors:
        fav_first, fav_last, fav_mid = parse_name_parts(fav_name)
        if fav_last != arx_last:
            continue
        if fav_first == arx_first:
            return "strong"
        if not fav_first or not arx_first:
            continue
        if "-" in fav_first and "-" in arx_first:
            fav_parts = fav_first.split("-")
            arx_parts = arx_first.split("-")
            if (len(fav_parts) == len(arx_parts) and
                    all(len(ap) == 1 and ap == fp[0]
                        for ap, fp in zip(arx_parts, fav_parts))):
                return "strong"

        if "-" in fav_first and len(arx_first) == 1:
            continue
        if fav_first[0] == arx_first[0]:
            if fav_mid and arx_mid and fav_mid == arx_mid:
                return "strong"
            if fav_mid and arx_mid and fav_mid != arx_mid:
                continue
            if arx_mid and not fav_mid:
                continue
            if fav_mid and not arx_mid:
                continue
            if len(arx_first) >= 2 and len(fav_first) >= 2:
                continue
            best = "weak"
    return best


def annotate_papers(papers, fav_authors):
    """Add local_match and local_authors fields to each paper dict in-place."""
    for paper in papers:
        local_authors = {}
        best = None
        for arxiv_name in paper.get("authors", []):
            strength = match_author(arxiv_name, fav_authors)
            if strength:
                local_authors[arxiv_name] = strength
                if strength == "strong":
                    best = "strong"
                elif best != "strong":
                    best = "weak"
        paper["local_match"] = best
        paper["local_authors"] = local_authors
