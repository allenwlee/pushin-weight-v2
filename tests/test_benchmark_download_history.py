import copy

import pytest

from core.measurement_taxonomy import digest
from core.models import MetricValue
from tests.test_benchmark_download_persistence import configured

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def manifest(contract):
    snapshots = []
    for day, downloads in [("2026-09-10", 6), ("2026-09-11", 12)]:
        payload = {
            "status": "ok",
            "rows": [
                {
                    "repo_id": "lab/Model",
                    "status": "ok",
                    "raw": {"downloads": downloads, "downloadsAllTime": 100},
                }
            ],
        }
        snapshots.append(
            {
                "date": day,
                "immutable_revision": "a" * 40,
                "file_path": "models.parquet",
                "raw_artifact_sha256": digest(payload),
                "payload": payload,
            }
        )
    return {
        "schema_version": 1,
        "contract_id": str(contract.pk),
        "source": "hf",
        "dataset_id": "cfahlgren1/hub-stats",
        "archive_publisher": "cfahlgren1",
        "artifact_kind": "selected_json",
        "start_date": "2026-09-10",
        "end_date": "2026-09-11",
        "snapshots": snapshots,
    }


def test_history_replay_keeps_snapshot_dates_separate_from_import_time():
    from core.benchmark_metric_history import import_history

    contract = configured()
    data = manifest(contract)
    run = import_history(data, apply=True)
    assert import_history(copy.deepcopy(data), apply=True).pk == run.pk
    assert run.observations.count() == 2
    assert {
        o.source_metadata["archive_snapshot_date"] for o in run.observations.all()
    } == {"2026-09-10", "2026-09-11"}
    assert all(o.observed_at >= run.started_at for o in run.observations.all())
    assert MetricValue.objects.filter(window_end_at__isnull=False).count() == 4
    for value in MetricValue.objects.select_related("observation", "source_metric"):
        from datetime import date, timedelta

        day = date.fromisoformat(
            value.observation.source_metadata["archive_snapshot_date"]
        )
        assert value.window_end_at.date() == day + timedelta(days=1)
        assert value.period_label_date == day
        assert value.temporal_status == "date_only"


def test_hash_mismatch_fails_before_any_write():
    from core.benchmark_metric_history import import_history

    data = manifest(configured())
    data["snapshots"][0]["payload"]["rows"][0]["raw"]["downloads"] = 99
    with pytest.raises(ValueError, match="hash"):
        import_history(data, apply=True)
    assert not MetricValue.objects.exists()


def test_history_validation_rejects_invalid_observation_without_writing():
    from core.benchmark_metric_history import import_history

    data = manifest(configured())
    snapshot = data["snapshots"][0]
    snapshot["payload"]["rows"][0]["raw"]["downloads"] = -1
    snapshot["raw_artifact_sha256"] = digest(snapshot["payload"])
    with pytest.raises(ValueError, match="invalid observation"):
        import_history(data)
    assert not MetricValue.objects.exists()


def test_arena_history_keeps_publication_when_selected_cohort_is_empty():
    from core.benchmark_metric_history import import_history
    from tests.test_benchmark_download_persistence import provider_contract

    contract = provider_contract("arena", ["rating"])
    data = manifest(contract)
    data.update(
        source="arena",
        dataset_id="lmarena-ai/leaderboard-dataset",
        archive_publisher="lmarena-ai",
    )
    for snapshot in data["snapshots"]:
        payload = {
            "status": "ok",
            "config": "text_style_control",
            "rows": [],
            "coverage": "publication_window",
            "publication_dates": [snapshot["date"]],
        }
        snapshot.update(payload=payload, raw_artifact_sha256=digest(payload))
    run = import_history(data, apply=True)
    assert run.status == "partial"
    from core.collection_capture import read_document

    assert run.raw_payload is None
    assert read_document(run.payload_archive)["coverage"] == "publication_window"
    assert read_document(run.source_metadata_archive)["publication_dates"] == ["2026-09-10", "2026-09-11"]
    assert set(run.observations.values_list("observation_kind", flat=True)) == {
        "publication_marker"
    }


@pytest.mark.parametrize("legacy_markers", [True, False], ids=["dual-write", "typed-only"])
def test_timing_repair_is_bounded_repeatable_and_restores_only_owned_fields(legacy_markers):
    from datetime import UTC, datetime
    from io import StringIO

    from django.core.management import call_command

    from core.models import Product

    contract = configured()
    Product.objects.filter(repo_id="lab/Model").update(
        created_at=datetime(2026, 9, 10, 13, tzinfo=UTC)
    )
    from core.benchmark_metric_history import import_history

    run = import_history(manifest(contract), apply=True)
    # Model the pre-policy rows from retained archive evidence.
    MetricValue.objects.all().update(
        window_start_at=None,
        window_end_at=None,
        period_label_date=None,
        temporal_status="unknown",
    )
    for observation in run.observations.all():
        metadata = observation.source_metadata
        metadata.pop("reported_time", None)
        metadata["unrelated"] = "preserve"
        type(observation).objects.filter(pk=observation.pk).update(
            source_metadata=metadata
        )
    before = list(
        MetricValue.objects.order_by("id").values(
            "id", "integer_value", "window_end_at", "temporal_status"
        )
    )
    cutoff = before[-1]["id"]
    from django.db import connection

    kwargs = {
        "database_name": connection.settings_dict["NAME"],
        "cutoff_value_id": cutoff,
        "batch_size": 2,
        "max_batches": 10,
        "stdout": StringIO(),
    }
    call_command("repair_metric_timing", **kwargs)
    assert (
        list(
            MetricValue.objects.order_by("id").values(
                "id", "integer_value", "window_end_at", "temporal_status"
            )
        )
        == before
    )
    call_command(
        "repair_metric_timing", apply=True, backup_id="verified-test-export", **kwargs
    )
    from core.models import CollectionCorrection

    assert CollectionCorrection.objects.count() == 4
    for correction in CollectionCorrection.objects.select_related("actor"):
        assert correction.actor.actor_kind == "system"
        assert correction.actor.actor_key == "benchmark_metric_timing_repair"
    assert all(row.before_window_end_at is None and row.after_window_end_at is not None for row in CollectionCorrection.objects.all())
    assert MetricValue.objects.filter(window_end_at__isnull=False).count() == 4
    cumulative = MetricValue.objects.filter(
        source_metric__metric_key="downloads_all_time"
    ).first()
    assert cumulative.window_start_at == datetime(2026, 9, 10, 13, tzinfo=UTC)
    assert cumulative.window_range.lower < cumulative.window_range.upper
    saved = list(run.observations.order_by("id").values("source_metadata"))
    output = StringIO()
    call_command(
        "repair_metric_timing",
        apply=True,
        backup_id="verified-test-export",
        **{**kwargs, "stdout": output},
    )
    import json

    summary = json.loads(output.getvalue().splitlines()[-1].split(" ", 1)[1])
    assert summary["changed_values"] == summary["metadata_updates"] == 0
    assert CollectionCorrection.objects.count() == 4
    assert list(run.observations.order_by("id").values("source_metadata")) == saved
    if not legacy_markers:
        # Rollback must remain available after the legacy marker is retired.
        run.observations.update(source_metadata={"unrelated": "preserve"})
    call_command(
        "repair_metric_timing",
        apply=True,
        rollback=True,
        backup_id="verified-test-export",
        **kwargs,
    )
    assert (
        list(
            MetricValue.objects.order_by("id").values(
                "id", "integer_value", "window_end_at", "temporal_status"
            )
        )
        == before
    )
    assert all(
        o.source_metadata["unrelated"] == "preserve" for o in run.observations.all()
    )
    assert CollectionCorrection.objects.count() == 8
    rollback_ids = set(CollectionCorrection.objects.values_list("pk", flat=True))
    call_command(
        "repair_metric_timing", apply=True, rollback=True,
        backup_id="verified-test-export", **kwargs,
    )
    assert set(CollectionCorrection.objects.values_list("pk", flat=True)) == rollback_ids
    assert list(
        MetricValue.objects.order_by("id").values(
            "id", "integer_value", "window_end_at", "temporal_status"
        )
    ) == before


@pytest.mark.parametrize(
    "failure", [
        "later_timing", "later_typed_timing", "later_typed_basis",
        "transaction", "busy", "wrong_database",
    ]
)
def test_timing_correction_refuses_conflicts_and_rolls_back_failed_batches(
    failure, monkeypatch
):
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError
    from django.db import connection

    from core.benchmark_metric_history import import_history
    from core.benchmark_metric_timing_repair import LOCK_KEY
    from core.models import CollectionObservation

    run = import_history(manifest(configured()), apply=True)
    MetricValue.objects.all().update(
        window_start_at=None,
        window_end_at=None,
        period_label_date=None,
        temporal_status="unknown",
    )
    for observation in run.observations.all():
        metadata = observation.source_metadata
        metadata.pop("reported_time", None)
        CollectionObservation.objects.filter(pk=observation.pk).update(
            source_metadata=metadata
        )
    kwargs = {
        "database_name": connection.settings_dict["NAME"],
        "cutoff_value_id": MetricValue.objects.order_by("-id").first().pk,
        "batch_size": 1,
        "max_batches": 20,
        "backup_id": "test-export",
        "stdout": StringIO(),
        "apply": True,
    }
    before = list(MetricValue.objects.order_by("pk").values())
    if failure == "transaction":
        from core import benchmark_metric_timing_repair as repair

        update = repair._update_locked_batch

        def fail_metadata(model, rows, names):
            if model is CollectionObservation:
                raise RuntimeError("simulated write failure")
            return update(model, rows, names)

        monkeypatch.setattr(repair, "_update_locked_batch", fail_metadata)
        with pytest.raises(RuntimeError, match="simulated write failure"):
            call_command("repair_metric_timing", **kwargs)
        assert list(MetricValue.objects.order_by("pk").values()) == before
        assert all(
            "timing_correction_v1" not in o.source_metadata
            for o in run.observations.all()
        )
    elif failure == "busy":
        import psycopg

        with psycopg.connect(
            **connection.get_connection_params(), autocommit=True
        ) as peer:
            peer.execute("SELECT pg_advisory_lock(%s)", [LOCK_KEY])
            with pytest.raises(ValueError, match="already running"):
                call_command("repair_metric_timing", **kwargs)
    elif failure == "wrong_database":
        with pytest.raises(CommandError, match="identity mismatch"):
            call_command("repair_metric_timing", **{**kwargs, "database_name": "wrong"})
        assert list(MetricValue.objects.order_by("pk").values()) == before
    else:
        call_command("repair_metric_timing", **kwargs)
        value = MetricValue.objects.order_by("pk").first()
        if failure.startswith("later_typed_"):
            run.observations.update(source_metadata={})
        if failure == "later_typed_basis":
            MetricValue.objects.filter(pk=value.pk).update(window_end_basis="later_review")
        else:
            MetricValue.objects.filter(pk=value.pk).update(window_end_at=None)
        out = StringIO()
        call_command("repair_metric_timing", rollback=True, **{**kwargs, "stdout": out})
        value.refresh_from_db()
        if failure == "later_typed_basis":
            assert value.window_end_basis == "later_review"
        else:
            assert value.window_end_at is None
        if failure == "later_timing":
            assert value.observation.source_metadata["timing_correction_v1"][str(value.pk)]
        else:
            assert value.observation.source_metadata == {}
        assert '"conflicts": 1' in out.getvalue().splitlines()[-1]
