"""Read the v22 master mockup as a deterministic test oracle.

The mockup is an authored artifact, not a page to fetch or a set of values to
retype.  This module keeps the small, stdlib-only translation boundary that
browser comparison tests can reuse without depending on Django or live data.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "docs/ideation/mockups/06-tier1-composed.v22-master.html"

_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


class MockupSpecError(ValueError):
    """An authored mockup cannot be used as an oracle."""


class _TreeParser(HTMLParser):
    """Strict-enough HTMLParser wrapper which produces JSON-shaped nodes."""

    def __init__(self, source: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.root: dict[str, Any] = {"tag": "document", "attrs": {}, "children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = {
            "tag": tag,
            "attrs": {key: "" if value is None else value for key, value in sorted(attrs)},
            "children": [],
        }
        self.stack[-1]["children"].append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if len(self.stack) == 1 or self.stack[-1]["tag"] != tag:
            raise MockupSpecError(f"Malformed mockup {self.source}: unexpected </{tag}>")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.stack[-1]["children"].append({"tag": "#text", "text": text})

    def close(self) -> None:
        super().close()
        if len(self.stack) != 1:
            unclosed = ", ".join(node["tag"] for node in self.stack[1:])
            raise MockupSpecError(f"Malformed mockup {self.source}: unclosed {unclosed}")


@dataclass(frozen=True)
class MockupSpec:
    """Normalized authored source plus its significant comparison regions."""

    source: Path
    dom: dict[str, Any]
    regions: dict[str, dict[str, Any]]
    chrome: dict[str, dict[str, str]]


def _read_source(source: Path | str) -> tuple[Path, str]:
    path = Path(source).resolve()
    try:
        return path, path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MockupSpecError(f"Mockup source not found: {path}") from exc
    except OSError as exc:
        raise MockupSpecError(f"Cannot read mockup source {path}: {exc}") from exc


def _descendants(node: dict[str, Any]):
    yield node
    for child in node.get("children", []):
        yield from _descendants(child)


def _has_class(node: dict[str, Any], class_name: str) -> bool:
    return class_name in node.get("attrs", {}).get("class", "").split()


def _first(
    node: dict[str, Any], description: str, predicate, source: Path = DEFAULT_SOURCE
) -> dict[str, Any]:
    for candidate in _descendants(node):
        if predicate(candidate):
            return candidate
    raise MockupSpecError(f"Mockup source missing {description}: {source}")


def _first_in_source(
    root: dict[str, Any], source: Path, description: str, predicate
) -> dict[str, Any]:
    return _first(root, description, predicate, source)


def _parse_dom(source: Path, html: str) -> dict[str, Any]:
    parser = _TreeParser(source)
    try:
        parser.feed(html)
        parser.close()
    except MockupSpecError:
        raise
    except Exception as exc:  # HTMLParser keeps its own error types private.
        raise MockupSpecError(f"Malformed mockup {source}: {exc}") from exc
    return parser.root


def _parse_chrome_object(source: Path, html: str) -> dict[str, dict[str, str]]:
    match = re.search(
        r"var\s+CHROME\s*=\s*\{\s*zh_cn\s*:\s*\{(?P<zh>.*?)\}\s*,\s*en\s*:\s*\{(?P<en>.*?)\}\s*,?\s*\};",
        html,
        re.DOTALL,
    )
    if not match:
        raise MockupSpecError(f"Mockup source {source}: missing CHROME object")

    def parse_entries(body: str) -> dict[str, str]:
        entries: dict[str, str] = {}
        for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")", body):
            entries[key] = ast.literal_eval(value)
        if not entries:
            raise MockupSpecError(f"Mockup source {source}: empty CHROME locale")
        return entries

    if not re.search(r"CHROME\.original\s*=\s*CHROME\.en\s*;", html):
        raise MockupSpecError(f"Mockup source {source}: missing CHROME.original English alias")
    en = parse_entries(match.group("en"))
    return {"zh_cn": parse_entries(match.group("zh")), "en": en, "original": en}


def extract_chrome(source: Path | str = DEFAULT_SOURCE) -> dict[str, dict[str, str]]:
    """Return the source-authored bilingual chrome; ``original`` is English."""
    path, html = _read_source(source)
    return _parse_chrome_object(path, html)


def load_spec(source: Path | str = DEFAULT_SOURCE) -> MockupSpec:
    """Parse the mockup into stable DOM and region records for downstream tests."""
    path, html = _read_source(source)
    dom = _parse_dom(path, html)
    regions = {
        "topbar": _first_in_source(dom, path, "topbar", lambda n: n["tag"] == "header" and _has_class(n, "topbar")),
        "filters": _first_in_source(dom, path, "filter bar", lambda n: n["tag"] == "nav" and _has_class(n, "filter-bar")),
        "chart": _first_in_source(dom, path, "chart", lambda n: n["tag"] == "section" and _has_class(n, "home-chart-wrap")),
        "feed": _first_in_source(dom, path, "feed", lambda n: n["tag"] == "section" and _has_class(n, "feed-strip")),
        "locale": _first_in_source(dom, path, "locale controls", lambda n: n.get("attrs", {}).get("data-i18n-aria") == "locale"),
        "timezone": _first_in_source(dom, path, "timezone controls", lambda n: "data-tz-widget" in n.get("attrs", {})),
    }
    return MockupSpec(source=path, dom=dom, regions=regions, chrome=_parse_chrome_object(path, html))


def _text(node: dict[str, Any]) -> str:
    parts = [candidate["text"] for candidate in _descendants(node) if candidate["tag"] == "#text"]
    return " ".join(parts)


def _descendants_with_class(node: dict[str, Any], class_name: str) -> list[dict[str, Any]]:
    return [candidate for candidate in _descendants(node) if _has_class(candidate, class_name)]


def _label_text(node: dict[str, Any]) -> str:
    return _text(node).strip()


def _chart_fixture(chart: dict[str, Any], source: Path) -> dict[str, Any]:
    svg = _first(
        chart, "chart SVG", lambda node: node["tag"] == "svg" and _has_class(node, "home-chart"), source
    )
    legend = _first(chart, "chart legend", lambda node: _has_class(node, "legend"), source)
    names = [_label_text(node) for node in legend["children"] if node["tag"] == "span"]
    lines = [node for node in _descendants(svg) if node["tag"] == "polyline"]
    if len(names) != len(lines):
        raise MockupSpecError(f"Mockup source {source}: chart legend/series mismatch")
    series = []
    for name, line in zip(names, lines):
        points = [[int(x), int(y)] for x, y in re.findall(r"(\d+),(\d+)", line["attrs"]["points"])]
        series.append({"name": name, "color": line["attrs"]["stroke"], "points": points})
    return {
        "series": series,
        "empty": {"series": [], "message": "No activity in window"},
    }


def _feed_fixture(feed: dict[str, Any], source: Path) -> dict[str, Any]:
    items = []
    for row in _descendants_with_class(feed, "feed-row"):
        text = _first(row, "feed text", lambda node: _has_class(node, "text"), source)
        items.append(
            {
                "handle": _text(_first(row, "feed handle", lambda node: _has_class(node, "handle"), source)),
                "offset_minutes": int(row["attrs"]["data-posted-offset-min"]),
                "text": {
                    "synthesis": text["attrs"].get("data-voice-zh-cn", ""),
                    "zh_cn": text["attrs"].get("data-text-zh-cn", ""),
                    "original": text["attrs"].get("data-text", ""),
                    "en": text["attrs"].get("data-text-en", text["attrs"].get("data-text", "")),
                },
                "sentiments": row["attrs"].get("data-sentiments", "").split(","),
                "post_types": row["attrs"].get("data-post-types", "").split(","),
            }
        )
    return {"items": items, "empty": {"items": [], "message": "No posts in this window"}}


def build_fixture(source: Path | str = DEFAULT_SOURCE) -> dict[str, Any]:
    """Build a live-value-free demo fixture directly from the canonical mockup."""
    spec = load_spec(source)
    topbar = spec.regions["topbar"]
    locale_buttons = [
        node["attrs"]["data-pw-locale-btn"]
        for node in _descendants(topbar)
        if "data-pw-locale-btn" in node.get("attrs", {})
    ]
    windows = [
        node["attrs"]["data-window"]
        for node in _descendants(topbar)
        if "data-window" in node.get("attrs", {})
    ]
    timezone = spec.regions["timezone"]
    filters = []
    for pill in _descendants_with_class(spec.regions["filters"], "filter-pill"):
        title = _first(pill, "filter title", lambda node: _has_class(node, "title"), spec.source)
        filters.append(
            {
                "group": pill["attrs"]["data-group"],
                "label": _text(title),
                "options": [_label_text(label) for label in _descendants(pill) if label["tag"] == "label"],
            }
        )
    return {
        "locale": "zh_cn",
        "chrome": spec.chrome,
        "topbar": {
            "locale_options": locale_buttons,
            "windows": windows,
            "timezone": {
                "active": timezone["attrs"].get("data-tz-active", "local"),
                "label": _text(_first(timezone, "timezone label", lambda node: "data-tz-zone" in node.get("attrs", {}), spec.source)),
            },
        },
        "filters": filters,
        "chart": _chart_fixture(spec.regions["chart"], spec.source),
        "feed": _feed_fixture(spec.regions["feed"], spec.source),
    }
