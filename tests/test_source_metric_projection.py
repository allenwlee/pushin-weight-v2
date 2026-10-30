"""PostgreSQL proof for native-grain projection through the shared numeric writer."""

import copy
import importlib
import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.benchmark_serving import github_asset_coordinates, observation_dimensions
from core.collection_capture import archive_legacy, read_document, run_report_document
from core.collection_jobs import register_job, set_job_state
from core.collection_state import StaleClaim, claim_job
from core.measurement_taxonomy import configure_taxonomy, digest, subject_id
from core.models import (
    CollectionObservation,
    CollectionRun,
    MetricValue,
    Product,
    TimeZone,
)
from tests.collection_fixtures import evidence_job
from tests.product_factory import product_type_fields

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
CAPTURED = datetime(2026, 10, 12, 4, 5, tzinfo=UTC)


@pytest.fixture(autouse=True)
def seed_utc_timezone():
    TimeZone.objects.get_or_create(pk="UTC")


def configured(source="hf", *, product_type=None, mapped=False):
    from core.benchmark_metric_identity import register_definitions
    from core.source_metric_projection import configure_source_statistics
    from tests.test_benchmark_download_db_identity import setup_spec
    from tests.test_benchmark_use_policy import decision

    if source == "hf":
        product, _ = setup_spec()
        account = product.publisher_account
        raw = {"id": "lab/Model", "downloads": 0, "likes": 4}
        metrics = ["downloads", "downloads_all_time", "likes", "followers"]
        identifier, scope = "lab/Model", "model"
    else:
        from tests.test_collection_identity import identities

        _, account, subject, raw = identities()
        product = subject.product
        subject.delete()  # This fixture predates the deterministic taxonomy subject IDs.
        raw.update(stargazers_count=3, forks_count=0, open_issues_count=2)
        register_definitions()
        metrics = ["stars", "forks", "open_issues", "subscribers", "asset_downloads"]
        identifier, scope = "123", "repository_id"
    source_row = account.data_source
    source_row.enabled = True
    source_row.adapter_key = (
        "github-catalog-v1" if source == "github" else "hf-model-v1"
    )
    source_row.metadata = {
        **source_row.metadata,
        "use_policy": {use: decision() for use in ("collection", "retention")},
    }
    source_row.save()
    product.product_type_id = product_type_fields(Product, product_type)["product_type_id"]
    product.save()
    subjects = [{"kind": "account", "key": str(account.pk)}]
    if mapped:
        subjects.append({"kind": "product", "key": str(product.product_key)})
    taxonomy = configure_taxonomy({"reviewed_by": "fixture", "subjects": subjects})
    mappings = [
        {
            "source": source,
            "source_subject_kind": "account",
            "identifier_scope": account.account_kind,
            "external_identifier": account.normalized_identifier,
            "subject_id": str(subject_id("account", account.pk)),
            "publisher_account_key": str(account.pk),
            "evidence_url": "https://example.com/publisher",
        }
    ]
    if mapped:
        mappings.append(
            {
                "source": source,
                "source_subject_kind": "repository",
                "identifier_scope": scope,
                "external_identifier": identifier,
                "subject_id": str(subject_id("product", product.product_key)),
                "publisher_account_key": str(account.pk),
                "identifier_metadata": {"role": "dedicated_model"},
                "evidence_url": "https://example.com/model",
            }
        )
    spec = {
        "taxonomy_version": str(taxonomy.pk),
        "reviewed_by": "fixture",
        "mappings": mappings,
        "source_configuration": {
            source: {
                "metrics": metrics,
                "metric_versions": {"downloads_all_time": 2} if source == "hf" else {},
            }
        },
    }
    return configure_source_statistics(spec), raw, product, spec


def evidence(source, raw, *, observed_at=CAPTURED):
    run = CollectionRun.objects.create(
        job=evidence_job(source_id=source, purpose="catalog"),
        ingestion_key=digest([source, raw, observed_at.isoformat()]),
        status="success",
        completed_at=timezone.now(),
    )
    # Saved catalog fixtures model historical evidence after the compatible
    # release has linked its actually stored instructions to an archival job.
    call_command("normalize_collection_run_jobs", verbosity=0)
    run.refresh_from_db()
    return CollectionObservation.objects.create(
        run=run,
        source_subject_kind="repository",
        source_identifier=str(raw["id"]),
        legacy_archive=archive_legacy({
            "listing": raw,
            "dimensions": {"kind": "repository"} if source == "github" else {},
            "source_metadata": {},
            "groups": {},
            "envelopes": [],
        }),
        observed_at=observed_at,
        observation_key=digest(["evidence", str(run.pk)]),
    )


def retained_document(raw, *, dimensions=None, metadata=None):
    return archive_legacy({
        "listing": raw, "dimensions": dimensions or {}, "source_metadata": metadata or {},
        "envelopes": [], "groups": {},
    })


def replace_evidence_document(observation, **changes):
    """Model a changed historical fixture by retaining a new immutable document."""
    document = read_document(observation.legacy_archive)
    document.update(changes)
    observation.legacy_archive = archive_legacy(document)
    observation.save(update_fields=["legacy_archive"])


def historical_projection_contract(scope, ownership):
    """Run the original SQL against its old table shape, independent of live DROP."""
    migration = importlib.import_module("core.migrations.0176_rg6_projection_contract_pin")
    with connection.cursor() as cursor:
        cursor.execute("""CREATE TEMPORARY TABLE collection_scope_runs (
            id bigint PRIMARY KEY, run_id uuid NOT NULL, scope_kind text NOT NULL,
            scope_key text NOT NULL, ownership jsonb NOT NULL, projection_contract_id uuid
        ) ON COMMIT DROP""")
        try:
            cursor.execute("""INSERT INTO pg_temp.collection_scope_runs
                (id,run_id,scope_kind,scope_key,ownership) VALUES (%s,%s,%s,%s,%s::jsonb)""",
                [scope.pk, scope.run_id, scope.scope_kind, scope.scope_key, json.dumps(ownership)])
            migration.copy_projection_contracts(None, SimpleNamespace(connection=connection))
            cursor.execute("SELECT projection_contract_id FROM pg_temp.collection_scope_runs WHERE id=%s", [scope.pk])
            return cursor.fetchone()[0]
        finally:
            cursor.execute("DROP TABLE pg_temp.collection_scope_runs")


def project(contract, source, snapshots, *, key="projection"):
    from core.models import DataSource
    from core.source_metric_projection import project_evidence

    selected = register_job(
        job_key=key,
        source=DataSource.objects.get(pk=source),
        purpose="metric",
        operation="collect_metrics",
        mode="historical",
        contract=contract,
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(selected.pk, "ready")
    return project_evidence(
        claim_job(selected.pk), [snapshot.pk for snapshot in snapshots]
    )


@pytest.mark.django_db(transaction=True)
def test_exact_release_capture_projects_into_reviewed_product_statistics():
    import httpx

    from core.models import DataSource, EventDossierClaim, Post
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report
    from core.source_metric_projection import (
        configure_source_statistics,
        evidence_rows,
        replay_saved_evidence,
    )

    contract, _, product, spec = configured("hf", product_type="llm-model", mapped=True)
    url = "https://huggingface.co/lab/Model"
    post = Post.objects.create(tweet_id="metric-release", text=f"Announcing Model {url}")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model", "source_url": url},
        release_identity="metric-release", observed_name="Model", source_url=url,
        brand=product.brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"id": "lab/Model", "author": "lab", "downloads": 17, "likes": 4}
    )))
    result = execute_hf_name_search(job.pk, client=client)
    captured = CollectionObservation.objects.get(run_id=result["run_id"])
    assert not captured.run.scopes.filter(scope_kind="numeric_projection").exists()
    first = project(contract, "hf", [captured], key="release-projection-one")
    assert first.status == "success"
    values = MetricValue.objects.filter(observation__run=first).select_related("source_metric", "observation")
    assert {v.source_metric.metric_key: int(v.integer_value) for v in values} == {"downloads": 17, "likes": 4}
    assert all(v.observation.observed_at == captured.observed_at for v in values)
    assert all(v.observation.mapping.subject.product_id == product.product_key for v in values)
    assert all(v.observation.inputs.filter(input_observation=captured).exists() for v in values)
    count = MetricValue.objects.count()
    replay = register_job(
        job_key="release-projection-replay", source=DataSource.objects.get(pk="hf"),
        purpose="metric", operation="collect_metrics", mode="historical", contract=contract,
        definition={
            "version": 1, "scope": {"origin_run_ids": [str(captured.run_id)]},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(replay.pk, "ready")
    second = replay_saved_evidence(replay.pk)
    assert second.status == "success" and second.selected_count == 1
    assert MetricValue.objects.count() == count
    # Without the reviewed repository mapping, the same counters stay at
    # native-resource level and cannot be attributed to the Product.
    native_spec = copy.deepcopy(spec)
    native_spec["mappings"] = [row for row in native_spec["mappings"]
                               if row["source_subject_kind"] == "account"]
    native = configure_source_statistics(native_spec)
    native_run = project(native, "hf", [captured], key="release-projection-native")
    native_values = MetricValue.objects.filter(observation__run=native_run)
    assert native_values.count() == 2
    assert all(v.observation.mapping_id is None for v in native_values)
    captured.projection_kind = "hf-release-search-v1"
    with pytest.raises(ValueError, match="evidence source mismatch"):
        list(evidence_rows(contract, "hf", captured))


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "mapped,paused,native_allowed,known_publisher",
    [(True, False, True, True), (False, False, True, True),
     (True, True, True, True), (False, False, False, True),
     (False, False, True, False)],
)
def test_exact_release_capture_queues_active_reviewed_publisher_for_projection(
    mapped, paused, native_allowed, known_publisher, monkeypatch
):
    import httpx

    from core import source_metric_projection
    from core.collection_scheduling import take_metric_authority
    from core.collection_state import BusyJob
    from core.models import DataSource, EventDossierClaim, Post
    from core.product_release_acquisition import (
        drain_due_hf_acquisitions,
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    contract, _, product, spec = configured("hf", product_type="llm-model", mapped=mapped)
    if not native_allowed:
        spec["source_configuration"]["hf"]["native_resources"] = False
        contract = source_metric_projection.configure_source_statistics(spec)
    authority = register_job(
        job_key="reviewed-hf-metric-authority", source=DataSource.objects.get(pk="hf"),
        purpose="metric", operation="collect_metrics", mode="recurring", contract=contract,
        definition={
            "version": 1, "scope": {},
            "schedule": {"kind": "interval", "driver": "shared", "seconds": 86400},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(authority.pk, "ready")
    take_metric_authority(authority.pk)
    if paused:
        set_job_state(authority.pk, "paused")
    repo = "lab/Model" if known_publisher else "unreviewed/Model"
    url = f"https://huggingface.co/{repo}"
    post = Post.objects.create(tweet_id="queued-metric-release", text=f"Announcing Model {url}")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model", "source_url": url},
        release_identity="queued-metric-release", observed_name="Model", source_url=url,
        brand=product.brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"id": repo, "author": repo.split("/")[0], "downloads": 17, "likes": 4}
    )))
    actual_drain = source_metric_projection.drain_pending_projections
    admitted = not paused and known_publisher and (mapped or native_allowed)
    if admitted:
        monkeypatch.setattr(source_metric_projection, "drain_pending_projections",
                            lambda *_args, **_kwargs: (_ for _ in ()).throw(BusyJob("busy")))
    result = drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
    assert result["provider_calls"] == 1
    run = CollectionRun.objects.get(pk=result["jobs"][0]["run_id"])
    if not admitted:
        assert not run.scopes.filter(scope_kind="numeric_projection").exists()
        assert actual_drain(job.pk)["written_values"] == 0
        assert not MetricValue.objects.exists()
        return
    pending = run.scopes.get(scope_kind="numeric_projection", projection_contract=contract)
    assert pending.outcome == "pending" and pending.child_scopes.count() == 1
    assert result["jobs"][0]["projection"]["outcome"] == "busy"
    assert not MetricValue.objects.exists()
    monkeypatch.setattr(source_metric_projection, "drain_pending_projections", actual_drain)
    recovered = drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
    assert recovered["provider_calls"] == 0
    drained = recovered["jobs"][0]["projection"]
    assert drained["written_values"] == 2 and drained["acknowledged"] == 1
    assert MetricValue.objects.count() == 2
    values = MetricValue.objects.select_related("observation")
    assert all(value.observation.observed_at == run.observations.get(
        projection_kind="hf-release-exact-v1").observed_at for value in values)
    assert all((value.observation.mapping_id is not None) == mapped for value in values)
    pending.refresh_from_db()
    assert pending.outcome == "complete"
    assert actual_drain(job.pk)["written_values"] == 0
    assert execute_hf_name_search(job.pk, client=client)["physical_requests"] == 0


@pytest.mark.django_db(transaction=True)
def test_saved_release_capture_waits_for_later_reviewed_authority_without_refetch():
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    from core.collection_scheduling import take_metric_authority
    from core.models import DataSource, EventDossierClaim, Post
    from core.product_release_acquisition import (
        drain_due_hf_acquisitions,
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report
    from core.source_metric_projection import recover_release_projection_followups

    contract, _, product, _ = configured("hf", product_type="llm-model", mapped=True)
    url = "https://huggingface.co/lab/Model"
    post = Post.objects.create(tweet_id="release-later-contract", text=f"Announcing Model {url}")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model", "source_url": url},
        release_identity="release-later-contract", observed_name="Model", source_url=url,
        brand=product.brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = EventDossierClaim.objects.get(event_dossier_source__event_dossier=dossier,
                                           claim_kind_reference__code="release_report")
    job = queue_hf_name_search(claim.pk)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "lab/Model", "author": "lab", "downloads": 17, "likes": 4})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    capture = execute_hf_name_search(job.pk, client=client)
    observation = CollectionObservation.objects.get(run_id=capture["run_id"])
    marker = observation.run.scopes.get(scope_kind="release_metric_followup")
    assert marker.outcome == "pending" and not MetricValue.objects.exists()
    assert recover_release_projection_followups(observation_ids=[observation.pk])["waiting"] == 1
    assert recover_release_projection_followups(observation_ids=[observation.pk + 1])["selected"] == 0
    with pytest.raises(ValueError, match="observation IDs"):
        recover_release_projection_followups(observation_ids=[])
    marker.refresh_from_db()
    assert marker.retry_at > timezone.now()
    authority = register_job(
        job_key="reviewed-later-hf-authority", source=DataSource.objects.get(pk="hf"),
        purpose="metric", operation="collect_metrics", mode="recurring", contract=contract,
        definition={"version": 1, "scope": {},
                    "schedule": {"kind": "interval", "driver": "shared", "seconds": 86400},
                    "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100}},
    )
    set_job_state(authority.pk, "ready")
    take_metric_authority(authority.pk)
    marker.retry_at = timezone.now() - timedelta(seconds=1)
    marker.save(update_fields=["retry_at"])
    assert recover_release_projection_followups()["queued"] == 1
    marker.refresh_from_db()
    assert marker.outcome == "complete"
    recovered = drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
    assert recovered["provider_calls"] == 0 and len(calls) == 1
    values = MetricValue.objects.select_related("observation")
    assert {int(value.integer_value) for value in values} == {17, 4}
    assert all(value.observation.observed_at == observation.observed_at for value in values)
    assert all(value.observation.mapping.subject.product_id == product.product_key for value in values)
    assert recover_release_projection_followups()["queued"] == 0
    assert drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])["provider_calls"] == 0
    assert MetricValue.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_waiting_release_followup_respects_exclusion_and_later_correction():
    import httpx

    from core.models import EventDossierClaim, Post
    from core.product_release_acquisition import (
        execute_hf_name_search,
        integrate_acquisition_run,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report
    from core.product_release_pipeline import record_intake_decision
    from core.source_metric_projection import (
        recover_release_projection_followups,
        retain_release_projection_followup,
    )

    _, _, product, _ = configured("hf", product_type="llm-model", mapped=True)
    url = "https://huggingface.co/lab/Model"
    post = Post.objects.create(tweet_id="release-reconsider", text=f"Announcing Model {url}")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model", "source_url": url},
        release_identity="release-reconsider", observed_name="Model", source_url=url,
        brand=product.brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = EventDossierClaim.objects.get(event_dossier_source__event_dossier=dossier,
                                           claim_kind_reference__code="release_report")
    job = queue_hf_name_search(claim.pk)
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"id": "lab/Model", "author": "lab", "downloads": 17}
    )))
    capture = execute_hf_name_search(job.pk, client=client)
    marker = CollectionRun.objects.get(pk=capture["run_id"]).scopes.get(scope_kind="release_metric_followup")
    marker.scope_key = "incorrect"
    marker.save(update_fields=["scope_key"])
    assert recover_release_projection_followups()["failed"] == 1
    marker.refresh_from_db()
    assert marker.outcome == "failed" and marker.error_code == "invalid_release_followup"
    marker.scope_key = str(marker.resource_observation_id)
    marker.save(update_fields=["scope_key"])
    with transaction.atomic():
        retain_release_projection_followup(marker.resource_observation)
    marker.refresh_from_db()
    assert marker.outcome == "pending"
    record_intake_decision(dossier.pk, claim_id=claim.pk, outcome="scam", actor="test", reason="evidence")
    assert recover_release_projection_followups()["excluded"] == 1
    marker.refresh_from_db()
    assert marker.outcome == "excluded" and not MetricValue.objects.exists()
    record_intake_decision(dossier.pk, claim_id=claim.pk, outcome="pending", actor="test", reason="correction")
    assert integrate_acquisition_run(capture["run_id"])["status"] == "complete"
    marker.refresh_from_db()
    assert marker.outcome == "pending" and marker.retry_at is None


@pytest.mark.django_db(transaction=True)
def test_native_release_measurement_waits_for_later_dedicated_product_mapping():
    import httpx

    from core.collection_scheduling import take_metric_authority
    from core.models import DataSource, EventDossierClaim, Post
    from core.product_release_acquisition import (
        drain_due_hf_acquisitions,
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report
    from core.source_metric_projection import (
        configure_source_statistics,
        recover_release_projection_followups,
    )

    dedicated, _, product, spec = configured("hf", product_type="llm-model", mapped=True)
    native_spec = copy.deepcopy(spec)
    native_spec["mappings"] = [m for m in native_spec["mappings"] if m["source_subject_kind"] == "account"]
    native = configure_source_statistics(native_spec)

    def authorize(contract, suffix):
        job = register_job(
            job_key=f"reviewed-release-authority-{suffix}", source=DataSource.objects.get(pk="hf"),
            purpose="metric", operation="collect_metrics", mode="recurring", contract=contract,
            definition={"version": 1, "scope": {},
                        "schedule": {"kind": "interval", "driver": "shared", "seconds": 86400},
                        "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100}},
        )
        set_job_state(job.pk, "ready")
        take_metric_authority(job.pk)

    authorize(native, "native")
    url = "https://huggingface.co/lab/Model"
    post = Post.objects.create(tweet_id="release-later-mapping", text=f"Announcing Model {url}")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model", "source_url": url},
        release_identity="release-later-mapping", observed_name="Model", source_url=url,
        brand=product.brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = EventDossierClaim.objects.get(event_dossier_source__event_dossier=dossier,
                                           claim_kind_reference__code="release_report")
    job = queue_hf_name_search(claim.pk)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "lab/Model", "author": "lab", "downloads": 17, "likes": 4})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    capture = execute_hf_name_search(job.pk, client=client)
    observation = CollectionObservation.objects.get(run_id=capture["run_id"])
    marker = observation.run.scopes.get(scope_kind="release_metric_followup")
    assert drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])["provider_calls"] == 0
    assert MetricValue.objects.filter(observation__mapping__isnull=True).count() == 2
    assert recover_release_projection_followups()["waiting"] == 1
    marker.refresh_from_db()
    assert marker.outcome == "pending" and marker.error_code == "awaiting_product_mapping"
    authorize(dedicated, "dedicated")
    marker.retry_at = timezone.now() - timedelta(seconds=1)
    marker.save(update_fields=["retry_at"])
    assert recover_release_projection_followups()["queued"] == 1
    marker.refresh_from_db()
    assert marker.outcome == "complete"
    assert drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])["provider_calls"] == 0
    mapped = MetricValue.objects.filter(observation__mapping__subject__product=product)
    assert mapped.count() == 2 and all(row.observation.observed_at == observation.observed_at for row in mapped)
    assert len(calls) == 1 and MetricValue.objects.count() == 4


@pytest.mark.django_db(transaction=True)
def test_github_replay_selects_archived_capture_after_old_columns_clear():
    from core.collection_resources import project_observation_facts
    from core.models import DataSource
    from core.source_metric_projection import replay_saved_evidence
    from tests.test_hf_catalog_retirement import denied_retirement_columns

    contract, raw, _, _ = configured("github")
    captured = evidence("github", raw)
    project_observation_facts(captured)
    assert captured.legacy_archive_id is not None
    job = register_job(
        job_key="archived-github-replay",
        source=DataSource.objects.get(pk="github"),
        purpose="metric", operation="collect_metrics", mode="historical",
        contract=contract,
        definition={
            "version": 1,
            "scope": {"origin_run_ids": [str(captured.run_id)]},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(job.pk, "ready")
    with denied_retirement_columns():
        run = replay_saved_evidence(job.pk)
        assert run.status == "success" and run.selected_count == 1
        assert MetricValue.objects.filter(observation__run=run).count() == 3


def test_hf_replay_skips_archived_evidence_without_selected_numbers():
    from core.models import DataSource
    from core.source_metric_projection import replay_saved_evidence

    contract, raw, _, _ = configured("hf")
    skipped = evidence("hf", raw)
    replace_evidence_document(skipped, source_metadata={"numeric_fields": []})
    selected = evidence("hf", raw, observed_at=CAPTURED + timedelta(seconds=1))
    job = register_job(
        job_key="archived-hf-replay",
        source=DataSource.objects.get(pk="hf"),
        purpose="metric", operation="collect_metrics", mode="historical",
        contract=contract,
        definition={
            "version": 1,
            "scope": {"origin_run_ids": [str(skipped.run_id), str(selected.run_id)]},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(job.pk, "ready")
    run = replay_saved_evidence(job.pk)
    assert run.status == "success" and run.selected_count == 1
    assert MetricValue.objects.filter(observation__run=run).count() == 2


@pytest.mark.parametrize("source,count", [("hf", 2), ("github", 3)])
def test_saved_native_counters_write_and_cross_job_replay_reuses_original_clock(
    source, count, monkeypatch
):
    monkeypatch.setattr(
        "httpx.Client.send", lambda *a, **kw: pytest.fail("HTTP forbidden")
    )
    contract, raw, product, _ = configured(source)
    snapshot = evidence(source, raw)
    original = copy.deepcopy(
        CollectionObservation.objects.filter(pk=snapshot.pk).values().get()
    )
    first = project(contract, source, [snapshot])
    assert (
        first.status == "success" and first.selected_count == first.success_count == 1
    )
    assert MetricValue.objects.count() == count
    observation = CollectionObservation.objects.exclude(pk=snapshot.pk).get()
    assert observation.mapping_id is None and observation.product_id is None
    assert observation.observed_at == CAPTURED
    for value in observation.values.all():
        if value.source_metric.measurement_kind == "state":
            assert value.as_of_at == CAPTURED
            assert value.window_range is None
        else:
            assert value.window_end_at == CAPTURED
            assert value.window_start_at == CAPTURED - timedelta(days=30)
        assert value.temporal_status == "exact"
    assert all(value.reported_time_policy == "reported-time-v1" for value in observation.values.all())
    assert any(v.integer_value == 0 for v in observation.values.all())
    # Numeric identity and timing are typed; its source document has no live ORM fields.
    assert not {"source_metadata", "dimensions"} & {
        field.name for field in CollectionObservation._meta.fields
    }
    second = project(contract, source, [snapshot], key="second")
    assert second.status == "success" and MetricValue.objects.count() == count
    assert run_report_document(second)["projection"]["reused_observation_ids"] == [observation.pk]
    observation.refresh_from_db()
    assert observation.run_id == first.pk
    assert (
        CollectionObservation.objects.filter(pk=snapshot.pk).values().get() == original
    )
    product.refresh_from_db()
    assert product.product_type_code is None


def test_replay_refuses_typed_retrieval_clock_drift_after_document_retirement():
    contract, raw, _, _ = configured()
    snapshot = evidence("hf", raw)
    first = project(contract, "hf", [snapshot])
    numeric = first.observations.get()
    CollectionObservation.objects.filter(pk=numeric.pk).update(
        original_retrieved_at=CAPTURED + timedelta(days=1),
    )
    with pytest.raises(ValueError, match="immutable snapshot clock conflict"):
        project(contract, "hf", [snapshot], key="drifted-typed-clock")


def test_bad_optional_fields_do_not_drop_other_numbers_and_new_capture_is_distinct():
    contract, raw, _, _ = configured()
    raw.update(likes="invalid", downloadsAllTime=None)
    first = project(contract, "hf", [evidence("hf", raw)])
    assert first.status == "success"
    assert MetricValue.objects.get().integer_value == 0
    assert run_report_document(first)["projection"]["rejections"]
    newer = evidence("hf", raw, observed_at=CAPTURED + timedelta(days=1))
    project(contract, "hf", [newer], key="new-capture")
    assert MetricValue.objects.count() == 2


def test_projection_links_saved_input_and_records_absent_and_invalid_selected_metrics():
    from core.models import CollectionMetricGap, CollectionObservationInput

    contract, raw, _, _ = configured()
    raw["likes"] = "invalid"
    source = evidence("hf", raw)
    run = project(contract, "hf", [source])
    numeric = run.observations.get()
    assert CollectionObservationInput.objects.get(observation=numeric).input_observation_id == source.pk
    assert numeric.projection_kind == "source-statistics-v1"
    assert numeric.definition_sha256
    gaps = {g.source_metric.metric_key: g for g in CollectionMetricGap.objects.filter(observation=numeric).select_related("source_metric")}
    assert set(gaps) == {"likes", "downloads_all_time"}
    assert gaps["likes"].reason_code == "invalid_metric_value"
    assert gaps["downloads_all_time"].reason_code == "selected_field_not_returned"
    assert not any(g.source_metric.metric_key == "followers" for g in gaps.values())
    assert numeric.values.get().integer_value == 0
    project(contract, "hf", [source], key="replay-gaps")
    assert CollectionMetricGap.objects.count() == 2
    assert CollectionObservationInput.objects.count() == 1


def test_archived_hf_field_selection_prevents_unselected_metric_gaps():
    from core.models import CollectionMetricGap

    contract, raw, _, _ = configured()
    raw["likes"] = "invalid"
    source = evidence("hf", raw)
    replace_evidence_document(source, source_metadata={"numeric_fields": ["downloads", "likes"]})
    run = project(contract, "hf", [source])
    numeric = run.observations.get()
    assert set(CollectionMetricGap.objects.filter(
        observation=numeric,
    ).values_list("source_metric__metric_key", flat=True)) == {"likes"}


def test_other_model_admission_is_separate_from_text_benchmark_policy():
    from core.benchmark_metric_identity import configure_collection

    contract, raw, product, spec = configured(
        product_type="other-ai-model", mapped=True
    )
    run = project(contract, "hf", [evidence("hf", raw)])
    numeric = run.observations.get()
    assert numeric.mapping.subject.product_id == product.product_key
    assert numeric.product_id == product.pk
    spec["mappings"] = spec["mappings"][1:]
    with pytest.raises(ValueError, match="llm-model"):
        configure_collection(spec)


def test_family_repo_stays_native_only_instead_of_copying_models():
    from core.source_metric_projection import configure_source_statistics

    contract, raw, _, spec = configured("github", product_type="llm-model", mapped=True)
    spec["mappings"][1]["identifier_metadata"]["role"] = "family_repository"
    contract = configure_source_statistics(spec)
    run = project(contract, "github", [evidence("github", raw)])
    assert run.observations.get().mapping_id is None
    assert MetricValue.objects.count() == 3
    assert run_report_document(run)["projection"]["mapped_resources"] == 0


def test_unreviewed_owner_cannot_be_admitted():
    contract, raw, _, _ = configured("github")
    raw["owner"]["id"] = 999
    run = project(contract, "github", [evidence("github", raw)])
    assert run.status == "partial"
    assert run_report_document(run)["projection"]["rejections"][0]["reason"]
    assert not MetricValue.objects.exists()


def test_projection_constraint_is_cross_run_and_only_for_selected_marker():
    contract, raw, _, _ = configured()
    snapshot = evidence("hf", raw)
    first = project(contract, "hf", [snapshot])
    numeric = first.observations.get()
    fields = {
        "run": first,
        "source_identifier": "lab/Model",
        "source_subject_kind": "repository",
        "observation_key": numeric.observation_key,
    }
    other = CollectionRun.objects.create(
        job=evidence_job(source_id="hf", purpose="metric", contract_id=contract.pk),
        ingestion_key="f" * 64,
        lease_expires_at=timezone.now() + timedelta(seconds=60),
        lease_token=uuid4(),
    )
    # The replacement invariant must also protect writers that no longer
    # duplicate the projection kind in legacy JSON.
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionObservation.objects.create(
            **{**fields, "run": other},
            projection_kind="source-statistics-v1",
        )
    CollectionObservation.objects.create(**{**fields, "run": other})


def test_numeric_failure_rolls_back_observations_and_checkpoint(monkeypatch):
    contract, raw, _, _ = configured()
    snapshot = evidence("hf", raw)
    monkeypatch.setattr(
        "core.benchmark_metric_store.MetricValue.objects.bulk_create",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("injected")),
    )
    with pytest.raises(RuntimeError, match="injected"):
        project(contract, "hf", [snapshot])
    assert CollectionObservation.objects.count() == 1
    assert not MetricValue.objects.exists()
    assert not CollectionRun.objects.get(job__purpose="metric").scopes.exists()


def test_replay_command_default_hook_is_bounded_resumable_and_has_no_http(monkeypatch):
    import json

    from core.data_source_backfill import register_campaign

    monkeypatch.setattr(
        "httpx.Client.send", lambda *a, **kw: pytest.fail("HTTP forbidden")
    )
    contract, raw, _, _ = configured()
    first = evidence("hf", raw)
    second = evidence("hf", raw, observed_at=CAPTURED + timedelta(hours=1))
    spec = {
        "job_key": "replay-cli",
        "source": "hf",
        "purpose": "metric",
        "operation": "collect_metrics",
        "contract": str(contract.pk),
        "definition": {
            "version": 1,
            "scope": {"origin_run_ids": [str(first.run_id), str(second.run_id)]},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 1},
            "campaign": {
                "kind": "backfiller-data-source-v1",
                "key": "replay",
                "cohort_hash": "a" * 64,
                "role": "projection",
                "phase": "replay",
                "contract_partition": str(contract.pk),
                "max_invocations": 3,
                "max_requests": 3,
            },
        },
    }
    selected = register_campaign([spec])[0]
    for expected in ("partial", "success"):
        out = StringIO()
        call_command(
            "backfiller_data_source",
            operation="replay",
            job=str(selected.pk),
            apply=True,
            stdout=out,
        )
        assert (
            json.loads(out.getvalue())["cells"][0]["last_attempt"]["status"] == expected
        )
    assert MetricValue.objects.count() == 4
    selected.refresh_from_db()
    assert selected.state == "completed"
    assert run_report_document(selected.last_success)["physical_accounting_complete"] is True


def test_unknown_flow_can_be_absent_while_likes_survive_and_optional_versions_are_pinned():
    contract, raw, _, _ = configured()
    raw.pop("downloads")
    run = project(contract, "hf", [evidence("hf", raw)])
    value = MetricValue.objects.get()
    assert run.status == "success" and value.source_metric.metric_key == "likes"
    pins = {
        d["metric_key"]: d for d in contract.source_configuration["hf"]["definitions"]
    }
    assert pins["downloads"]["version"] == 2 and pins["downloads"]["required"] is False
    from core.models import SourceMetric

    assert (
        SourceMetric.objects.get(
            source_id="hf", metric_key="downloads", version=1
        ).required
        is True
    )


def test_asset_dimensions_sizes_and_counter_do_not_become_repo_totals():
    from core.collection_reports import resource_statistics
    from core.collection_resources import snapshot_resource
    from core.models import CollectionObservationInput
    from core.source_metric_projection import configure_source_statistics

    contract, raw, _, spec = configured("github")
    spec["source_configuration"]["github"]["metrics"] += [
        "repository_size_kb",
        "asset_size_bytes",
    ]
    contract = configure_source_statistics(spec)
    raw["size"] = 10
    repo = evidence("github", raw)
    release = CollectionObservation.objects.create(
        run=repo.run, source_identifier="123", source_subject_kind="repository",
        observation_key="b" * 64, observed_at=CAPTURED,
        legacy_archive=retained_document({"id": 8}, dimensions={"kind": "releases"}, metadata={"owner_id": 42}),
        observation_kind="releases",
    )
    asset = CollectionObservation.objects.create(
        run=repo.run,
        source_identifier="123",
        source_subject_kind="repository",
        observation_key="a" * 64,
        observed_at=CAPTURED,
        legacy_archive=retained_document(
            {"id": 7, "size": 1024, "download_count": 9},
            dimensions={"kind": "release_asset", "release_id": 8, "asset_id": 7},
            metadata={"owner_id": 42},
        ),
    )
    CollectionObservationInput.objects.create(
        observation=asset, input_observation=release,
        input_role="release_asset_parent", row_locator="8",
        input_sha256=release.observation_key,
    )
    snapshot_resource(release)
    snapshot_resource(asset)
    run = project(contract, "github", [repo, asset])
    values = {
        v.source_metric.metric_key: v
        for v in MetricValue.objects.select_related("source_metric", "observation")
    }
    assert run.selected_count == run.success_count == 2
    assert values["repository_size_kb"].integer_value == 10
    assert values["repository_size_kb"].source_metric.unit_reference_id == "kilobytes"
    assert values["asset_size_bytes"].integer_value == 1024
    assert values["asset_size_bytes"].source_metric.unit_reference_id == "bytes"
    assert github_asset_coordinates([values["asset_downloads"].observation_id])[values["asset_downloads"].observation_id] == {
        "release_id": 8,
        "asset_id": 7,
    }
    assert observation_dimensions(values["stars"].observation) == {}
    replay = project(contract, "github", [repo, asset], key="typed-asset-replay")
    assert run_report_document(replay)["projection"]["reused_observation_ids"]
    report = resource_statistics(
        contract_id=contract.pk, source="github", identifier="123",
    )
    assert {
        row["metric"]: row["dimensions"] for row in report["values"]
        if row["metric"] in {"asset_downloads", "asset_size_bytes"}
    } == {
        "asset_downloads": {"release_id": 8, "asset_id": 7},
        "asset_size_bytes": {"release_id": 8, "asset_id": 7},
    }
    CollectionObservationInput.objects.filter(
        observation=asset, input_role="release_asset_parent",
    ).delete()
    with pytest.raises(ValueError, match="GitHub asset coordinates are not retained"):
        resource_statistics(contract_id=contract.pk, source="github", identifier="123")


@pytest.mark.parametrize("publication_day", ["2026-10-01", None])
def test_published_revision_reuses_identity_and_conflicting_number_fails_visibly(
    publication_day,
):
    contract, raw, _, _ = configured()
    first = evidence("hf", raw)
    metadata = {
        "numeric_snapshot_identity": {"date": publication_day, "revision": "v1"},
        "metric_times": {
            "likes": {"temporal_status": "date_only", "as_of_date": "2026-10-01"}
        },
    }
    replace_evidence_document(first, source_metadata=metadata)
    run = project(contract, "hf", [first])
    second = evidence("hf", raw, observed_at=CAPTURED + timedelta(hours=1))
    replace_evidence_document(second, source_metadata=metadata)
    repeated = project(contract, "hf", [second], key="publication-again")
    assert MetricValue.objects.count() == 2
    assert run_report_document(repeated)["projection"]["reused_observation_ids"] == [
        run.observations.get().pk
    ]
    assert (
        MetricValue.objects.get(
            source_metric__metric_key="likes"
        ).as_of_date.isoformat()
        == "2026-10-01"
    )
    replace_evidence_document(second, listing={**raw, "likes": 100})
    with pytest.raises(ValueError, match="immutable numeric snapshot conflict"):
        project(contract, "hf", [second], key="conflict")
    assert MetricValue.objects.get(source_metric__metric_key="likes").integer_value == 4
    failed = CollectionRun.objects.get(job__job_key="conflict")
    assert failed.scopes.get(scope_kind="numeric_projection").outcome == "failed"
    assert not failed.scopes.filter(scope_kind__in=["numeric_projection_result", "numeric_projection_output"]).exists()


def test_pending_projection_reference_is_atomic_with_evidence_and_pause_fences_writer():
    from core.collection_state import fenced_run
    from core.models import DataSource
    from core.source_metric_projection import enqueue_projection, project_evidence

    contract, raw, _, _ = configured()
    capture = register_job(
        job_key="capture",
        source=DataSource.objects.get(pk="hf"),
        purpose="catalog",
        operation="hf_catalog",
        mode="manual",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "bytes": 100000, "seconds": 60, "items": 100},
        },
    )
    set_job_state(capture.pk, "ready")
    claim = claim_job(capture.pk)

    def commit_capture(*, fail=False):
        with fenced_run(claim) as (_, run):
            snapshot = CollectionObservation.objects.create(
                run=run, source_identifier="lab/Model", source_subject_kind="repository",
                legacy_archive=retained_document(raw), observation_key="b" * 64,
            )
            enqueue_projection(claim, contract=contract, evidence_ids=[snapshot.pk])
            if fail:
                raise RuntimeError("after-enqueue")

    with pytest.raises(RuntimeError, match="after-enqueue"):
        commit_capture(fail=True)
    assert not CollectionObservation.objects.exists()
    assert not CollectionRun.objects.get(pk=claim.run_id).scopes.exists()
    commit_capture()
    pending = CollectionRun.objects.get(pk=claim.run_id).scopes.get(
        scope_kind="numeric_projection"
    )
    assert pending.projection_contract_id == contract.pk
    assert historical_projection_contract(pending, {
        "contract_id": str(contract.pk), "contract_hash": contract.contract_hash,
    }) == contract.pk
    snapshot = CollectionObservation.objects.get()
    item = pending.child_scopes.get(scope_kind="numeric_projection_item")
    assert item.resource_observation_id == snapshot.pk
    assert item.projection_contract_id == contract.pk
    assert item.outcome == "pending" and not item.enumeration_complete
    selected = register_job(
        job_key="paused-projection",
        source=DataSource.objects.get(pk="hf"),
        purpose="metric",
        operation="collect_metrics",
        mode="historical",
        contract=contract,
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(selected.pk, "ready")
    metric_claim = claim_job(selected.pk)
    set_job_state(selected.pk, "paused")
    with pytest.raises(StaleClaim):
        project_evidence(metric_claim, [snapshot.pk])
    assert not MetricValue.objects.exists()


def test_historical_metric_projection_scope_uses_owning_job_contract():
    contract, raw, _, _ = configured()
    snapshot = evidence("hf", raw)
    run = project(contract, "hf", [snapshot], key="historical-metric-pin")
    scope = run.scopes.get(scope_kind="numeric_projection")
    assert scope.projection_contract_id == contract.pk
    assert historical_projection_contract(scope, {"contract_hash": contract.contract_hash}) == contract.pk


@pytest.mark.parametrize("historical", [False, True], ids=["typed-queue", "archived-queue"])
def test_historical_projection_queue_adopts_exact_pending_inputs_once(historical, monkeypatch):
    from core.collection_capture import archive_legacy
    from core.models import CollectionScopeRun
    from core.source_metric_projection import drain_pending_projections

    contract, raw, _, _ = configured()
    captured = projection_queue_capture(contract, raw)
    queue = CollectionScopeRun.objects.create(
        run=captured.run, scope_kind="numeric_projection", scope_key=str(contract.pk),
        projection_contract=contract, phase=None if historical else "projection_queue",
        legacy_archive=archive_legacy({
            "ownership": {"contract_id": str(contract.pk), "contract_hash": contract.contract_hash},
            "cursor_history": [], "envelopes": [{"observation_id": captured.pk}],
        }) if historical else None,
    )
    if not historical:
        CollectionScopeRun.objects.create(
            run=captured.run, scope_kind="numeric_projection_item",
            scope_key=f"{contract.pk}:{captured.pk}", projection_contract=contract,
            parent_scope=queue, resource_observation=captured,
        )
    result = drain_pending_projections(captured.run.job_id)
    assert result["acknowledged"] == 1 and result["written_values"] == 2
    assert result["pending_resources"] == 0
    queue.refresh_from_db()
    child = queue.child_scopes.get(scope_kind="numeric_projection_item")
    assert child.resource_observation_id == captured.pk
    assert child.projection_contract_id == contract.pk
    assert child.outcome == "complete" and child.enumeration_complete
    # The untouched historical document is evidence, not the current queue.
    monkeypatch.setattr(
        "core.collection_capture.scope_object_documents",
        lambda *a, **kw: pytest.fail("adopted queue read old pending references"),
    )
    assert drain_pending_projections(captured.run.job_id)["acknowledged"] == 0
    assert MetricValue.objects.count() == 2


def test_projection_queue_refuses_foreign_capture_job_before_writing_children():
    from core.models import CollectionScopeRun
    from core.source_metric_projection import drain_pending_projections

    contract, raw, _, _ = configured()
    captured = projection_queue_capture(contract, raw)
    foreign = evidence("github", {"id": 123})
    queue = CollectionScopeRun.objects.create(
        run=captured.run, scope_kind="numeric_projection", scope_key=str(contract.pk),
        projection_contract=contract,
        legacy_archive=archive_legacy({"ownership": {}, "cursor_history": [],
                                       "envelopes": [{"observation_id": foreign.pk}]}),
    )
    with pytest.raises(ValueError, match="outside capture job"):
        drain_pending_projections(captured.run.job_id)
    queue.refresh_from_db()
    assert queue.phase is None
    assert not queue.child_scopes.exists()
    assert not MetricValue.objects.exists()


def projection_queue_capture(contract, raw):
    job = register_job(
        job_key="queued-capture", source=contract.mappings.first().source,
        purpose="catalog", operation="hf_catalog", mode="manual",
        definition={
            "version": 1, "scope": {},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    run = CollectionRun.objects.create(
        job=job, ingestion_key=digest(["queued-capture"]), status="success",
        completed_at=timezone.now(),
    )
    return CollectionObservation.objects.create(
        run=run, source_subject_kind="repository", source_identifier=raw["id"],
        legacy_archive=retained_document(raw), observed_at=CAPTURED, observation_key=digest(["queued-evidence"]),
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_different_jobs_replay_one_snapshot_without_reparenting():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    from core.models import DataSource
    from core.source_metric_projection import project_evidence

    contract, raw, _, _ = configured()
    snapshot = evidence("hf", raw)
    claims = []
    for key in ("parallel-a", "parallel-b"):
        selected = register_job(
            job_key=key,
            source=DataSource.objects.get(pk="hf"),
            purpose="metric",
            operation="collect_metrics",
            mode="historical",
            contract=contract,
            definition={
                "version": 1,
                "scope": {},
                "schedule": {"kind": "manual", "driver": "manual"},
                "budgets": {
                    "requests": 1,
                    "seconds": 60,
                    "bytes": 100000,
                    "items": 100,
                },
            },
        )
        set_job_state(selected.pk, "ready")
        claims.append(claim_job(selected.pk))

    def execute(claim):
        close_old_connections()
        try:
            return project_evidence(claim, [snapshot.pk])
        except ValueError as exc:
            assert str(exc) == "metric collection is already running"
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, claims))
    for claim, result in zip(claims, results):
        if result is None:
            project_evidence(claim, [snapshot.pk])
    assert MetricValue.objects.count() == 2
    assert CollectionObservation.objects.count() == 2
    assert (
        CollectionRun.objects.filter(job__purpose="metric", status="success").count()
        == 2
    )
    assert (
        sum(
            run_report_document(r)["projection"]["written_values"]
            for r in CollectionRun.objects.filter(job__purpose="metric")
        )
        == 2
    )


def test_campaign_over_1000_models_partitions_and_routes_each_native_grain_once():
    from core.models import Product
    from core.source_metric_projection import configure_statistics_partitions

    _contract, _, product, spec = configured(product_type="llm-model", mapped=True)
    products = Product.objects.bulk_create(
        [
            Product(
                repo_id=f"lab/Model-{n}",
                publisher_account=product.publisher_account,
                brand=product.brand,
                **product_type_fields(Product, "llm-model"),
            )
            for n in range(2100)
        ]
    )
    subjects = [{"kind": "account", "key": str(product.publisher_account_id)}] + [
        {"kind": "product", "key": str(item.product_key)} for item in products
    ]
    taxonomy = configure_taxonomy({"reviewed_by": "fixture", "subjects": subjects})
    spec["taxonomy_version"] = str(taxonomy.pk)
    template = spec["mappings"][1]
    spec["mappings"] = [spec["mappings"][0]] + [
        {
            **template,
            "external_identifier": item.repo_id,
            "subject_id": str(subject_id("product", item.product_key)),
        }
        for item in products
    ]
    parts = configure_statistics_partitions(spec)
    assert len(parts) == 3
    assert all(part.mappings.count() <= 1000 for part in parts)
    assert (
        sum(
            part.mappings.exclude(source_subject_kind="account").count()
            for part in parts
        )
        == 2100
    )
    assert [part.source_configuration["hf"]["native_resources"] for part in parts] == [
        True,
        False,
        False,
    ]
    selected = parts[2].mappings.exclude(source_subject_kind="account").first()
    assert (
        selected.normalized_identifier
        in parts[0].source_configuration["hf"]["native_exclusions"]
    )
    assert [part.pk for part in configure_statistics_partitions(spec)] == [
        part.pk for part in parts
    ]


def test_registry_preserves_existing_github_catalog_adapter_and_disabled_state():
    from core.benchmark_metric_identity import register_definitions
    from core.models import DataSource

    source = DataSource.objects.create(
        pk="github",
        name="GitHub",
        source_type="model_adoption",
        enabled=False,
        adapter_key="github-catalog-v1",
        metadata={"adapter_key": "github-catalog-v1", "custom": "preserved"},
    )
    before = copy.deepcopy(DataSource.objects.filter(pk=source.pk).values().get())
    register_definitions()
    assert DataSource.objects.filter(pk=source.pk).values().get() == before


@pytest.mark.parametrize("source", ["hf", "github"])
def test_supplied_account_followers_keep_native_account_grain(source):
    from core.source_metric_projection import configure_source_statistics

    contract, raw, _, spec = configured(source)
    if source == "github":
        spec["source_configuration"][source]["metrics"].append("followers")
        from core.benchmark_metric_identity import register_definitions

        register_definitions()
        contract = configure_source_statistics(spec)
    publisher = contract.mappings.get(source_subject_kind="account")
    snapshot = evidence(source, raw)
    snapshot.source_identifier = publisher.normalized_identifier
    snapshot.source_subject_kind = "account"
    snapshot.save(update_fields=["source_identifier", "source_subject_kind"])
    replace_evidence_document(
        snapshot, listing={"id": 42, "followers": 10} if source == "github" else {"name": "lab", "numFollowers": 10},
        dimensions={"kind": "publisher"},
    )
    run = project(contract, source, [snapshot])
    value = MetricValue.objects.get()
    assert run.status == "success"
    assert value.source_metric.metric_key == "followers" and value.integer_value == 10
    assert value.observation.source_subject_kind == "account"
    assert value.observation.mapping_id == publisher.pk and value.observation.product_id is None
    assert run_report_document(run)["projection"]["mapped_resources"] == 0


def test_replay_refuses_publisher_ownership_drift_since_contract_review():
    from core.models import Company, CompanyAccount

    contract, raw, product, _ = configured()
    replacement = Company.objects.create(nickname="replacement-owner")
    CompanyAccount.objects.filter(account_id=product.publisher_account_id).update(
        company=replacement
    )
    run = project(contract, "hf", [evidence("hf", raw)])
    assert run.status == "partial" and not MetricValue.objects.exists()
    assert (
        "ownership pin changed" in read_document(run.scopes.get(scope_kind="numeric_projection_result").legacy_archive)["rejections"][0]["reason"]
    )


def test_new_optional_number_attaches_to_existing_publication_with_provenance():
    contract, raw, _, _ = configured()
    first = evidence("hf", {"id": raw["id"], "downloads": 0})
    metadata = {"numeric_snapshot_identity": {"period": "2026-10-01", "revision": "v1"}}
    replace_evidence_document(first, source_metadata=metadata)
    initial = project(contract, "hf", [first])
    second = evidence("hf", raw, observed_at=CAPTURED + timedelta(hours=1))
    replace_evidence_document(second, source_metadata=metadata)
    additional = project(contract, "hf", [second], key="additional-counter")
    assert additional.status == "success"
    assert run_report_document(additional)["projection"]["written_values"] == 1
    assert run_report_document(additional)["projection"]["source_observation_ids"] == [second.pk]
    assert MetricValue.objects.count() == 2
    assert initial.observations.get().values.count() == 2
    numeric = initial.observations.get()
    assert set(numeric.inputs.values_list("input_observation_id", flat=True)) == {first.pk, second.pk}
    assert numeric.observed_at == CAPTURED
    assert not numeric.metric_gaps.filter(source_metric__metric_key="likes").exists()


def test_saved_projection_enforces_its_pinned_byte_budget():
    contract, raw, _, _ = configured()
    raw["large_source_description"] = "x" * 100001
    with pytest.raises(ValueError, match="projection byte budget"):
        project(contract, "hf", [evidence("hf", raw)])
    assert not MetricValue.objects.exists()


@pytest.mark.parametrize(
    "origin_case", ["native", "catalog", "conflict", "floor", "missing", "after"]
)
def test_reported_cumulative_origins_keep_original_capture_and_replay(origin_case):
    contract, raw, product, _ = configured()
    origin = datetime(2026, 10, 1, 13, 30, tzinfo=UTC)
    if origin_case in {"native", "conflict", "floor", "after"}:
        raw["createdAt"] = (
            datetime(2022, 1, 1, tzinfo=UTC)
            if origin_case == "floor"
            else CAPTURED + timedelta(days=2)
            if origin_case == "after"
            else origin
        ).isoformat()
    if origin_case in {"catalog", "conflict"}:
        product.created_at = (
            origin + timedelta(hours=1) if origin_case == "conflict" else origin
        )
        product.save(update_fields=["created_at"])
    raw["downloadsAllTime"] = 0
    snapshot = evidence("hf", raw)
    replace_evidence_document(snapshot, source_metadata={
        "archive_snapshot_date": "2026-10-01",
        "numeric_fields": ["downloads", "downloadsAllTime", "likes"],
    })
    first = project(contract, "hf", [snapshot])
    value = MetricValue.objects.get(source_metric__metric_key="downloads_all_time")
    assert value.integer_value == 0
    assert value.window_end_at == datetime(2026, 10, 2, tzinfo=UTC)
    assert value.period_label_date.isoformat() == "2026-10-01"
    assert value.temporal_status == "date_only"
    if origin_case in {"native", "catalog"}:
        assert value.window_start_at == origin
        assert value.window_range.lower == origin
    else:
        assert value.window_start_at is None
        assert value.window_start_unknown_reason
    assert value.observation.observed_at == CAPTURED
    assert project(contract, "hf", [snapshot], key="repeat-origin").status == "success"
    assert MetricValue.objects.count() == 3
    assert first.status == "success"


@pytest.mark.parametrize(
    "metric,field",
    [("downloads", "window_end_at"), ("downloads_all_time", "window_start_at")],
)
def test_reported_policy_preserves_a_retained_single_endpoint(metric, field):
    contract, raw, _, _ = configured()
    if metric == "downloads_all_time":
        raw["downloadsAllTime"] = 10
    known = CAPTURED - timedelta(days=10)
    snapshot = evidence("hf", raw)
    replace_evidence_document(snapshot, source_metadata={
        "metric_times": {
            metric: {"temporal_status": "unknown", field: known.isoformat()}
        }
    })
    assert project(contract, "hf", [snapshot]).status == "success"
    value = MetricValue.objects.get(source_metric__metric_key=metric)
    assert getattr(value, field) == known
    assert value.window_start_at is not None and value.window_end_at is not None
    assert value.window_range is not None
