"""Real database evidence drives previews and durable reviewed application."""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.collection_capture import archive_legacy
from core.collection_jobs import register_job
from core.measurement_taxonomy import digest
from core.models import (
    Brand,
    BrandCompany,
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    Company,
    DataSource,
    MeasurementSubject,
    Product,
    SourceSubjectMapping,
)
from tests.product_factory import product_type_fields
from tests.publisher_fixtures import hf_publisher

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def catalog_fixture(name="Model-7B-Instruct", source="arena", native=None):
    brand, _ = Brand.objects.get_or_create(nickname="fixture-brand")
    company, _ = Company.objects.get_or_create(nickname="fixture-company")
    BrandCompany.objects.get_or_create(brand=brand, company=company)
    publisher = hf_publisher(namespace="Fixture", company=company, confirmed=True)
    product = Product.objects.create(
        repo_id=f"Fixture/{name}",
        brand=brand,
        publisher_account=publisher.account,
        created_at=timezone.now(),
        **product_type_fields(Product, "model-llm"),
        private=False,
    )
    provider, _ = DataSource.objects.get_or_create(
        pk=source,
        defaults={
            "name": source,
            "source_type": "model_adoption",
            "enabled": True,
            "adapter_key": "test-fixture",
        },
    )
    job = register_job(
        job_key="fixture:" + str(product.pk),
        source=provider,
        purpose="catalog",
        operation="model_history",
        mode="historical",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {"requests": 1, "bytes": 100000, "seconds": 60, "items": 100},
        },
    )
    run = CollectionRun.objects.create(
        job=job,
        ingestion_key=digest(str(product.pk)),
        status="success",
        completed_at=timezone.now(),
    )
    native = native or name.lower()
    observation = CollectionObservation.objects.create(
        run=run,
        source_identifier=native,
        source_subject_kind="model",
        observation_key=digest([str(product.pk), native]),
        observation_kind="publication_row",
        legacy_archive=archive_legacy({
            "dimensions": {"kind": "publication_row"},
            "listing": {"rows": [{"model": native}]},
            "source_metadata": {},
        }),
    )
    return brand, product, observation


def preview(brand, **kwargs):
    from core.collection_matching import preview_matches

    return preview_matches(brand_ids=[brand.pk], sources=["arena"], **kwargs)


def test_preview_is_read_only_and_name_only_does_not_admit():
    brand, product, observation = catalog_fixture()
    before = (
        CollectionJob.objects.count(),
        CollectionRun.objects.count(),
        MeasurementSubject.objects.count(),
        SourceSubjectMapping.objects.count(),
    )
    report = preview(brand)
    candidate = report["products"][0]["candidates"][0]
    assert candidate["identifier"] == observation.source_identifier
    assert candidate["identifier_scope"] == "arena_model_name"
    assert candidate["db_presence"] == "present"
    assert candidate["evidence"]["observation_id"] == observation.pk
    assert candidate["confidence_pct"] == 90
    assert candidate["decision"] == "needs_review"
    assert report["products"][0]["product_key"] == str(product.product_key)
    assert before == (
        CollectionJob.objects.count(),
        CollectionRun.objects.count(),
        MeasurementSubject.objects.count(),
        SourceSubjectMapping.objects.count(),
    )


@pytest.mark.parametrize(
    "native",
    [
        "model-70b-instruct",
        "model-7b-base",
        "model-7b-instruct-fp8",
        "model-7b-instruct:free",
    ],
)
def test_variant_tokens_are_not_erased(native):
    brand, _, _ = catalog_fixture(native=native)
    assert preview(brand)["products"][0]["candidates"] == []


def test_null_brand_and_type_catalog_is_visible_through_confirmed_publisher():
    brand, product, _ = catalog_fixture()
    product.brand = product.product_type = None
    product.save()
    report = preview(brand)
    assert report["products"][0]["product_key"] == str(product.product_key)
    assert len(report["products"][0]["candidates"]) == 1


def test_product_without_provider_repository_can_be_previewed():
    brand, product, _ = catalog_fixture()
    product.display_name = "Model-7B-Instruct"
    product.repo_id = None
    product.save(update_fields=["display_name", "repo_id"])
    report = preview(brand)
    row = next(row for row in report["products"] if row["product_key"] == str(product.product_key))
    candidate = row["candidates"][0]
    assert row["hf_product"] is None
    assert candidate["decision"] == "needs_review"
    assert candidate["ownership"]["display_name"] == "Model-7B-Instruct"
    assert SourceSubjectMapping.objects.count() == 0
    assert apply_reviewed(report)["status"] == "success"
    assert SourceSubjectMapping.objects.get().subject.product_id == product.product_key


def test_named_product_without_publisher_evidence_stays_unmatched():
    brand, product, _ = catalog_fixture()
    product.display_name = "Model-7B-Instruct"
    product.repo_id = None
    product.publisher_account = None
    product.save(update_fields=["display_name", "repo_id", "publisher_account"])
    candidate = preview(brand)["products"][0]["candidates"][0]
    assert candidate["decision"] == "unmatched"
    assert candidate["reasons"] == ["publisher_ownership_unqualified"]
    assert not SourceSubjectMapping.objects.exists()


@pytest.mark.parametrize("source,scope,row_key", [
    ("arena", "arena_model_name", "model_name"),
    ("openrouter", "rankings_permaslug", "model_permaslug"),
])
def test_pending_target_preview_pins_one_saved_publication_row(source, scope, row_key, monkeypatch):
    from django.db import connection, transaction

    import core.collection_matching as matching
    from core.collection_matching import (
        execute_matches,
        pending_target_pin,
        preview_pending_target,
        register_pending_publication_targets,
    )
    from core.collection_reports import job_status

    _, product, old = catalog_fixture(source=source)
    observation = CollectionObservation.objects.create(
        run=old.run, source_identifier="aggregate", source_subject_kind="aggregate",
        observation_key=digest([source, "rows"]), observation_kind="publication_window",
        legacy_archive=archive_legacy({
            "dimensions": {}, "listing": {"rows": [{row_key: "another-model"}, {row_key: "model-7b-instruct"}]},
            "source_metadata": {},
        }),
    )
    pin = pending_target_pin(observation, scope, 1)
    budgets = {"requests": 1, "bytes": 10000, "seconds": 30, "items": 1}
    with pytest.raises(ValueError, match="byte or time budget"):
        register_pending_publication_targets(
            observation_id=observation.pk, row_indices=[1], budgets={**budgets, "bytes": 1},
        )
    with monkeypatch.context() as patcher:
        ticks = iter([0, 2])
        patcher.setattr(matching, "monotonic", lambda: next(ticks))
        with pytest.raises(ValueError, match="byte or time budget"):
            register_pending_publication_targets(
                observation_id=observation.pk, row_indices=[1], budgets={**budgets, "seconds": 1},
            )
    job = register_pending_publication_targets(observation_id=observation.pk, row_indices=[1], budgets=budgets)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '200ms'")
        assert register_pending_publication_targets(observation_id=observation.pk, row_indices=[1], budgets=budgets).pk == job.pk
        cursor.execute("SHOW lock_timeout")
        assert cursor.fetchone()[0] == "200ms"
    with pytest.raises(ValueError, match="distinct"):
        register_pending_publication_targets(observation_id=observation.pk, row_indices=[1, 1], budgets=budgets)
    with pytest.raises(ValueError, match="budget"):
        register_pending_publication_targets(observation_id=observation.pk, row_indices=[0, 1], budgets=budgets)
    with pytest.raises(ValueError, match="publication row"):
        register_pending_publication_targets(observation_id=observation.pk, row_indices=[99], budgets=budgets)
    with pytest.raises(ValueError, match="reviewed resolution"):
        execute_matches(job.pk)
    target = job.targets.get()
    assert target.selection_sha256 == pin
    assert job_status(job.pk)["matching"]["remaining"] == 1
    before = (target.subject_id, target.selection_sha256, target.source_row_index)
    report = preview_pending_target(target_id=target.pk, product_key=product.product_key)
    candidate = report["products"][0]["candidates"][0]
    assert candidate["identifier"] == "model-7b-instruct"
    assert candidate["publication_row_index"] == 1
    target.refresh_from_db()
    assert (target.subject_id, target.selection_sha256, target.source_row_index) == before
    assert not SourceSubjectMapping.objects.exists()
    assert pending_target_pin(observation, scope, 0) != pin
    unrelated = Product.objects.create(display_name="Unrelated model", brand=product.brand)
    with pytest.raises(ValueError, match="does not match Product name"):
        preview_pending_target(target_id=target.pk, product_key=unrelated.product_key)
    observation.observation_kind = "model_catalog"
    with pytest.raises(ValueError, match="publication row"):
        pending_target_pin(observation, scope, 1)
    observation.observation_kind = "publication_window"
    observation.source_subject_kind = "model"
    with pytest.raises(ValueError, match="publication row"):
        pending_target_pin(observation, scope, 1)
    observation.source_subject_kind = "aggregate"
    original_archive = observation.legacy_archive
    observation.legacy_archive = archive_legacy({
        "dimensions": {}, "listing": {"rows": [{row_key: "model-7b-instruct"}, {row_key: "another-model"}]},
        "source_metadata": {},
    })
    observation.save(update_fields=["legacy_archive"])
    with pytest.raises(ValueError, match="evidence changed"):
        preview_pending_target(target_id=target.pk, product_key=product.product_key)
    observation.legacy_archive = original_archive
    observation.save(update_fields=["legacy_archive"])
    assert apply_reviewed(report)["status"] == "success"
    mapping = SourceSubjectMapping.objects.get()
    assert mapping.subject.product_id == product.product_key
    decision = CollectionObservation.objects.get(observation_kind="product_match_decision")
    lineage = decision.inputs.get(input_role="match_candidate")
    assert lineage.input_observation_id == observation.pk
    assert lineage.row_locator == f"target:{target.pk};row:1"
    target.refresh_from_db()
    assert (target.subject_id, target.selection_sha256, target.source_row_index) == before
    assert apply_reviewed(report)["status"] == "success"
    assert SourceSubjectMapping.objects.count() == 1
    assert job_status(job.pk)["matching"]["remaining"] == 0
    both = register_pending_publication_targets(
        observation_id=observation.pk, row_indices=[0, 1], budgets={**budgets, "items": 2},
    )
    assert both.targets.count() == 2
    assert job_status(both.pk)["matching"]["remaining"] == 2


@pytest.mark.django_db(transaction=True)
def test_pending_registration_respects_lock_timeout():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic

    from django.db import OperationalError, close_old_connections, transaction

    from core.collection_matching import register_pending_publication_targets

    _, _, old = catalog_fixture(source="arena")
    observation = CollectionObservation.objects.create(
        run=old.run, source_identifier="aggregate", source_subject_kind="aggregate",
        observation_key=digest(["arena", "locked-rows"]), observation_kind="publication_window",
        legacy_archive=archive_legacy({"dimensions": {}, "listing": {"rows": [{"model_name": "model-7b-instruct"}]}, "source_metadata": {}}),
    )
    locked, release = Event(), Event()

    def hold_lock():
        close_old_connections()
        try:
            with transaction.atomic():
                CollectionObservation.objects.select_for_update().get(pk=observation.pk)
                locked.set()
                release.wait(5)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold_lock)
        try:
            assert locked.wait(3)
            start = monotonic()
            with pytest.raises(OperationalError):
                register_pending_publication_targets(
                    observation_id=observation.pk, row_indices=[0],
                    budgets={"requests": 1, "bytes": 10000, "seconds": 1, "items": 1},
                )
            assert monotonic() - start < 4
        finally:
            release.set()
            future.result(timeout=5)


def test_openrouter_catalog_does_not_prove_usage_scope():
    from core.collection_matching import preview_matches

    brand, _, observation = catalog_fixture(
        source="openrouter", native="fixture/model-7b-instruct"
    )
    observation.dimensions = {"kind": "model_catalog"}
    observation.observation_kind = "model_catalog"
    observation.listing = {
        "id": observation.source_identifier,
        "canonical_slug": "different-slug",
    }
    observation.save()
    result = preview_matches(brand_ids=[brand.pk], sources=["openrouter"])
    assert {c["identifier_scope"] for c in result["products"][0]["candidates"]} == {
        "catalog_id"
    }


def test_default_command_cannot_reach_writer(monkeypatch):
    import core.collection_matching as matching

    brand, _, _ = catalog_fixture()
    monkeypatch.setattr(
        matching, "apply_matches", lambda **_: pytest.fail("preview wrote")
    )
    output = StringIO()
    call_command(
        "match_collection_products", brand=[brand.pk], source=["arena"], stdout=output
    )
    assert json.loads(output.getvalue())["writes"] == 0


def apply_reviewed(report, **kwargs):
    from core.collection_matching import apply_matches

    return apply_matches(
        preview=report,
        input_sha256=report["input_sha256"],
        reviewed_by="allenwlee",
        review_basis="Owner confirmed exact candidates",
        reviewed_candidate_ids=[
            c["candidate_id"] for p in report["products"] for c in p["candidates"]
        ],
        **kwargs,
    )


def test_reviewed_apply_is_idempotent_and_durable_without_metric_writes():
    from core.collection_matching import apply_matches
    from core.collection_reports import job_status
    from core.models import CollectionScopeRun, MetricValue

    brand, product, _ = catalog_fixture()
    report = preview(brand)
    before = MetricValue.objects.count()
    result = apply_reviewed(report)
    assert result["status"] == "success"
    mapping = SourceSubjectMapping.objects.get()
    assert mapping.subject.product_id == product.product_key
    assert (
        mapping.identifier_scope_code == "arena_model_name" and mapping.purpose == "catalog"
    )
    assert mapping.reviewed_by == "allenwlee"
    assert (
        mapping.identifier_metadata["match_review"]["basis"]
        == "Owner confirmed exact candidates"
    )
    assert MetricValue.objects.count() == before
    assert (
        CollectionScopeRun.objects.get(scope_kind="product_match").outcome == "admitted"
    )
    job = CollectionJob.objects.get(operation="match_crosswalk")
    assert job.instruction_version == 2
    assert job.definition["version"] == 2
    assert "matches" not in job.definition["options"]
    target = job.targets.get(target_kind="match_candidate")
    assert target.subject.product_id == product.product_key
    assert target.evidence_observation_id
    assert target.review_confirmed is True
    assert job.last_success.scopes.get(scope_kind="product_match").job_target_id == target.pk
    assert job.last_success.request_count == 0
    from core.collection_capture import run_report_document

    assert run_report_document(job.last_success)["decisions"] == {"admitted": 1}
    assert job_status(job.pk)["matching"]["decisions"] == {"admitted": 1}
    assert job_status(job.pk)["matching"]["remaining"] == 0
    again = apply_matches(resume_job_id=job.pk)
    assert again["status"] == "success"
    assert SourceSubjectMapping.objects.count() == 1
    assert CollectionRun.objects.filter(job=job).count() == 1


@pytest.mark.django_db(transaction=True)
def test_reviewed_match_uses_typed_decision_after_observation_json_retirement():
    from core.collection_capture import run_report_document
    from core.collection_matching import apply_matches
    from tests.test_hf_catalog_retirement import denied_retirement_columns

    brand, product, observation = catalog_fixture()
    assert observation.legacy_archive_id is not None
    with denied_retirement_columns():
        report = preview(brand)
        result = apply_reviewed(report)
        assert result["status"] == "success"
        job = CollectionJob.objects.get(operation="match_crosswalk")
        scope = job.last_success.scopes.get(scope_kind="product_match")
        assert scope.phase == "typed-product-match-v1"
        assert scope.admission_outcome == "admitted"
        decision = scope.observations.get(observation_kind="product_match_decision")
        assert decision.mapping.subject.product_id == product.product_key
        assert run_report_document(job.last_success)["decisions"] == {"admitted": 1}
        assert apply_matches(resume_job_id=job.pk)["status"] == "success"


def test_unreviewed_candidate_persists_unmatched_decision():
    from core.collection_matching import apply_matches
    from core.models import CollectionScopeRun

    brand, _, _ = catalog_fixture()
    report = preview(brand)
    apply_matches(
        preview=report,
        input_sha256=report["input_sha256"],
        reviewed_by="operator",
        review_basis="Preview only",
        reviewed_candidate_ids=[],
    )
    assert not SourceSubjectMapping.objects.exists()
    assert CollectionScopeRun.objects.get(scope_kind="product_match").outcome == "unmatched"


def test_changed_evidence_rolls_back_mapping_and_checkpoint():
    from core.models import CollectionScopeRun

    brand, _, observation = catalog_fixture()
    report = preview(brand)
    observation.source_identifier = "changed-model"
    observation.save()
    with pytest.raises(ValueError, match="evidence changed"):
        apply_reviewed(report)
    assert not SourceSubjectMapping.objects.exists()
    assert not CollectionScopeRun.objects.exists()


def test_match_evidence_pin_survives_retired_observation_documents():
    brand, _, observation = catalog_fixture()
    cutoff = timezone.now()
    expected = preview(brand, cutoff=cutoff)
    assert observation.legacy_archive_id is not None
    assert not hasattr(observation, "listing")
    observation.refresh_from_db()
    assert preview(brand, cutoff=cutoff) == expected
    apply_reviewed(expected)
    assert SourceSubjectMapping.objects.get().external_identifier == observation.source_identifier


def test_null_brand_review_does_not_change_metric_ownership_qualification():
    from core.collection_identity import qualified_ownership

    brand, product, _ = catalog_fixture()
    product.brand = product.product_type = None
    product.save()
    apply_reviewed(preview(brand))
    mapping = SourceSubjectMapping.objects.get()
    product.refresh_from_db()
    assert product.brand_id is None and product.product_type_code is None
    assert not qualified_ownership(mapping.publisher_account, mapping.subject)


def test_apply_rollback_and_resume_without_preview(monkeypatch):
    import core.collection_matching as matching
    from core.models import CollectionScopeRun

    brand, _, _ = catalog_fixture()
    report = preview(brand)
    original = matching._admit_choice

    def broken(*args):
        original(*args)
        raise RuntimeError("injected crash after mapping")

    monkeypatch.setattr(matching, "_admit_choice", broken)
    with pytest.raises(RuntimeError, match="injected crash"):
        apply_reviewed(report)
    assert not SourceSubjectMapping.objects.exists()
    assert not CollectionScopeRun.objects.filter(scope_kind="product_match").exists()
    job = CollectionJob.objects.get(operation="match_crosswalk")
    monkeypatch.setattr(matching, "_admit_choice", original)
    assert matching.apply_matches(resume_job_id=job.pk)["status"] == "success"
    assert SourceSubjectMapping.objects.count() == 1


def test_presence_distinguishes_unknown_absent_and_wrong_scope():
    from core.collection_matching import identifier_presence

    _, _, observation = catalog_fixture()
    args = {"source": "arena", "kind": "model", "scope": "arena_model_name"}
    assert (
        identifier_presence(**args, identifier=observation.source_identifier)
        == "present"
    )
    assert identifier_presence(**args, identifier="missing") == "absent"
    assert (
        identifier_presence(**args, identifier="missing", checked=False)
        == "not_checked"
    )
    assert identifier_presence(**args, identifier=None) == "not_applicable"
    assert (
        identifier_presence(
            **{**args, "scope": "catalog_id"}, identifier=observation.source_identifier
        )
        == "absent"
    )


def test_admitted_link_reaches_fresh_cohort_and_preserves_old_instructions():
    from core.model_history_cohort import freeze_model_history

    brand, _, _ = catalog_fixture()
    brands = [brand.pk] + [
        Brand.objects.create(nickname=f"empty-{i}").pk for i in range(20)
    ]
    cutoff = timezone.now()
    budgets = {"requests": 1, "bytes": 100000, "seconds": 60, "items": 100}
    earlier = freeze_model_history(
        brand_ids=brands, cutoff=cutoff, job_key_prefix="before-match", budgets=budgets
    )
    frozen = {j.pk: j.definition_sha256 for j in earlier}
    apply_reviewed(preview(brand))
    later = freeze_model_history(
        brand_ids=brands, cutoff=cutoff, job_key_prefix="after-match", budgets=budgets
    )
    arena_job = next(
        j
        for j in later
        if j.source_id == "arena" and j.definition["scope"]["brand_id"] == brand.pk
    )
    model = arena_job.definition["scope"]["models"][0]
    assert any(
        p["identifier_scope"] == "arena_model_name" for p in model["provider_pins"]
    )
    assert {
        j.pk: CollectionJob.objects.get(pk=j.pk).definition_sha256 for j in earlier
    } == frozen


def test_database_only_matching_does_not_activate_disabled_source():
    brand, _, observation = catalog_fixture()
    DataSource.objects.filter(pk=observation.run.job.source_id).update(enabled=False)
    result = apply_reviewed(preview(brand))
    assert result["status"] == "success"
    assert not DataSource.objects.get(pk="arena").enabled


def test_product_reference_change_invalidates_automatic_match():
    brand, product, _ = catalog_fixture()
    report = preview(brand)
    product.card_data = {"other": "changed identity evidence"}
    product.save()
    with pytest.raises(ValueError, match="product/publisher.*changed"):
        apply_reviewed(report)
    assert not SourceSubjectMapping.objects.exists()


def test_embedded_publication_identity_is_present_without_metric_rows():
    from core.collection_capture import archive_legacy

    brand, _, observation = catalog_fixture()
    identifier = observation.source_identifier
    observation.source_identifier = "publication:2026-10-17"
    observation.source_subject_kind = "aggregate"
    observation.observation_kind = "publication_window"
    observation.legacy_archive = archive_legacy({
        "listing": {"rows": [{"model_name": identifier}]},
        "dimensions": {"kind": "publication_window"},
        "source_metadata": {},
    })
    observation.save(update_fields=[
        "source_identifier", "source_subject_kind", "observation_kind", "legacy_archive",
    ])
    report = preview(brand)
    assert report["products"][0]["candidates"][0]["identifier"] == identifier
    apply_reviewed(report)
    assert SourceSubjectMapping.objects.get().external_identifier == identifier


def test_continuation_processes_at_most_fifty_choices_and_reuses_run():
    from core.collection_matching import apply_matches

    brand, first, observation = catalog_fixture(name="Model0")
    for index in range(1, 51):
        Product.objects.create(
            repo_id=f"Fixture/Model{index}",
            brand=brand,
            publisher_account=first.publisher_account,
            created_at=first.created_at,
        )
        CollectionObservation.objects.create(
            run=observation.run,
            source_identifier=f"model{index}",
            source_subject_kind="model",
            observation_key=digest(["continuation", index]),
            observation_kind="publication_row",
            legacy_archive=archive_legacy({
                "listing": {"rows": [{"model": f"model{index}"}]},
                "dimensions": {"kind": "publication_row"},
                "source_metadata": {},
            }),
        )
    first_result = apply_reviewed(preview(brand))
    assert first_result["status"] == "partial"
    assert SourceSubjectMapping.objects.count() == 50
    job = CollectionJob.objects.get(operation="match_crosswalk")
    result = apply_matches(resume_job_id=job.pk)
    assert result["status"] == "success" and SourceSubjectMapping.objects.count() == 51
    assert CollectionRun.objects.filter(job=job).count() == 1


def test_native_conflict_is_a_durable_outcome_without_partial_mapping():
    from core.collection_identity import review_catalog_mapping
    from core.models import CollectionScopeRun

    brand, product, observation = catalog_fixture()
    report = preview(brand)
    other_product = Product.objects.create(repo_id="Different/Other", brand=brand)
    other_subject = MeasurementSubject.objects.create(
        subject_kind="product", product=other_product
    )
    review_catalog_mapping(
        source=observation.run.job.source,
        subject=other_subject,
        external_identifier=observation.source_identifier,
        source_subject_kind="model",
        identifier_scope="arena_model_name",
        publisher_account=product.publisher_account,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://example.org/identity",
        reviewed_by="other-review",
        identity_snapshot={},
    )
    result = apply_reviewed(report)
    assert result["status"] == "success"
    assert SourceSubjectMapping.objects.count() == 1
    assert CollectionScopeRun.objects.get(scope_kind="product_match").outcome == "conflict"


@pytest.mark.django_db(transaction=True)
def test_concurrent_shared_writer_admits_one_dedicated_native_identity():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    from core.collection_identity import review_github_mapping
    from tests.test_collection_identity import identities

    brand, _, subject, repo = identities()
    product = Product.objects.create(brand=brand, repo_id="Different/Product")
    other = MeasurementSubject.objects.create(subject_kind="product", product=product)

    def attempt(subject_id):
        close_old_connections()
        try:
            target = MeasurementSubject.objects.get(pk=subject_id)
            review_github_mapping(
                subject=target,
                repo=repo,
                role="dedicated_model",
                evidence_url="https://github.com/publisher/family",
                reviewed_by="test",
            )
            return "admitted"
        except ValueError as exc:
            assert "conflict" in str(exc) or "busy" in str(exc)
            return "blocked"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [subject.pk, other.pk]))
    assert sorted(results) == ["admitted", "blocked"]
    assert SourceSubjectMapping.objects.count() == 1


def test_review_preview_restores_outer_transaction_settings():
    from django.db import connection

    brand, _, _ = catalog_fixture()
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        before = cursor.fetchone()[0]
    preview(brand)
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == before


def test_review_unconfirmed_publisher_cannot_be_approved():
    from core.models import CompanyAccount

    brand, product, _ = catalog_fixture()
    CompanyAccount.objects.filter(account=product.publisher_account).update(
        ownership_confirmed=False
    )
    report = preview(brand)
    assert report["products"][0]["candidates"][0]["decision"] == "unmatched"
    with pytest.raises(ValueError, match="ownership conflict"):
        apply_reviewed(report)
    assert not SourceSubjectMapping.objects.exists()


def test_review_manual_writer_rejects_conflicting_publisher_companies():
    from core.collection_identity import review_catalog_mapping
    from core.models import CompanyAccount

    _, product, observation = catalog_fixture()
    other = Company.objects.create(nickname="conflicting-owner")
    CompanyAccount.objects.create(
        company=other,
        account=product.publisher_account,
        role_id="official",
        ownership_confirmed=True,
    )
    subject = MeasurementSubject.objects.create(subject_kind="product", product=product)
    with pytest.raises(ValueError, match="ownership"):
        review_catalog_mapping(
            source=observation.run.job.source,
            subject=subject,
            external_identifier=observation.source_identifier,
            source_subject_kind="model",
            identifier_scope="arena_model_name",
            publisher_account=product.publisher_account,
            role="dedicated_model",
            version_selector=None,
            evidence_url="https://example.org/review",
            reviewed_by="operator",
            identity_snapshot={},
        )
    assert not SourceSubjectMapping.objects.exists()


def test_review_capped_publication_search_preserves_unknown_presence():
    from core.collection_matching import identifier_presence

    _, _, observation = catalog_fixture()
    identity = observation.source_identifier
    observation.source_identifier = "publication:oldest"
    observation.source_subject_kind = "aggregate"
    observation.observation_kind = "publication_window"
    observation.legacy_archive = archive_legacy({
        "listing": {"rows": [{"model_name": identity}]},
        "dimensions": {"kind": "publication_window"},
        "source_metadata": {},
    })
    observation.save(update_fields=[
        "source_identifier", "source_subject_kind", "observation_kind", "legacy_archive",
    ])
    unrelated = archive_legacy({
        "listing": {"rows": [{"model_name": "unrelated"}]},
        "dimensions": {"kind": "publication_window"},
        "source_metadata": {},
    })
    CollectionObservation.objects.bulk_create(
        [
            CollectionObservation(
                run=observation.run,
                source_identifier=f"publication:{i}",
                source_subject_kind="aggregate",
                observation_key=digest(["cap", i]),
                observation_kind="publication_window",
                legacy_archive=unrelated,
            )
            for i in range(501)
        ]
    )
    assert (
        identifier_presence(
            source="arena", kind="model", scope="arena_model_name", identifier=identity
        )
        == "not_checked"
    )


def test_review_invalid_resume_uses_command_error():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="invalid saved matching identity"):
        call_command(
            "match_collection_products",
            resume="invalid-uuid",
            apply=True,
            stdout=StringIO(),
        )


def test_review_explicit_first_party_reference_qualifies_without_candidate_approval():
    from core.account_identity import upsert_account
    from core.collection_matching import apply_matches, preview_matches
    from core.models import CompanyAccount

    brand, product, observation = catalog_fixture(source="github", native="123")
    publisher = upsert_account(
        source="github",
        external_identifier="42",
        handle="publisher",
        account_kind="organization",
    )
    CompanyAccount.objects.create(
        company_id="fixture-company",
        account=publisher,
        role_id="official",
        ownership_confirmed=True,
    )
    url = "https://github.com/publisher/Model-7B-Instruct"
    product.card_data = {"github": url}
    product.save()
    observation.source_subject_kind = "repository"
    observation.observation_kind = "repository"
    observation.legacy_archive = archive_legacy({
        "listing": {
            "id": 123,
            "full_name": "publisher/Model-7B-Instruct",
            "private": False,
            "owner": {"id": 42, "login": "publisher"},
        },
        "dimensions": {"kind": "repository"},
        "source_metadata": {},
    })
    observation.save(update_fields=[
        "source_subject_kind", "observation_kind", "legacy_archive",
    ])
    report = preview_matches(brand_ids=[brand.pk], sources=["github"])
    candidate = report["products"][0]["candidates"][0]
    assert candidate["decision"] == "qualified" and candidate["confidence_pct"] == 99
    apply_matches(
        preview=report,
        input_sha256=report["input_sha256"],
        reviewed_by="operator",
        review_basis="Stored first-party cross-reference",
        reviewed_candidate_ids=[],
    )
    mapping = SourceSubjectMapping.objects.get()
    assert (
        mapping.external_identifier == "123"
        and mapping.publisher_account_id == publisher.pk
    )
    assert mapping.identifier_metadata["match_review"]["owner_confirmed"] is False


# --- GDPx: freshly collected typed observations (U6, R12, R13) ---------------


def gdpx_products(*names, payload_change=None):
    """Store the recorded GDPx publication through persist_source, then name products."""
    from tests.test_benchmark_gdpx_store import contract, payload

    data = payload(payload_change)
    from core.benchmark_metric_store import persist_source

    run = persist_source(contract(), "gdpx", "9" * 64, data)
    assert run.status == "success"
    brand, _ = Brand.objects.get_or_create(nickname="gdpx-brand")
    company, _ = Company.objects.get_or_create(nickname="gdpx-company")
    BrandCompany.objects.get_or_create(brand=brand, company=company)
    publisher = hf_publisher(namespace="GdpxFixture", company=company, confirmed=True)
    products = {
        name: Product.objects.create(
            display_name=name,
            repo_id=None,
            brand=brand,
            publisher_account=publisher.account,
            created_at=timezone.now(),
            **product_type_fields(Product, "model-llm"),
            private=False,
        )
        for name in names
    }
    return brand, products, run


def gdpx_preview(brand):
    from core.collection_matching import preview_matches

    return preview_matches(brand_ids=[brand.pk], sources=["gdpx"])


def candidates_for(report, product):
    return next(
        p for p in report["products"] if p["product_key"] == str(product.product_key)
    )["candidates"]


def test_gdpx_preview_reads_typed_observations_without_legacy_archives():
    from core.collection_matching import identifier_presence

    brand, products, run = gdpx_products("Claude Opus 5.5")
    stored = CollectionObservation.objects.filter(run=run)
    assert stored.exists() and not stored.filter(legacy_archive__isnull=False).exists()
    report = gdpx_preview(brand)
    (candidate,) = candidates_for(report, products["Claude Opus 5.5"])
    assert candidate["source"] == "gdpx"
    assert candidate["identifier"] == "claude-opus-5-5"
    assert candidate["identifier_scope"] == "model_id"
    assert candidate["source_subject_kind"] == "model"
    assert candidate["observed_label"] == "Claude Opus 5.5"
    assert candidate["publisher_hint"] == "Anthropic"
    assert candidate["decision"] == "needs_review"
    assert candidate["confidence_pct"] == 90
    assert candidate["evidence_url"] == "https://gdpx.semianalysis.com/"
    evidence = CollectionObservation.objects.get(pk=candidate["evidence"]["observation_id"])
    assert evidence.run_id == run.pk and evidence.source_identifier == "claude-opus-5-5"
    assert report["writes"] == 0 and report["partial"] == []
    assert identifier_presence(
        source="gdpx", kind="model", scope="model_id", identifier="claude-opus-5-5"
    ) == "present"


def test_gdpx_preview_reads_the_shared_run_payload_archive_once(monkeypatch):
    """One daily GDPx run's payload archive backs every model observation in
    that run. The preview must read/parse/checksum it once per run, not once
    per model observation, and its output must be unchanged by caching."""
    from core import collection_capture

    brand, products, run = gdpx_products("Claude Opus 5.5")
    model_rows = CollectionObservation.objects.filter(
        run=run, source_subject_kind="model", observation_kind__isnull=True
    )
    # The recorded GDPx fixture publication covers many models sharing this
    # one run; reading each model's labels must not re-read the archive.
    assert model_rows.count() > 1

    calls = []
    original_read_document = collection_capture.read_document

    def counting_read_document(archive):
        calls.append(archive.pk)
        return original_read_document(archive)

    monkeypatch.setattr(collection_capture, "read_document", counting_read_document)

    report = gdpx_preview(brand)

    assert calls == [run.payload_archive_id], (
        "expected the run's payload archive to be read exactly once "
        f"for {model_rows.count()} model observations, got {len(calls)} reads"
    )

    # Output is byte-for-byte what the uncached path produces.
    (candidate,) = candidates_for(report, products["Claude Opus 5.5"])
    assert candidate["source"] == "gdpx"
    assert candidate["identifier"] == "claude-opus-5-5"
    assert candidate["identifier_scope"] == "model_id"
    assert candidate["source_subject_kind"] == "model"
    assert candidate["observed_label"] == "Claude Opus 5.5"
    assert candidate["publisher_hint"] == "Anthropic"
    assert candidate["decision"] == "needs_review"
    assert candidate["confidence_pct"] == 90
    assert candidate["evidence_url"] == "https://gdpx.semianalysis.com/"
    evidence = CollectionObservation.objects.get(pk=candidate["evidence"]["observation_id"])
    assert evidence.run_id == run.pk and evidence.source_identifier == "claude-opus-5-5"
    assert report["writes"] == 0 and report["partial"] == []


def test_gdpx_reviewed_match_admits_a_catalog_mapping():
    brand, products, _ = gdpx_products("Claude Opus 5.5")
    report = gdpx_preview(brand)
    assert apply_reviewed(report)["status"] == "success"
    mapping = SourceSubjectMapping.objects.get()
    assert (mapping.source_id, mapping.identifier_scope_code, mapping.external_identifier) == (
        "gdpx", "model_id", "claude-opus-5-5"
    )
    assert mapping.subject.product_id == products["Claude Opus 5.5"].product_key
    assert mapping.evidence_url == "https://gdpx.semianalysis.com/"


def test_gdpx_unreviewed_name_match_is_not_linked():
    from core.collection_matching import apply_matches

    brand, _, _ = gdpx_products("Claude Opus 5.5")
    report = gdpx_preview(brand)
    apply_matches(
        preview=report,
        input_sha256=report["input_sha256"],
        reviewed_by="operator",
        review_basis="Preview only",
        reviewed_candidate_ids=[],
    )
    assert not SourceSubjectMapping.objects.exists()


def test_gdpx_matches_on_display_name_never_on_slug():
    brand, products, _ = gdpx_products("gpt-6-2-astra", "GPT 6.2 Astra")
    report = gdpx_preview(brand)
    assert candidates_for(report, products["gpt-6-2-astra"]) == []
    (candidate,) = candidates_for(report, products["GPT 6.2 Astra"])
    assert candidate["identifier"] == "gpt-6-2-astra"
    assert candidate["observed_label"] == "GPT 6.2 Astra"


def test_gdpx_specialist_and_abliterated_rows_never_link_to_a_product():
    brand, products, _ = gdpx_products(
        "Kimi K3.1 Pro", "Kimi K3.1 Pro Abliterated", "HO1"
    )
    report = gdpx_preview(brand)
    (base,) = candidates_for(report, products["Kimi K3.1 Pro"])
    assert base["identifier"] == "kimi-k3-1-pro" and base["decision"] == "needs_review"
    for name, native in (
        ("Kimi K3.1 Pro Abliterated", "kimi-k3-1-pro-abliterated"),
        ("HO1", "hinoki-ho1"),
    ):
        (excluded,) = candidates_for(report, products[name])
        assert excluded["identifier"] == native
        assert excluded["decision"] == "unmatched"
        assert excluded["reasons"] == ["specialist_or_abliterated_variant"]
    with pytest.raises(ValueError, match="review cannot override"):
        apply_reviewed(report)
    assert not SourceSubjectMapping.objects.exists()


def test_gdpx_abliterated_name_is_excluded_without_a_specialist_label():
    def unlabel(dataset):
        for model in dataset["models"]:
            if model["id"] == "kimi-k3-1-pro-abliterated":
                del model["specialist"]

    brand, products, _ = gdpx_products(
        "Kimi K3.1 Pro Abliterated", payload_change=unlabel
    )
    (excluded,) = candidates_for(gdpx_preview(brand), products["Kimi K3.1 Pro Abliterated"])
    assert excluded["decision"] == "unmatched"
    assert excluded["reasons"] == ["specialist_or_abliterated_variant"]


def test_gdpx_two_models_claiming_one_product_are_both_unmatched():
    def collide(dataset):
        for model in dataset["models"]:
            if model["id"] == "claude-sonnet-5-5":
                model["name"] = "Claude-Opus 5.5"

    brand, products, _ = gdpx_products("Claude Opus 5.5", payload_change=collide)
    found = candidates_for(gdpx_preview(brand), products["Claude Opus 5.5"])
    assert {c["identifier"] for c in found} == {"claude-opus-5-5", "claude-sonnet-5-5"}
    assert {c["decision"] for c in found} == {"unmatched"}
    assert all(c["reasons"] == ["competing_source_identity"] for c in found)


def test_gdpx_dry_run_command_lists_recorded_fixture_models():
    brand, _, _ = gdpx_products("Claude Fable 5.2", "Kimi K3")
    output = StringIO()
    call_command(
        "match_collection_products", brand=[brand.pk], source=["gdpx"], stdout=output
    )
    report = json.loads(output.getvalue())
    assert report["sources"] == ["gdpx"] and report["writes"] == 0
    assert {
        c["identifier"] for p in report["products"] for c in p["candidates"]
    } == {"claude-fable-5-2", "kimi-k3"}
    assert not SourceSubjectMapping.objects.exists()


def test_arena_candidate_shape_is_unchanged_by_gdpx_support():
    brand, _, _ = catalog_fixture()
    (candidate,) = preview(brand)["products"][0]["candidates"]
    assert set(candidate) == {
        "source", "identifier", "identifier_scope", "source_subject_kind",
        "observed_label", "db_presence", "evidence", "publisher_account_key",
        "repo", "publication_row_index", "product_key", "role", "confidence_pct",
        "confidence_basis", "decision", "reasons", "ownership", "evidence_url",
        "candidate_id", "input_sha256",
    }
    assert candidate["evidence_url"] == (
        "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset"
    )


def test_gdpx_target_guard_migration_rewrites_only_the_source_list():
    """0248 adds gdpx to the guard's match_candidate source list and reverses cleanly."""
    from importlib import import_module

    from django.db import connection

    migration = import_module("core.migrations.0248_gdpx_match_candidate_namespace")

    def definition():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_functiondef(%s::regproc)", [migration.FUNCTION])
            return cursor.fetchone()[0]

    applied = definition()
    assert applied.count(migration.AFTER) == 1 and migration.BEFORE not in applied
    with connection.schema_editor() as editor:
        migration.backwards(None, editor)
    reverted = definition()
    assert reverted == applied.replace(migration.AFTER, migration.BEFORE)
    with connection.schema_editor() as editor:
        migration.forwards(None, editor)
    assert definition() == applied
    with connection.schema_editor() as editor, pytest.raises(RuntimeError):
        migration.forwards(None, editor)
    assert definition() == applied
