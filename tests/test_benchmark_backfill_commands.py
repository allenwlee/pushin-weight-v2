import json

import pytest
from django.core.management import CommandError, call_command

from core.benchmark_metric_identity import configure_collection
from core.measurement_taxonomy import digest
from core.models import MetricValue
from tests.test_benchmark_download_persistence import provider_contract
from tests.test_benchmark_engagement import engagement_spec

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_engagement_command_replay_keeps_two_history_bases(tmp_path):
    contract = configure_collection(engagement_spec())
    data = {
        "identifier": "lab/Model",
        "kind": "repository",
        "current": {"downloads": 10, "downloadsAllTime": 100, "likes": 5},
        "observed_at": "2026-10-07T01:00:00Z",
        "retrieved_at": "2026-10-07T01:00:01Z",
        "counts": {"2026-09-10": 2, "2026-09-11": 3},
        "page_sha256": ["a" * 64],
        "endpoint": "https://huggingface.co/api/models/lab/Model/likers",
    }
    (tmp_path / "repo.json").write_text(
        json.dumps({"data": data, "sha256": digest(data)})
    )
    (tmp_path / "coverage.json").write_text(
        json.dumps({"complete": True, "completed": [{"artifact": "repo.json"}]})
    )
    for _ in range(2):
        call_command(
            "import_hf_backfill",
            str(tmp_path),
            "--kind",
            "engagement",
            "--contract",
            str(contract.pk),
            "--apply",
        )
    assert MetricValue.objects.count() == 5

    assert set(
        MetricValue.objects.filter(source_metric__metric_key="likes").values_list(
            "integer_value", flat=True
        )
    ) == {2, 3, 5}
    data["current"]["likes"] = 99
    (tmp_path / "repo.json").write_text(json.dumps({"data": data, "sha256": "a" * 64}))
    with pytest.raises(CommandError, match="hash"):
        call_command(
            "import_hf_backfill",
            str(tmp_path),
            "--kind",
            "engagement",
            "--contract",
            str(contract.pk),
            "--apply",
        )
    assert MetricValue.objects.count() == 5


def test_engagement_validation_rejects_wrong_checkpoint_identity(tmp_path):
    contract = configure_collection(engagement_spec())
    data = {
        "identifier": "other/model",
        "kind": "repository",
        "current": {"downloads": 10, "downloadsAllTime": 100, "likes": 5},
        "observed_at": "2026-10-07T01:00:00Z",
        "counts": {},
    }
    (tmp_path / "repo.json").write_text(
        json.dumps({"data": data, "sha256": digest(data)})
    )
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {
                "complete": True,
                "completed": [
                    {
                        "artifact": "repo.json",
                        "identifier": "lab/Model",
                        "kind": "repository",
                    }
                ],
            }
        )
    )
    with pytest.raises(CommandError, match="identity mismatch"):
        call_command(
            "import_hf_backfill",
            str(tmp_path),
            "--kind",
            "engagement",
            "--contract",
            str(contract.pk),
        )
    assert not MetricValue.objects.exists()


def test_openrouter_cached_all_cohort_replay_needs_no_credentials(
    tmp_path, monkeypatch
):
    from scripts.benchmark_download_collector.sources import Budget

    contract = provider_contract("openrouter", ["total_tokens"])
    payload = {
        "status": "ok",
        "meta": {"version": "v1", "start_date": "2026-10-01", "end_date": "2026-10-01"},
        "as_of": "2026-10-02T00:00:00Z",
        "missing_dates": [],
        "rows": [
            {
                "date": "2026-10-01",
                "model_permaslug": "other-lab/old-model",
                "total_tokens": "100",
            }
        ],
    }
    (tmp_path / "openrouter-2026-10-01-2026-10-01.json").write_text(
        json.dumps(
            {
                "payload": payload,
                "sha256": digest(payload),
                "retrieved_at": "2026-10-02T00:00:00Z",
            }
        )
    )
    monkeypatch.setattr(
        Budget, "get", lambda *a, **k: pytest.fail("cached replay used network")
    )
    for _ in range(2):
        call_command(
            "backfill_openrouter_history",
            "--contract",
            str(contract.pk),
            "--output",
            str(tmp_path),
            "--start-date",
            "2026-10-01",
            "--end-date",
            "2026-10-01",
            "--apply",
        )
    assert MetricValue.objects.count() == 1
    assert MetricValue.objects.get().observation.mapping_id is None
    assert json.loads((tmp_path / "coverage.json").read_text())["complete"] is True
