from __future__ import annotations

from pathlib import Path

from scripts.ollija.config import load_project_config
from scripts.ollija.render import (
    assert_blueprints_are_disjoint,
    load_staging_topology,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_release_differentiators_remain_bound_in_one_contract() -> None:
    config = load_project_config(REPO_ROOT)
    staging = config.environments["staging"]
    production = config.environments["production"]

    assert config.authority.canonical_host == "fuchitalee"
    assert "allenwlee" in config.authority.forbidden_hosts
    assert config.git.staging_branch == "staging"
    assert config.git.production_branch == "main"
    assert staging["database_name"] != production["database_name"]
    assert staging["database_resource_id"] not in set(
        config.database_safety["production_resource_ids"]
    )
    assert config.verification["headline_selector"] == "[data-pw-headline-body]"
    assert config.verification["production_base_url"].startswith("https://")


def test_staging_topology_has_no_provider_or_recurring_service() -> None:
    topology = load_staging_topology(REPO_ROOT / "render-staging.yaml")

    assert topology.service_types == ("web",)
    assert "DEEPSEEK_API_KEY" not in topology.environment_keys
    assert "TWITTERAPI_IO_API_KEY" not in topology.environment_keys
    assert_blueprints_are_disjoint(
        REPO_ROOT / "render-staging.yaml",
        REPO_ROOT / "render.yaml",
    )
