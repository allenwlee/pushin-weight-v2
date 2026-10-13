"""Shared collection storage preserves numeric admission and catalog recovery."""

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.models import (
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
    DataSource,
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def source():
    return DataSource.objects.get_or_create(
        id="hf", defaults={"name": "HF", "source_type": "model_adoption"}
    )[0]


def test_live_legacy_benchmark_launcher_uses_shared_storage(settings, monkeypatch):
    import uuid
    from pathlib import Path

    import httpx

    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_download_persistence import configured, payload

    contract = configured()
    batch = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "pw-benchmark-production-bootstrap:" + str(contract.pk) + ":hf",
    )
    run = persist_source(contract, "hf", "9" * 64, payload(), batch_id=batch)
    settings.BENCHMARK_COLLECTION_ENABLED = True

    def no_provider_request(*args, **kwargs):
        raise AssertionError(
            "A retained bootstrap and disabled schedule need no request"
        )

    monkeypatch.setattr(httpx.Client, "send", no_provider_request)
    script = (
        Path(__file__).parent
        / "fixtures/collection_schema/legacy_benchmark_launcher.txt"
    ).read_text()
    script = script.replace("75c4a856-385b-429a-9b03-c7e023ea6f73", str(contract.pk))
    # Execute the vetted, checked-in launcher to cover its actual import/query path.
    exec(compile(script, "legacy_benchmark_launcher.py", "exec"), {})  # noqa: S102
    assert CollectionRun.objects.count() == 1
    assert CollectionRun.objects.get(pk=run.pk).observations.count() == 1


def test_existing_tables_remain_consolidated_with_the_shared_job_registry():
    tables = set(connection.introspection.table_names())
    assert {
        "collection_runs",
        "collection_observations",
        "collection_scope_runs",
        "collection_jobs",
    } <= tables
    assert (
        not {
            "hf_model_catalog_runs",
            "hf_model_catalog_observations",
        }
        & tables
    )


def test_numeric_run_still_requires_a_reviewed_contract():
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRun.objects.create(
            source=source(), ingestion_key="a" * 64, lease_expires_at=timezone.now()
        )


def test_catalog_partial_remains_resumable_without_fake_numeric_contract():
    run = CollectionRun.objects.create(
        source=source(),
        purpose="catalog",
        ingestion_key="b" * 64,
        status="partial",
        scope={"namespaces": []},
    )
    run.refresh_from_db()
    assert run.completed_at is None and run.contract_id is None
    scope = CollectionScopeRun.objects.create(
        run=run, scope_key="publisher", ownership={}, cursor="next"
    )
    observation = CollectionObservation.objects.create(
        run=run,
        scope_run=scope,
        resource_key="publisher/model",
        source_identifier="publisher/Model",
        source_subject_kind="repository",
        observation_key="c" * 64,
        groups={"listing": "ok"},
        processing_outcome="pending",
    )
    assert observation.values.count() == 0
    assert scope.cursor == "next"


def test_metric_partial_requires_completed_timestamp():
    # The former metric-run constraint must remain strict for numeric-purpose rows.
    from tests.test_benchmark_download_db_models import measurement

    _, _, observation = measurement()
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionRun.objects.create(
            source=source(),
            contract=observation.run.contract,
            purpose="metric",
            ingestion_key="d" * 64,
            status="partial",
            lease_expires_at=timezone.now(),
        )


def test_numeric_evidence_cannot_enter_catalog_projection():
    from core.hf_catalog import persist_product
    from tests.test_benchmark_download_db_models import measurement

    _, _, observation = measurement()
    before = (observation.source_metadata, observation.observed_at, observation.status)
    with pytest.raises(ValueError, match="matching catalog evidence"):
        persist_product(observation, {}, [], {}, "detail")
    observation.refresh_from_db()
    assert (
        observation.source_metadata,
        observation.observed_at,
        observation.status,
    ) == before
