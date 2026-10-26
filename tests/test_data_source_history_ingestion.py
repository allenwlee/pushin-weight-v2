"""Publication campaigns automatically project typed values from durable evidence."""

import copy
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from django.core.management import call_command
from django.utils import timezone

from core.collection_identity import review_catalog_mapping
from core.collection_jobs import register_job, set_job_state
from core.measurement_taxonomy import digest, subject_id
from core.model_history_collection import execute_model_history
from core.model_history_statistics import prepare_history_statistics_scope
from core.models import (
    CollectionObservation,
    CollectionRun,
    DataSource,
    MeasurementSubject,
    MetricValue,
)
from scripts.benchmark_download_collector.sources import Budget
from tests.collection_fixtures import evidence_job
from tests.product_factory import product_type_fields
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize("source_id", ["arena", "openrouter"])
def test_selected_publication_rows_keep_typed_origin_links_and_coordinates(source_id):
    source, _product, scope = publication_scope(source_id)
    budget, _requests = transport(source_id)
    run = execute_model_history(register(source, scope).pk, budget=budget, key="fixture")
    assert run.status == "success", run.report
    selected = list(CollectionObservation.objects.filter(observation_kind="publication_row"))
    assert selected
    expected = {}
    for observation in selected:
        edge = observation.inputs.get(input_role="publication_row_origin")
        original = edge.input_observation
        assert original.pk == observation.source_metadata["origin_publication_observation_id"]
        assert original.run.job.source_id == source_id
        assert edge.input_sha256 == original.observation_key
        snapshot = observation.source_metadata["numeric_snapshot_identity"]
        assert observation.provider_revision == snapshot["revision"]
        assert observation.source_record_date.isoformat() == snapshot["period"]
        assert observation.category_key == snapshot["category"]
        if source_id == "openrouter":
            assert observation.published_date is None
        expected[observation.pk] = original.pk
    CollectionObservation.objects.filter(pk__in=expected).update(listing={}, source_metadata={}, dimensions={})
    for observation in CollectionObservation.objects.filter(pk__in=expected):
        assert observation.inputs.get(input_role="publication_row_origin").input_observation_id == expected[observation.pk]


def publication_scope(source="openrouter", *, config="text", identifier_scope=None):
    product, _ = setup_spec()
    subject = MeasurementSubject.objects.get(
        pk=subject_id("product", product.product_key)
    )
    provider = DataSource.objects.get(pk=source)
    provider.enabled = True
    provider.save()
    mapping = review_catalog_mapping(
        source=provider,
        subject=subject,
        external_identifier="lab/model",
        source_subject_kind="model",
        identifier_scope=identifier_scope
        or ("rankings_permaslug" if source == "openrouter" else "arena_model_name"),
        publisher_account=product.publisher_account,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://example.org/reviewed-model-crosswalk",
        reviewed_by="fixture",
        identity_snapshot={},
    )
    scope = {
        "brand_id": product.brand_id,
        "cohort_hash": "a" * 64,
        "cutoff": "2026-09-12T00:00:00Z",
        "global_start_at": "2026-09-10T00:00:00Z",
        "arena_config": config,
        "models": [
            {
                "product_key": str(product.product_key),
                "creation": {"at": "2026-09-10T00:00:00Z"},
                "provider_pins": [
                    {
                        "mapping_id": str(mapping.pk),
                        "mapping_hash": mapping.mapping_hash,
                        "source": source,
                        "native_identifier": "lab/model",
                        "identifier_scope": mapping.identifier_scope_code,
                    }
                ],
            }
        ],
    }
    return (
        provider,
        product,
        prepare_history_statistics_scope(
            source=provider, scope=scope, reviewed_by="fixture"
        ),
    )


def register(source, scope, *, key="history", items=1000):
    job = register_job(
        job_key=key,
        source=source,
        purpose="catalog",
        operation="model_history",
        mode="historical",
        definition={
            "version": 1,
            "scope": scope,
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {
                "requests": 30,
                "seconds": 60,
                "bytes": 1000000,
                "items": items,
            },
        },
    )
    return set_job_state(job.pk, "ready")


def transport(
    source="openrouter",
    *,
    revision="rev1",
    tokens="123",
    model="lab/model",
    config="text",
):
    requests = []

    def respond(request):
        requests.append(request)
        if source == "openrouter":
            start, end = (
                request.url.params["start_date"],
                request.url.params["end_date"],
            )
            days = [
                datetime.fromisoformat(start).date() + timedelta(days=i)
                for i in range(
                    (
                        datetime.fromisoformat(end).date()
                        - datetime.fromisoformat(start).date()
                    ).days
                    + 1
                )
            ]
            return httpx.Response(
                200,
                json={
                    "meta": {
                        "version": "v1",
                        "start_date": start,
                        "end_date": end,
                        "as_of": "2026-09-12T03:00:00Z",
                    },
                    "data": [
                        {
                            "date": d.isoformat(),
                            "model_permaslug": name,
                            "total_tokens": count,
                        }
                        for d in days
                        for name, count in [(model, tokens), ("other", "999")]
                    ],
                },
            )
        row = {
            "model_name": model,
            "category": "overall",
            "leaderboard_publish_date": "2026-09-11",
            "rank": 1,
        }
        row.update(
            {
                "score": 0.6,
                "score_ci_lower": 0.5,
                "score_ci_upper": 0.7,
                "observation_count": 22,
                "session_count": 9,
            }
            if config == "agent"
            else {
                "rating": 1400.0,
                "rating_lower": 1390.0,
                "rating_upper": 1410.0,
                "vote_count": 12,
            }
        )
        return httpx.Response(
            200,
            json={
                "num_rows_total": 1,
                "dataset_git_revision": revision,
                "rows": [{"row": row, "truncated_cells": []}],
            },
        )

    return Budget(
        httpx.Client(transport=httpx.MockTransport(respond)),
        max_requests=30,
        max_bytes=1000000,
    ), requests


@pytest.mark.parametrize(
    "source,config", [("openrouter", "text"), ("arena", "text"), ("arena", "agent")]
)
def test_actual_history_dispatch_writes_numeric_and_reuses_saved_publication(
    source, config, monkeypatch
):
    from core.collection_scheduling import execute_due_job

    monkeypatch.setenv("BENCHMARK_OPENROUTER_API_KEY", "fixture")

    provider, product, scope = publication_scope(source, config=config)
    job = register(provider, scope)
    budget, _requests = transport(source, config=config)
    run = execute_due_job(job, {"slot": None}, budget)
    assert run.status == "success", run.report
    selection_scopes = list(run.scopes.filter(scope_kind="publication_selection"))
    assert selection_scopes
    for selected_scope in selection_scopes:
        assert selected_scope.resource_observation_id == selected_scope.ownership["publication_observation_id"]
        assert selected_scope.projection_contract.contract_hash == selected_scope.ownership["contract_hash"]
    assert MetricValue.objects.exists()
    assert MetricValue.objects.filter(observation__product=product).exists()
    assert all(v.observation.run.purpose == "metric" for v in MetricValue.objects.all())
    before = MetricValue.objects.count()
    replay = register(provider, scope, key="history-other-job")
    fresh_budget, fresh_requests = transport(source, config=config)
    again = execute_model_history(replay.pk, budget=fresh_budget, key="fixture")
    assert again.status == "success", again.report
    assert not fresh_requests and MetricValue.objects.count() == before
    assert again.report["numeric_projection"]["after_acquisition"][
        "reused_resources"
    ] > 0 or any(
        entry.get("numeric_reused")
        for cell in again.report["coverage"]
        for entry in cell["evidence"]
    )
    if source == "openrouter":
        aggregate = MetricValue.objects.filter(observation__source_identifier="other")
        assert aggregate.exists() and all(
            v.observation.mapping_id is None for v in aggregate
        )
        assert all(v.temporal_status == "exact" for v in aggregate)
    elif config == "agent":
        assert set(
            MetricValue.objects.values_list("source_metric__metric_key", flat=True)
        ) == {
            "agent_score",
            "agent_score_ci_lower",
            "agent_score_ci_upper",
            "observation_count",
            "session_count",
            "rank",
        }
        assert not MetricValue.objects.filter(
            source_metric__metric_key="vote_count"
        ).exists()


def test_publication_scope_copy_preserves_exact_refs_and_refuses_identity_drift():
    from core.collection_storage_migration import (
        project_publication_scope_references_batch,
    )
    from core.models import CollectionScopeRun

    provider, _product, scope = publication_scope()
    run = execute_model_history(register(provider, scope).pk, budget=transport()[0], key="fixture")
    assert run.status == "success", run.report
    selected = run.scopes.get(scope_kind="publication_selection")
    expected = (selected.resource_observation_id, selected.projection_contract_id)
    CollectionScopeRun.objects.filter(pk=selected.pk).update(
        resource_observation=None, projection_contract=None,
    )
    with pytest.raises(ValueError, match="missing typed references"):
        project_publication_scope_references_batch(verify_only=True)
    assert project_publication_scope_references_batch().updated == 1
    selected.refresh_from_db()
    assert (selected.resource_observation_id, selected.projection_contract_id) == expected
    assert project_publication_scope_references_batch().updated == 0
    assert project_publication_scope_references_batch(verify_only=True).scanned == 1
    CollectionScopeRun.objects.filter(pk=selected.pk).update(scope_key="changed")
    with pytest.raises(ValueError, match="reference differs"):
        project_publication_scope_references_batch(verify_only=True)
    other_observation = CollectionObservation.objects.exclude(pk=expected[0]).first()
    CollectionScopeRun.objects.filter(pk=selected.pk).update(
        scope_key=selected.scope_key, resource_observation=other_observation,
    )
    with pytest.raises(ValueError, match="pin changed"):
        project_publication_scope_references_batch()
    selected.refresh_from_db()
    assert selected.resource_observation_id == other_observation.pk


def test_arena_revised_publication_keeps_both_snapshots():
    provider, _product, scope = publication_scope("arena")
    first = register(provider, scope)
    execute_model_history(first.pk, budget=transport("arena")[0])
    count = MetricValue.objects.count()
    # A different requested window acquires the provider's changed real revision.
    later = copy.deepcopy(scope)
    later["cutoff"] = "2026-09-13T00:00:00Z"
    second = register(provider, later, key="revised")
    execute_model_history(second.pk, budget=transport("arena", revision="rev2")[0])
    assert MetricValue.objects.count() == count * 2
    assert set(
        CollectionObservation.objects.filter(
            source_metadata__projection_kind="source-statistics-v1"
        ).values_list("source_metadata__snapshot_identity__revision", flat=True)
    ) == {"rev1", "rev2"}


def test_catalog_id_is_not_a_rankings_identifier_and_top_n_omission_is_not_zero():
    provider, _product, scope = publication_scope(identifier_scope="catalog_id")
    job = register(provider, scope)
    budget, requests = transport()
    run = execute_model_history(job.pk, budget=budget)
    assert run.report["coverage"][0]["outcome"] == "unmapped"
    assert not requests and not MetricValue.objects.exists()


def test_omitted_model_has_no_value_but_other_remains_aggregate():
    provider, product, scope = publication_scope()
    run = execute_model_history(
        register(provider, scope).pk,
        budget=transport(model="elsewhere/model")[0],
        key="fixture",
    )
    assert run.report["coverage"][0]["reason"] == "not_in_provider_publications"
    assert not MetricValue.objects.filter(observation__product=product).exists()
    assert set(
        MetricValue.objects.values_list("observation__source_identifier", flat=True)
    ) == {"other"}


def test_pending_numeric_survives_crash_without_any_transport_files():
    provider, _product, scope = publication_scope()
    job = register(provider, scope)
    from core.source_metric_projection import drain_pending_projections

    calls = []

    def crash_after_capture(job_id, **kwargs):
        calls.append(job_id)
        if len(calls) == 2:
            raise RuntimeError("injected crash")
        return drain_pending_projections(job_id, **kwargs)

    with (
        patch(
            "core.model_history_collection.drain_pending_projections",
            side_effect=crash_after_capture,
        ),
        pytest.raises(RuntimeError, match="injected"),
    ):
        execute_model_history(job.pk, budget=transport()[0], key="fixture")
    assert CollectionObservation.objects.filter(
        dimensions__kind="publication_row"
    ).exists()
    assert not MetricValue.objects.exists()
    # Expired lease models a successor after process death; data is all in DB.
    CollectionRun.objects.filter(job=job, status="running").update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    budget, requests = transport()
    recovered = execute_model_history(job.pk, budget=budget, key="fixture")
    assert recovered.status == "success", recovered.report
    assert not requests and MetricValue.objects.exists()


def test_unsupported_arena_configuration_is_terminal_without_fake_values():
    provider, _product, scope = publication_scope("arena")
    scope["arena_config"] = "unreviewed-board"
    run = execute_model_history(
        register(provider, scope).pk, budget=transport("arena")[0]
    )
    assert run.status == "success"
    assert run.report["coverage"][0]["reason"] == "unreviewed_arena_configuration"
    assert not MetricValue.objects.exists()


@pytest.mark.parametrize("drift", ["evidence", "owner"])
def test_opt_in_model_kind_pins_native_evidence_without_changing_taxonomy_type(drift):
    from core.model_history_cohort import build_cohort, validate_model_pins
    from core.model_kind_qualification import MODEL_KIND_POLICY
    from core.models import Brand, Product

    product, _ = setup_spec()
    product.product_type = None
    product.created_at = datetime(2026, 9, 1, tzinfo=UTC)
    product.save()
    brands = [product.brand_id] + [
        Brand.objects.create(nickname=f"other-{i}").pk for i in range(20)
    ]
    run = CollectionRun.objects.create(
        job=evidence_job(source_id="hf", purpose="catalog"),
        status="success",
        completed_at=timezone.now(),
        ingestion_key="b" * 64,
    )
    evidence = CollectionObservation.objects.create(
        run=run,
        product=product,
        source_identifier=product.repo_id,
        source_subject_kind="repository",
        observation_key="c" * 64,
        listing={
            "id": product.repo_id,
            "private": False,
            "createdAt": "2026-09-01T00:00:00Z",
        },
        dimensions={"kind": "creation_inventory"},
    )
    call_command("normalize_collection_run_jobs", verbosity=0)
    from core.collection_resources import project_observation_facts

    project_observation_facts(evidence)
    CollectionObservation.objects.filter(pk=evidence.pk).update(dimensions={})
    evidence.refresh_from_db()
    arguments = {"brand_ids": brands, "cutoff": "2026-09-12T00:00:00Z"}
    original = build_cohort(**arguments)
    assert not original["brands"][product.brand_id]["models"]
    assert digest(original) == digest(
        build_cohort(**arguments, qualification_policy=None)
    )
    qualified = build_cohort(**arguments, qualification_policy=MODEL_KIND_POLICY)
    selected = qualified["brands"][product.brand_id]["models"]
    assert selected[0]["product_key"] == str(product.product_key)
    assert selected[0]["qualification"]["subtype"] == "unknown"
    scope = {
        "brand_id": product.brand_id,
        "cohort_hash": digest(qualified),
        "models": selected,
    }
    provider = DataSource.objects.get(pk="hf")
    provider.enabled = True
    provider.save()
    job = register(provider, scope)
    assert validate_model_pins(job)
    if drift == "evidence":
        evidence.listing["private"] = True
        evidence.save()
    else:
        ownership = product.publisher_ownership
        ownership.ownership_confirmed = False
        ownership.save()
    with pytest.raises(ValueError):
        validate_model_pins(job)
    assert Product.objects.get(pk=product.pk).product_type_code is None


def test_rolling_publication_selection_uses_current_window_with_frozen_cohort():
    from types import SimpleNamespace

    from core.collection_storage_migration import (
        project_publication_runtime_bounds_batch,
    )
    from core.model_history_collection import _runtime_publication_window
    from core.models import CollectionScopeRun

    provider, _product, scope = publication_scope()
    original = copy.deepcopy(scope)
    scope.update(
        publication_window_policy="rolling-completed-days-v1",
        publication_recheck_days=2,
    )
    job = register(provider, scope)
    now = datetime(2026, 10, 15, 3, tzinfo=UTC)
    budget, requests = transport()
    with patch("core.model_history_collection.timezone.now", return_value=now):
        run = execute_model_history(job.pk, budget=budget, key="fixture")
    assert requests[0].url.params["start_date"] == "2026-10-13"
    assert requests[0].url.params["end_date"] == "2026-10-14"
    job.refresh_from_db()
    assert job.definition["scope"]["cutoff"] == original["cutoff"]
    runtime = run.scopes.get(scope_kind="publication_runtime")
    assert runtime.envelopes[0]["cutoff"] == "2026-10-15T00:00:00+00:00"
    CollectionScopeRun.objects.filter(pk=runtime.pk).update(
        requested_start_at=None, requested_end_at=None,
    )
    with pytest.raises(ValueError, match="missing typed bounds"):
        project_publication_runtime_bounds_batch(verify_only=True)
    assert project_publication_runtime_bounds_batch(batch_size=1).updated == 1
    assert project_publication_runtime_bounds_batch(batch_size=1).updated == 0
    assert project_publication_runtime_bounds_batch(verify_only=True).scanned == 1
    runtime.refresh_from_db()
    assert runtime.requested_start_at == datetime(2026, 10, 13, tzinfo=UTC)
    assert runtime.requested_end_at == datetime(2026, 10, 15, tzinfo=UTC)

    # A historical resume reads the saved typed window even after the legacy
    # envelope is absent and the wall clock has advanced.
    saved_envelopes = copy.deepcopy(runtime.envelopes)
    runtime.envelopes = []
    runtime.save(update_fields=["envelopes"])
    with patch(
        "core.model_history_collection.timezone.now",
        return_value=now + timedelta(days=20),
    ):
        resumed = _runtime_publication_window(SimpleNamespace(run_id=run.pk), job)
    assert resumed.scope["cutoff"] == "2026-10-15T00:00:00+00:00"
    assert resumed.scope["publication_start_at"] == "2026-10-13T00:00:00+00:00"

    saved_envelopes[0]["cutoff"] = "2026-10-16T00:00:00+00:00"
    runtime.envelopes = saved_envelopes
    runtime.save(update_fields=["envelopes"])
    with pytest.raises(ValueError, match="conflicting typed bounds"):
        project_publication_runtime_bounds_batch()
    runtime.envelopes[0]["cutoff"] = "2026-10-15T00:00:00+00:00"
    runtime.ownership["cohort_hash"] = "e" * 64
    runtime.save(update_fields=["ownership", "envelopes"])
    with pytest.raises(ValueError, match="runtime identity"):
        project_publication_runtime_bounds_batch()


def test_native_publication_scope_needs_no_invented_products_or_accounts():
    from core.models import Account, Product

    product, _ = setup_spec()
    source = DataSource.objects.get(pk="openrouter")
    source.enabled = True
    source.save()
    counts = (Account.objects.count(), Product.objects.count())
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
    run = execute_model_history(
        register(source, scope).pk, budget=transport()[0], key="fixture"
    )
    assert run.status == "success", run.report
    assert MetricValue.objects.exists()
    assert not MetricValue.objects.exclude(observation__mapping=None).exists()
    assert counts == (Account.objects.count(), Product.objects.count())


def test_small_projection_budget_is_partial_then_resumes_pending_rows():
    source, _product, scope = publication_scope()
    job = register(source, scope, items=3)
    first = execute_model_history(job.pk, budget=transport()[0], key="fixture")
    assert first.status == "partial", first.report
    assert first.report["numeric_projection"]["after_acquisition"]["pending"]
    budget, requests = transport()
    second = execute_model_history(job.pk, budget=budget, key="fixture")
    assert second.status == "success", second.report
    assert not requests
    assert MetricValue.objects.count() == 4


def test_campaign_facade_accounts_publication_requests_on_shared_child(monkeypatch):
    from core.data_source_backfill import campaign_usage, execute_phase

    monkeypatch.setenv("BENCHMARK_OPENROUTER_API_KEY", "fixture")
    source, _product, scope = publication_scope()
    campaign = {
        "kind": "backfiller-data-source-v1",
        "key": "publication-proof",
        "cohort_hash": scope["cohort_hash"],
        "role": "history",
        "phase": "acquire",
        "contract_partition": None,
        "max_invocations": 100,
        "max_requests": 1000,
    }
    job = register_job(
        job_key="campaign-proof",
        source=source,
        purpose="catalog",
        operation="model_history",
        mode="historical",
        definition={
            "version": 1,
            "scope": scope,
            "campaign": campaign,
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 30, "seconds": 60, "bytes": 1000000, "items": 1000},
        },
    )
    budget, requests = transport()
    run = execute_phase(job.pk, budget=budget)
    assert run.status == "success", run.report
    assert MetricValue.objects.exists()
    assert run.request_count == 0
    usage = campaign_usage(job)
    assert usage["recorded_requests"] == len(requests) == 1


def test_provider_qualified_unknown_subtype_can_map_statistics_but_not_text_benchmark():
    from core.benchmark_metric_identity import configure_collection
    from core.collection_storage_migration import project_observation_groups_batch
    from core.model_kind_qualification import qualify_model_kind, validate_model_kind
    from tests.test_source_metric_projection import project

    product, _ = setup_spec()
    product.product_type = None
    product.save()
    evidence_run = CollectionRun.objects.create(
        job=evidence_job(source_id="hf", purpose="catalog"),
        status="success",
        completed_at=timezone.now(),
        ingestion_key="d" * 64,
    )
    observation = CollectionObservation.objects.create(
        run=evidence_run,
        product=product,
        source_identifier=product.repo_id,
        source_subject_kind="repository",
        observation_key="e" * 64,
        listing={"id": product.repo_id, "private": False, "downloads": 7, "likes": 2},
        dimensions={"kind": "creation_inventory"},
        groups={"listing": "ok"},
    )
    call_command("normalize_collection_run_jobs", verbosity=0)
    from core.collection_resources import project_observation_facts

    project_observation_facts(observation)
    project_observation_groups_batch(after_id=observation.pk - 1, batch_size=1)
    qualification = qualify_model_kind(product)
    assert qualification
    CollectionObservation.objects.filter(pk=observation.pk).update(groups={})
    assert validate_model_kind(product, qualification) == qualification
    from core.collection_capture import archive_legacy

    archive = archive_legacy({
        "listing": observation.listing,
        "dimensions": observation.dimensions,
        "source_metadata": observation.source_metadata,
        "envelopes": observation.envelopes,
        "groups": {"listing": "ok"},
    })
    CollectionObservation.objects.filter(pk=observation.pk).update(
        legacy_archive=archive, listing={}, dimensions={}, source_metadata={},
    )
    assert validate_model_kind(product, qualification) == qualification
    subject = MeasurementSubject.objects.get(
        pk=subject_id("product", product.product_key)
    )
    source = DataSource.objects.get(pk="hf")
    mapping = review_catalog_mapping(
        source=source,
        subject=subject,
        external_identifier=product.repo_id,
        source_subject_kind="repository",
        identifier_scope="model",
        publisher_account=product.publisher_account,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://huggingface.co/lab/Model",
        reviewed_by="fixture",
        identity_snapshot={},
    )
    scope = prepare_history_statistics_scope(
        source=source,
        reviewed_by="fixture",
        scope={
            "cohort_hash": "f" * 64,
            "models": [
                {
                    "product_key": str(product.product_key),
                    "qualification": qualification,
                    "provider_pins": [
                        {
                            "mapping_id": str(mapping.pk),
                            "mapping_hash": mapping.mapping_hash,
                            "source": "hf",
                        }
                    ],
                }
            ],
        },
    )
    from core.models import MetricCollectionContract

    contract = MetricCollectionContract.objects.get(pk=scope["numeric_contract_id"])
    source.enabled = True
    source.save()
    run = project(contract, "hf", [observation])
    assert run.status == "success"
    assert MetricValue.objects.filter(observation__product=product).count() == 2
    with pytest.raises(ValueError, match="type"):
        configure_collection(
            {
                "reviewed_by": "fixture",
                "taxonomy_version": str(contract.taxonomy_version_id),
                "mappings": [
                    {
                        "source": "hf",
                        "source_subject_kind": "repository",
                        "identifier_scope": "model",
                        "external_identifier": product.repo_id,
                        "subject_id": str(subject.pk),
                        "evidence_url": "https://huggingface.co/lab/Model",
                    }
                ],
                "source_configuration": {"hf": {"metrics": ["downloads"]}},
            }
        )
    product.refresh_from_db()
    assert product.product_type_code is None


def test_history_statistics_reuses_existing_product_and_publisher_subjects():
    from core.benchmark_metric_identity import configure_collection
    from core.model_kind_qualification import qualify_model_kind
    from core.models import MetricCollectionContract, Product, SourceSubjectMapping

    original_product, original_spec = setup_spec()
    original_contract = configure_collection(original_spec)
    account = original_product.publisher_account
    product = Product.objects.create(
        repo_id="lab/Legacy",
        brand=original_product.brand,
        publisher_account=account,
        **product_type_fields(Product, None),
        private=False,
        disabled=False,
    )
    subject = MeasurementSubject.objects.create(subject_kind="product", product=product)
    publisher_subject = MeasurementSubject.objects.create(
        subject_kind="account", account=account
    )
    assert subject.pk != subject_id("product", product.product_key)
    assert publisher_subject.pk != subject_id("account", account.pk)
    source = DataSource.objects.get(pk="hf")
    mappings = []
    for provider, scope in (
        (source, "model"),
        (DataSource.objects.get(pk="openrouter"), "rankings_permaslug"),
    ):
        mappings.append(
            review_catalog_mapping(
                source=provider,
                subject=subject,
                external_identifier=product.repo_id,
                source_subject_kind="repository" if provider == source else "model",
                identifier_scope=scope,
                publisher_account=account,
                role="dedicated_model",
                version_selector=None,
                evidence_url="https://huggingface.co/lab/Legacy",
                reviewed_by="fixture",
                identity_snapshot={},
            )
        )
    evidence_run = CollectionRun.objects.create(
        job=evidence_job(source_id=source.pk, purpose="catalog"),
        status="success",
        completed_at=timezone.now(),
        ingestion_key="1" * 64,
    )
    evidence = CollectionObservation.objects.create(
        run=evidence_run,
        product=product,
        source_identifier=product.repo_id,
        source_subject_kind="repository",
        observation_key="2" * 64,
        listing={"id": product.repo_id, "private": False},
        dimensions={"kind": "creation_inventory"},
    )
    call_command("normalize_collection_run_jobs", verbosity=0)
    from core.collection_resources import project_observation_facts

    project_observation_facts(evidence)
    qualification = qualify_model_kind(product)
    assert qualification
    draft = {
        "cohort_hash": "f" * 64,
        "models": [
            {
                "product_key": str(product.product_key),
                "qualification": qualification,
                "provider_pins": [
                    {
                        "mapping_id": str(mappings[0].pk),
                        "mapping_hash": mappings[0].mapping_hash,
                        "source": "hf",
                    }
                ],
            }
        ],
    }
    original_draft = copy.deepcopy(draft)
    old_subjects = list(MeasurementSubject.objects.order_by("pk").values())
    old_mapping_ids = list(SourceSubjectMapping.objects.values_list("pk", flat=True))
    old_mappings = list(SourceSubjectMapping.objects.order_by("pk").values())
    old_contract = (
        MetricCollectionContract.objects.filter(pk=original_contract.pk).values().get()
    )

    prepared = prepare_history_statistics_scope(
        source=source, scope=draft, reviewed_by="fixture"
    )
    assert draft == original_draft
    assert (
        prepare_history_statistics_scope(
            source=source, scope=draft, reviewed_by="fixture"
        )
        == prepared
    )
    contract = MetricCollectionContract.objects.get(pk=prepared["numeric_contract_id"])
    expected = {subject.pk, publisher_subject.pk}
    assert set(contract.mappings.values_list("subject_id", flat=True)) == expected
    assert set(contract.taxonomy_version.snapshot["subjects"]) == {
        str(pk) for pk in expected
    }
    assert list(MeasurementSubject.objects.order_by("pk").values()) == old_subjects
    assert (
        list(
            SourceSubjectMapping.objects.filter(pk__in=old_mapping_ids)
            .order_by("pk")
            .values()
        )
        == old_mappings
    )
    assert (
        MetricCollectionContract.objects.filter(pk=original_contract.pk).values().get()
        == old_contract
    )
    product.refresh_from_db()
    assert product.product_type_code is None


@pytest.mark.parametrize("items", [1000, 2])
def test_sparse_hf_archive_acquisition_automatically_projects_without_interpolation(
    items,
):
    from core.collection_identity import review_catalog_mapping

    product, _ = setup_spec()
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.save()
    from core.measurement_taxonomy import configure_taxonomy
    from core.models import Product

    second = Product.objects.create(
        repo_id="lab/Second",
        publisher_account=product.publisher_account,
        brand=product.brand,
        **product_type_fields(Product, "llm-model"),
        private=False,
        disabled=False,
    )
    configure_taxonomy(
        {
            "reviewed_by": "fixture",
            "subjects": [
                {"kind": "product", "key": str(p.product_key)}
                for p in (product, second)
            ],
        }
    )
    models = []
    for selected in (product, second):
        subject = MeasurementSubject.objects.get(
            pk=subject_id("product", selected.product_key)
        )
        mapping = review_catalog_mapping(
            source=source,
            subject=subject,
            external_identifier=selected.repo_id,
            source_subject_kind="repository",
            identifier_scope="model",
            publisher_account=selected.publisher_account,
            role="dedicated_model",
            version_selector=None,
            evidence_url="https://huggingface.co/" + selected.repo_id,
            reviewed_by="fixture",
            identity_snapshot={},
        )
        models.append(
            {
                "product_key": str(selected.product_key),
                "creation": {
                    "at": "2026-09-01T00:00:00Z",
                    "source": "hf",
                    "native_identifier": selected.repo_id,
                },
                "provider_pins": [
                    {
                        "mapping_id": str(mapping.pk),
                        "mapping_hash": mapping.mapping_hash,
                        "source": "hf",
                        "native_identifier": selected.repo_id,
                        "identifier_scope": "model",
                    }
                ],
            }
        )
    scope = prepare_history_statistics_scope(
        source=source,
        reviewed_by="fixture",
        scope={
            "cohort_hash": "a" * 64,
            "brand_id": product.brand_id,
            "cutoff": "2026-09-12T00:00:00Z",
            "global_start_at": "2026-09-01T00:00:00Z",
            "models": models,
            "hf_archive": {
                "dataset_id": "cfahlgren1/hub-stats",
                "archive_publisher": "cfahlgren1",
                "revisions": [
                    {"id": "a" * 40, "snapshot_date": "2026-09-02"},
                    {"id": "b" * 40, "snapshot_date": "2026-09-09"},
                ],
            },
        },
    )
    budget = Budget(
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(404, json={}))
        ),
        max_requests=20,
        max_bytes=1000000,
    )
    with patch(
        "scripts.benchmark_download_collector.hf_archive.select_snapshot",
        return_value={
            "rows": [
                {"id": repo, "downloads": 5, "likes": 2}
                for repo in (product.repo_id, "lab/Second")
            ],
            "file_path": "saved.parquet",
        },
    ):
        job = register(source, scope, items=items)
        for _ in range(6):
            run = execute_model_history(job.pk, budget=budget)
            if run.status != "partial":
                break
            budget = Budget(
                httpx.Client(
                    transport=httpx.MockTransport(
                        lambda request: pytest.fail("resume must not refetch archives")
                    )
                )
            )
    assert run.status == "success", run.report
    assert MetricValue.objects.count() == 8
    assert (
        CollectionObservation.objects.filter(values__isnull=False).distinct().count()
        == 4
    )
    assert not run.scopes.filter(
        scope_kind="numeric_projection", outcome="pending"
    ).exists()
    assert set(
        MetricValue.objects.filter(source_metric__metric_key="likes").values_list(
            "as_of_date", flat=True
        )
    ) == {date(2026, 9, 2), date(2026, 9, 9)}
    downloads = list(
        MetricValue.objects.filter(source_metric__metric_key="downloads")
    )
    expected_ends = {
        date(2026, 9, 2): datetime(2026, 9, 3, tzinfo=UTC),
        date(2026, 9, 9): datetime(2026, 9, 10, tzinfo=UTC),
    }
    assert len(downloads) == 4
    assert {value.period_label_date for value in downloads} == set(expected_ends)
    for value in downloads:
        assert value.temporal_status == "date_only"
        assert value.window_end_at == expected_ends[value.period_label_date]
        assert value.window_start_at == value.window_end_at - timedelta(days=30)
        assert value.window_range.lower == value.window_start_at
        assert value.window_range.upper == value.window_end_at
        assert value.window_range.lower_inc and not value.window_range.upper_inc


def test_existing_completed_or_day_reuses_original_contract_and_only_acquires_gap():
    from core.benchmark_metric_identity import configure_collection
    from core.benchmark_metric_store import persist_source
    from core.models import MetricCollectionContract

    source, product, scope = publication_scope()
    statistics = MetricCollectionContract.objects.get(pk=scope["numeric_contract_id"])
    legacy = configure_collection(
        {
            "reviewed_by": "fixture",
            "taxonomy_version": str(statistics.taxonomy_version_id),
            "source_configuration": {"openrouter": {"metrics": ["total_tokens"]}},
            "mappings": [
                {
                    "source": "openrouter",
                    "external_identifier": "lab/model",
                    "source_subject_kind": "model",
                    "subject_id": str(subject_id("product", product.product_key)),
                    "evidence_url": "https://example.org/reviewed-crosswalk",
                }
            ],
        }
    )
    original = persist_source(
        legacy,
        "openrouter",
        "9" * 64,
        {
            "status": "ok",
            "meta": {"version": "v1"},
            "rows": [
                {
                    "date": "2026-09-10",
                    "model_permaslug": "lab/model",
                    "total_tokens": "42",
                    "_source_metadata": {"immutable_revision": "8" * 64},
                }
            ],
        },
    )
    value = MetricValue.objects.get(observation__run=original)
    budget, requests = transport()
    run = execute_model_history(
        register(source, scope).pk, budget=budget, key="fixture"
    )
    assert run.status == "success", run.report
    assert requests[0].url.params["start_date"] == "2026-09-11"
    assert requests[0].url.params["end_date"] == "2026-09-11"
    reused = [
        entry
        for entry in run.report["coverage"][0]["evidence"]
        if entry.get("numeric_reused")
    ]
    assert len(reused) == 1
    assert reused[0]["value_id"] == value.pk
    assert reused[0]["contract_id"] == str(legacy.pk)
    assert reused[0]["run_id"] == str(original.pk)
    value.refresh_from_db()
    assert value.integer_value == 42 and value.observation.run_id == original.pk


def test_statistics_arena_windows_are_pinned_and_have_no_synthetic_carry_in():
    source, _product, scope = publication_scope("arena")
    scope["publication_window_days"] = 1
    budget, requests = transport("arena")
    # The requested campaign starts on the actual fixture publication date.
    scope["global_start_at"] = "2026-09-11T00:00:00Z"
    run = execute_model_history(register(source, scope).pk, budget=budget)
    assert run.status == "success", run.report
    assert "2026-09-11" in requests[0].url.params["where"]
    assert "2026-08-" not in requests[0].url.params["where"]


def latest_arena_transport(*, published="2026-09-11", rating=1400.0):
    import pyarrow as pa
    import pyarrow.parquet as pq

    sink = pa.BufferOutputStream()
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "model_name": "lab/model",
                    "category": "overall",
                    "leaderboard_publish_date": published,
                    "rating": rating,
                    "rating_lower": rating - 10,
                    "rating_upper": rating + 10,
                    "vote_count": 12,
                    "rank": 1,
                }
            ]
        ),
        sink,
    )
    content = sink.getvalue().to_pybytes()
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == "huggingface.co"
        assert request.url.path.endswith("/text/latest-00000-of-00001.parquet")
        return httpx.Response(200, content=content)

    return Budget(
        httpx.Client(transport=httpx.MockTransport(respond)),
        max_requests=30,
        max_bytes=1000000,
    ), requests


@pytest.mark.parametrize(
    "published,has_values",
    [
        ("2026-09-11", True),
        ("2026-09-09", False),
        ("2026-09-12", False),
    ],
)
def test_latest_arena_artifact_dispatch_preserves_publication_window(
    published, has_values
):
    from core.collection_scheduling import execute_due_job

    source, _product, scope = publication_scope("arena")
    scope.update(arena_publication_mode="latest-artifact-v1", publication_window_days=1)
    budget, requests = latest_arena_transport(published=published)
    run = execute_due_job(register(source, scope), {"slot": None}, budget)
    assert run.status == "success", run.report
    assert len(requests) == 1  # One bounded artifact for the whole multi-day window.
    assert MetricValue.objects.exists() is has_values
    cell = run.report["coverage"][0]
    assert cell["outcome"] == "not_published"
    assert cell["coverage_complete"] is False
    evidence = cell["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["provider_coverage"] == "latest_publication_only"
    assert bool(evidence[0]["matched_rows"]) is has_values
    raw = CollectionObservation.objects.get(dimensions__kind="publication_window")
    assert raw.listing["rows"][0]["leaderboard_publish_date"] == published
    assert raw.listing["artifact_sha256"]
    child_scope = raw.run.job.definition["scope"]
    assert child_scope["arena_publication_mode"] == "latest-artifact-v1"
    if has_values:
        assert set(MetricValue.objects.values_list("as_of_date", flat=True)) == {
            datetime.fromisoformat(published).date()
        }


def test_latest_arena_artifact_cache_separates_history_and_retains_revisions():
    source, _product, scope = publication_scope("arena")
    execute_model_history(register(source, scope).pk, budget=transport("arena")[0])
    historical_count = MetricValue.objects.count()
    scope["arena_publication_mode"] = "latest-artifact-v1"
    budget, requests = latest_arena_transport()
    first = execute_model_history(
        register(source, scope, key="artifact").pk, budget=budget
    )
    assert first.status == "success", first.report
    assert len(requests) == 1
    count = MetricValue.objects.count()
    assert count == historical_count * 2
    budget, requests = latest_arena_transport()
    again = execute_model_history(
        register(source, scope, key="artifact-repeat").pk, budget=budget
    )
    assert again.status == "success", again.report
    assert not requests and MetricValue.objects.count() == count
    later = copy.deepcopy(scope)
    later["cutoff"] = "2026-09-13T00:00:00Z"
    budget, requests = latest_arena_transport(rating=1401.0)
    revised = execute_model_history(
        register(source, later, key="artifact-revised").pk, budget=budget
    )
    assert revised.status == "success", revised.report
    assert len(requests) == 1
    assert MetricValue.objects.count() == count + historical_count


@pytest.mark.parametrize(
    "source,mode",
    [
        ("arena", "unknown"),
        ("openrouter", "latest-artifact-v1"),
    ],
)
def test_arena_publication_mode_rejects_unsupported_instructions_without_http(
    source, mode
):
    provider, _product, scope = publication_scope(source)
    scope["arena_publication_mode"] = mode
    budget, requests = transport(source)
    run = execute_model_history(
        register(provider, scope).pk, budget=budget, key="fixture"
    )
    assert run.status == "partial", run.report
    assert not requests and not MetricValue.objects.exists()


def test_latest_arena_mode_requires_source_statistics_contract():
    provider, _product, scope = publication_scope("arena")
    scope["arena_publication_mode"] = "latest-artifact-v1"
    scope.pop("numeric_contract_id")
    scope.pop("numeric_projection_policy")
    budget, requests = latest_arena_transport()
    run = execute_model_history(register(provider, scope).pk, budget=budget)
    assert run.status == "partial", run.report
    assert not requests and not MetricValue.objects.exists()


def test_rolling_latest_arena_reacquires_each_generation_without_duplicate_values():
    provider, _product, scope = publication_scope("arena")
    scope.update(
        arena_publication_mode="latest-artifact-v1",
        publication_window_policy="rolling-completed-days-v1",
        publication_recheck_days=2,
    )
    now = datetime(2026, 9, 12, 3, tzinfo=UTC)
    count = None
    for key in ("rolling-first", "rolling-second"):
        budget, requests = latest_arena_transport()
        with patch("core.model_history_collection.timezone.now", return_value=now):
            run = execute_model_history(
                register(provider, scope, key=key).pk, budget=budget
            )
        assert run.status == "success", run.report
        assert len(requests) == 1
        if count is None:
            count = MetricValue.objects.count()
            assert count > 0
        else:
            assert MetricValue.objects.count() == count
    publications = CollectionObservation.objects.filter(
        dimensions__kind="publication_window"
    )
    assert publications.count() == 2
    assert (
        len(
            {
                row.run.job.definition["scope"]["acquisition_generation"]
                for row in publications
            }
        )
        == 2
    )
