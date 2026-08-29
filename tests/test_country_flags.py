"""Runtime country identity generated from the approved flag manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor.country_flags import (
    COUNTRY_FLAGS,
    country_identity,
    normalize_country_code,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPO_ROOT / "docs/ideation/assets/2026-08-29-162947-country-flag-pixels.json"
)


def test_runtime_country_identity_matches_every_manifest_entry() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {
        flag["code"]: {
            "name_en": flag["name"],
            "name_zh_cn": flag["name_zh_cn"],
        }
        for flag in manifest["flags"]
    }

    assert COUNTRY_FLAGS == expected
    assert len(COUNTRY_FLAGS) == 197


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("US", "US"),
        ("us", "US"),
        (" United States ", "US"),
        ("China", "CN"),
        ("中国", "CN"),
        ("South Korea", "KR"),
        ("韩国", "KR"),
    ),
)
def test_normalize_country_code_accepts_only_supported_codes_and_exact_names(
    raw: str,
    expected: str,
) -> None:
    assert normalize_country_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    (None, "", " ", "USA", "UK", "Beijing", "Seoul, Korea", "WW", "HF", "ZZ"),
)
def test_normalize_country_code_fails_closed_for_unknown_locations(
    raw: str | None,
) -> None:
    assert normalize_country_code(raw) is None


@pytest.mark.parametrize("locale", ("zh_cn", "zh_hans", "zh-CN", "zh-Hans"))
def test_country_identity_uses_official_zh_cn_name(locale: str) -> None:
    assert country_identity("KR", locale) == {"code": "KR", "name": "韩国"}


@pytest.mark.parametrize("locale", ("en", "original", "ja", ""))
def test_country_identity_uses_english_outside_zh_locales(locale: str) -> None:
    assert country_identity("South Korea", locale) == {
        "code": "KR",
        "name": "South Korea",
    }


def test_country_identity_omits_unknown_values() -> None:
    assert country_identity(None, "en") is None
    assert country_identity("New York", "zh_cn") is None
