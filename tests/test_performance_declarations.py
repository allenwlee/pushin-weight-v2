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
        expectation["path"] == "/static/pw-processing-glyphs.svg"
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


def test_general_candidate_preserves_pro_workloads_and_checks_immutable_assets() -> None:
    from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
    from django.core.files.base import ContentFile

    baseline = _load("declaration.local-candidate.json")
    general = _load("declaration.general-candidate.json")
    sprite = Path(__file__).parents[1] / "monitor/static/pw-processing-glyphs.svg"
    hashed_name = ManifestStaticFilesStorage().hashed_name(
        sprite.name, content=ContentFile(sprite.read_bytes())
    )
    for actual, original in zip(general["scenarios"][:2], baseline["scenarios"]):
        assert actual["cache_expectations"] == [{
            "path": "/static/" + hashed_name,
            "policy": "immutable",
            "min_max_age_seconds": 31_536_000,
            "must_reuse": True,
        }]
        comparable = copy.deepcopy(actual)
        comparable["cache_expectations"] = original["cache_expectations"]
        assert comparable == original
    assert {case["id"] for case in general["scenarios"][2:]} == {
        "general-desktop", "general-mobile"
    }


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


def test_each_candidate_preserves_four_workloads_and_measures_rich_each_legend() -> None:
    import hashlib
    from urllib.parse import parse_qs, urlparse

    from bridgewright.performance.contracts import PerformanceDeclaration
    from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
    from django.core.files.base import ContentFile

    root = Path(__file__).parents[1]
    general = _load("declaration.general-candidate.json")
    each = _load("declaration.each-candidate.json")
    PerformanceDeclaration.model_validate(each)

    # Extending candidate coverage must never alter existing workloads, budgets,
    # cache requirements, metric engines, run counts, or device profiles.
    assert each["scenarios"][:4] == general["scenarios"]
    assert {key: value for key, value in each.items() if key not in {"scenarios", "fixture"}} == {
        key: value for key, value in general.items() if key not in {"scenarios", "fixture"}
    }
    assert each["fixture"] == {
        "path": "tests/fixtures/performance_assurance/each-seed.json",
        "sha256": hashlib.sha256((root / "tests/fixtures/performance_assurance/each-seed.json").read_bytes()).hexdigest(),
    }
    seed_recipe = json.loads((root / each["fixture"]["path"]).read_text())
    assert seed_recipe["schema_version"] == "pushinweight.performance-seed/v1"
    inputs = {item["id"]: item for item in seed_recipe["inputs"]}
    assert len(inputs) == len(seed_recipe["inputs"]) == 12
    assert {key: item["path"] for key, item in inputs.items()} == {
        "base-oracle": "docs/ideation/mockups/06-tier1-composed.v22-master.html",
        "base-fixture": "tests/golden/v22_mockup_fixture.json",
        "base-oracle-reader": "tests/mockup_spec.py",
        "base-seeder": "tests/v22_support.py",
        "each-manifest": "tests/fixtures/ui_assurance/each-fixture.json",
        "each-seeder": "tests/each_area_fixture.py",
        "general-contract": "tests/fixtures/general_feed_contract.json",
        "general-seeder": "tests/general_helpers.py",
        "combined-seeder": "tests/each_performance_fixture.py",
        "harvest-coverage-seeder": "tests/test_chart_harvest_coverage.py",
        "ping-delay-bootstrap": "tests/fixtures/performance_assurance/ping-delay-bootstrap.js",
        "preview-transport": "tests/ui_assurance/local_preview.py",
    }
    for item in inputs.values():
        assert item["sha256"] == hashlib.sha256((root / item["path"]).read_bytes()).hexdigest(), item["path"]
    bootstrap = seed_recipe["fixture_bootstrap"]
    assert bootstrap["input"] == "ping-delay-bootstrap"
    assert bootstrap["sha256"] == inputs["ping-delay-bootstrap"]["sha256"]
    assert bootstrap["transport_input"] == "preview-transport"
    assert bootstrap["target"] == "CSSStyleDeclaration.prototype.setProperty(--pw-ping-delay, value, priority)"
    assert bootstrap["numeric_lexeme_width"] == bootstrap["maximum_numeric_digits"] == 40
    assert bootstrap["raw_max_characters"] == 42
    assert bootstrap["phase_ms"] == [-2250, 0]
    assert "execution cost remain in the measurement" in bootstrap["injection"]
    assert "Object.is" in bootstrap["transformation"] and "negative zero" in bootstrap["transformation"]
    assert "Remove documentElement and throw" in bootstrap["invalid_input"]
    assert seed_recipe["entrypoint"] == {
        "call": "tests.each_performance_fixture.seed_each_performance_orm(now=captured_preview_seed_time)",
        "returns": "captured_preview_seed_time", "inputs": ["combined-seeder"],
    }
    recipe = {step["id"]: step for step in seed_recipe["recipe"]}
    assert list(recipe) == ["general-clock", "base", "base-synthesis", "each", "general", "general-closed-job", "harvest-coverage"]
    assert recipe["base"]["call"] == "tests.v22_support.seed_real_home_orm(tests.v22_support.fixture_from_oracle())"
    assert recipe["base-synthesis"]["for_each"] == 'post in Post.objects.filter(tweet_id__startswith="u3-post-")'
    assert recipe["base-synthesis"]["call"] == 'tests.general_helpers.saved_commentary(post, texts={"en": post.commentary_en, "zh-cn": post.commentary_zh_cn, "ja": f"保存されたテスト用解説 {post.pk}"})'
    assert recipe["base-synthesis"]["expected_status"] == "ready"
    assert recipe["each"]["call"] == "tests.each_area_fixture.seed_each_area_orm(json.loads(each_manifest))"
    assert recipe["each"]["expected_return"] == 62
    assert recipe["general-clock"]["assign"] == "tests.general_helpers.NOW = captured_preview_seed_time"
    assert recipe["general"]["for_each"] == 'post_id, category in general_contract["sections"].items()'
    assert recipe["general"]["call"] == "tests.general_helpers.saved_commentary(tests.general_helpers.classified_post(post_id, category))"
    assert recipe["general-closed-job"]["call"] == 'tests.general_helpers.saved_commentary(tests.general_helpers.classified_post(general_contract["closed_job"], brand="claude"))'
    assert recipe["harvest-coverage"]["call"] == "tests.test_chart_harvest_coverage.record_harvest(captured_preview_seed_time, finished_at=captured_preview_seed_time, staggered=False)"
    assert seed_recipe["time_policy"]["kind"] == "frozen-preview-test-clock"
    assert seed_recipe["time_policy"]["general_override"] == {
        "symbol": "tests.general_helpers.NOW", "value": "captured preview seed time",
    }
    assert {name for names in seed_recipe["workloads"].values() for name in names} == {
        case["id"] for case in each["scenarios"]
    }
    seed = json.loads((root / inputs["each-manifest"]["path"]).read_text())
    assert seed["brand"] == "deepseek" and seed["days"] == 7
    assert seed["counts"] == [8, 9, 10, 8, 9, 10, 8]
    assert sum(seed["counts"]) == 62 and "bug" in seed["products"]

    additions = each["scenarios"][4:]
    assert [case["id"] for case in additions] == ["each-desktop", "each-mobile"]
    assert [case["profile"] for case in additions] == ["desktop", "mobile"]
    expected_assets = []
    for filename in ("pw-each-chart.js", "pw-each-chart.css"):
        asset = root / "monitor/static" / filename
        hashed = ManifestStaticFilesStorage().hashed_name(filename, content=ContentFile(asset.read_bytes()))
        expected_assets.append({
            "path": "/static/" + hashed, "policy": "immutable",
            "min_max_age_seconds": 31_536_000, "must_reuse": True,
        })
    for case, locale in zip(additions, ("en", "zh_cn"), strict=True):
        route = urlparse(case["route"])
        assert route.path == "/dashboard/each"
        assert parse_qs(route.query) == {
            "brand": ["deepseek"], "locale": [locale], "window": ["7"],
            "tab": ["product_labels"], "timezone": ["Asia/Tokyo"],
        }
        assert case["actions"] == [{"kind": "click", "target": '[data-each-category="bug"]'}]
        assert case["cache_expectations"] == expected_assets
        original = next(item for item in general["scenarios"] if item["id"] == "general-" + case["profile"])
        for field in ("runs", "required_metrics", "metric_engines", "web_vitals_metrics", "lighthouse_assertions", "budgets"):
            assert case[field] == original[field]
        assert case["network_expectations"] == [
            {"path": "/dashboard/each/chart/", "max_requests": 2, "max_bytes": 500_000},
            {"path": "/api/v2/dashboard/each/headline/", "max_requests": 0, "max_bytes": 0},
            {"path": "/feed/", "max_requests": 0, "max_bytes": 0},
            {"path": "/chart.html", "max_requests": 0, "max_bytes": 0},
        ]
