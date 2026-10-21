"""The new provider-free job must not inherit collection credentials/schedules."""

from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("staging", [False, True])
def test_count_maintenance_has_only_owned_database_configuration(staging):
    blueprint = yaml.safe_load(
        Path("render-staging.yaml" if staging else "render.yaml").read_text()
    )
    name = "pushinweight-staging-home-counts" if staging else "pushinweight-home-counts"
    jobs = [service for service in blueprint["services"] if service["name"] == name]
    assert len(jobs) == 1, "declare exactly one isolated count maintenance job"
    job = jobs[0]
    assert job["type"] == "cron"
    assert job["startCommand"] == "python manage.py refresh_home_counts"
    assert job["schedule"] == ("0 0 31 2 *" if staging else "7,22,37,52 * * * *")
    environment = {item["key"]: item for item in job["envVars"]}
    assert set(environment) == {
        "PYTHON_VERSION",
        "DEBUG",
        "X_MONITOR_DEPLOYMENT_ENVIRONMENT",
        "DATABASE_URL",
    }
    assert environment["DATABASE_URL"]["fromDatabase"]["name"] == (
        "pushinweight-staging-db" if staging else "pushinweight-db-shadow"
    )
