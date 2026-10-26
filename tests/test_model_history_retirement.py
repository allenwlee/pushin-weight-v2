"""Typed coverage, original evidence links, and explicit legacy projection."""

from datetime import UTC, date, datetime

import httpx
import pytest

from core.collection_capture import archive_legacy, read_document, run_report_document
from core.collection_identity import review_github_mapping
from core.collection_state import checkpoint_scope, claim_job
from core.measurement_taxonomy import digest
from core.model_history_collection import (
    _coverage_writer,
    _existing_evidence,
    execute_model_history,
    history_report,
    project_legacy_history_coverage,
)
from core.models import (
    CollectionObservation,
    CollectionObservationInput,
    CollectionRequest,
    CollectionResourceSnapshot,
    CollectionRun,
    CollectionScopeRun,
    MetricValue,
)
from scripts.benchmark_download_collector.sources import Budget
from tests.test_collection_identity import identities
from tests.test_model_history_collection import history_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.fixture
def selection():
    brand, account, subject, repo = identities()
    source = account.data_source
    source.enabled, source.adapter_key = True, "github-catalog-v1"
    source.save()
    mapping = review_github_mapping(subject=subject, repo=repo, role="dedicated_model",
                                    version_selector=None, evidence_url="https://github.com/publisher/family",
                                    reviewed_by="fixture")
    pin = {"mapping_id": str(mapping.pk), "mapping_hash": mapping.mapping_hash,
           "source": "github", "native_identifier": "123", "identifier_scope": "repository_id"}
    job = history_job(source, brand, subject.product, pins=[pin])
    return job, subject.product, account, pin


def captured_source(run, account, **overrides):
    archive = archive_legacy({"listing": {"provider_wording": "unaltered source evidence"},
                              "dimensions": {"kind": "deliberately_unusable"},
                              "source_metadata": {"clocks": {"committer_at": "unusable legacy timestamp"}},
                              "envelopes": [], "groups": {}})
    row = CollectionObservation.objects.create(
        run=run, source_identifier="123", source_subject_kind="repository",
        observation_kind="commits", observation_key=digest(["fixture-source", str(run.pk)]),
        payload_sha256=digest(["fixture-source-body", str(run.pk)]),
        observed_at=datetime(2026, 9, 4, tzinfo=UTC), source_record_date=date(2026, 9, 3),
        provider_revision="request-head", history_reconstructed=True, secondary_source=False,
        reconstruction_date=date(2026, 9, 4), legacy_archive=archive, **overrides,
    )
    CollectionResourceSnapshot.objects.create(
        observation=row, resource_kind="commits", native_identifier="123",
        revision="original-commit", publisher_account=account,
    )
    return row


def coverage_cell(job, product, source):
    return {"source": job.source_id, "product_key": str(product.product_key),
            "requested_start_at": "2026-09-01T00:00:00Z", "requested_cutoff": job.scope["cutoff"],
            "outcome": "observed", "reason": "native_evidence_only", "coverage_complete": False,
            "evidence": [{"observation_id": source.pk}]}


def coverage_owner(job, product, pin):
    return {"product_key": str(product.product_key), "cohort_hash": job.scope["cohort_hash"],
            "provider_pins": [pin]}


def test_report_keeps_original_typed_facts_and_inspectable_source_links(selection):
    job, product, account, pin = selection
    claim = claim_job(job.pk, typed=True)
    run = CollectionRun.objects.get(pk=claim.run_id)
    original = captured_source(run, account)
    references = _existing_evidence(job, {"product_key": str(product.product_key)}, [pin])
    assert references[0]["source_time_precision"] == "date"
    assert references[0]["source_metadata"]["history_reconstructed"] is True
    assert references[0]["source_metadata"]["secondary_source"] is False
    cell = coverage_cell(job, product, original)
    scoped = checkpoint_scope(
        claim, scope_kind="model_coverage", scope_key=str(product.product_key),
        ownership=coverage_owner(job, product, pin), typed=True,
        requested_start_at=datetime(2026, 9, 1, tzinfo=UTC), requested_end_at=datetime(2026, 9, 12, tzinfo=UTC),
        outcome="observed", enumeration_complete=True, write=_coverage_writer(claim, cell),
    )
    CollectionRun.objects.filter(pk=run.pk).update(report={"coverage": "unusable retired report"})
    CollectionScopeRun.objects.filter(pk=scoped.pk).update(ownership={}, envelopes=[{"unusable": True}])
    run.refresh_from_db()
    report = run_report_document(run)
    assert report == history_report(run)
    evidence = report["coverage"][0]["evidence"][0]
    assert evidence["observation_id"] == original.pk and evidence["run_id"] == str(run.pk)
    assert evidence["observed_at"] == original.observed_at.isoformat()
    assert evidence["publication_precision"] == "unknown" and evidence["source_time_precision"] == "date"
    assert evidence["source_metadata"]["provider_revision"] == "request-head"
    assert evidence["source_metadata"]["resource_revision"] == "original-commit"
    assert evidence["source_metadata"]["publisher_account_id"] == account.pk
    assert "matched_rows" not in evidence and evidence["metric_value_ids"] == []
    edge = CollectionObservationInput.objects.get(pk=evidence["input_id"])
    assert edge.input_observation_id == original.pk
    assert edge.input_sha256 == original.payload_sha256
    assert read_document(edge.input_observation.legacy_archive)["listing"]["provider_wording"] == "unaltered source evidence"
    assert report["observed_cells"] == 1 and report["all_requested_history_available"] is False
    assert not CollectionRequest.objects.exists() and not MetricValue.objects.exists()


def test_legacy_coverage_requires_explicit_projection_then_resumes_typed(selection):
    job, product, account, pin = selection
    claim = claim_job(job.pk, typed=True)
    run = CollectionRun.objects.get(pk=claim.run_id)
    original = captured_source(run, account)
    cell, owner = coverage_cell(job, product, original), coverage_owner(job, product, pin)
    archive = archive_legacy({"ownership": owner, "cursor_history": [], "envelopes": [cell]})
    scoped = CollectionScopeRun.objects.create(
        run=run, scope_kind="model_coverage", scope_key=str(product.product_key), ownership=owner,
        envelopes=[cell], outcome="observed", enumeration_complete=True, legacy_archive=archive,
    )
    with pytest.raises(ValueError, match="typed migration"):
        history_report(run)
    adopted = project_legacy_history_coverage(scoped)
    result_id = adopted.resource_observation_id
    assert project_legacy_history_coverage(scoped).resource_observation_id == result_id
    scoped.refresh_from_db()
    assert scoped.envelopes == [cell] and scoped.legacy_archive_id == archive.pk
    scoped.envelopes, scoped.ownership = [], {}
    scoped.save(update_fields=["envelopes", "ownership"])
    report = history_report(run)
    assert report["coverage"][0]["evidence"][0]["observation_id"] == original.pk
    result = CollectionObservation.objects.get(pk=result_id)
    assert result.original_retrieved_at is None
    assert run.attempts.count() == 1 and not CollectionRequest.objects.exists()


def test_early_failure_has_typed_marker_and_no_fabricated_coverage(selection, monkeypatch):
    job, _product, _account, _pin = selection

    def invalid(*args, **kwargs):
        raise ValueError("invalid fixture evidence")

    monkeypatch.setattr("core.model_history_collection._execute_models", invalid)
    budget = Budget(httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("unexpected HTTP"))), max_requests=1)
    run = execute_model_history(job.pk, budget=budget)
    assert run.status == "partial" and run.error_code == "invalid_history_evidence"
    assert run.scopes.filter(scope_kind="history_execution", phase="typed-history-v1").exists()
    report = run_report_document(run)
    assert report["coverage"] == [] and report["evaluated_cells"] == 0
    assert report["physical_requests_this_invocation"] == 0
    assert report["physical_accounting_complete"] is False
    assert not run.observations.exists()


def test_native_publication_selection_keeps_source_ids_without_echoing_rows(monkeypatch):
    from core.collection_jobs import register_job, set_job_state
    from core.models import DataSource

    provider = DataSource.objects.create(pk="openrouter", name="OpenRouter", source_type="model_adoption",
                                         enabled=True, adapter_key="openrouter-v1")
    job = register_job(
        job_key="native-coverage", source=provider, purpose="catalog", operation="model_history", mode="historical",
        definition={"version": 1, "scope": {
            "cohort_hash": "a" * 64, "models": [], "native_publication_identifiers": ["lab/model"],
            "global_start_at": "2026-09-01T00:00:00Z", "cutoff": "2026-09-12T00:00:00Z",
        }, "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "bytes": 10000, "seconds": 30, "items": 100}},
    )
    set_job_state(job.pk, "ready")
    originals = []

    def evidence(claim, *_args, **_kwargs):
        original = CollectionObservation.objects.create(
            run_id=claim.run_id, source_identifier="publication-window", source_subject_kind="aggregate",
            observation_kind="publication_window", observation_key=digest(["native-window", str(claim.run_id)]),
        )
        originals.append(original.pk)
        return [{"observation_id": original.pk, "matched_rows": [{"model_permaslug": "lab/model", "total_tokens": "7"}]}], {
            "outcome": "observed", "reason": "native_publications",
        }

    monkeypatch.setattr("core.model_history_collection._publication_evidence", evidence)
    budget = Budget(httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("unexpected HTTP"))), max_requests=1)
    run = execute_model_history(job.pk, budget=budget)
    assert run.status == "success"
    scoped = run.scopes.get(scope_kind="native_publication_coverage")
    assert scoped.envelopes == [] and scoped.ownership == {}
    assert scoped.resource_observation.source_subject_kind == "aggregate"
    cell = history_report(run)["coverage"][0]
    assert cell["native_identifiers"] == ["lab/model"] and cell["outcome"] == "observed"
    assert [row["observation_id"] for row in cell["evidence"]] == originals
    assert "matched_rows" not in cell["evidence"][0]
    assert cell["evidence"][0]["source_time_precision"] == "unknown"
    assert not MetricValue.objects.exists()
