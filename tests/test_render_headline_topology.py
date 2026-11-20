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
        "pushinweight-enrichment",
        "pushinweight-harvest",
        "pushinweight-jobs",
        "pushinweight-home-counts",
        "pushinweight-graphics-a",
        "pushinweight-graphics-b",
        "pushinweight-graphics-review",
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
        database = next(entry for entry in services[service_name]["envVars"]
                        if entry.get("key") == "DATABASE_URL")
        if service_name == "pushinweight-web":
            assert database == {"key": "DATABASE_URL", "sync": False}
            assert environment["PW_DATABASE_ACCESS_MODE"] == "serving"
        else:
            assert database["fromDatabase"]["name"] == "pushinweight-db-shadow"


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
    assert environment["DEEPINFRA_API_KEY"]["sync"] is False
    assert "DEEPSEEK_API_KEY" not in environment
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
        "pushinweight-home-counts": (
            "7,22,37,52 * * * *",
            "python manage.py refresh_materializations",
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


def test_enrichment_worker_has_one_process_and_no_collection_credentials():
    for filename, name in (
        ("render.yaml", "pushinweight-enrichment"),
        ("render-staging.yaml", "pushinweight-staging-enrichment"),
    ):
        worker = next(service for service in yaml.safe_load(Path(filename).read_text())["services"] if service["name"] == name)
        environment = {entry["key"]: entry for entry in worker["envVars"] if "key" in entry}
        assert worker["type"] == "worker"
        assert worker["numInstances"] == 1
        assert worker["maxShutdownDelaySeconds"] == 120
        assert worker["startCommand"] == "python manage.py run_enrichment_worker --json"
        assert environment["X_MONITOR_ENRICHMENT_PROVIDER_CALLS_ACTIVE"] == {
            "key": "X_MONITOR_ENRICHMENT_PROVIDER_CALLS_ACTIVE", "sync": False,
        }
        assert "schedule" not in worker
        assert not {"TWITTERAPI_IO_SCHEDULED_API_KEY", "TWITTERAPI_IO_ON_DEMAND_API_KEY"} & set(environment)
        if filename == "render.yaml":
            assert "CELERY_BROKER_URL" not in environment
        else:
            assert environment["CELERY_BROKER_URL"]["fromService"]["name"] == "pushinweight-staging-headlines-broker"


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


def test_harvest_declares_direct_typesafe_credential_without_a_value():
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    harvest = next(
        service
        for service in blueprint["services"]
        if service["name"] == "pushinweight-harvest"
    )
    environment = {
        entry["key"]: entry for entry in harvest["envVars"] if "key" in entry
    }

    assert environment["TYPESAFE_API_KEY"] == {
        "key": "TYPESAFE_API_KEY",
        "sync": False,
    }


def test_enrichment_workers_preserve_production_processing_configuration(monkeypatch):
    import os

    from x_monitor.config import load_config

    def effective(path, name):
        blueprint = yaml.safe_load(Path(path).read_text())
        service = next(row for row in blueprint["services"] if row["name"] == name)
        with monkeypatch.context() as env:
            for key in os.environ:
                if key.startswith("X_MONITOR_"):
                    env.delenv(key, raising=False)
            for row in service["envVars"]:
                if "value" in row:
                    env.setenv(row["key"], str(row["value"]))
            return load_config(Path("config.yaml"))

    harvest = effective("render.yaml", "pushinweight-harvest")
    for path, name in [("render.yaml", "pushinweight-enrichment"), ("render-staging.yaml", "pushinweight-staging-enrichment")]:
        worker = effective(path, name)
        assert worker.harvest.enrichment.provider_calls_active is False
        if path == "render-staging.yaml":
            assert worker.llm.classifier_pipeline == "compressed8_pulse_v1"
            assert worker.llm.model_copy(update={"classifier_pipeline": harvest.llm.classifier_pipeline}) == harvest.llm
        else:
            assert worker.llm == harvest.llm
        assert worker.targeted_extraction == harvest.targeted_extraction
        assert worker.discovery.rare_types == harvest.discovery.rare_types


def test_enrichment_activation_survives_later_blueprint_sync(monkeypatch):
    from x_monitor.config import load_config

    for filename, name in [("render.yaml", "pushinweight-enrichment"), ("render-staging.yaml", "pushinweight-staging-enrichment")]:
        service = next(row for row in yaml.safe_load(Path(filename).read_text())["services"] if row["name"] == name)
        with monkeypatch.context() as env:
            env.setenv("X_MONITOR_ENRICHMENT_PROVIDER_CALLS_ACTIVE", "True")
            for row in service["envVars"]:
                if "value" in row:
                    env.setenv(row["key"], str(row["value"]))
            assert load_config(Path("config.yaml")).harvest.enrichment.provider_calls_active is True


def test_staging_pulse_uses_one_broker_and_shared_control_without_enabling_model_calls():
    blueprint = yaml.safe_load(Path('render-staging.yaml').read_text(encoding='utf-8'))
    services = {row['name']: row for row in blueprint['services']}
    names = ('pushinweight-staging-web', 'pushinweight-staging-headlines',
             'pushinweight-staging-enrichment', 'pushinweight-staging-harvest')
    for name in names:
        env = {entry['key']: entry for entry in services[name]['envVars'] if 'key' in entry}
        assert env['PULSE_CONTROL_R2_BUCKET']['value'] == 'pushinweight-media-staging'
        assert env['PRODUCT_RELEASE_BACKGROUND_ENABLED']['value'] == 'True'
        assert env['X_MONITOR_CLASSIFIER_PIPELINE']['value'] == 'compressed8_pulse_v1'
        assert env['CELERY_BROKER_URL']['fromService']['name'] == 'pushinweight-staging-headlines-broker'
        if name != 'pushinweight-staging-web':
            for key in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY'):
                assert env[key]['fromService']['name'] == 'pushinweight-staging-web'
    headline_env = {item['key']: item for item in services['pushinweight-staging-headlines']['envVars'] if 'key' in item}
    enrichment_env = {item['key']: item for item in services['pushinweight-staging-enrichment']['envVars'] if 'key' in item}
    assert headline_env['X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED']['value'] == 'False'
    assert enrichment_env['X_MONITOR_ENRICHMENT_PROVIDER_CALLS_ACTIVE']['sync'] is False
