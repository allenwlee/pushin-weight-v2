from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor.account_geography import (
    COUNTRY_NAMES,
    REGION_NAMES,
    resolve_account_based_in,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "monitor" / "data" / "account_geography.json"


def test_manifest_has_complete_iso_inventory_and_localized_labels():
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert len(payload["countries"]) == 249
    assert len({country["code"] for country in payload["countries"]}) == 249
    assert len({country["m49_code"] for country in payload["countries"]}) == 249
    assert all(
        set(country["labels"]) == {"en", "zh-cn"} for country in payload["countries"]
    )
    assert all(country["region_key"] for country in payload["countries"])
    assert len(COUNTRY_NAMES) == 249


def test_manifest_has_acyclic_localized_region_hierarchy():
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    regions = {region["key"]: region for region in payload["regions"]}

    assert set(REGION_NAMES) == set(regions)
    assert all(set(region["labels"]) == {"en", "zh-cn"} for region in regions.values())
    for start in regions:
        seen = set()
        current = start
        while current is not None:
            assert current not in seen
            seen.add(current)
            current = regions[current]["parent"]


@pytest.mark.parametrize(
    ("raw", "country_code", "region_key"),
    [
        ("United States", "US", None),
        ("Turkey", "TR", None),
        ("Russian Federation", "RU", None),
        ("Macedonia", "MK", None),
        ("Hong Kong", "HK", None),
        ("Macao", "MO", None),
        ("Taiwan", "TW", None),
        ("Bonaire", "BQ", None),
        ("Europe", None, "europe"),
        ("Eastern Europe (Non-EU)", None, "eastern-europe-non-eu"),
        ("South Asia", None, "southern-asia"),
    ],
)
def test_exact_provider_values_resolve_to_one_target(raw, country_code, region_key):
    resolved = resolve_account_based_in(raw)

    assert resolved is not None
    assert resolved.country_code == country_code
    assert resolved.region_key == region_key


@pytest.mark.parametrize(
    "raw",
    [None, "", " united states", "united states", "Korea", "Congo", "Seoul"],
)
def test_unreviewed_or_ambiguous_values_remain_unresolved(raw):
    assert resolve_account_based_in(raw) is None


def test_guiding_country_relationships_are_exact_and_directional():
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    countries = {country["code"]: country for country in payload["countries"]}
    expected = {
        "HK": ("CN", "special_administrative_region"),
        "MO": ("CN", "special_administrative_region"),
        "TW": ("CN", "owner_display_context"),
        "PR": ("US", "us_insular_area"),
        "VI": ("US", "us_insular_area"),
        "RE": ("FR", "french_overseas"),
        "PF": ("FR", "french_overseas"),
        "MQ": ("FR", "french_overseas"),
        "NC": ("FR", "french_overseas"),
        "GF": ("FR", "french_overseas"),
        "KY": ("GB", "british_overseas_territory"),
        "AI": ("GB", "british_overseas_territory"),
        "BM": ("GB", "british_overseas_territory"),
        "GI": ("GB", "british_overseas_territory"),
        "JE": ("GB", "crown_dependency"),
        "GG": ("GB", "crown_dependency"),
        "IM": ("GB", "crown_dependency"),
        "AW": ("NL", "kingdom_constituent_country"),
        "BQ": ("NL", "netherlands_public_body"),
    }

    assert {
        code: (
            countries[code]["display_parent_country"],
            countries[code]["display_parent_relationship_type"],
        )
        for code in expected
    } == expected
    assert all(
        countries[parent]["display_parent_country"] is None
        for parent in ("CN", "US", "FR", "GB", "NL")
    )
