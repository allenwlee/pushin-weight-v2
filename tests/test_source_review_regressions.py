"""Real acquisition/recovery regressions for the confirmed source review defects."""

import copy
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest

from core.collection_jobs import register_job, set_job_state
from core.models import CollectionObservation, MetricValue
from scripts.benchmark_download_collector.sources import Budget
from tests.test_data_source_history_ingestion import (
    publication_scope,
    register,
    transport,
)
from tests.test_hf_source_ingestion import ingestion_job
from tests.test_source_metric_projection import configured, evidence, project

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_rolling_same_day_new_run_refetches_but_continuation_reuses_generation():
    from core.model_history_collection import execute_model_history

    source, _, scope = publication_scope()
    scope.update(
        publication_window_policy="rolling-completed-days-v1",
        publication_recheck_days=2,
    )
    draft = register(source, scope, items=2)
    definition = copy.deepcopy(draft.definition)
    definition["schedule"] = {"kind": "interval", "driver": "shared", "seconds": 3600}
    job = register_job(
        job_key="rolling-recurring",
        source=source,
        purpose="catalog",
        operation="model_history",
        mode="recurring",
        definition=definition,
    )
    job = set_job_state(job.pk, "ready")
    frozen = copy.deepcopy(job.definition)
    now = datetime(2026, 10, 15, 11, tzinfo=UTC)
    generations = []
    for value in ("123", "456"):
        budget, calls = transport(tokens=value)
        with patch("core.model_history_collection.timezone.now", return_value=now):
            first = execute_model_history(job.pk, budget=budget, key="fixture")
        assert first.status == "partial", first.report
        assert len(calls) == 2
        resume_budget, resume_calls = transport(tokens=value)
        with patch("core.model_history_collection.timezone.now", return_value=now):
            resumed = execute_model_history(job.pk, budget=resume_budget, key="fixture")
        assert resumed.status == "success", resumed.report
        assert resumed.pk == first.pk and not resume_calls
        generations.append(
            (
                resumed.scopes.get(scope_kind="publication_runtime").envelopes[0],
                first.pk,
            )
        )
    job.refresh_from_db()
    assert job.definition == frozen
    # Changed model rows get new snapshots; unchanged "other" rows are reused.
    assert MetricValue.objects.count() == 6
    assert all(
        window["acquisition_generation"] == str(run_id)
        for window, run_id in generations
    )
    assert set(
        MetricValue.objects.filter(
            observation__source_identifier="lab/model"
        ).values_list("integer_value", flat=True)
    ) == {123, 456}


@pytest.mark.parametrize("followers_only,all_invalid", [(True, False), (False, True)])
def test_inventory_terminal_missing_counters_ack_and_next_acquisition(
    followers_only, all_invalid
):
    from core.model_inventory import execute_model_inventory
    from core.source_metric_projection import configure_source_statistics

    contract, raw, _, spec = configured()
    if followers_only:
        spec["source_configuration"]["hf"]["metrics"] = ["followers"]
        spec["source_configuration"]["hf"]["metric_versions"] = {}
        contract = configure_source_statistics(spec)
    job = ingestion_job(contract)
    calls = []
    broken = True

    def respond(request):
        calls.append(str(request.url))
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "lab", "numFollowers": 7})
        if (
            broken
            and "expand" in request.url.params
            and request.url.path.endswith("/Model")
        ):
            return httpx.Response(404, json={"error": "temporarily unavailable"})
        row = {**raw, "downloads": None, "likes": "invalid"} if all_invalid else raw
        rows = [row, {**raw, "id": "lab/Valid", "downloads": 9}]
        return httpx.Response(
            200,
            json=rows
            if request.url.path == "/api/models"
            else {**row, "id": request.url.path.removeprefix("/api/models/")},
        )

    partial = execute_model_inventory(
        job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond)))
    )
    assert partial.status == "partial", partial.report
    broken = False
    for attempt in range(2):
        calls.clear()
        run = execute_model_inventory(
            job.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond)))
        )
        assert run.status == "success", run.report
        if attempt == 0:
            assert run.pk == partial.pk
            assert not any(httpx.URL(url).path == "/api/models" for url in calls)
        assert (
            calls
            and not run.scopes.filter(
                scope_kind="numeric_projection", outcome="pending"
            ).exists()
        )
        if followers_only:
            from core.models import CollectionRun

            queued_ids = [
                pk
                for numeric in CollectionRun.objects.filter(job__purpose="metric")
                for pk in numeric.report.get("projection", {}).get(
                    "source_observation_ids", []
                )
            ]
            assert not CollectionObservation.objects.filter(
                pk__in=queued_ids, source_subject_kind="repository"
            ).exists()
    assert list(
        MetricValue.objects.filter(source_metric__metric_key="followers").values_list(
            "integer_value", flat=True
        )
    ) == [7, 7]
    if all_invalid:
        assert (
            MetricValue.objects.filter(
                observation__source_identifier="lab/Valid", integer_value=9
            ).count()
            == 2
        )
        assert not MetricValue.objects.filter(
            observation__source_identifier="lab/Model"
        ).exists()
        from core.models import CollectionRun

        coverage = [
            c
            for r in CollectionRun.objects.filter(job__purpose="metric")
            for c in r.report.get("coverage", [])
        ]
        assert any(c["outcome"] == "invalid" for c in coverage)


@pytest.mark.parametrize(
    "counters,outcome",
    [({"downloads": None, "likes": "bad"}, "invalid"), ({}, "not_returned")],
)
def test_zero_counter_metric_attempt_is_terminal_without_values(counters, outcome):
    contract, raw, _, _ = configured()
    run = project(contract, "hf", [evidence("hf", {"id": raw["id"], **counters})])
    assert run.status == "success", run.report
    assert run.selected_count == 1 and run.success_count == 0
    assert run.report["projection"]["terminal_resources"] == 1
    assert not MetricValue.objects.exists()
    assert any(row["outcome"] == outcome for row in run.report["coverage"])


def replay_job(contract, snapshots, *, key="replay-bounded", byte_limit=25000):
    job = register_job(
        job_key=key,
        source=contract.mappings.first().source,
        purpose="metric",
        operation="collect_metrics",
        mode="historical",
        contract=contract,
        definition={
            "version": 1,
            "scope": {"origin_run_ids": [str(s.run_id) for s in snapshots]},
            "campaign": {
                "kind": "backfiller-data-source-v1",
                "key": key,
                "cohort_hash": "a" * 64,
                "role": "projection",
                "phase": "replay",
                "contract_partition": str(contract.pk),
                "max_invocations": 100,
                "max_requests": 100,
            },
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {
                "requests": 1,
                "seconds": 60,
                "bytes": byte_limit,
                "items": 100,
            },
        },
    )
    return set_job_state(job.pk, "ready")


def test_replay_streams_aggregate_byte_limit_and_restarts_at_last_admitted(monkeypatch):
    import core.source_metric_projection as projection

    contract, raw, _, _ = configured()
    snapshots = [
        evidence("hf", {**raw, "id": f"lab/Model{i}", "padding": "x" * 10000})
        for i in range(12)
    ]
    job = replay_job(contract, snapshots)
    loaded = []
    actual_from_db = CollectionObservation.from_db
    actual_project = projection.project_evidence
    batches = []

    def from_db(*args, **kwargs):
        row = actual_from_db(*args, **kwargs)
        if row.pk in {s.pk for s in snapshots}:
            loaded.append(row.pk)
        return row

    def capture(*args, **kwargs):
        assert len(loaded) <= 3, (
            "selection eagerly hydrated records past its byte limit"
        )
        assert kwargs.get("deadline") is not None
        batches.append(list(args[1]))
        return actual_project(*args, **kwargs)

    monkeypatch.setattr(CollectionObservation, "from_db", from_db)
    monkeypatch.setattr(projection, "project_evidence", capture)
    first = projection.replay_saved_evidence(job.pk)
    assert first.status == "partial" and batches == [[s.pk for s in snapshots[:2]]]
    assert first.scopes.get(scope_key="saved-evidence").cursor == str(snapshots[1].pk)
    # Reenter the real replay path; the campaign copies its durable cursor.
    for _ in range(5):
        loaded.clear()
        latest = projection.replay_saved_evidence(job.pk)
    assert latest.status == "success", latest.report
    assert batches == [[s.pk for s in snapshots[i : i + 2]] for i in range(0, 12, 2)]
    assert latest.report["projection"]["selected_resources"] == 12
    assert MetricValue.objects.count() == 24


def test_replay_selection_and_projection_share_entry_deadline(monkeypatch):
    import core.source_metric_projection as projection

    contract, raw, _, _ = configured()
    snapshot = evidence("hf", raw)
    job = replay_job(contract, [snapshot], key="replay-deadline")
    clock = [100.0]
    actual_size = projection._evidence_bytes
    actual_project = projection.project_evidence
    monkeypatch.setattr(projection, "monotonic", lambda: clock[0])

    def slow_size(row):
        clock[0] += 61
        return actual_size(row)

    def capture(*args, **kwargs):
        assert kwargs["deadline"] == 160.0
        return actual_project(*args, **kwargs)

    monkeypatch.setattr(projection, "_evidence_bytes", slow_size)
    monkeypatch.setattr(projection, "project_evidence", capture)
    first = projection.replay_saved_evidence(job.pk)
    assert first.status == "partial" and not MetricValue.objects.exists()
    assert first.scopes.get(scope_key="saved-evidence").cursor == "0"
    monkeypatch.setattr(projection, "_evidence_bytes", actual_size)
    monkeypatch.setattr(projection, "project_evidence", actual_project)
    resumed = projection.replay_saved_evidence(job.pk)
    assert resumed.status == "success", resumed.report
    assert MetricValue.objects.count() == 2


def test_native_only_publication_continuation_acknowledges_completed_selection():
    from core.model_history_collection import execute_model_history
    from core.model_history_statistics import prepare_history_statistics_scope

    source, product, _ = publication_scope()
    scope = prepare_history_statistics_scope(
        source=source,
        reviewed_by="fixture",
        scope={
            "brand_id": product.brand_id,
            "cohort_hash": "a" * 64,
            "models": [],
            "global_start_at": "2026-09-10T00:00:00Z",
            "cutoff": "2026-09-12T00:00:00Z",
            "native_publication_identifiers": ["lab/model"],
        },
    )
    job = register(source, scope, items=3)
    first = execute_model_history(job.pk, budget=transport()[0], key="fixture")
    assert first.status == "partial", first.report
    budget, calls = transport()
    resumed = execute_model_history(job.pk, budget=budget, key="fixture")
    assert resumed.status == "success", resumed.report
    assert not calls and MetricValue.objects.count() == 4
    assert not resumed.scopes.filter(
        scope_kind="numeric_projection", outcome="pending"
    ).exists()
