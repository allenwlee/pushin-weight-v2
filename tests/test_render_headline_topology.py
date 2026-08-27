"""Static release contract for the queue-isolated Render headline topology."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

PRODUCTION_BLUEPRINT_SHA256 = (
    "2e85c84ebd5eb45557ec5fdecf5cd1ccc444283049cb4c72f1af8f66c67ac84f"
)


def test_production_blueprint_is_unchanged_by_staging_topology_work():
    contents = Path("render.yaml").read_bytes()

    assert hashlib.sha256(contents).hexdigest() == PRODUCTION_BLUEPRINT_SHA256


def test_headline_blueprint_is_queue_isolated_with_owner_override_activation():
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    assert set(services) == {
        "pushinweight-headlines-broker",
        "pushinweight-web",
        "pushinweight-headlines",
        "pushinweight-harvest",
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
            "v23-per-brand-why-first-v1"
        )
        database = next(
            entry["fromDatabase"]["name"]
            for entry in services[service_name]["envVars"]
            if entry.get("key") == "DATABASE_URL"
        )
        assert database == "pushinweight-db-shadow"


def test_render_cron_is_the_only_declared_scheduler():
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    cron_services = [
        service for service in blueprint["services"] if service["type"] == "cron"
    ]

    assert [
        (service["name"], service["schedule"], service["startCommand"])
        for service in cron_services
    ] == [("pushinweight-harvest", "*/15 * * * *", "python manage.py run_cycle")]
    assert all(
        "beat" not in service.get("startCommand", "")
        for service in blueprint["services"]
    )
