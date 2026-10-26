"""Real database evidence drives previews and durable reviewed application."""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

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
        **product_type_fields(Product, "llm-model"),
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
        dimensions={"kind": "publication_row"},
        listing={"rows": [{"model": native}]},
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
    assert job.last_success.scopes.get().job_target_id == target.pk
    assert job.last_success.request_count == 0
    job.last_success.report = {}
    job.last_success.save(update_fields=["report"])
    assert job_status(job.pk)["matching"]["decisions"] == {"admitted": 1}
    assert job_status(job.pk)["matching"]["remaining"] == 0
    again = apply_matches(resume_job_id=job.pk)
    assert again["status"] == "success"
    assert SourceSubjectMapping.objects.count() == 1
    assert CollectionRun.objects.filter(job=job).count() == 1


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
    assert CollectionScopeRun.objects.get().outcome == "unmatched"


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
    from core.collection_capture import archive_legacy

    brand, _, observation = catalog_fixture()
    cutoff = timezone.now()
    expected = preview(brand, cutoff=cutoff)
    observation.legacy_archive = archive_legacy(
        {
            "listing": observation.listing,
            "dimensions": observation.dimensions,
            "source_metadata": observation.source_metadata,
        }
    )
    observation.listing = {}
    observation.dimensions = {}
    observation.source_metadata = {}
    observation.save(
        update_fields=["legacy_archive", "listing", "dimensions", "source_metadata"]
    )
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
    assert not CollectionScopeRun.objects.exists()
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
    observation.dimensions = {"kind": "publication_window"}
    observation.observation_kind = "publication_window"
    observation.listing = {"rows": [{"model_name": identifier}]}
    observation.save()
    observation.legacy_archive = archive_legacy({
        "listing": observation.listing,
        "dimensions": observation.dimensions,
        "source_metadata": observation.source_metadata,
    })
    observation.listing = {}
    observation.dimensions = {}
    observation.source_metadata = {}
    observation.save(update_fields=[
        "legacy_archive", "listing", "dimensions", "source_metadata",
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
            dimensions={"kind": "publication_row"},
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
    assert CollectionScopeRun.objects.get().outcome == "conflict"


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
    observation.dimensions = {"kind": "publication_window"}
    observation.observation_kind = "publication_window"
    observation.listing = {"rows": [{"model_name": identity}]}
    observation.save()
    CollectionObservation.objects.bulk_create(
        [
            CollectionObservation(
                run=observation.run,
                source_identifier=f"publication:{i}",
                source_subject_kind="aggregate",
                observation_key=digest(["cap", i]),
                observation_kind="publication_window",
                listing={"rows": [{"model_name": f"unrelated-{i}"}]},
                dimensions={"kind": "publication_window"},
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
    observation.dimensions = {"kind": "repository"}
    observation.observation_kind = "repository"
    observation.listing = {
        "id": 123,
        "full_name": "publisher/Model-7B-Instruct",
        "private": False,
        "owner": {"id": 42, "login": "publisher"},
    }
    observation.save()
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
