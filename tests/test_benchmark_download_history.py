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
    assert MetricValue.objects.filter(window_end_at__isnull=False).count() == 0


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
    assert run.raw_payload["coverage"] == "publication_window"
    assert run.source_metadata["publication_dates"] == ["2026-09-10", "2026-09-11"]
    assert not run.observations.exists()
