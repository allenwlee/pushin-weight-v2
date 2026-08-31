from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING_DATABASE = "pushinweight-staging-db"
STAGING_BROKER = "pushinweight-staging-headlines-broker"
DORMANT_SCHEDULE = "0 0 31 2 *"


def _blueprint() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "render-staging.yaml").read_text(encoding="utf-8")
    )


def _environment_by_key(service: dict) -> dict[str, dict]:
    return {
        entry["key"]: entry for entry in service.get("envVars", []) if "key" in entry
    }


def _service(blueprint: dict, name: str) -> dict:
    return next(service for service in blueprint["services"] if service["name"] == name)


def test_staging_blueprint_declares_one_resource_for_each_owned_role() -> None:
    blueprint = _blueprint()
    services = {service["name"]: service["type"] for service in blueprint["services"]}

    assert services == {
        STAGING_BROKER: "keyvalue",
        "pushinweight-staging-web": "web",
        "pushinweight-staging-headlines": "worker",
        "pushinweight-staging-harvest": "cron",
    }
    assert [database["name"] for database in blueprint["databases"]] == [
        STAGING_DATABASE
    ]
    assert all(name.startswith("pushinweight-staging-") for name in services)


def test_staging_web_remains_owner_only_and_provider_dark() -> None:
    service = _service(_blueprint(), "pushinweight-staging-web")
    environment = _environment_by_key(service)

    assert service["branch"] == "staging"
    assert environment["OLLIJA_STAGING_MODE"]["value"] == "True"
    assert environment["OLLIJA_STAGING_ALLOWED_EMAILS"]["sync"] is False
    assert environment["GOOGLE_CLIENT_ID"]["sync"] is False
    assert environment["GOOGLE_CLIENT_SECRET"]["sync"] is False
    assert "XMONITOR_DRY_RUN" not in environment
    assert environment["X_MONITOR_DEPLOYMENT_ENVIRONMENT"]["value"] == "staging"
    assert environment["X_MONITOR_HEADLINE_SERVING_ENABLED"]["value"] == "False"
    assert environment["X_MONITOR_HEADLINE_ENQUEUE_ENABLED"]["value"] == "False"
    assert environment["X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED"]["value"] == "False"
    assert environment["STAGING_DATA_REFRESH_ENABLED"]["value"] == "True"
    assert environment["STAGING_REFRESH_SOURCE_DATABASE_URL"] == {
        "key": "STAGING_REFRESH_SOURCE_DATABASE_URL",
        "sync": False,
    }
    assert not {
        "DEEPSEEK_API_KEY",
        "TWITTERAPI_IO_SCHEDULED_API_KEY",
        "TWITTERAPI_IO_ON_DEMAND_API_KEY",
    } & set(environment)


def test_staging_harvester_is_dormant_guarded_and_hard_scoped() -> None:
    service = _service(_blueprint(), "pushinweight-staging-harvest")
    environment = _environment_by_key(service)

    assert service["schedule"] == DORMANT_SCHEDULE
    assert service["branch"] == "staging"
    assert service["startCommand"] == (
        "python manage.py run_cycle --staging-acceptance "
        '"${X_MONITOR_STAGING_ACCEPTANCE_CALL_ID:?staging acceptance call ID missing}" '
        "--json"
    )
    assert environment["X_MONITOR_STAGING_ACCEPTANCE_CALL_ID"]["value"] == "A"
    assert environment["X_MONITOR_STAGING_ACCEPTANCE_ENABLED"]["value"] == "True"
    assert environment["X_MONITOR_DEPLOYMENT_ENVIRONMENT"]["value"] == "staging"
    assert (
        environment["X_MONITOR_STAGING_ACCEPTANCE_SERVICE"]["value"] == service["name"]
    )
    assert environment["X_MONITOR_HEADLINE_ENQUEUE_ENABLED"]["value"] == "True"
    assert (
        environment["X_MONITOR_HEADLINE_ACTIVATION_STATE"]["value"] == "owner_override"
    )
    assert environment["X_MONITOR_HEADLINE_SERVING_ENABLED"]["value"] == "False"
    assert "OLLIJA_STAGING_MODE" not in environment
    assert environment["TWITTERAPI_IO_SCHEDULED_API_KEY"]["sync"] is False
    assert environment["TWITTERAPI_IO_ON_DEMAND_API_KEY"]["sync"] is False
    assert not any("fromGroup" in entry for entry in service["envVars"])


def test_staging_worker_is_queue_only_and_provider_scoped() -> None:
    service = _service(_blueprint(), "pushinweight-staging-headlines")
    environment = _environment_by_key(service)
    command = service["startCommand"]

    assert service["branch"] == "staging"
    assert "celery -A project worker" in command
    assert "-Q trend-narratives" in command
    assert "--concurrency=1" in command
    assert "--prefetch-multiplier=1" in command
    assert " beat " not in f" {command} "
    assert environment["X_MONITOR_DEPLOYMENT_ENVIRONMENT"]["value"] == "staging"
    assert environment["X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED"]["value"] == "True"
    assert (
        environment["X_MONITOR_HEADLINE_ACTIVATION_STATE"]["value"] == "owner_override"
    )
    assert environment["X_MONITOR_HEADLINE_SERVING_ENABLED"]["value"] == "False"
    assert environment["DEEPSEEK_API_KEY"]["sync"] is False
    assert "OLLIJA_STAGING_MODE" not in environment
    assert "X_MONITOR_HEADLINE_ENQUEUE_ENABLED" not in environment
    assert not any("fromGroup" in entry for entry in service["envVars"])


def test_every_stateful_runtime_binds_only_to_staging_database_and_broker() -> None:
    blueprint = _blueprint()
    for service_name in (
        "pushinweight-staging-web",
        "pushinweight-staging-headlines",
        "pushinweight-staging-harvest",
    ):
        environment = _environment_by_key(_service(blueprint, service_name))
        assert environment["DATABASE_URL"] == {
            "key": "DATABASE_URL",
            "fromDatabase": {
                "name": STAGING_DATABASE,
                "property": "connectionString",
            },
        }

    broker_keys_by_service = {
        "pushinweight-staging-web": ("CELERY_BROKER_URL",),
        "pushinweight-staging-headlines": (
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
        ),
        "pushinweight-staging-harvest": (
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
        ),
    }
    for service_name, broker_keys in broker_keys_by_service.items():
        environment = _environment_by_key(_service(blueprint, service_name))
        for key in broker_keys:
            assert environment[key] == {
                "key": key,
                "fromService": {
                    "type": "keyvalue",
                    "name": STAGING_BROKER,
                    "property": "connectionString",
                },
            }

    database = blueprint["databases"][0]
    broker = _service(blueprint, STAGING_BROKER)
    assert database["ipAllowList"] == []
    assert broker["ipAllowList"] == []
    assert broker["maxmemoryPolicy"] == "noeviction"


def test_staging_and_production_blueprints_claim_disjoint_resource_names() -> None:
    staging = _blueprint()
    production = yaml.safe_load((REPO_ROOT / "render.yaml").read_text(encoding="utf-8"))

    staging_names = {
        resource["name"]
        for resource in [*staging.get("services", []), *staging.get("databases", [])]
    }
    production_names = {
        resource["name"]
        for resource in [
            *production.get("services", []),
            *production.get("databases", []),
        ]
    }
    assert staging_names.isdisjoint(production_names)

    for service in production["services"]:
        environment = _environment_by_key(service)
        assert not {
            "X_MONITOR_STAGING_ACCEPTANCE_ENABLED",
            "X_MONITOR_STAGING_ACCEPTANCE_CALL_ID",
            "X_MONITOR_STAGING_ACCEPTANCE_SERVICE",
            "STAGING_DATA_REFRESH_ENABLED",
            "STAGING_REFRESH_SOURCE_DATABASE_URL",
        } & set(environment)
