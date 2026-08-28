"""Target-owned conformance checks for the Bridgewright assurance declaration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from monitor.views import (
    _DASHBOARD_DISCOURSE_FILTER_KEYS,
    _DASHBOARD_LANG_FILTER_KEYS,
    _DASHBOARD_NATIONALISM_KEYS,
    _DASHBOARD_POST_TYPE_KEYS,
    _DASHBOARD_ROLE_FILTER_KEYS,
    HOME_SELECTABLE_BRAND_NICKNAMES,
)
from tests.ui_assurance.covering import (
    covered_tuples,
    covering_rows,
    ordered_sequences,
    required_tuples,
)

ROOT = Path(__file__).resolve().parents[1]
DECLARATION_PATH = ROOT / "tests/fixtures/ui_assurance/declaration.json"
FIXTURE_PATH = ROOT / "tests/fixtures/ui_assurance/data.json"


def _declaration() -> dict:
    return json.loads(DECLARATION_PATH.read_text(encoding="utf-8"))


def _controls() -> dict[str, dict]:
    return {item["id"]: item for item in _declaration()["controls"]}


def test_manifest_pins_the_exact_bridgewright_assurance_build() -> None:
    manifest = yaml.safe_load((ROOT / "bridgewright.yaml").read_text(encoding="utf-8"))

    assert manifest["configuration"]["assurance"] == {
        "profile": "stateful-ui-assurance/v1",
        "declaration": "tests/fixtures/ui_assurance/declaration.json",
    }
    assert manifest["requires"] == {
        "bridgewright_version": "0.1.0",
        "source_revision": "e94b04a9511b3ef494478b84a970035861ab4400",
        "capability_schema": "bridgewright.capabilities/v1",
        "schema_set_digest": "b0d89d3fadb4ccd8d736af2375bc98d1fd50070fe38f3da9ec25fa0558007509",
        "skill_digest": "2504868d2eacb21828ac0b68487cd760f9741c9955810f932e4c9c915d9abc37",
    }


def test_declaration_inventory_matches_the_production_control_vocabulary() -> None:
    controls = _controls()

    assert controls["brands"]["values"] == [
        "__all__",
        *HOME_SELECTABLE_BRAND_NICKNAMES,
    ]
    assert "test_brand" not in controls["brands"]["values"]
    assert controls["sentiment"]["values"] == [
        "__all__", "mixed", "negative", "neutral", "positive"
    ]
    assert controls["post_type"]["values"] == ["__all__", *_DASHBOARD_POST_TYPE_KEYS]
    assert controls["lang"]["values"] == ["__all__", *_DASHBOARD_LANG_FILTER_KEYS]
    assert controls["role"]["values"] == ["__all__", *_DASHBOARD_ROLE_FILTER_KEYS]
    assert controls["nationalism_cn"]["values"] == [
        "__all__", *_DASHBOARD_NATIONALISM_KEYS
    ]
    assert controls["nationalism_us"]["values"] == [
        "__all__", *_DASHBOARD_NATIONALISM_KEYS
    ]
    assert controls["discourse"]["values"] == [
        "__all__", *_DASHBOARD_DISCOURSE_FILTER_KEYS
    ]
    assert controls["unsanctioned"]["values"] == ["off", "only"]
    assert controls["locale"]["values"] == ["en", "zh_cn", "original"]
    assert controls["window"]["values"] == ["1", "7", "30", "365"]
    assert controls["timezone"]["values"] == ["local", "ca"]
    assert controls["brand_lens"]["values"] == ["open", "closed"]
    assert controls["nationalism_lens"]["values"] == ["us", "cn"]
    assert controls["bulk_action"]["values"] == ["idle", "all", "clear"]


def test_fixture_digest_and_declared_brands_are_exact() -> None:
    declaration = _declaration()
    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture = json.loads(fixture_bytes)

    assert hashlib.sha256(fixture_bytes).hexdigest() == declaration["fixture"]["sha256"]
    assert {brand for post in fixture["posts"] for brand in post["brands"]} == set(
        HOME_SELECTABLE_BRAND_NICKNAMES
    )


def test_covering_rows_close_every_declared_tway_tuple_deterministically() -> None:
    declaration = _declaration()
    first = covering_rows(declaration)
    second = covering_rows(declaration)

    assert first == second
    assert covered_tuples(declaration, first) == required_tuples(declaration)
    assert len(first) < len(required_tuples(declaration))
    assert ordered_sequences(declaration)


def test_escaped_regressions_are_named_permanent_seeds() -> None:
    seed_ids = {item["id"] for item in _declaration()["seeded_regressions"]}

    assert seed_ids == {
        "deepseek-select-deselect-restores-all",
        "mimo-seven-to-one-latest-wins",
        "unsanctioned-only-off-partition",
        "hover-freeze-preserves-brand-and-restores-locale",
    }
