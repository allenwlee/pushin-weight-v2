"""Authored/data-aware structural diagnostics for the v22 shell oracle."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from tests.mockup_spec import MockupSpec

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
AUTHORED_REGIONS = (
    ("topbar", "header.topbar"),
    ("filters", "nav.filter-bar"),
    ("chart", "section.home-chart-wrap"),
    ("feed", "section.feed-strip"),
    ("locale", "nav.locale-toggle"),
    ("timezone", "[data-tz-widget]"),
)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: dict[str, Any] = {"tag": "document", "attrs": {}, "children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = {"tag": tag, "attrs": {k: v or "" for k, v in sorted(attrs)}, "children": []}
        self.stack[-1]["children"].append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        # Browsers recover from optional/misnested HTML; Django responses are
        # compared as browser-like markup rather than rejected on recovery.
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        # Django template comments are authored implementation notes, not
        # browser DOM.  Some rendered/template test paths retain them as raw
        # text, so discard them before comparing visible authored children.
        text = " ".join(re.sub(r"\{#.*?#\}", "", data, flags=re.DOTALL).split())
        if text:
            self.stack[-1]["children"].append({"tag": "#text", "text": text})


def parse_rendered_html(html: str) -> dict[str, Any]:
    parser = _Parser()
    parser.feed(html)
    parser.close()
    return parser.root


def _descendants(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield node
    for child in node.get("children", []):
        yield from _descendants(child)


def _has_class(node: dict[str, Any], name: str) -> bool:
    return name in node.get("attrs", {}).get("class", "").split()


def _matches(node: dict[str, Any], selector: str) -> bool:
    tag, _, class_name = selector.partition(".")
    if selector.startswith("[") and selector.endswith("]"):
        return selector[1:-1] in node.get("attrs", {})
    if tag and node.get("tag") != tag:
        return False
    return not class_name or _has_class(node, class_name)


def select_one(root: dict[str, Any], *, selector: str, locale: str, viewport: str, oracle_source: str) -> dict[str, Any]:
    for node in _descendants(root):
        if _matches(node, selector):
            return node
    raise AssertionError(
        "v22 selector matched zero elements: "
        f"selector={selector!r}; locale={locale!r}; viewport={viewport!r}; "
        f"oracle_source={oracle_source!r}"
    )


@dataclass(frozen=True)
class Difference:
    region: str
    selector: str
    category: str
    path: str
    expected: Any
    actual: Any

    def report(self, *, locale: str, viewport: str, oracle_source: str) -> str:
        return (
            "v22 authored shell mismatch: "
            f"selector={self.selector!r}; region={self.region!r}; category={self.category!r}; "
            f"path={self.path!r}; expected={self.expected!r}; actual={self.actual!r}; "
            f"locale={locale!r}; viewport={viewport!r}; oracle_source={oracle_source!r}"
        )


_AUTHORED_ATTRS = {"class", "role", "tabindex", "type", "checked", "id", "title"}


def _authored_attrs(node: dict[str, Any]) -> dict[str, str]:
    attrs = node.get("attrs", {})
    return {
        key: value for key, value in attrs.items()
        if key in _AUTHORED_ATTRS or key.startswith(("aria-", "data-i18n"))
        or key in {"data-group", "data-lens", "data-lens-pair", "data-tier-grid", "data-active-lens", "data-tz-widget", "data-tz-idea", "data-tz-active", "data-pw-locale-btn", "data-label-en", "data-label-zh", "data-dd-action", "data-dd-scope"}
    }


def _is_data_area(node: dict[str, Any]) -> bool:
    return any(_has_class(node, klass) for klass in ("pulse-bar", "dd-grid", "home-chart", "feed-scroll"))


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [child for child in node.get("children", []) if child.get("tag") != "#text" or child.get("text")]


def _compare_nodes(expected: dict[str, Any], actual: dict[str, Any], *, region: str, selector: str, path: str) -> Difference | None:
    if expected["tag"] != actual["tag"]:
        return Difference(region, selector, "tag", path, expected["tag"], actual["tag"])
    if expected["tag"] == "#text":
        if expected["text"] != actual.get("text"):
            return Difference(region, selector, "authored-text", path, expected["text"], actual.get("text"))
        return None
    expected_attrs, actual_attrs = _authored_attrs(expected), _authored_attrs(actual)
    if expected_attrs != actual_attrs:
        return Difference(region, selector, "authored-attributes", path, expected_attrs, actual_attrs)
    # Lens counts are populated from the rendered fixture. Preserve the span
    # and its authored attributes, but do not compare its data-derived text.
    if "data-lens-count" in expected.get("attrs", {}) or "data-lens-count" in actual.get("attrs", {}):
        return None
    if _is_data_area(expected) or _is_data_area(actual):
        return None
    expected_children, actual_children = _children(expected), _children(actual)
    if len(expected_children) != len(actual_children):
        return Difference(region, selector, "ordered-children", path, len(expected_children), len(actual_children))
    for index, (expected_child, actual_child) in enumerate(zip(expected_children, actual_children)):
        diff = _compare_nodes(expected_child, actual_child, region=region, selector=selector, path=f"{path}/{expected_child['tag']}[{index}]")
        if diff:
            return diff
    return None


def validate_allowlist(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict) or set(payload) != {"entries"} or not isinstance(payload["entries"], list):
        raise AssertionError("v22 allowlist schema requires exactly {'entries': [...]}.")
    entries: list[dict[str, str]] = []
    for index, entry in enumerate(payload["entries"]):
        if not isinstance(entry, dict) or set(entry) != {"selector", "region", "rationale"}:
            raise AssertionError(f"v22 allowlist entry {index} requires selector, region, and rationale only.")
        if not all(isinstance(entry[key], str) and entry[key].strip() for key in entry):
            raise AssertionError(f"v22 allowlist entry {index} has blank selector, region, or rationale.")
        selector = entry["selector"].strip()
        if "*" in selector or selector in {"html", "body", "document"}:
            raise AssertionError(f"v22 allowlist entry {index} uses a broad wildcard selector: {selector!r}")
        entries.append({key: entry[key].strip() for key in ("selector", "region", "rationale")})
    return entries


def first_authored_difference(spec: MockupSpec, rendered_html: str, *, locale: str, viewport: str, allowlist: list[dict[str, str]]) -> Difference | None:
    rendered = parse_rendered_html(rendered_html)
    chrome_locale = "zh_cn" if locale in {"zh_cn", "zh-CN", "zh-cn"} else "original" if locale == "original" else "en"
    chrome = spec.chrome[chrome_locale]
    use_zh_labels = chrome_locale == "zh_cn"

    def localize_expected(node: dict[str, Any]) -> dict[str, Any]:
        """Project the mockup's authored bilingual chrome for this locale."""
        node = deepcopy(node)
        attrs = node.get("attrs", {})
        if attrs.get("data-i18n") in chrome:
            node["children"] = [{"tag": "#text", "text": chrome[attrs["data-i18n"]]}]
        aria_key = attrs.get("data-i18n-aria")
        if aria_key and f"{aria_key}_aria" in chrome:
            attrs["aria-label"] = chrome[f"{aria_key}_aria"]
        label = attrs.get("data-label-zh" if use_zh_labels else "data-label-en")
        if label:
            node["children"] = [{"tag": "#text", "text": label}]
        if "data-tz-widget" in attrs:
            attrs["title"] = chrome["tz_title"]
            attrs["aria-label"] = chrome["tz_title"]
        if attrs.get("data-pw-locale-btn"):
            attrs.pop("class", None)
            if attrs["data-pw-locale-btn"] == locale:
                attrs["class"] = "is-active"
        for index, child in enumerate(node.get("children", [])):
            if child.get("tag") != "#text":
                node["children"][index] = localize_expected(child)
        return node

    for region, selector in AUTHORED_REGIONS:
        expected = localize_expected(spec.regions[region])
        actual = select_one(rendered, selector=selector, locale=locale, viewport=viewport, oracle_source=str(spec.source))
        diff = _compare_nodes(expected, actual, region=region, selector=selector, path=selector)
        if diff and not any(entry["selector"] == diff.selector and entry["region"] == diff.region for entry in allowlist):
            return diff
    return None


def assert_data_shape(spec: MockupSpec, fixture: dict[str, Any], rendered_html: str, *, locale: str, viewport: str) -> None:
    """Check declared data density without comparing mutable data values."""
    rendered = parse_rendered_html(rendered_html)
    feed = select_one(rendered, selector="section.feed-strip", locale=locale, viewport=viewport, oracle_source=str(spec.source))
    rows = [node for node in _descendants(feed) if _has_class(node, "feed-row")]
    expected_count = len(fixture["feed"]["items"])
    if len(rows) != expected_count:
        raise AssertionError(f"v22 data-shape mismatch: selector='.feed-row'; expected_count={expected_count}; actual_count={len(rows)}; locale={locale!r}; viewport={viewport!r}; oracle_source={str(spec.source)!r}")
    chart = select_one(rendered, selector="svg.home-chart", locale=locale, viewport=viewport, oracle_source=str(spec.source))
    payload = json.loads(chart["attrs"].get("data-home", "{}"))
    expected_series = len(fixture["chart"]["series"])
    actual_series = len(payload.get("series", {}))
    if actual_series != expected_series:
        raise AssertionError(f"v22 data-shape mismatch: selector='svg.home-chart'; expected_series={expected_series}; actual_series={actual_series}; locale={locale!r}; viewport={viewport!r}; oracle_source={str(spec.source)!r}")
