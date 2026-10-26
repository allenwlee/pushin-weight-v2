"""HF archive acquisition preserves selected binary evidence without live JSON."""

import io
import re
from datetime import UTC, date, datetime

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from core.collection_capture import observation_object_documents
from core.collection_state import claim_job
from core.measurement_taxonomy import digest
from core.model_history_archives import (
    ROW_CAPTURE,
    SNAPSHOT_CAPTURE,
    _snapshot_key,
    acquire_hf_archives,
)
from core.models import CollectionObservation, CollectionScopeRun, MetricValue
from core.source_metric_projection import drain_pending_projections
from scripts.benchmark_download_collector.sources import Budget
from tests.test_hf_catalog_retirement import denied_retirement_columns
from tests.test_model_history_collection import history_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def configured(*, statistics=True, duplicates=False):
    if statistics:
        from core.source_metric_projection import configure_source_statistics
        from tests.test_benchmark_use_policy import decision
        from tests.test_source_metric_projection import configured as source_contract

        _, _, product, spec = source_contract(mapped=True, product_type="llm-model")
        policy = {use: decision() for use in ("collection", "retention")}
        policy["datasets"] = {
            "cfahlgren1/hub-stats": {
                use: decision() for use in ("collection", "retention")
            }
        }
        spec["source_configuration"]["hf"]["use_policy"] = policy
        contract = configure_source_statistics(spec)
    else:
        from core.benchmark_metric_identity import configure_collection
        from tests.test_benchmark_download_db_identity import setup_spec

        _, spec = setup_spec()
        spec["source_configuration"]["hf"]["metric_versions"] = {
            "downloads_all_time": 2
        }
        contract = configure_collection(spec)
        product = contract.mappings.get(source_id="hf").subject.product
    source = product.publisher_account.data_source
    source.enabled = True
    source.save(update_fields=["enabled"])
    revision = {
        "id": "a" * 40,
        "date": "2026-09-10T00:00:00Z",
        "snapshot_date": "2026-09-10",
    }
    job = history_job(
        source,
        product.brand,
        product,
        creation={
            "at": "2026-09-01T00:00:00Z",
            "source": "hf",
            "native_identifier": product.repo_id,
        },
        extra={
            "numeric_contract_id": str(contract.pk),
            "hf_archive": {
                "dataset_id": "cfahlgren1/hub-stats",
                "archive_publisher": "cfahlgren1",
                "revisions": [revision],
            },
        },
    )
    rows = [
        {"id": product.repo_id, "downloads": 0, "downloadsAllTime": None, "likes": 2}
    ]
    if duplicates:
        rows *= 2
    output = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), output)
    binary = output.getvalue()
    calls = []

    def response(request):
        calls.append(request)
        start, end = map(
            int, re.fullmatch(r"bytes=(\d+)-(\d+)", request.headers["range"]).groups()
        )
        return httpx.Response(
            206,
            content=binary[start : end + 1],
            headers={
                "content-range": f"bytes {start}-{end}/{len(binary)}",
            },
        )

    return (
        job,
        contract,
        Budget(
            httpx.Client(transport=httpx.MockTransport(response)),
            max_requests=30,
            max_bytes=1000000,
        ),
        calls,
    )


@pytest.mark.parametrize("statistics", [False, True])
def test_selected_snapshot_numeric_rows_and_cache_use_no_retired_columns(statistics):
    job, _, budget, calls = configured(statistics=statistics, duplicates=True)
    with denied_retirement_columns():
        claim = claim_job(job.pk, typed=True)
        result = acquire_hf_archives(claim, job, budget)
        assert result["snapshots"] == 1 and result["daily_interpolation"] is False
        snapshot = CollectionObservation.objects.get(projection_kind=SNAPSHOT_CAPTURE)
        archived_id, archived_bytes = (
            snapshot.legacy_archive_id,
            bytes(snapshot.legacy_archive.body),
        )
        document = observation_object_documents(snapshot)[0]
        assert (
            document["upstream_retrieval_coordinates"]["identical_duplicates_collapsed"]
            == 1
        )
        assert snapshot.scope_run.raw_count == 2
        assert snapshot.archive_snapshot_date == date(2026, 9, 10)
        assert snapshot.original_retrieved_at == snapshot.observed_at
        assert 30 - budget.remaining == len(calls) > 0
        assert not snapshot.scope_run.requests.exists()
        if statistics:
            row = CollectionObservation.objects.get(projection_kind=ROW_CAPTURE)
            assert (
                row.inputs.get(input_role="hf_archive_row").input_observation_id
                == snapshot.pk
            )
            assert row.inputs.get().row_locator == "0"
            assert observation_object_documents(row)[0]["downloads"] == 0
            drain_pending_projections(job.pk, budget=budget, origin_claim=claim)
            likes = MetricValue.objects.get(source_metric__metric_key="likes")
            assert likes.as_of_date == date(2026, 9, 10) and likes.as_of_at is None
        value = MetricValue.objects.get(source_metric__metric_key="downloads")
        assert value.integer_value == 0 and value.temporal_status == "date_only"
        assert value.window_end_at == datetime(2026, 9, 11, tzinfo=UTC)
        assert not MetricValue.objects.filter(
            source_metric__metric_key="downloads_all_time"
        ).exists()
        before = (len(calls), MetricValue.objects.count())
        acquire_hf_archives(claim, job, budget)
        assert (len(calls), MetricValue.objects.count()) == before
        snapshot.refresh_from_db()
        assert (snapshot.legacy_archive_id, bytes(snapshot.legacy_archive.body)) == (
            archived_id,
            archived_bytes,
        )
        assert (
            snapshot.source_dataset.source_id == "hf"
            and snapshot.source_dataset.code == "cfahlgren1/hub-stats"
        )


@pytest.mark.parametrize("tamper", ["position", "hash", "revision", "clock", "dataset"])
def test_changed_selected_archive_link_fails_closed(tamper):
    job, _, budget, calls = configured()
    with denied_retirement_columns():
        claim = claim_job(job.pk, typed=True)
        acquire_hf_archives(claim, job, budget)
        row = CollectionObservation.objects.get(projection_kind=ROW_CAPTURE)
        if tamper == "position":
            row.inputs.update(row_locator="1")
        elif tamper == "hash":
            row.inputs.update(input_sha256="0" * 64)
        else:
            change = {
                "revision": {"provider_revision": "b" * 40},
                "clock": {"observed_at": datetime(2025, 1, 1, tzinfo=UTC)},
                "dataset": {"source_dataset": None},
            }[tamper]
            CollectionObservation.objects.filter(pk=row.pk).update(**change)
        row.refresh_from_db()
        before = len(calls)
        with pytest.raises(ValueError, match="HF archive"):
            observation_object_documents(row)
        assert len(calls) == before and not MetricValue.objects.exists()


@pytest.mark.parametrize("legacy", ["scope", "observation"])
def test_unadopted_old_archive_is_rejected_before_any_range_request(legacy):
    job, _, budget, calls = configured()
    claim = claim_job(job.pk, typed=True)
    revision = job.scope["hf_archive"]["revisions"][0]
    key = _snapshot_key(job, revision)
    if legacy == "scope":
        CollectionScopeRun.objects.create(
            run_id=claim.run_id,
            scope_kind="archive_snapshot",
            scope_key=key,
            ownership={},
        )
    else:
        CollectionObservation.objects.create(
            run_id=claim.run_id,
            source_identifier="cfahlgren1/hub-stats",
            source_subject_kind="aggregate",
            observation_key=key,
        )
    with (
        denied_retirement_columns(),
        pytest.raises(ValueError, match="requires typed adoption"),
    ):
        acquire_hf_archives(claim, job, budget)
    assert not calls and not MetricValue.objects.exists()


def test_generic_archive_repair_keeps_selected_source_capture():
    from core.collection_storage_migration import (
        archive_legacy_batch,
        stale_legacy_archive_count,
    )

    job, _, budget, _ = configured()
    claim = claim_job(job.pk, typed=True)
    acquire_hf_archives(claim, job, budget)
    snapshot = CollectionObservation.objects.get(projection_kind=SNAPSHOT_CAPTURE)
    archive_id = snapshot.legacy_archive_id
    archive_legacy_batch("collection_observations", batch_size=100, repair_stale=True)
    snapshot.refresh_from_db()
    assert snapshot.legacy_archive_id == archive_id
    assert stale_legacy_archive_count("collection_observations") == 0
    assert observation_object_documents(snapshot)[0]["raw_artifact_sha256"] == digest(
        observation_object_documents(snapshot)[0]["payload"]
    )


def test_snapshot_commit_then_projection_crash_resumes_without_range_requests(
    monkeypatch,
):
    from core import model_history_archives as archives

    job, _, budget, calls = configured()
    original = archives._queue_hf_archive
    with denied_retirement_columns():
        claim = claim_job(job.pk, typed=True)
        monkeypatch.setattr(
            archives,
            "_queue_hf_archive",
            lambda *args: (_ for _ in ()).throw(RuntimeError("after snapshot commit")),
        )
        with pytest.raises(RuntimeError, match="after snapshot commit"):
            acquire_hf_archives(claim, job, budget)
        assert (
            CollectionObservation.objects.filter(
                projection_kind=SNAPSHOT_CAPTURE
            ).count()
            == 1
        )
        assert not CollectionObservation.objects.filter(
            projection_kind=ROW_CAPTURE
        ).exists()
        count = len(calls)
        monkeypatch.setattr(archives, "_queue_hf_archive", original)
        acquire_hf_archives(claim, job, budget)
        drain_pending_projections(job.pk, budget=budget, origin_claim=claim)
        assert len(calls) == count and MetricValue.objects.count() == 2


def test_cached_archive_still_obeys_current_dataset_restrictions():
    from core.benchmark_attribution import UseNotPermitted
    from tests.test_benchmark_use_policy import decision

    job, _, budget, calls = configured()
    with denied_retirement_columns():
        claim = claim_job(job.pk, typed=True)
        acquire_hf_archives(claim, job, budget)
        count = len(calls)
        source = job.source
        source.metadata = {
            **source.metadata,
            "use_policy": {
                "datasets": {
                    "cfahlgren1/hub-stats": {
                        "collection": decision("prohibited"),
                        "retention": decision(),
                    }
                }
            },
        }
        source.save(update_fields=["metadata"])
        with pytest.raises(UseNotPermitted):
            acquire_hf_archives(claim, job, budget)
        assert len(calls) == count


def test_timing_repair_follows_exact_typed_archive_row_after_numeric_projection():
    from core.benchmark_metric_timing_repair import repair_batch
    from core.collection_corrections import TIME_BASIS_FIELDS

    job, _, budget, calls = configured()
    with denied_retirement_columns():
        claim = claim_job(job.pk, typed=True)
        acquire_hf_archives(claim, job, budget)
        drain_pending_projections(job.pk, budget=budget, origin_claim=claim)
        value = MetricValue.objects.get(source_metric__metric_key="downloads")
        MetricValue.objects.filter(pk=value.pk).update(
            window_start_at=None,
            window_end_at=None,
            period_label_date=None,
            temporal_status="unknown",
            **dict.fromkeys(TIME_BASIS_FIELDS),
        )
        count = len(calls)
        repaired = repair_batch(cutoff=value.pk, after=value.pk - 1, apply=True)
        assert repaired["changed_values"] == 1
        value.refresh_from_db()
        assert value.window_end_at == datetime(2026, 9, 11, tzinfo=UTC)
        assert value.period_label_date == date(2026, 9, 10)
        assert len(calls) == count
