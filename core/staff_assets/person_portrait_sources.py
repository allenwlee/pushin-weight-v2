"""Extract attributable portrait candidates from bounded source pages."""

import re
from urllib.parse import urljoin, urlsplit

from monitor.editorial.graphics_sources import PageImages


def contains_name(text, name):
    return bool(
        name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE)
    )


def public_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return ""
    try:
        parts = urlsplit(value)
        if (
            parts.scheme in {"http", "https"}
            and parts.hostname
            and not (parts.username or parts.password)
        ):
            return value
    except ValueError:
        pass
    return ""


class PortraitPage(PageImages):
    def __init__(self):
        super().__init__()
        self.text = []
        self.figure = None
        self.caption = False
        self.hidden = 0
        self.x_links = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script", "noscript", "template"}:
            self.hidden += 1
        if self.hidden:
            return
        super().handle_starttag(tag, attrs)
        if tag == "figure":
            self.figure = {"caption": []}
        if tag == "figcaption":
            self.caption = True
        if tag == "img":
            self.images[-1]["figure"] = self.figure
        if tag == "a":
            href = dict(attrs).get("href") or ""
            match = re.fullmatch(
                r"https?://(?:www\.)?(?:x|twitter)\.com/([a-zA-Z0-9_]{1,15})/?", href
            )
            if match and match[1].casefold() not in {
                "home",
                "intent",
                "share",
                "search",
                "about",
                "settings",
            }:
                self.anchor = {"handle": match[1], "url": href, "label": []}
                self.x_links.append(self.anchor)

    def handle_endtag(self, tag):
        if tag in {"style", "script", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)
        if self.hidden:
            return
        super().handle_endtag(tag)
        if tag == "figure":
            self.figure = None
        if tag == "figcaption":
            self.caption = False
        if tag == "a":
            self.anchor = None

    def handle_data(self, data):
        if self.hidden:
            return
        super().handle_data(data)
        self.text.append(data)
        if self.figure is not None and self.caption:
            self.figure["caption"].append(data)
        if self.anchor is not None:
            self.anchor["label"].append(data)


def read_page(raw, *, name, requested_url, final_url):
    page = PortraitPage()
    page.feed(raw.decode("utf-8", "replace"))
    title = (page.title or "")[:512]
    text = " ".join(" ".join(page.text).split())
    centre = max(0, text.casefold().find(name.casefold()) - 600)
    excerpt = text[centre : centre + 7000]
    ranked = []
    for image in [
        *page.images,
        {
            "src": page.meta.get("og:image"),
            "alt": page.meta.get("og:image:alt"),
            "social_preview": True,
        },
    ]:
        src = image.get("data-src") or image.get("src")
        if not src:
            continue
        url = public_url(urljoin(final_url, src))
        label = (image.get("alt") or "").strip()[:600]
        caption = " ".join(
            " ".join((image.get("figure") or {}).get("caption", [])).split()
        )[:850]
        if not url or re.search(
            r"(?:^|[^a-z])(logo|icon|placeholder|favicon)(?:[^a-z]|$)",
            label + " " + url,
            re.IGNORECASE,
        ):
            continue
        # Filenames and names elsewhere on a news page do not attribute the image.
        named = contains_name(label, name) or contains_name(caption, name)
        # For an unlabeled image, only a dedicated subject page and its primary
        # image can be presented to the combined source/pixels assessment.
        primary = contains_name(title, name) and (
            image.get("social_preview")
            or (image.get("in_main") and len(page.images) == 1)
        )
        if not (named or primary):
            continue
        ranked.append(
            (
                int(named) * 4 + int(bool(caption)) + int(bool(image.get("in_main"))),
                {
                    "url": url,
                    "alt": label,
                    "caption": caption,
                    "page_primary_only": not named,
                },
            )
        )
    return {
        "requested_url": requested_url,
        "source_url": final_url,
        "title": title,
        "passage": excerpt,
        "candidate": max(ranked, key=lambda item: item[0])[1] if ranked else None,
        "x_links": [
            {**item, "label": " ".join(item["label"])[:250]}
            for item in page.x_links[:12]
        ],
    }
