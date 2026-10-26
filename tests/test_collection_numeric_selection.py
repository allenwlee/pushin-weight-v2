"""HF selection parity and real capture/replay ownership through JSON retirement."""

from datetime import timedelta

import httpx
import pytest
from django.utils import timezone

from core.collection_jobs import register_job
from core.collection_numeric_selection import (
    hf_numeric_selection_integrity_counts,
    numeric_fields,
    project_hf_numeric_job_pins_batch,
    project_hf_numeric_selections_batch,
)
from core.measurement_taxonomy import digest
from core.models import (
    CollectionObservation,
    CollectionObservationMetricSelection,
    CollectionRun,
    MetricValue,
    TimeZone,
)
from core.source_metric_projection import configure_source_statistics, evidence_rows
from tests.test_source_metric_projection import CAPTURED, configured, project

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def seed_utc_timezone():
    TimeZone.objects.get_or_create(pk="UTC")


def selection_contract():
    _, raw, _, spec = configured()
    spec["source_configuration"]["hf"]["metrics"].append("trending_score")
    return configure_source_statistics(spec), raw


def historical_captures():
    contract, raw = selection_contract()
    job = register_job(
        job_key="historical-hf-selection", source=contract.mappings.first().source,
        purpose="catalog", operation="hf_catalog", mode="manual",
        definition={
            "version": 1, "scope": {"numeric_contract_id": str(contract.pk)},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 10, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    run = CollectionRun.objects.create(
        job=job, ingestion_key=digest(["selection-history"]), status="success",
        completed_at=timezone.now(),
    )
    observations = []
    for index, fields in enumerate((None, [], ["downloadsAllTime", "trendingScore"])):
        observations.append(CollectionObservation.objects.create(
            run=run, source_subject_kind="repository", source_identifier=raw["id"],
            observed_at=CAPTURED + timedelta(seconds=index),
            listing={**raw, "downloadsAllTime": "invalid", "trendingScore": 1.5},
            source_metadata={} if fields is None else {"numeric_fields": fields},
            observation_key=digest(["selection", index]),
        ))
    return job, contract, observations


@pytest.mark.parametrize("archived", [False, True])
def test_bounded_copy_and_full_three_state_parity_preserve_exact_versions(archived):
    from core.collection_capture import archive_legacy

    job, contract, observations = historical_captures()
    if archived:
        for observation in observations:
            observation.legacy_archive = archive_legacy({
                "listing": observation.listing, "dimensions": observation.dimensions,
                "source_metadata": observation.source_metadata,
            })
            observation.listing, observation.dimensions, observation.source_metadata = {}, {}, {}
            observation.save(update_fields=["legacy_archive", "listing", "dimensions", "source_metadata"])
    identity = (job.definition_sha256, job.definition)
    with pytest.raises(ValueError, match="contract pin is not projected"):
        project_hf_numeric_selections_batch()
    assert not CollectionObservationMetricSelection.objects.exists()
    assert project_hf_numeric_job_pins_batch().updated == 1
    job.refresh_from_db()
    assert job.numeric_contract_id == contract.pk
    assert (job.definition_sha256, job.definition) == identity
    assert project_hf_numeric_job_pins_batch(verify_only=True).updated == 0
    cursor, totals = 0, [0, 0, 0, 0]
    while True:
        batch = project_hf_numeric_selections_batch(after_id=cursor, batch_size=2)
        totals = [a + b for a, b in zip(totals, (
            batch.implicit, batch.explicit_empty, batch.explicit_selected, batch.selection_rows,
        ), strict=True)]
        cursor = batch.last_id
        if batch.exhausted:
            break
    assert totals == [1, 1, 1, 2]
    assert project_hf_numeric_selections_batch().updated == 0
    parity = project_hf_numeric_selections_batch(verify_only=True)
    assert (parity.scanned, parity.implicit, parity.explicit_empty, parity.explicit_selected, parity.selection_rows) == (3, 1, 1, 1, 2)
    assert hf_numeric_selection_integrity_counts() == {"unprojected": 0, "invalid_selection_owners": 0}
    refreshed = list(CollectionObservation.objects.filter(pk__in=[row.pk for row in observations]).order_by("pk"))
    assert [numeric_fields(row) for row in refreshed] == [None, [], ["downloadsAllTime", "trendingScore"]]
    assert list(refreshed[2].numeric_selections.order_by("source_metric__metric_key").values_list(
        "source_metric__metric_key", "source_metric__version",
    )) == [("downloads_all_time", 2), ("trending_score", 1)]


def test_archived_replay_uses_typed_selection_with_identical_projection_identity(monkeypatch):
    from core.collection_capture import archive_legacy

    _, contract, observations = historical_captures()
    selected = observations[-1]
    before = list(evidence_rows(contract, "hf", selected))
    project_hf_numeric_job_pins_batch()
    project_hf_numeric_selections_batch()
    # Only provider evidence remains in the archive. The selection is operational
    # state and its original meaning must now come from the typed relationship.
    selected.legacy_archive = archive_legacy({
        "listing": selected.listing, "dimensions": {}, "source_metadata": {},
    })
    selected.listing, selected.dimensions, selected.source_metadata = {}, {}, {"numeric_fields": []}
    selected.save(update_fields=["legacy_archive", "listing", "dimensions", "source_metadata"])
    selected.refresh_from_db()
    assert list(evidence_rows(contract, "hf", selected)) == before
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: pytest.fail("provider called during replay"))
    first = project(contract, "hf", [selected], key="typed-field-replay")
    assert first.status == "success", first.report
    numeric = first.observations.get()
    assert list(numeric.values.values_list("source_metric__metric_key", "float_value")) == [("trending_score", 1.5)]
    assert list(numeric.metric_gaps.values_list("source_metric__metric_key", "reason_code")) == [
        ("downloads_all_time", "invalid_metric_value"),
    ]
    repeated = project(contract, "hf", [selected], key="typed-field-repeat")
    assert repeated.report["projection"]["written_values"] == 0


def test_saved_replay_skips_typed_empty_selection_after_old_metadata_clear(monkeypatch):
    from core.collection_jobs import set_job_state
    from core.source_metric_projection import replay_saved_evidence

    capture_job, contract, observations = historical_captures()
    project_hf_numeric_job_pins_batch()
    project_hf_numeric_selections_batch()
    CollectionObservation.objects.filter(pk__in=[row.pk for row in observations]).update(source_metadata={})
    job = register_job(
        job_key="typed-selection-cli-replay", source=capture_job.source,
        purpose="metric", operation="collect_metrics", mode="historical", contract=contract,
        definition={
            "version": 1, "scope": {"origin_run_ids": [str(observations[0].run_id)]},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(job.pk, "ready")
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: pytest.fail("provider called during replay"))
    result = replay_saved_evidence(job.pk)
    assert result.status == "success", result.report
    assert result.selected_count == 2
    assert MetricValue.objects.count() == 4


@pytest.mark.parametrize("fields", [["unknown"], ["likes", "likes"], [True], "likes", None])
def test_bad_historical_selection_refuses_entire_batch(fields):
    _, _, observations = historical_captures()
    selected = observations[-1]
    selected.source_metadata = {"numeric_fields": fields}
    selected.save(update_fields=["source_metadata"])
    project_hf_numeric_job_pins_batch()
    with pytest.raises(ValueError, match="invalid HF numeric field selection"):
        project_hf_numeric_selections_batch()
    assert not CollectionObservationMetricSelection.objects.exists()
    assert not CollectionObservation.objects.filter(numeric_fields_explicit__isnull=False).exists()


@pytest.mark.parametrize("conflict", ["job_hash", "contract_pin", "definition", "marker", "extra_selection"])
def test_copy_refuses_changed_frozen_identity_or_typed_selection(conflict):
    from core.models import CollectionJob, MetricCollectionContract, SourceMetric

    job, contract, observations = historical_captures()
    if conflict == "job_hash":
        # Existing job hashes are protected by the database. An imported bad
        # instruction must still be rejected before the copier pins its FK.
        CollectionJob.objects.create(
            job_key="bad-imported-hash", source=job.source, purpose="catalog",
            operation=job.operation, mode=job.mode, definition=job.definition,
            definition_sha256="a" * 64,
        )
    elif conflict == "contract_pin":
        other = MetricCollectionContract.objects.exclude(pk=contract.pk).first()
        CollectionJob.objects.filter(pk=job.pk).update(numeric_contract=other)
    elif conflict == "definition":
        SourceMetric.objects.filter(source_id="hf", metric_key="trending_score").update(name="changed")
    if conflict in {"job_hash", "contract_pin", "definition"}:
        with pytest.raises(ValueError, match="hash mismatch|pin conflict|definition changed"):
            project_hf_numeric_job_pins_batch()
        assert CollectionJob.objects.get(pk=job.pk).numeric_contract_id == (other.pk if conflict == "contract_pin" else None)
        return
    project_hf_numeric_job_pins_batch()
    project_hf_numeric_selections_batch()
    if conflict == "marker":
        CollectionObservation.objects.filter(pk=observations[0].pk).update(numeric_fields_explicit=True)
    else:
        CollectionObservationMetricSelection.objects.create(
            observation=observations[-1],
            source_metric=SourceMetric.objects.get(source_id="hf", metric_key="downloads_all_time", version=1),
        )
    with pytest.raises(ValueError, match="selection conflicts"):
        project_hf_numeric_selections_batch(verify_only=True)


def test_real_hf_resume_keeps_first_invalid_optional_field_after_json_clear(monkeypatch):
    from core.collection_capture import archive_legacy
    from core.model_inventory import execute_model_inventory
    from scripts.benchmark_download_collector.sources import Budget
    from tests.test_hf_source_ingestion import ingestion_job

    contract, raw = selection_contract()
    job = ingestion_job(contract)
    interrupted = True
    seen = []

    def respond(request):
        seen.append(str(request.url))
        if request.url.path == "/api/models":
            return httpx.Response(200, json=[raw])
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab"})
        if "blobs" in request.url.params:
            return httpx.Response(200, json={**raw, "downloadsAllTime": "invalid"})
        if interrupted:
            raise RuntimeError("fixture interrupted after detail capture")
        return httpx.Response(200, json={**raw, "downloadsAllTime": 99, "trendingScore": 2.5})

    with pytest.raises(RuntimeError, match="after detail capture"):
        execute_model_inventory(job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond))))
    detail = CollectionObservation.objects.get(observation_kind="hf_metadata")
    assert numeric_fields(detail) == ["downloadsAllTime"]
    detail.legacy_archive = archive_legacy({
        "listing": detail.listing, "dimensions": detail.dimensions,
        "source_metadata": {key: value for key, value in detail.source_metadata.items() if key != "numeric_fields"},
    })
    detail.source_metadata = {}
    detail.save(update_fields=["legacy_archive", "source_metadata"])
    CollectionRun.objects.filter(job=job, status="running").update(
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    interrupted = False
    seen.clear()
    resumed = execute_model_inventory(job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond))))
    assert resumed.status == "success", resumed.report
    assert len(seen) == 2 and not any("blobs=true" in url for url in seen)
    captures = list(resumed.observations.filter(observation_kind="hf_metadata").order_by("pk"))
    assert [numeric_fields(row) for row in captures] == [["downloadsAllTime"], ["trendingScore"]]
    assert not MetricValue.objects.filter(source_metric__metric_key="downloads_all_time").exists()
    assert MetricValue.objects.get(source_metric__metric_key="trending_score").float_value == 2.5
    assert not resumed.observations.filter(values__isnull=False).exists()
