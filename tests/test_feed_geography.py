"""Presentation contract for normalized account geography in the public feed."""

from __future__ import annotations

import pytest

from monitor.views import (
    _compact_language_display,
    _compact_region_label,
    _feed_geography_wire,
    _feed_signal_inspections,
    _localize_classification_value,
)

GUIDING_COUNTRIES = {
    "HK": "CN",
    "MO": "CN",
    "TW": "CN",
    "PR": "US",
    "VI": "US",
    "RE": "FR",
    "PF": "FR",
    "MQ": "FR",
    "NC": "FR",
    "GF": "FR",
    "KY": "GB",
    "AI": "GB",
    "BM": "GB",
    "GI": "GB",
    "JE": "GB",
    "GG": "GB",
    "IM": "GB",
    "AW": "NL",
    "BQ": "NL",
}


@pytest.mark.parametrize(("child_code", "parent_code"), GUIDING_COUNTRIES.items())
def test_every_guiding_country_precedes_its_child_signal(
    child_code: str,
    parent_code: str,
) -> None:
    source = {
        "country_code": child_code,
        "country_labels": {"en": f"Child {child_code}", "zh_cn": f"子项{child_code}"},
        "parent_country_code": parent_code,
        "parent_country_labels": {
            "en": f"Parent {parent_code}",
            "zh_cn": f"父项{parent_code}",
        },
        "relationship_type": "reviewed_relationship",
        "fallback_region_labels": {"en": "Fallback", "zh_cn": "后备区域"},
        "direct_region_labels": {},
    }

    geography = _feed_geography_wire(source, "en")

    assert geography is not None
    assert [flag["code"] for flag in geography["flags"]] == [parent_code] + (
        [] if child_code == "TW" else [child_code]
    )
    if child_code == "TW":
        assert geography["kind"] == "taiwan"
        assert geography["text"] == "TW · Child TW"
        assert all(flag["symbol_id"] != "flag-tw" for flag in geography["flags"])
    else:
        assert geography["kind"] == "hierarchy"
        assert geography["text"] == ""


@pytest.mark.parametrize(
    ("locale", "expected_label", "expected_accessible"),
    (
        ("en", "Europe", "X reports this account is based in Europe"),
        ("original", "Europe", "X reports this account is based in Europe"),
        ("zh_cn", "欧洲", "X 显示此账号所在地为欧洲"),
        ("zh_hans", "欧洲", "X 显示此账号所在地为欧洲"),
    ),
)
def test_direct_region_uses_the_requested_seeded_locale(
    locale: str,
    expected_label: str,
    expected_accessible: str,
) -> None:
    geography = _feed_geography_wire(
        {
            "country_code": None,
            "direct_region_labels": {"en": "Europe", "zh_cn": "欧洲"},
        },
        locale,
    )

    assert geography == {
        "kind": "region",
        "label": expected_label,
        "accessible_label": expected_accessible,
        "flags": [],
        "text": expected_label,
        "relationship_type": "",
    }


def test_country_without_approved_symbol_falls_back_to_its_region() -> None:
    geography = _feed_geography_wire(
        {
            "country_code": "AX",
            "country_labels": {"en": "Åland Islands", "zh_cn": "奥兰群岛"},
            "parent_country_code": None,
            "fallback_region_labels": {
                "en": "Northern Europe",
                "zh_cn": "北欧",
            },
        },
        "en",
    )

    assert geography is not None
    assert geography["kind"] == "region"
    assert geography["flags"] == []
    assert geography["text"] == "N Europe"


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("Northern Europe", "N Europe"),
        ("Eastern Asia", "E Asia"),
        ("South-Eastern Asia", "SE Asia"),
        ("Southeastern Asia", "SE Asia"),
        ("Northwestern Europe", "NW Europe"),
        ("Central Asia", "Central Asia"),
    ),
)
def test_english_region_direction_is_compact_presentation_only(
    source: str,
    expected: str,
) -> None:
    assert _compact_region_label(source, "en") == expected
    assert _compact_region_label(source, "zh_cn") == source


@pytest.mark.parametrize(
    ("language", "en", "zh_cn"),
    (
        ("en-US", "en", "英语"),
        ("zh-Hans", "zh", "简体中文"),
        ("zh-Hant", "zh", "繁体中文"),
        ("other", "other", "其他"),
        (None, "undetected", "未检测"),
    ),
)
def test_language_projection_uses_persisted_value_only(
    language: str | None,
    en: str,
    zh_cn: str,
) -> None:
    assert _compact_language_display(language, "en") == en
    assert _compact_language_display(language, "zh_cn") == zh_cn


def test_deduplicated_signal_inspection_retains_every_brand() -> None:
    inspections = _feed_signal_inspections(
        {
            "minimax": {
                "sentiments": [{"key": "positive", "label": "Positive"}],
            },
            "qwen": {
                "sentiments": [{"key": "positive", "label": "Positive"}],
            },
        },
        [
            {"nickname": "minimax", "display_name_en": "MiniMax"},
            {"nickname": "qwen", "display_name_en": "Qwen"},
        ],
        "en",
        unsanctioned=False,
    )

    assert [entry["brand"] for entry in inspections["sentiment"]["positive"]] == [
        "MiniMax",
        "Qwen",
    ]
    assert [entry["text"] for entry in inspections["sentiment"]["positive"]] == [
        "MiniMax Sentiment: Positive",
        "Qwen Sentiment: Positive",
    ]


@pytest.mark.parametrize(
    ("family", "key", "locale", "expected"),
    (
        ("sentiment", "positive", "en", "Positive"),
        ("post_type", "buzz_releases", "en", "Buzz & Releases"),
        ("sentiment", "positive", "zh_cn", "正面"),
        ("post_type", "buzz_releases", "zh_cn", "热点发布"),
    ),
)
def test_signal_copy_has_canonical_fallback_when_seed_rows_are_missing(
    family: str,
    key: str,
    locale: str,
    expected: str,
) -> None:
    assert _localize_classification_value(family, key, locale, {}) == expected


@pytest.mark.parametrize(
    "source",
    (
        None,
        {},
        {"country_code": "ZZ", "country_labels": {"en": "Unknown"}},
        {"country_code": None, "direct_region_labels": {}},
    ),
)
def test_unresolved_or_malformed_geography_reserves_no_signal(
    source: dict[str, object] | None,
) -> None:
    assert _feed_geography_wire(source, "en") is None
