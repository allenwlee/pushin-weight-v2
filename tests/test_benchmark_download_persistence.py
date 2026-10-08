from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from core.models import MetricCollectionRun, MetricObservation, MetricValue
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def configured():
    from core.benchmark_metric_identity import configure_collection

    _, spec = setup_spec()
    return configure_collection(spec)


def payload(downloads=10):
    return {
        "status": "ok",
        "rows": [
            {
                "repo_id": "lab/Model",
                "status": "ok",
                "raw": {"downloads": downloads, "downloadsAllTime": 100},
            }
        ],
    }


def test_hf_atomic_idempotent_values_do_not_invent_window_bounds():
    from core.benchmark_metric_store import persist_source

    contract = configured()
    run = persist_source(contract, "hf", "a" * 64, payload())
    assert run.status == "success"
    assert persist_source(contract, "hf", "a" * 64, payload()).pk == run.pk
    assert MetricObservation.objects.count() == 1
    values = list(MetricValue.objects.order_by("source_metric__metric_key"))
    assert [v.integer_value for v in values] == [10, 100]
    assert all(
        v.window_start_at is None
        and v.window_end_at is None
        and v.temporal_status == "unknown"
        for v in values
    )
    assert all(v.observation.observed_at is not None for v in values)


@pytest.mark.parametrize("bad", [1.5, True, -1, "10", 2**63])
def test_hf_bad_counts_retain_failed_envelope_without_values(bad):
    from core.benchmark_metric_store import persist_source

    run = persist_source(configured(), "hf", "b" * 64, payload(bad))
    assert run.status == "failed"
    assert run.raw_payload is not None
    assert not MetricValue.objects.exists()


def test_injected_database_write_failure_cannot_publish_success():
    from core.benchmark_metric_store import persist_source

    contract = configured()
    with (
        patch(
            "core.benchmark_metric_store.MetricValue.objects.bulk_create",
            side_effect=RuntimeError("injected"),
        ),
        pytest.raises(RuntimeError),
    ):
        persist_source(contract, "hf", "c" * 64, payload())
    assert MetricCollectionRun.objects.get().status == "running"
    assert not MetricObservation.objects.exists()


def test_calendar_days_respect_daylight_saving_and_reject_ambiguous_times():
    from core.benchmark_metric_store import aware_instant, calendar_window

    start, end = calendar_window("2026-03-08", "America/New_York")
    assert (end - start).total_seconds() == 23 * 3600
    start, end = calendar_window("2026-11-01", "America/New_York")
    assert (end - start).total_seconds() == 25 * 3600
    with pytest.raises(ValueError):
        aware_instant("2026-11-01T01:30:00")


def provider_contract(source, metrics):
    from core.benchmark_metric_identity import configure_collection

    _, spec = setup_spec()
    spec["mappings"][0].update(
        source=source,
        source_subject_kind="model",
        identifier_scope="",
        external_identifier="lab/model",
    )
    spec["source_configuration"] = {source: {"metrics": metrics}}
    return configure_collection(spec)


def test_openrouter_keeps_exact_integer_and_completed_utc_period():
    from core.benchmark_metric_store import persist_source

    contract = provider_contract("openrouter", ["total_tokens"])
    data = {
        "status": "ok",
        "meta": {"version": "v1"},
        "as_of": "2026-10-06T00:30:00Z",
        "rows": [
            {
                "date": "2026-10-05",
                "model_permaslug": "lab/model",
                "total_tokens": "6458330218100",
            },
            {
                "date": "2026-10-05",
                "model_permaslug": "other",
                "total_tokens": "9007199254740993000000",
            },
        ],
    }
    run = persist_source(contract, "openrouter", "d" * 64, data)
    assert run.status == "success"
    value = MetricValue.objects.get(observation__mapping__isnull=False)
    assert str(value.integer_value) == "6458330218100"
    assert value.window_start_at == datetime(2026, 10, 5, tzinfo=UTC)
    assert value.window_end_at == datetime(2026, 10, 6, tzinfo=UTC)
    assert run.source_as_of == datetime(2026, 10, 6, 0, 30, tzinfo=UTC)
    assert (
        MetricObservation.objects.get(source_subject_kind="aggregate").mapping_id
        is None
    )


def test_arena_failure_is_atomic_and_publication_date_is_not_midnight():
    from core.benchmark_metric_store import persist_source

    contract = provider_contract(
        "arena", ["rating", "rating_lower", "rating_upper", "rank"]
    )
    row = {
        "model_name": "lab/model",
        "category": "overall",
        "leaderboard_publish_date": "2026-09-25",
        "rating": 1476.5,
        "rating_lower": 1460.0,
        "rating_upper": 1480.0,
        "rank": 29.0,
    }
    data = {"status": "ok", "config": "text_style_control", "rows": [row]}
    run = persist_source(contract, "arena", "e" * 64, data)
    assert run.status == "success"
    value = MetricValue.objects.get(source_metric__metric_key="rating")
    assert str(value.as_of_date) == "2026-09-25" and value.as_of_at is None
    assert value.observation.published_at is None
    data["rows"].append({**row, "model_name": "broken", "rating": 2000.0})
    failed = persist_source(contract, "arena", "f" * 64, data)
    assert failed.status == "failed" and not failed.observations.exists()


def test_fourth_benchmark_needs_only_its_own_score_definition():
    from core.benchmark_metric_identity import configure_collection
    from core.benchmark_metric_store import persist_source
    from core.models import DataSource, SourceMetric

    _, spec = setup_spec()
    DataSource.objects.create(
        pk="fixture_bench",
        name="Fixture benchmark",
        source_type="benchmark",
        adapter_key="fixture-only",
    )
    SourceMetric.objects.create(
        source_id="fixture_bench",
        metric_type_id="benchmark_score",
        metric_key="score",
        version=1,
        name="Score",
        unit="fixture_points",
        value_kind="float",
        quantity_form="score",
        measurement_kind="state",
    )
    spec["mappings"][0].update(
        source="fixture_bench",
        source_subject_kind="model",
        identifier_scope="",
        external_identifier="fixture-model",
    )
    from tests.test_benchmark_use_policy import decision

    spec["source_configuration"] = {
        "fixture_bench": {
            "metrics": ["score"],
            "use_policy": {use: decision() for use in ("collection", "retention")},
        }
    }
    contract = configure_collection(spec)
    data = {
        "rows": [
            {
                "source_identifier": "fixture-model",
                "source_subject_kind": "model",
                "metrics": {"score": {"value": 42.5}},
            }
        ]
    }
    run = persist_source(
        contract, "fixture_bench", "1" * 64, data, adapter=lambda raw: raw["rows"]
    )
    assert run.status == "success"
    assert run.observations.get().values.get().float_value == 42.5


def test_source_lock_contention_and_expired_run_recovery():
    from datetime import timedelta

    from django.db import connection
    from django.utils import timezone

    from core.benchmark_metric_store import collection_lock, persist_source
    from core.measurement_taxonomy import digest

    contract = configured()
    lock_key = int(digest(["benchmark-metrics-v1", str(contract.pk), "hf"])[:15], 16)
    import psycopg

    params = connection.get_connection_params()
    params.pop("cursor_factory", None)
    other = psycopg.connect(**params, autocommit=True)
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [lock_key])
        with (
            pytest.raises(ValueError, match="already running"),
            collection_lock(contract, "hf"),
        ):
            pytest.fail("contended lock was admitted")
    finally:
        other.close()
    run = MetricCollectionRun.objects.create(
        contract=contract,
        source_id="hf",
        ingestion_key="2" * 64,
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    aborted = persist_source(contract, "hf", "2" * 64, payload())
    assert aborted.pk == run.pk and aborted.status == "aborted"
    assert not aborted.observations.exists()
    assert persist_source(contract, "hf", "3" * 64, payload()).status == "success"
