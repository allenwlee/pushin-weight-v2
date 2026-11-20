"""Saved provider rows enter review without another collection request."""

import pytest

from core.model_history_collection import execute_model_history
from core.models import (
    CollectionJob,
    CollectionJobTarget,
    CollectionScopeRun,
    SourceSubjectMapping,
)
from tests.test_data_source_history_ingestion import (
    publication_scope,
    register,
    transport,
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize("source", ["arena", "openrouter"])
def test_saved_unknown_row_is_admitted_once_without_extra_provider_calls(source):
    provider, _, scope = publication_scope(source)
    before_mappings = SourceSubjectMapping.objects.count()
    first_budget, first_requests = transport(source, model="elsewhere/model")
    first = execute_model_history(register(provider, scope).pk, budget=first_budget, key="fixture")
    assert first.status == "success" and first_requests
    pending = CollectionJob.objects.get(job_key__startswith="pending-match:", source_id=source)
    targets = list(pending.targets.select_related("evidence_observation"))
    assert targets and all(target.resolution_state == "unresolved" and target.native_identifier == "elsewhere/model" for target in targets)
    assert all(target.evidence_observation.observation_kind == "publication_window" and target.source_row_index is not None for target in targets)
    assert SourceSubjectMapping.objects.count() == before_mappings
    scope_row = CollectionScopeRun.objects.get(run=first, scope_kind="pending_publication_admission")
    assert scope_row.enumeration_complete and {scope_row.resource_observation_id} == {target.evidence_observation_id for target in targets}
    before_targets = CollectionJobTarget.objects.filter(job=pending).count()
    next_budget, next_requests = transport(source, model="elsewhere/model")
    replay = execute_model_history(register(provider, scope, key="replayed-history").pk, budget=next_budget, key="fixture")
    assert replay.status == "success" and not next_requests
    assert CollectionJob.objects.filter(job_key__startswith="pending-match:", source_id=source).count() == 1
    assert CollectionJobTarget.objects.filter(job=pending).count() == before_targets
    assert SourceSubjectMapping.objects.count() == before_mappings


def test_admission_failure_keeps_collector_success_and_cached_retry(monkeypatch):
    import core.collection_matching as matching

    provider, _, scope = publication_scope("openrouter")
    original = matching.register_pending_publication_targets
    def fail(**kwargs):
        raise ValueError("injected local admission failure")
    monkeypatch.setattr(matching, "register_pending_publication_targets", fail)
    budget, requests = transport("openrouter", model="elsewhere/model")
    first = execute_model_history(register(provider, scope).pk, budget=budget, key="fixture")
    assert first.status == "success" and requests
    pending = CollectionScopeRun.objects.get(run=first, scope_kind="pending_publication_admission")
    assert pending.outcome == "pending" and pending.error_code == "pending_admission_failed"
    assert not CollectionJob.objects.filter(job_key__startswith="pending-match:").exists()
    monkeypatch.setattr(matching, "register_pending_publication_targets", original)
    retry_budget, retry_requests = transport("openrouter", model="elsewhere/model")
    retry = execute_model_history(register(provider, scope, key="admission-retry").pk, budget=retry_budget, key="fixture")
    assert retry.status == "success" and not retry_requests
    assert CollectionJob.objects.filter(job_key__startswith="pending-match:").count() == 1


def test_non_dedicated_mapping_does_not_hide_unresolved_row():
    from core.collection_identity import review_catalog_mapping
    from core.measurement_taxonomy import subject_id
    from core.models import MeasurementSubject

    provider, product, scope = publication_scope("arena")
    review_catalog_mapping(source=provider, subject=MeasurementSubject.objects.get(pk=subject_id("product", product.product_key)),
                           external_identifier="elsewhere/model", source_subject_kind="model", identifier_scope="arena_model_name",
                           publisher_account=product.publisher_account, role="family_repository", version_selector="version needed",
                           evidence_url="https://example.org/evidence", reviewed_by="fixture", identity_snapshot={})
    budget, _ = transport("arena", model="elsewhere/model")
    run = execute_model_history(register(provider, scope).pk, budget=budget, key="fixture")
    assert run.status == "success"
    assert CollectionJobTarget.objects.filter(job__job_key__startswith="pending-match:", native_identifier="elsewhere/model").exists()


def test_one_off_collector_admission_recovers_in_bounded_pages(monkeypatch):
    from django.utils import timezone

    import core.collection_matching as matching

    provider, _, scope = publication_scope("openrouter")
    original = matching.register_pending_publication_targets
    def fail(**kwargs):
        raise ValueError("temporary admission failure")
    monkeypatch.setattr(matching, "register_pending_publication_targets", fail)
    job = register(provider, scope)
    budget, requests = transport("openrouter", model="elsewhere/model")
    run = execute_model_history(job.pk, budget=budget, key="fixture")
    assert run.status == "success"
    request_count = len(requests)
    admission = CollectionScopeRun.objects.get(run=run, scope_kind="pending_publication_admission")
    assert admission.outcome == "pending"
    monkeypatch.setattr(matching, "register_pending_publication_targets", original)
    tiny = {**job.budgets, "items": 1}
    first = matching.drain_pending_publication_scope(admission.pk, budgets=tiny)
    assert first["status"] == "pending" and first["admitted"] == 1
    admission.refresh_from_db()
    assert admission.retry_at <= timezone.now()
    result = matching.drain_pending_publication_scopes(max_jobs=2, max_seconds=10)
    admission.refresh_from_db()
    assert result["processed"] == 1 and admission.outcome == "complete"
    assert len(requests) == request_count
    targets = CollectionJobTarget.objects.filter(evidence_observation=admission.resource_observation,
                                                  native_identifier="elsewhere/model", resolution_state="unresolved")
    assert targets.count() == 2 and set(targets.values_list("source_row_index", flat=True)) == {0, 2}
    assert matching.drain_pending_publication_scope(admission.pk)["reused"] is True


def test_oversized_saved_publication_stays_blocked_until_larger_explicit_budget(monkeypatch):
    import core.collection_matching as matching

    provider, _, scope = publication_scope("openrouter")
    original = matching.register_pending_publication_targets
    monkeypatch.setattr(matching, "register_pending_publication_targets", lambda **kwargs: (_ for _ in ()).throw(ValueError("temporary")))
    job = register(provider, scope)
    budget, requests = transport("openrouter", model="elsewhere/model")
    run = execute_model_history(job.pk, budget=budget, key="fixture")
    assert run.status == "success"
    admission = CollectionScopeRun.objects.get(run=run, scope_kind="pending_publication_admission")
    monkeypatch.setattr(matching, "register_pending_publication_targets", original)
    assert matching.drain_pending_publication_scope(admission.pk, budgets={**job.budgets, "bytes": 1})["status"] == "blocked"
    admission.refresh_from_db()
    assert admission.error_code == "pending_admission_byte_limit" and admission.retry_at is None
    assert matching.drain_pending_publication_scope(admission.pk)["status"] == "blocked"
    before = len(requests)
    assert matching.drain_pending_publication_scope(admission.pk, budgets=job.budgets)["status"] == "complete"
    assert len(requests) == before


def test_due_admission_selector_uses_partial_index():
    from django.db import connection, transaction
    from django.utils import timezone

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        query = CollectionScopeRun.objects.filter(scope_kind="pending_publication_admission", outcome="pending",
                                                  retry_at__lte=timezone.now()).order_by("retry_at", "pk")[:2]
        assert "idx_pending_pub_admission" in query.explain()


def test_old_cached_openrouter_publication_is_admitted_when_numeric_days_are_reused(monkeypatch):
    import copy

    import httpx

    import core.collection_matching as matching

    provider, _, scope = publication_scope("openrouter")
    budget, requests = transport("openrouter")
    underlying = budget.client._transport
    def with_unknown(request):
        payload = underlying.handle_request(request).json()
        extra = [dict(row, model_permaslug="elsewhere/model") for row in payload["data"] if row["model_permaslug"] == "lab/model"]
        payload["data"].extend(extra)
        return httpx.Response(200, json=payload)
    budget.client = httpx.Client(transport=httpx.MockTransport(with_unknown))
    original = matching.admit_saved_publication_rows
    monkeypatch.setattr(matching, "admit_saved_publication_rows", lambda **kwargs: None)
    initial = execute_model_history(register(provider, scope).pk, budget=budget, key="fixture")
    assert initial.status == "success" and requests
    assert not CollectionJob.objects.filter(job_key__startswith="pending-match:").exists()
    monkeypatch.setattr(matching, "admit_saved_publication_rows", original)
    next_budget, next_requests = transport("openrouter")
    replay = execute_model_history(register(provider, copy.deepcopy(scope), key="cached-after-upgrade").pk,
                                   budget=next_budget, key="fixture")
    assert replay.status == "success" and not next_requests
    staged = CollectionScopeRun.objects.filter(run=replay, scope_kind="pending_publication_admission", outcome="pending")
    assert staged.exists()
    assert matching.drain_pending_publication_scopes(max_jobs=10, max_seconds=10)["processed"] >= 1
    pending = CollectionJob.objects.get(job_key__startswith="pending-match:")
    assert pending.targets.filter(native_identifier="elsewhere/model").count() == 2


def test_large_saved_publication_hashes_evidence_once_and_reports_growth(monkeypatch):
    import time

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    import core.collection_matching as matching
    from core.collection_capture import archive_legacy
    from core.measurement_taxonomy import digest
    from core.models import CollectionObservation
    from tests.test_collection_matching import catalog_fixture

    _, _, old = catalog_fixture(source="arena")
    observation = CollectionObservation.objects.create(
        run=old.run, source_identifier="aggregate", source_subject_kind="aggregate", observation_kind="publication_window",
        observation_key=digest("large-admission-window"),
        legacy_archive=archive_legacy({"dimensions": {}, "listing": {"rows": [{"model_name": f"vendor/model-{i}"} for i in range(100)]}, "source_metadata": {}}),
    )
    calls = []
    original = matching._evidence_pin
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(matching, "_evidence_pin", counted)
    start = time.monotonic()
    with CaptureQueriesContext(connection) as queries:
        job = matching.register_pending_publication_targets(observation_id=observation.pk, row_indices=list(range(100)),
                                                             budgets={"requests": 1, "bytes": 100000, "seconds": 30, "items": 100})
    print("PENDING_100_GROWTH", {"queries": len(queries), "seconds": round(time.monotonic() - start, 3), "jobs": 1, "targets": job.targets.count()})
    assert len(calls) == 1 and job.targets.count() == 100


def test_admission_checks_all_budgets_even_for_mapped_rows(monkeypatch):
    import core.collection_matching as matching
    from core.models import CollectionObservation

    provider, _, scope = publication_scope("arena")
    job = register(provider, scope)
    budget, _ = transport("arena", model="lab/model")
    run = execute_model_history(job.pk, budget=budget, key="fixture")
    assert run.status == "success"
    admission = CollectionScopeRun.objects.get(run=run, scope_kind="pending_publication_admission")
    CollectionScopeRun.objects.filter(pk=admission.pk).update(outcome="pending", enumeration_complete=False)
    for invalid in ({**job.budgets, "items": 0}, {**job.budgets, "bytes": 0}, {**job.budgets, "requests": 0}):
        with pytest.raises(ValueError, match="budgets"):
            matching.drain_pending_publication_scope(admission.pk, budgets=invalid)
    observation = CollectionObservation.objects.get(pk=admission.resource_observation_id)
    raw_bytes = observation.run.payload_archive.byte_count
    original = matching.observation_object_documents
    def enlarged(value):
        listing, dimensions, metadata = original(value)
        return listing, dimensions, {**metadata, "synthetic_padding": "x" * (raw_bytes + 1000)}
    monkeypatch.setattr(matching, "observation_object_documents", enlarged)
    result = matching.drain_pending_publication_scope(admission.pk, budgets={**job.budgets, "bytes": raw_bytes + 100})
    assert result["status"] == "blocked"
    admission.refresh_from_db()
    assert admission.error_code == "pending_admission_byte_limit" and not admission.enumeration_complete


@pytest.mark.django_db(transaction=True)
def test_recovery_busy_observation_moves_to_later_without_blocking(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, transaction
    from django.utils import timezone

    import core.collection_matching as matching
    from core.models import CollectionObservation

    provider, _, scope = publication_scope("openrouter")
    original = matching.register_pending_publication_targets
    monkeypatch.setattr(matching, "register_pending_publication_targets", lambda **kwargs: (_ for _ in ()).throw(ValueError("temporary")))
    job = register(provider, scope)
    run = execute_model_history(job.pk, budget=transport("openrouter", model="elsewhere/model")[0], key="fixture")
    admission = CollectionScopeRun.objects.get(run=run, scope_kind="pending_publication_admission")
    monkeypatch.setattr(matching, "register_pending_publication_targets", original)
    CollectionScopeRun.objects.filter(pk=admission.pk).update(retry_at=timezone.now())
    locked, release = Event(), Event()
    def hold():
        close_old_connections()
        try:
            with transaction.atomic():
                CollectionObservation.objects.select_for_update().get(pk=admission.resource_observation_id)
                locked.set()
                assert release.wait(5)
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold)
        assert locked.wait(5)
        try:
            assert matching.drain_pending_publication_scope(admission.pk)["status"] == "busy"
            admission.refresh_from_db()
            assert admission.retry_at > timezone.now()
        finally:
            release.set()
            future.result(timeout=5)
    assert matching.drain_pending_publication_scope(admission.pk)["status"] == "complete"
