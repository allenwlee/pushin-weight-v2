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

    assert staging["base_origin"] == "https://pushinweight-staging-web.onrender.com"
    assert staging["asset_origins"] == production["asset_origins"]
    assert {profile["destination_scope"] for profile in staging["profiles"]} == {"remote"}


def test_performance_actions_use_inert_inspection_click() -> None:
    expected = ".follower-magnitude.pw-inspection-trigger"
    for name in ("declaration.json", "declaration.staging.json"):
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
