from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.ollija.render import (
    RenderTopologyError,
    assert_blueprints_are_disjoint,
    load_staging_topology,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_staging_blueprint_has_only_owner_review_web_and_database() -> None:
    topology = load_staging_topology(REPO_ROOT / "render-staging.yaml")

    assert topology.web_service_name == "pushinweight-staging-web"
    assert topology.database_name == "pushinweight-staging-db"
    assert topology.branch == "staging"
    assert topology.service_types == ("web",)
    assert "DEEPSEEK_API_KEY" not in topology.environment_keys
    assert "TWITTERAPI_IO_API_KEY" not in topology.environment_keys
    assert "CELERY_BROKER_URL" not in topology.environment_keys


def test_staging_and_production_blueprints_claim_disjoint_resources() -> None:
    assert_blueprints_are_disjoint(
        REPO_ROOT / "render-staging.yaml",
        REPO_ROOT / "render.yaml",
    )


@pytest.mark.parametrize("service_type", ["worker", "cron", "keyvalue"])
def test_staging_topology_rejects_recurring_or_queue_services(
    tmp_path: Path,
    service_type: str,
) -> None:
    body = yaml.safe_load((REPO_ROOT / "render-staging.yaml").read_text())
    body["services"][0]["type"] = service_type
    path = tmp_path / "render-staging.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")

    with pytest.raises(RenderTopologyError, match="recurring_service_forbidden"):
        load_staging_topology(path)


def test_staging_topology_rejects_provider_secrets_and_production_groups(
    tmp_path: Path,
) -> None:
    body = yaml.safe_load((REPO_ROOT / "render-staging.yaml").read_text())
    body["services"][0]["envVars"].extend(
        [{"key": "DEEPSEEK_API_KEY", "sync": False}, {"fromGroup": "prod"}]
    )
    path = tmp_path / "render-staging.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")

    with pytest.raises(RenderTopologyError):
        load_staging_topology(path)
