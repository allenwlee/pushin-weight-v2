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
