from __future__ import annotations

import copy
import json
from pathlib import Path

FIXTURE_ROOT = Path(__file__).parent / "fixtures/performance_assurance"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _semantic_body(declaration: dict) -> dict:
    body = copy.deepcopy(declaration)
    body.pop("base_origin")
    body.pop("asset_origins")
    for profile in body["profiles"]:
        profile.pop("destination_scope")
    return body


def test_staging_declaration_only_changes_deployment_scope() -> None:
    production = _load("declaration.json")
    staging = _load("declaration.staging.json")

    assert _semantic_body(staging) == _semantic_body(production)

    assert production["base_origin"] == "https://pushinweight-web.onrender.com"
    assert staging["base_origin"] == "https://pushinweight-staging-web.onrender.com"
    assert staging["asset_origins"] == production["asset_origins"]
    assert {profile["destination_scope"] for profile in staging["profiles"]} == {"remote"}


def test_local_candidate_declaration_is_isolated_and_keeps_both_workloads() -> None:
    production = _load("declaration.json")
    local = _load("declaration.local-candidate.json")

    assert local["fixture"] == production["fixture"]
    assert local["package_source_revision"] == production["package_source_revision"]
    assert local["base_origin"] == "http://127.0.0.1:8764"
    assert local["asset_origins"] == []
    assert {profile["destination_scope"] for profile in local["profiles"]} == {
        "local-only"
    }
    assert [scenario["id"] for scenario in local["scenarios"]] == [
        "homepage-desktop",
        "homepage-mobile",
    ]
    assert all(
        expectation["path"] == "/static/country-flags.svg"
        for scenario in local["scenarios"]
        for expectation in scenario["cache_expectations"]
    )


def test_performance_actions_use_inert_inspection_click() -> None:
    expected = ".follower-magnitude.pw-inspection-trigger"
    for name in (
        "declaration.json",
        "declaration.staging.json",
        "declaration.local-candidate.json",
    ):
        declaration = _load(name)
        assert all(
            action == {"kind": "click", "target": expected}
            for scenario in declaration["scenarios"]
            for action in scenario["actions"]
        )


def test_performance_scenarios_seed_conflicting_locale_and_legacy_state() -> None:
    for name in ("declaration.json", "declaration.staging.json"):
        declaration = _load(name)
        for scenario in declaration["scenarios"]:
            seeds = scenario["state_seeds"]
            locale_seeds = [seed for seed in seeds if seed["storage"] == "cookie" and seed["name"] == "locale"]
            window_seeds = [
                seed
                for seed in seeds
                if seed["storage"] == "cookie" and seed["name"] == "home_window"
            ]
            legacy_seeds = [
                seed
                for seed in seeds
                if seed["storage"] == "local_storage"
                and seed["name"] == "pushinweight.home.preferences.v1:anonymous"
            ]
            assert len(seeds) == 3
            assert locale_seeds == [{"storage": "cookie", "name": "locale", "value": "en"}]
            assert window_seeds == [
                {"storage": "cookie", "name": "home_window", "value": "365"}
            ]
            assert len(legacy_seeds) == 1
            legacy = json.loads(legacy_seeds[0]["value"])
            assert legacy["version"] == 1
            assert legacy["locale"] == "zh_cn"
            assert legacy["timezone"] == "ca"
            assert legacy["lens"] == {"brands": "closed", "nationalism": "cn"}
            assert legacy["window"] == 365
            assert legacy["filters"] == {"brands": ["qwen"], "window": 365}
            assert legacy["pulseBrands"] == ["qwen"]
