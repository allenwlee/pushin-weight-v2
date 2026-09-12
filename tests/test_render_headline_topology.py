"""Static release contract for the queue-isolated Render headline topology."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_headline_blueprint_is_queue_isolated_with_owner_override_activation():
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    assert set(services) == {
        "pushinweight-headlines-broker",
        "pushinweight-web",
        "pushinweight-headlines",
        "pushinweight-synthesis",
        "pushinweight-harvest",
        "pushinweight-jobs",
    }
    assert [database["name"] for database in blueprint["databases"]] == [
        "pushinweight-db-shadow"
    ]

    worker = services["pushinweight-headlines"]
    command = worker["startCommand"]
    assert "-Q trend-narratives" in command
    assert "--concurrency=1" in command
    assert "--prefetch-multiplier=1" in command
    assert " beat " not in f" {command} "
    assert {entry.get("key") for entry in worker["envVars"]} >= {
        "DATABASE_URL",
        "CELERY_BROKER_URL",
        "DEEPSEEK_API_KEY",
        "X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED",
    }
    assert not any("fromGroup" in entry for entry in worker["envVars"])

    expected_controls = {
        "pushinweight-web": "X_MONITOR_HEADLINE_SERVING_ENABLED",
        "pushinweight-headlines": "X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED",
        "pushinweight-harvest": "X_MONITOR_HEADLINE_ENQUEUE_ENABLED",
    }
    for service_name, control in expected_controls.items():
        environment = {
            entry["key"]: entry.get("value")
            for entry in services[service_name]["envVars"]
            if "key" in entry
        }
        assert environment[control] == "True"
        assert environment["X_MONITOR_HEADLINE_ACTIVATION_STATE"] == "owner_override"
        assert environment["X_MONITOR_HEADLINE_CONTROL_REVISION"] == (
            "v24-integrated-ja-demand-20260911"
        )
        database = next(
            entry["fromDatabase"]["name"]
            for entry in services[service_name]["envVars"]
            if entry.get("key") == "DATABASE_URL"
        )
        assert database == "pushinweight-db-shadow"


def test_synthesis_worker_is_database_only_and_provider_scoped():
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}
    worker = services["pushinweight-synthesis"]
    environment = {entry["key"]: entry for entry in worker["envVars"] if "key" in entry}

    assert worker["type"] == "worker"
    assert worker["startCommand"] == "python manage.py run_synthesis_worker"
    assert environment["DATABASE_URL"]["fromDatabase"]["name"] == (
        "pushinweight-db-shadow"
    )
    assert environment["DEEPSEEK_API_KEY"]["sync"] is False
    assert environment["X_MONITOR_SYNTHESIS_PROVIDER_CALLS_ENABLED"]["value"] == "True"
    assert environment["X_MONITOR_SYNTHESIS_ACTIVATION_STATE"]["value"] == (
        "owner_override"
    )
    assert not {
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "TWITTERAPI_IO_SCHEDULED_API_KEY",
        "TWITTERAPI_IO_ON_DEMAND_API_KEY",
    } & set(environment)
    assert not any("fromGroup" in entry for entry in worker["envVars"])


def test_render_crons_keep_harvest_as_the_only_cycle_scheduler():
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    cron_services = [
        service for service in blueprint["services"] if service["type"] == "cron"
    ]

    assert {
        service["name"]: (service["schedule"], service["startCommand"])
        for service in cron_services
    } == {
        "pushinweight-harvest": (
            "*/15 * * * *",
            "python manage.py run_cycle --scheduled",
        ),
        "pushinweight-jobs": (
            "17 */6 * * *",
            "python manage.py sync_job_sources",
        ),
    }
    cycle_schedulers = [
        service for service in cron_services if "run_cycle" in service["startCommand"]
    ]
    assert [service["name"] for service in cycle_schedulers] == ["pushinweight-harvest"]
    assert all(
        "beat" not in service.get("startCommand", "")
        for service in blueprint["services"]
    )


def test_about_backfill_hosts_have_explicit_production_identity():
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    for service_name in ("pushinweight-web", "pushinweight-harvest"):
        environment = {
            entry["key"]: entry.get("value")
            for entry in services[service_name]["envVars"]
            if "key" in entry
        }
        assert environment["X_MONITOR_DEPLOYMENT_ENVIRONMENT"] == "production"
