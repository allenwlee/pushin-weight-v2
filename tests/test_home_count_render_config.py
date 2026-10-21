"""The new provider-free job must not inherit collection credentials/schedules."""

from pathlib import Path

import yaml


def test_count_maintenance_has_only_owned_database_configuration():
    blueprint = yaml.safe_load(Path("render.yaml").read_text())
    name = "pushinweight-home-counts"
    jobs = [service for service in blueprint["services"] if service["name"] == name]
    assert len(jobs) == 1, "declare exactly one isolated count maintenance job"
    job = jobs[0]
    assert job["type"] == "cron"
    assert job["startCommand"] == "python manage.py refresh_home_counts"
    assert job["schedule"] == "7,22,37,52 * * * *"
    environment = {item["key"]: item for item in job["envVars"]}
    assert set(environment) == {
        "PYTHON_VERSION",
        "DEBUG",
        "X_MONITOR_DEPLOYMENT_ENVIRONMENT",
        "DATABASE_URL",
    }
    assert environment["DATABASE_URL"]["fromDatabase"]["name"] == "pushinweight-db-shadow"


def test_schema_integration_does_not_provision_staging_count_maintenance():
    blueprint = yaml.safe_load(Path("render-staging.yaml").read_text())
    assert all(
        service["name"] != "pushinweight-staging-home-counts"
        and service.get("startCommand") != "python manage.py refresh_home_counts"
        for service in blueprint["services"]
    ), "staging count-cron provisioning is excluded from this delivery"
