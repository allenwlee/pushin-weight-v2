"""Runtime flag availability generated from the approved pixel manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor.country_flags import COUNTRY_FLAG_CODES, country_flag_symbol_id

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPO_ROOT / "docs/ideation/assets/2026-08-29-162947-country-flag-pixels.json"
)


def test_runtime_flag_inventory_matches_every_manifest_entry() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = frozenset(flag["code"] for flag in manifest["flags"])

    assert COUNTRY_FLAG_CODES == expected
    assert len(COUNTRY_FLAG_CODES) == 215
    assert "TW" in COUNTRY_FLAG_CODES


@pytest.mark.parametrize("code", ("CN", "HK", "KR", "MO", "TW", "US"))
def test_country_flag_symbol_id_accepts_only_exact_approved_codes(code: str) -> None:
    assert country_flag_symbol_id(code) == f"flag-{code.lower()}"


@pytest.mark.parametrize(
    "value",
    (None, "", "us", " US ", "United States", "WW", "HF", "ZZ", 1),
)
def test_country_flag_symbol_id_fails_closed_for_unapproved_values(
    value: object,
) -> None:
    assert country_flag_symbol_id(value) is None
