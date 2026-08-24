from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _blueprint() -> dict:
    return yaml.safe_load((REPO_ROOT / "render-staging.yaml").read_text(encoding="utf-8"))


def _environment_by_key(service: dict) -> dict[str, dict]:
    return {entry["key"]: entry for entry in service["envVars"]}


def test_staging_blueprint_keeps_one_isolated_owner_only_web_service() -> None:
    blueprint = _blueprint()

    assert len(blueprint["services"]) == 1
    service = blueprint["services"][0]
    environment = _environment_by_key(service)

    assert service["type"] == "web"
    assert service["name"] == "pushinweight-staging-web"
    assert service["branch"] == "staging"
    assert environment["OLLIJA_STAGING_MODE"]["value"] == "True"
    assert environment["OLLIJA_STAGING_ALLOWED_EMAILS"]["sync"] is False
    assert environment["GOOGLE_CLIENT_ID"]["sync"] is False
    assert environment["GOOGLE_CLIENT_SECRET"]["sync"] is False
    assert environment["XMONITOR_DRY_RUN"]["value"] == "True"
    assert environment["X_MONITOR_HEADLINE_SERVING_ENABLED"]["value"] == "False"
    assert environment["X_MONITOR_HEADLINE_ENQUEUE_ENABLED"]["value"] == "False"
    assert environment["X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED"]["value"] == "False"
    assert environment["X_MONITOR_HEADLINE_ACTIVATION_STATE"]["value"] == "pending"
    assert not {"DEEPSEEK_API_KEY", "TWITTERAPI_IO_API_KEY", "CELERY_BROKER_URL"} & set(environment)


def test_staging_database_has_no_public_ingress_and_only_binds_to_its_web_service() -> None:
    blueprint = _blueprint()
    service = blueprint["services"][0]
    database = blueprint["databases"][0]
    environment = _environment_by_key(service)

    assert database["name"] == "pushinweight-staging-db"
    assert database["ipAllowList"] == []
    assert "DATABASE_URL" in environment
    assert environment["DATABASE_URL"] == {
        "key": "DATABASE_URL",
        "fromDatabase": {
            "name": "pushinweight-staging-db",
            "property": "connectionString",
        },
    }
    database_bindings = [
        entry
        for entry in service["envVars"]
        if "fromDatabase" in entry
    ]
    assert database_bindings == [environment["DATABASE_URL"]]


def test_staging_and_production_blueprints_claim_disjoint_resource_names() -> None:
    staging = _blueprint()
    production = yaml.safe_load((REPO_ROOT / "render.yaml").read_text(encoding="utf-8"))

    staging_names = {
        resource["name"]
        for resource in [*staging.get("services", []), *staging.get("databases", [])]
    }
    production_names = {
        resource["name"]
        for resource in [*production.get("services", []), *production.get("databases", [])]
    }

    assert staging_names.isdisjoint(production_names)
