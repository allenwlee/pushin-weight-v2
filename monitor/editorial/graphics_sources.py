"""Select source images using evidence from the fetched page."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


class PageImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.meta = {}
        self.title_parts = []
        self.in_title = False
        self.in_main = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "main":
            self.in_main = True
        if tag == "meta":
            self.meta[values.get("property") or values.get("name")] = values.get(
                "content", ""
            )
        if tag == "img":
            self.images.append({**values, "in_main": self.in_main})

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "main":
            self.in_main = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self):
        return self.meta.get("og:title") or " ".join(self.title_parts).strip()


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - {
        "the",
        "and",
        "of",
        "a",
        "an",
        "www",
        "com",
        "https",
        "http",
        "book",
        "books",
        "edition",
        "original",
        "illustration",
        "cover",
        "site",
        "activities",
        "activity",
    }


def select_image(html, requested_url, final_url, requested_title):
    """Never promote a generic index's social card to the requested named artifact."""
    page = PageImages()
    page.feed(html)
    path = urlsplit(final_url).path.rstrip("/")
    if path in {"", "/activities", "/books", "/activity", "/search"}:
        return (
            None,
            page.title,
            "resolved page is a generic index, not the requested artifact",
        )
    target = words(requested_title)
    page_matches = bool(target & words(page.title))
    if not page_matches and requested_url != final_url:
        return (
            None,
            page.title,
            "redirected page title does not identify the requested artifact",
        )
    ranked = []
    for image in page.images:
        source = image.get("data-src") or image.get("src")
        if not source or source.startswith("data:"):
            continue
        label = image.get("alt", "")
        if re.search(r"(?:^|[^a-z])(logo|avatar|icon)(?:[^a-z]|$)", label + " " + source, re.IGNORECASE):
            continue
        overlap = len(target & words(label + " " + source))
        named_cover = "cover" in label.lower() and page_matches
        if overlap or named_cover:
            score = overlap * 10 + int(named_cover) * 3 + int(image["in_main"])
            ranked.append((score, source, "named page image: " + label))
    if ranked:
        _, source, basis = max(ranked, key=lambda item: item[0])
        return urljoin(final_url, source), page.title, basis
    if page_matches and page.meta.get("og:image"):
        return (
            urljoin(final_url, page.meta["og:image"]),
            page.title,
            "page-specific social preview; visual suitability unconfirmed",
        )
    return None, page.title, "no image tied to the named artifact"
