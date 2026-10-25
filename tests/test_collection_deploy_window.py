"""The deployed0092 ORM and dispatcher remain usable during additive rollout."""

import hashlib
import sys
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from core.collection_jobs import register_job, set_job_state
from core.collection_scheduling import collection_authority, take_collection_authority
from core.models import DataSource
from tests.collection_bridge_fixture import HASHES

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.fixture
def previous(monkeypatch):
    historical = MigrationLoader(connection).project_state(
        [("core", "0092_measurement_window_index")]
    ).apps
    modules = {}
    for name in ("collection_jobs", "collection_scheduling", "collection_state"):
        path = Path(__file__).parent / "fixtures/collection_compat" / (
            name + "_64b95c26.py.txt"
        )
        module = ModuleType("previous_" + name)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        source = path.read_bytes()
        assert hashlib.sha256(source).hexdigest() == HASHES[name]
        exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102 - hash-pinned deployed fixture
        module.CollectionJob = historical.get_model("core", "CollectionJob")
        module.CollectionRun = historical.get_model("core", "CollectionRun")
        module.DataSource = historical.get_model("core", "DataSource")
        module.CollectionScopeRun = historical.get_model("core", "CollectionScopeRun")
        modules[name] = module
    modules["collection_scheduling"].validate_job = modules["collection_jobs"].validate_job
    modules["collection_state"].validate_job = modules["collection_jobs"].validate_job
    return SimpleNamespace(
        jobs=modules["collection_jobs"],
        scheduling=modules["collection_scheduling"],
        state=modules["collection_state"],
        Source=historical.get_model("core", "DataSource"),
    )


def definition():
    return {
        "version": 1,
        "scope": {"routine_role": "inventory:compat"},
        "schedule": {"kind": "daily_utc", "hour": 10, "driver": "shared"},
        "budgets": {"requests": 10, "bytes": 10000, "seconds": 30, "items": 100},
    }


def current_job():
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.adapter_key = "hf-v1"
    source.save(update_fields=["enabled", "adapter_key"])
    job = register_job(
        job_key="compat-current", source=source, purpose="catalog",
        operation="hf_catalog", mode="recurring", definition=definition(),
    )
    return set_job_state(job.pk, "ready")


def test_previous_orm_can_register_and_select_authority_on_expanded_database(previous):
    previous.Source.objects.create(
        pk="deploy-compat", name="Compatibility source", source_type="model_adoption"
    )
    source = previous.Source.objects.get(pk="hf")
    source.enabled = True
    source.adapter_key = "hf-v1"
    source.save(update_fields=["enabled", "adapter_key"])
    job = previous.jobs.register_job(
        job_key="compat-old", source=source, purpose="catalog", operation="hf_catalog",
        mode="recurring", definition=definition(),
    )
    job = previous.jobs.set_job_state(job.pk, "ready")
    previous.scheduling.take_collection_authority(job.pk)
    source.refresh_from_db()
    assert previous.scheduling.collection_authority(source, "inventory:compat") == str(job.pk)
    assert collection_authority(DataSource.objects.get(pk="hf"), "inventory:compat") == str(job.pk)
    claim = previous.state.claim_job(job.pk)
    previous.state.checkpoint_scope(claim, scope_key="compat", ownership={})
    previous.state.finish_run(claim, status="partial", request_count=0)
    run = previous.state.CollectionRun.objects.get(pk=claim.run_id)
    assert run.status == "partial" and run.scopes.get().scope_key == "compat"


def test_copy_keeps_previous_dispatcher_authority_and_unrelated_metadata(previous):
    job = current_job()
    previous.scheduling.take_collection_authority(job.pk)
    source = DataSource.objects.get(pk="hf")
    source.metadata = {**source.metadata, "unrelated": {"preserve": True}}
    source.save(update_fields=["metadata"])
    migration = import_module("core.migrations.0106_collection_schedule_data")
    from django.apps import apps

    migration.forward(apps, SimpleNamespace(connection=connection))
    source.refresh_from_db()
    assert previous.scheduling.collection_authority(source, "inventory:compat") == str(job.pk)
    assert collection_authority(source, "inventory:compat") == str(job.pk)
    assert source.metadata["unrelated"] == {"preserve": True}


def test_new_v1_authority_is_readable_by_previous_dispatcher(previous):
    job = current_job()
    take_collection_authority(job.pk)
    source = DataSource.objects.get(pk="hf")
    assert previous.scheduling.collection_authority(source, "inventory:compat") == str(job.pk)


def test_previous_budget_write_updates_typed_limits_without_touching_other_metadata(previous):
    source = DataSource.objects.get(pk="hf")
    old = previous.Source.objects.get(pk=source.pk)
    old.metadata = {
        "unrelated": "retained",
        "collection_role_dispatch_budget": {"requests": 12, "bytes": 12000, "seconds": 45},
    }
    old.save(update_fields=["metadata"])
    source.refresh_from_db()
    assert (source.dispatch_max_requests, source.dispatch_max_bytes, source.dispatch_max_seconds) == (12, 12000, 45)
    assert source.metadata["unrelated"] == "retained"


@contextmanager
def copying_before_bridge_install():
    """Reproduce the real gap between the first copy and trigger installation."""
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE data_sources DISABLE TRIGGER collection_previous_dispatch_bridge")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE data_sources ENABLE TRIGGER collection_previous_dispatch_bridge")


def replay_copy():
    from django.apps import apps

    import_module("core.migrations.0106_collection_schedule_data").forward(
        apps, SimpleNamespace(connection=connection)
    )


def test_final_copy_reconciles_a_legacy_takeover_during_build(previous):
    from core.models import CollectionJob

    first = current_job()
    take_collection_authority(first.pk)
    with copying_before_bridge_install():
        previous.jobs.set_job_state(first.pk, "cancelled")
        second = previous.jobs.register_job(
            job_key="compat-replacement", source=previous.Source.objects.get(pk="hf"),
            purpose="catalog", operation="hf_catalog", mode="recurring", definition=definition(),
        )
        previous.scheduling.take_collection_authority(second.pk)
        replay_copy()
    assert not CollectionJob.objects.get(pk=first.pk).authority_enabled
    assert collection_authority(DataSource.objects.get(pk="hf"), "inventory:compat") == str(second.pk)


def test_final_copy_does_not_reactivate_a_removed_legacy_authority(previous):
    from core.models import CollectionJob

    job = current_job()
    take_collection_authority(job.pk)
    with copying_before_bridge_install():
        source = previous.Source.objects.get(pk="hf")
        source.metadata = {**source.metadata, "collection_role_authorities": {}}
        source.save(update_fields=["metadata"])
        replay_copy()
    assert not CollectionJob.objects.get(pk=job.pk).authority_enabled
    assert collection_authority(DataSource.objects.get(pk="hf"), "inventory:compat") is None
