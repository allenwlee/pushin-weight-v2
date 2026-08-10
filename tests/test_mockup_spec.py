"""Regression pins for the v22 master mockup oracle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.mockup_spec import (
    DEFAULT_SOURCE,
    MockupSpecError,
    build_fixture,
    extract_chrome,
    load_spec,
)


def test_load_spec_normalizes_authored_regions_in_document_order():
    spec = load_spec()

    assert spec.source == DEFAULT_SOURCE
    assert spec.dom["tag"] == "document"
    assert list(spec.regions) == ["topbar", "filters", "chart", "feed", "locale", "timezone"]
    assert spec.regions["topbar"]["tag"] == "header"
    assert spec.regions["filters"]["attrs"]["class"] == "filter-bar"
    assert spec.regions["chart"]["tag"] == "section"
    assert spec.regions["feed"]["tag"] == "section"
    assert spec.regions["locale"]["attrs"]["data-i18n-aria"] == "locale"
    assert spec.regions["timezone"]["attrs"]["data-tz-widget"] == ""

    topbar_children = spec.regions["topbar"]["children"]
    assert [child["tag"] for child in topbar_children if child["tag"] != "#text"] == ["div", "div"]
    assert list(spec.regions["locale"]["attrs"]) == sorted(spec.regions["locale"]["attrs"])


def test_extract_chrome_keeps_both_authored_locales_and_original_alias():
    chrome = extract_chrome()

    assert chrome["zh_cn"]["feed_title"] == "本窗口最新"
    assert chrome["en"]["feed_title"] == "Latest in window"
    assert chrome["zh_cn"]["tz_title"] == "切换 本地 ⇄ 加州时间"
    assert chrome["en"]["tz_title"] == "Toggle local ⇄ California time"
    assert chrome["original"] is chrome["en"]


def test_fixture_is_static_mockup_content_with_predictable_empty_shapes():
    fixture = build_fixture()

    assert fixture["locale"] == "zh_cn"
    assert fixture["topbar"]["windows"] == ["1", "7", "30", "365"]
    assert fixture["topbar"]["timezone"] == {"active": "local", "label": "本地"}
    assert [item["group"] for item in fixture["filters"]] == [
        "brands", "discourse", "role", "lang", "sentiment", "nationalism", "unsanctioned"
    ]
    assert [series["name"] for series in fixture["chart"]["series"]] == [
        "Kimi", "DeepSeek", "MiniMax", "Qwen", "ERNIE"
    ]
    assert all(len(series["points"]) == 13 for series in fixture["chart"]["series"])
    assert fixture["chart"]["empty"] == {"series": [], "message": "No activity in window"}
    assert [post["handle"] for post in fixture["feed"]["items"]] == [
        "@kimi_moonshot", "@awnihannun", "@rasbt"
    ]
    assert fixture["feed"]["items"][0]["text"]["en"].startswith("Kimi K3 open weights")
    assert fixture["feed"]["empty"] == {"items": [], "message": "No posts in this window"}


def test_fixture_matches_checked_in_golden():
    golden_path = Path(__file__).with_name("golden") / "v22_mockup_fixture.json"

    assert json.loads(golden_path.read_text(encoding="utf-8")) == build_fixture()


def test_missing_or_malformed_sources_name_the_source_path(tmp_path: Path):
    missing = tmp_path / "missing.html"
    with pytest.raises(MockupSpecError, match=str(missing)):
        load_spec(missing)

    malformed = tmp_path / "broken.html"
    malformed.write_text("<html><body><header></body></html>", encoding="utf-8")
    with pytest.raises(MockupSpecError, match=str(malformed)):
        load_spec(malformed)


def test_missing_authored_chrome_is_an_actionable_source_error(tmp_path: Path):
    source = tmp_path / "no-chrome.html"
    source.write_text("<html><body></body></html>", encoding="utf-8")

    with pytest.raises(MockupSpecError, match=f"{source}.*CHROME"):
        extract_chrome(source)
