"""PostgreSQL proof for native-grain projection through the shared numeric writer."""

import copy
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

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
        listing=raw,
        observed_at=observed_at,
        observation_key=digest(["evidence", str(run.pk)]),
        dimensions={"kind": "repository"} if source == "github" else {},
    )


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
    assert observation.source_metadata["native_only"] is True
    assert observation.observed_at == CAPTURED
    for value in observation.values.all():
        if value.source_metric.measurement_kind == "state":
            assert value.as_of_at == CAPTURED
            assert value.window_range is None
        else:
            assert value.window_end_at == CAPTURED
            assert value.window_start_at == CAPTURED - timedelta(days=30)
        assert value.temporal_status == "exact"
    assert observation.source_metadata["reported_time"]["policy"] == "reported-time-v1"
    assert all(value.reported_time_policy == "reported-time-v1" for value in observation.values.all())
    assert any(v.integer_value == 0 for v in observation.values.all())
    second = project(contract, source, [snapshot], key="second")
    assert second.status == "success" and MetricValue.objects.count() == count
    assert second.report["projection"]["reused_observation_ids"] == [observation.pk]
    observation.refresh_from_db()
    assert observation.run_id == first.pk
    assert (
        CollectionObservation.objects.filter(pk=snapshot.pk).values().get() == original
    )
    product.refresh_from_db()
    assert product.product_type_code is None


def test_bad_optional_fields_do_not_drop_other_numbers_and_new_capture_is_distinct():
    contract, raw, _, _ = configured()
    raw.update(likes="invalid", downloadsAllTime=None)
    first = project(contract, "hf", [evidence("hf", raw)])
    assert first.status == "success"
    assert MetricValue.objects.get().integer_value == 0
    assert first.report["projection"]["rejections"]
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
    assert run.report["projection"]["mapped_resources"] == 0


def test_unreviewed_owner_cannot_be_admitted():
    contract, raw, _, _ = configured("github")
    raw["owner"]["id"] = 999
    run = project(contract, "github", [evidence("github", raw)])
    assert run.status == "partial"
    assert run.report["projection"]["rejections"][0]["reason"]
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
    with pytest.raises(IntegrityError), transaction.atomic():
        CollectionObservation.objects.create(
            **{**fields, "run": other},
            source_metadata={"projection_kind": "source-statistics-v1"},
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
    assert selected.last_success.report["physical_accounting_complete"] is True


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
    from core.source_metric_projection import configure_source_statistics

    contract, raw, _, spec = configured("github")
    spec["source_configuration"]["github"]["metrics"] += [
        "repository_size_kb",
        "asset_size_bytes",
    ]
    contract = configure_source_statistics(spec)
    raw["size"] = 10
    repo = evidence("github", raw)
    asset = CollectionObservation.objects.create(
        run=repo.run,
        source_identifier="123",
        source_subject_kind="repository",
        observation_key="a" * 64,
        observed_at=CAPTURED,
        listing={"id": 7, "size": 1024, "download_count": 9},
        dimensions={"kind": "release_asset", "release_id": 8, "asset_id": 7},
        source_metadata={"owner_id": 42},
    )
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
    assert values["asset_downloads"].observation.dimensions == {
        "release_id": 8,
        "asset_id": 7,
    }
    assert values["stars"].observation.dimensions == {}


@pytest.mark.parametrize("publication_day", ["2026-10-01", None])
def test_published_revision_reuses_identity_and_conflicting_number_fails_visibly(
    publication_day,
):
    contract, raw, _, _ = configured()
    first = evidence("hf", raw)
    first.source_metadata = {
        "numeric_snapshot_identity": {"date": publication_day, "revision": "v1"},
        "metric_times": {
            "likes": {"temporal_status": "date_only", "as_of_date": "2026-10-01"}
        },
    }
    first.save()
    run = project(contract, "hf", [first])
    second = evidence("hf", raw, observed_at=CAPTURED + timedelta(hours=1))
    second.source_metadata = first.source_metadata
    second.save()
    repeated = project(contract, "hf", [second], key="publication-again")
    assert MetricValue.objects.count() == 2
    assert repeated.report["projection"]["reused_observation_ids"] == [
        run.observations.get().pk
    ]
    assert (
        MetricValue.objects.get(
            source_metric__metric_key="likes"
        ).as_of_date.isoformat()
        == "2026-10-01"
    )
    second.listing = {**raw, "likes": 100}
    second.save()
    with pytest.raises(ValueError, match="immutable numeric snapshot conflict"):
        project(contract, "hf", [second], key="conflict")
    assert MetricValue.objects.get(source_metric__metric_key="likes").integer_value == 4
    assert not CollectionRun.objects.get(job__job_key="conflict").scopes.exists()


def test_pending_projection_reference_is_atomic_with_evidence_and_pause_fences_writer():
    from core.collection_state import checkpoint_scope
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

    def write(run, scope):
        snapshot = CollectionObservation.objects.create(
            run=run,
            scope_run=scope,
            source_identifier="lab/Model",
            source_subject_kind="repository",
            listing=raw,
            observation_key="b" * 64,
        )
        enqueue_projection(claim, contract=contract, evidence_ids=[snapshot.pk])
        raise RuntimeError("after-enqueue")

    with pytest.raises(RuntimeError):
        checkpoint_scope(claim, scope_key="capture", ownership={}, write=write)
    assert not CollectionObservation.objects.exists()
    assert not CollectionRun.objects.get(pk=claim.run_id).scopes.exists()

    def complete(run, scope):
        snapshot = CollectionObservation.objects.create(
            run=run,
            scope_run=scope,
            source_identifier="lab/Model",
            source_subject_kind="repository",
            listing=raw,
            observation_key="b" * 64,
        )
        enqueue_projection(claim, contract=contract, evidence_ids=[snapshot.pk])

    checkpoint_scope(claim, scope_key="capture", ownership={}, write=complete)
    pending = CollectionRun.objects.get(pk=claim.run_id).scopes.get(
        scope_kind="numeric_projection"
    )
    snapshot = CollectionObservation.objects.get()
    assert pending.envelopes == [{"observation_id": snapshot.pk}]
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
            r.report["projection"]["written_values"]
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
    snapshot.listing = (
        {"id": 42, "followers": 10}
        if source == "github"
        else {"name": "lab", "numFollowers": 10}
    )
    snapshot.dimensions = {"kind": "publisher"}
    snapshot.save()
    run = project(contract, source, [snapshot])
    value = MetricValue.objects.get()
    assert run.status == "success"
    assert value.source_metric.metric_key == "followers" and value.integer_value == 10
    assert value.observation.source_subject_kind == "account"
    assert value.observation.source_metadata["native_only"] is True
    assert run.report["projection"]["mapped_resources"] == 0


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
        "ownership pin changed" in run.report["projection"]["rejections"][0]["reason"]
    )


def test_new_optional_number_attaches_to_existing_publication_with_provenance():
    contract, raw, _, _ = configured()
    first = evidence("hf", {"id": raw["id"], "downloads": 0})
    first.source_metadata = {
        "numeric_snapshot_identity": {"period": "2026-10-01", "revision": "v1"}
    }
    first.save()
    initial = project(contract, "hf", [first])
    second = evidence("hf", raw, observed_at=CAPTURED + timedelta(hours=1))
    second.source_metadata = first.source_metadata
    second.save()
    additional = project(contract, "hf", [second], key="additional-counter")
    assert additional.status == "success"
    assert additional.report["projection"]["written_values"] == 1
    assert additional.report["projection"]["source_observation_ids"] == [second.pk]
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
    snapshot.source_metadata = {
        "archive_snapshot_date": "2026-10-01",
        "numeric_fields": ["downloads", "downloadsAllTime", "likes"],
    }
    snapshot.save()
    first = project(contract, "hf", [snapshot])
    value = MetricValue.objects.get(source_metric__metric_key="downloads_all_time")
    assert value.integer_value == 0
    assert value.window_end_at == datetime(2026, 10, 2, tzinfo=UTC)
    assert value.period_label_date.isoformat() == "2026-10-01"
    assert value.temporal_status == "date_only"
    basis = value.observation.source_metadata["reported_time"]["metrics"][
        "downloads_all_time"
    ]
    if origin_case in {"native", "catalog"}:
        assert value.window_start_at == origin
        assert value.window_range.lower == origin
    else:
        assert value.window_start_at is None
        assert basis["unknowns"]["start"]
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
    snapshot.source_metadata = {
        "metric_times": {
            metric: {"temporal_status": "unknown", field: known.isoformat()}
        }
    }
    snapshot.save()
    assert project(contract, "hf", [snapshot]).status == "success"
    value = MetricValue.objects.get(source_metric__metric_key=metric)
    assert getattr(value, field) == known
    assert value.window_start_at is not None and value.window_end_at is not None
    assert value.window_range is not None
