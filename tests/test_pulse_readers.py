"""Inclusive Pulse reads use stored dossiers without changing their evidence."""

import hashlib
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.collection_capture import archive_document
from core.event_dossiers import (
    ClaimDecision,
    ProductReleaseInput,
    add_claim,
    attach_source,
    complete_review,
    create_dossier,
    identity_key,
)
from core.models import (
    Brand,
    BrandCompany,
    CollectionObservation,
    CollectionRun,
    Company,
    CompanyLabel,
    DataSource,
    Post,
    PostBrandProduct,
    Product,
    ProductType,
    ReleaseMaturity,
)
from core.product_release_dossiers import record_release_report
from core.pulse_readers import (
    CATEGORY_ANCHOR_LIMIT,
    MAX_CATEGORY_PACKET_BYTES,
    _saved_category,
    release_page,
    release_sources,
)
from tests.collection_fixtures import evidence_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def historical_product(**values):
    """Create a pre-0227 row, then read it with all current guards installed."""
    from django.db.migrations.executor import MigrationExecutor

    MigrationExecutor(connection).migrate([("core", "0234_each_signal_aggregation")])
    try:
        category, _ = ProductType.objects.get_or_create(code="model")
        product = Product.objects.create(product_type=category, **values)
    finally:
        MigrationExecutor(connection).migrate([("core", "0240_pending_publication_admission_index")])
    return product


def pending_release(key, name="Observed model"):
    post = Post.objects.create(tweet_id=key, text=f"Announcing {name}")
    event, _, _ = record_release_report(
        post=post,
        record={"model_name": name},
        release_identity=key,
        observed_name=name,
        source_url=f"https://example.com/{key}",
        maturity_code="stable",
        release_value=None,
        release_precision="unknown",
        extraction_version="pulse-reader-test-v1",
    )
    return event


def reviewed_release(key, *, product=None, state="provisional"):
    event = pending_release(key)
    claim = event.sources.get().claims.get()
    complete_review(
        event.pk,
        expected_current_review_id=None,
        display_title="Reviewed title",
        review_state=state,
        evidence_cutoff_at=timezone.now(),
        method_version="pulse-reader-test-v1",
        actor="test",
        reason="Source-backed fixture",
        claims=[ClaimDecision(claim.pk, "accepted", "Source-backed fixture")],
        product_release=ProductReleaseInput(
            observed_name="Reviewed model",
            product_key=product.product_key if product else None,
        ),
    )
    return event


def github_product_claim(source, product, repository_id="123"):
    return add_claim(
        source.pk,
        claim_kind="release_context",
        scope_key=f"github_named_product:{repository_id}",
        assertion_text=f"The source names {product.display_name} as a released project; publisher control remains unresolved",
        source_excerpt=product.display_name,
        source_locator=f"https://github.com/publisher/project-{repository_id}",
        extraction_version="github-named-product-v1",
        reported_product_id=product.pk,
    )


def pulse_identity_release(
    key,
    *,
    claim_kind="release_context",
    scope_prefix="pulse-self-identity-v1",
    extraction_version="pulse-product-identity-v1",
):
    brand = Brand.objects.create(nickname=f"{key}-brand", display_name="Known publisher")
    kind, _ = ProductType.objects.get_or_create(code="model-llm")
    product = Product.objects.create(
        display_name="Existing model", brand=brand, product_type=kind
    )
    post = Post.objects.create(tweet_id=key, text="Announcing EXISTING MODEL")
    PostBrandProduct.objects.create(
        post=post,
        brand=brand,
        product=product,
        observed_name="Existing model",
        verification_policy_version="pulse-reader-test-v1",
    )
    event, _, _ = record_release_report(
        post=post,
        record={"model_name": "EXISTING MODEL"},
        release_identity=key,
        observed_name="EXISTING MODEL",
        source_url=f"https://example.com/{key}",
        brand=brand,
        maturity_code="stable",
        release_value=None,
        release_precision="unknown",
        extraction_version="pulse-reader-test-v1",
    )
    anchor = event.sources.get().claims.get()
    claim = add_claim(
        anchor.event_dossier_source_id,
        claim_kind=claim_kind,
        scope_key=f"{scope_prefix}:{key}",
        assertion_text="Existing Product matched the same post, brand, and observed name",
        source_excerpt=post.text,
        source_archive_id=anchor.source_archive_id,
        extraction_version=extraction_version,
        reported_product_id=product.pk,
        reported_brand_id=brand.pk,
    )
    return event, product, claim


def saved_category_claim(
    event,
    *,
    category="model-llm",
    observed_name="Qwen4",
    finding_key="a" * 64,
    packet_updates=None,
    finding_updates=None,
    claim_updates=None,
    body=None,
):
    source = event.sources.get()
    packet = {
        "schema": "pulse-release-intake-v1",
        "source": {
            "kind": "post" if source.post_id is not None else "observation",
            "id": source.post_id if source.post_id is not None else source.collection_observation_id,
        },
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "compressed8-pulse-content-v1",
        "finding": {
            "finding_key": finding_key,
            "observed_name": observed_name,
            "version": None,
            "variant": None,
            "novelty": "new_release",
            "category": category,
            "brand_id": None,
            "brand_candidate_id": None,
            "candidate_repo_id": None,
            "assertions": [{
                "claim_kind": "availability",
                "assertion_text": "Weights are available",
                "source_excerpt": "Weights are available today",
                "source_locator": None,
                "access_channel": "weights",
                "effective_precision": "unknown",
                "event_timezone": None,
                "effective_at": None,
                "effective_date": None,
                "effective_year": None,
                "effective_month": None,
                "not_before": None,
                "not_after": None,
            }],
        },
    }
    packet["finding"].update(finding_updates or {})
    packet.update(packet_updates or {})
    if body is None:
        body = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    elif callable(body):
        body = body(packet)
    archive = archive_document(
        body, encoding="selected-json-canonical-v1", capture_kind="product_release_intake"
    )
    claim_values = {
        "claim_kind": "release_report" if observed_name else "release_signal",
        "scope_key": f"pulse-finding-v1:{finding_key}",
        "assertion_text": observed_name or "Weights are available",
        "source_excerpt": "Weights are available today",
        "extraction_version": f"pulse-classified-findings-v1:{'b' * 64}",
        "source_archive_id": archive.pk,
        "release_maturity_id": ReleaseMaturity.objects.get(code="unknown").pk
        if observed_name else None,
    }
    claim_values.update(claim_updates or {})
    return add_claim(source.pk, **claim_values)


def category_release(key, **kwargs):
    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("category-test", key)
    )
    post = Post.objects.create(tweet_id=key, text="Weights are available today")
    attach_source(event.pk, post_id=post.pk)
    saved_category_claim(event, **kwargs)
    return event


def test_pending_and_review_without_product_are_both_visible():
    pending = pending_release("pending")
    reviewed = reviewed_release("reviewed")
    rows = {row["id"]: row for row in release_page()["entries"]}
    assert set(rows) == {str(pending.pk), str(reviewed.pk)}
    assert rows[str(pending.pk)]["name"] == "Observed model"
    assert rows[str(pending.pk)]["review_state"] == "pending"
    assert rows[str(pending.pk)]["product_identity_state"] == "pending"
    assert rows[str(reviewed.pk)]["name"] == "Reviewed model"
    assert rows[str(reviewed.pk)]["review_state"] == "provisional"
    assert rows[str(reviewed.pk)]["product_key"] is None
    assert rows[str(reviewed.pk)]["product_identity_state"] == "pending"


def test_generic_release_signal_is_not_presented_as_a_product_name():
    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("test", "unnamed")
    )
    post = Post.objects.create(tweet_id="unnamed", text="A release may be approaching")
    source = attach_source(event.pk, post_id=post.pk)
    add_claim(
        source.pk,
        claim_kind="release_signal",
        scope_key="body",
        assertion_text="Release candidate from announcement",
        source_excerpt=post.text,
        extraction_version="test-v1",
    )
    row = release_page()["entries"][0]
    assert row["id"] == str(event.pk)
    assert row["name"] is None


@pytest.mark.parametrize("observed_name", ["Model A", None])
def test_classified_report_prose_is_evidence_not_a_name_or_category_anchor(observed_name):
    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("test", "report-prose")
    )
    post = Post.objects.create(tweet_id="report-prose", text="Released Model A in 2026")
    source = attach_source(event.pk, post_id=post.pk)
    assertion = {
        "claim_kind": "release_report",
        "assertion_text": "Released Model A",
        "source_excerpt": post.text,
        "source_locator": None,
        "access_channel": None,
        "effective_precision": "year",
        "event_timezone": None,
        "effective_at": None,
        "effective_date": None,
        "effective_year": 2026,
        "effective_month": None,
        "not_before": None,
        "not_after": None,
    }
    anchor = saved_category_claim(
        event,
        observed_name=observed_name,
        finding_updates={"assertions": [assertion]},
        claim_updates={
            "assertion_text": observed_name or assertion["assertion_text"],
            "source_excerpt": post.text,
        },
    )
    assertion_hash = hashlib.sha256(json.dumps(
        assertion, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()).hexdigest()
    evidence = add_claim(
        source.pk,
        scope_key=f"pulse-assertion-v1:{'a' * 64}:{assertion_hash}",
        extraction_version=anchor.extraction_version,
        source_archive_id=anchor.source_archive_id,
        release_maturity_id=ReleaseMaturity.objects.get(code="unknown").pk,
        **assertion,
    )
    later = Post.objects.create(tweet_id="report-prose-later", text="Discussing this release")
    attach_source(event.pk, post_id=later.pk)
    row = release_page()["entries"][0]
    assert row["name"] == observed_name
    assert row["identity_conflict"] is False
    assert row["category"] == "model-llm"
    assert row["category_evidence_incomplete"] is False
    date = next(item for item in row["release_dates"] if item["id"] == str(evidence.pk))
    assert date["kind"] == "release_report" and date["value"] == "2026"
    assert date["source_id"] == source.pk
    assert row["sources_count"] == 2
    assert {item["post_id"] for item in release_sources(event.pk)["entries"]} == {post.pk, later.pk}


def test_legacy_release_report_name_preserves_arbitrary_identity_and_version():
    post = Post.objects.create(tweet_id="legacy-name", text="Announcing Legacy Model")
    record_release_report(
        post=post,
        record={"model_name": "Legacy Model"},
        release_identity="legacy:arbitrary/release-identity",
        observed_name="Legacy Model",
        source_url=None,
        maturity_code="stable",
        release_value=None,
        release_precision="unknown",
        extraction_version="custom-legacy-extractor-v9",
    )
    row = release_page()["entries"][0]
    assert row["name"] == "Legacy Model"
    assert row["identity_conflict"] is False
    assert row["category_evidence_incomplete"] is False


def test_sources_include_later_discussion_outside_the_completed_review():
    event = reviewed_release("original")
    later = Post.objects.create(
        tweet_id="later-discussion", text="Our experience with this release"
    )
    source = attach_source(event.pk, post_id=later.pk)
    assert attach_source(event.pk, post_id=later.pk).pk == source.pk
    page = release_sources(event.pk)
    assert {row["post_id"] for row in page["entries"]} == {"original", later.pk}
    later_row = next(row for row in page["entries"] if row["post_id"] == later.pk)
    assert later_row["supports_current_review"] is False
    assert release_page()["entries"][0]["sources_count"] == 2


def test_product_without_brand_company_or_provider_still_has_canonical_identity():
    kind, _ = ProductType.objects.get_or_create(code="model-llm")
    product = Product.objects.create(display_name="Canonical model", product_type=kind)
    event = reviewed_release("canonical", product=product)
    row = release_page()["entries"][0]
    assert row["id"] == str(event.pk)
    assert row["product_key"] == str(product.product_key)
    assert row["product_identity_state"] == "reviewed"
    assert row["category"] == "model-llm"
    assert row["brand"] is None
    assert row["companies"] == []


def test_discovery_pagination_survives_later_sources_and_new_discoveries():
    events = [pending_release(f"page-{i}") for i in range(4)]
    first = release_page(limit=2)
    post = Post.objects.create(tweet_id="new-discussion", text="More discussion")
    attach_source(events[-1].pk, post_id=post.pk)
    added = pending_release("after-page-one")
    second = release_page(cursor=first["next_cursor"], limit=2)
    ids = [row["id"] for row in first["entries"] + second["entries"]]
    assert len(ids) == len(set(ids)) == 4
    assert set(ids) == {str(event.pk) for event in events}
    assert str(added.pk) not in ids
    assert second["next_cursor"] is None


def test_date_precision_and_source_identity_remain_separate_from_discovery():
    event = pending_release("historical")
    source = event.sources.get()
    dated = add_claim(
        source.pk,
        claim_kind="source_stated_release",
        scope_key="historical-date",
        assertion_text="Released last year",
        source_excerpt="Released in 2025",
        extraction_version="test-v1",
        effective_precision="year",
        effective_year=2025,
    )
    row = release_page()["entries"][0]
    date_row = next(
        item for item in row["release_dates"] if item["id"] == str(dated.pk)
    )
    assert date_row["precision"] == "year"
    assert date_row["value"] == "2025"
    assert date_row["source_id"] == source.pk
    assert row["discovered_at"].year != 2025


def test_invalid_cursor_and_unbounded_limits_are_rejected():
    with pytest.raises(ValueError):
        release_page(cursor="invalid")
    with pytest.raises(ValueError):
        release_page(limit=10000)


def test_page_queries_do_not_grow_with_each_dossier():
    pending_release("query-one")
    started = perf_counter()
    with CaptureQueriesContext(connection) as one:
        release_page()
    one_ms = (perf_counter() - started) * 1000
    for number in range(24):
        pending_release(f"query-more-{number}")
    started = perf_counter()
    with CaptureQueriesContext(connection) as many:
        page = release_page()
    many_ms = (perf_counter() - started) * 1000
    assert len(page["entries"]) == 25
    assert len(many) == len(one)
    assert all(sql["sql"].lstrip().upper().startswith("SELECT") for sql in many)
    artifact = Path(settings.BASE_DIR) / ".local/pulse-p3/query-timings.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps([
        {"cards": size, "queries": len(queries), "sql_ms": sum(float(q["time"]) * 1000 for q in queries), "reader_ms": elapsed}
        for size, queries, elapsed in [(1, one, one_ms), (25, many, many_ms)]
    ], indent=2) + "\n")


def test_pending_identity_retains_a_source_reported_brand():
    brand = Brand.objects.create(
        nickname="reported-owner", display_name="Reported owner"
    )
    post = Post.objects.create(
        tweet_id="known-brand", text="Reported owner announces a model"
    )
    event, _, _ = record_release_report(
        post=post,
        record={"model_name": "Named model"},
        release_identity="known-brand",
        observed_name="Named model",
        source_url=None,
        brand=brand,
        maturity_code="stable",
        release_value=None,
        release_precision="unknown",
        extraction_version="test-v1",
    )
    row = release_page()["entries"][0]
    assert row["id"] == str(event.pk)
    assert row["brand"] == {"id": brand.pk, "name": "Reported owner"}
    assert row["product_key"] is None


def test_conflicting_claim_product_references_do_not_pick_the_first():
    event = pending_release("conflict")
    source = event.sources.get()
    products = [
        Product.objects.create(display_name=f"Candidate {number}")
        for number in range(2)
    ]
    for number, product in enumerate(products):
        github_product_claim(source, product, repository_id=str(number))
    row = release_page()["entries"][0]
    assert row["product_key"] is None
    assert row["identity_conflict"] is True


def test_unreviewed_report_prose_without_named_intake_provenance_is_not_a_name():
    from core.collection_capture import archive_document
    from core.models import ReleaseMaturity

    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("test", "prose")
    )
    post = Post.objects.create(
        tweet_id="prose", text="People discuss a possible release"
    )
    source = attach_source(event.pk, post_id=post.pk)
    archive = archive_document(
        b"People speculate about a release", encoding="wire-bytes-v1", capture_kind="test_source"
    )
    add_claim(
        source.pk,
        claim_kind="release_report",
        scope_key="body",
        assertion_text="People speculate about a release",
        source_excerpt=post.text,
        extraction_version="test-v1",
        source_archive_id=archive.pk,
        release_maturity_id=ReleaseMaturity.objects.get(code="unknown").pk,
    )
    assert release_page()["entries"][0]["name"] is None


def test_sources_are_paginated_without_dropping_late_unreviewed_links():
    event = reviewed_release("source-page-original")
    for number in range(8):
        post = Post.objects.create(tweet_id=f"source-page-{number}", text="Discussion")
        attach_source(event.pk, post_id=post.pk)
    page = release_page()["entries"][0]
    assert len(page["sources"]) == 3
    assert page["sources_count"] == 9
    cursor, seen = None, []
    while True:
        sources = release_sources(event.pk, cursor=cursor, limit=3)
        seen.extend(row["id"] for row in sources["entries"])
        cursor = sources["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 9


def test_date_preview_is_bounded_and_marks_more_evidence():
    event = pending_release("many-dates")
    source = event.sources.get()
    for number in range(8):
        add_claim(
            source.pk,
            claim_kind="availability",
            scope_key=f"date-{number}",
            assertion_text="Available during the stated year",
            source_excerpt="Available in that year",
            extraction_version="test-v1",
            effective_precision="year",
            effective_year=2020 + number,
        )
    row = release_page()["entries"][0]
    assert len(row["release_dates"]) == 5
    assert row["dates_more"] is True


def test_explicit_nonrelease_and_retired_records_keep_their_actual_states():
    from core.product_release_pipeline import record_intake_decision

    nonrelease = pending_release("known-nonrelease")
    record_intake_decision(
        nonrelease.pk,
        claim_id=nonrelease.sources.get().claims.get().pk,
        outcome="non_release",
        actor="test",
        reason="Earlier model update",
    )
    retired = reviewed_release("retired", state="retired")
    rows = {row["id"]: row for row in release_page()["entries"]}
    assert rows[str(nonrelease.pk)]["intake_outcome"] == "non_release"
    assert rows[str(retired.pk)]["review_state"] == "retired"


def test_source_urls_reject_executable_schemes_and_credentials():
    event = pending_release("unsafe-url")
    Post.objects.filter(pk="unsafe-url").update(tweet_url="javascript:alert(1)")
    assert release_sources(event.pk)["entries"][0]["url"] is None
    Post.objects.filter(pk="unsafe-url").update(
        tweet_url="https://user:password@example.com/source"
    )
    assert release_sources(event.pk)["entries"][0]["url"] is None


def test_saved_catalog_mapping_is_separate_from_identity_and_metric_activation():
    from core.collection_identity import review_github_mapping
    from tests.test_collection_identity import identities

    _, _, subject, repo = identities()
    event = reviewed_release("provider-link", product=subject.product)
    before = release_page()["entries"][0]
    assert before["provider_mapping_present"] is False
    mapping = review_github_mapping(
        subject=subject,
        repo=repo,
        role="family_repository",
        version_selector="v2",
        evidence_url="https://github.com/publisher/family",
        reviewed_by="test-reviewer",
    )
    row = release_page()["entries"][0]
    assert row["id"] == str(event.pk)
    assert row["provider_mapping_present"] is True
    assert row["catalog_mapping_present"] is True
    assert row["metric_mapping_present"] is False
    assert mapping.purpose == "catalog" and mapping.contract_id is None


def test_equal_timestamp_pagination_and_tampered_cursor():
    instant = timezone.now()
    with patch("django.utils.timezone.now", return_value=instant):
        events = [pending_release(f"same-time-{n}") for n in range(4)]
    first = release_page(limit=2)
    second = release_page(cursor=first["next_cursor"], limit=2)
    assert [row["id"] for row in first["entries"] + second["entries"]] == sorted(
        [str(event.pk) for event in events], reverse=True
    )
    cursor = first["next_cursor"]
    with pytest.raises(ValueError):
        release_page(cursor=cursor[:-1] + ("A" if cursor[-1] != "A" else "B"))


def test_merged_alias_reads_all_canonical_sources_without_duplicate_feed_entries():
    from core.product_release_pipeline import merge_dossiers

    alias, canonical = pending_release("alias"), pending_release("canonical-merge")
    merge_dossiers(alias.pk, canonical.pk, actor="test", reason="Same release")
    assert [row["id"] for row in release_page()["entries"]] == [str(canonical.pk)]
    with CaptureQueriesContext(connection) as queries:
        page = release_sources(alias.pk)
    assert page["event_id"] == str(canonical.pk)
    assert {row["post_id"] for row in page["entries"]} == {"alias", "canonical-merge"}
    assert all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries)


def test_multiple_company_owners_and_legacy_category_remain_explicit():
    brand = Brand.objects.create(nickname="shared-brand", display_name="Shared brand")
    for name in ("company-a", "company-b"):
        company = Company.objects.create(nickname=name)
        CompanyLabel.objects.create(company=company, locale_id="und", label=name.title())
        BrandCompany.objects.create(brand=brand, company=company)
    product = historical_product(display_name="Legacy model", brand=brand)
    reviewed_release("multiple-owners", product=product)
    row = release_page()["entries"][0]
    assert row["brand"] == {"id": brand.pk, "name": "Shared brand"}
    assert row["companies"] == [{"id": name, "name": name.title()} for name in ("company-a", "company-b")]
    assert row["category"] is None and row["legacy_category"] == "model"


def test_rejected_identity_claim_does_not_become_current_identity():
    event = pending_release("rejected-identity", name="Rejected report name")
    source = event.sources.get()
    brand = Brand.objects.create(nickname="rejected-brand", display_name="Rejected brand")
    kind, _ = ProductType.objects.get_or_create(code="model-llm")
    reported = Product.objects.create(
        display_name="Wrong identity", brand=brand, product_type=kind
    )
    claim = github_product_claim(source, reported)
    brand_claim = add_claim(
        source.pk,
        claim_kind="release_context",
        scope_key="wrong-brand",
        assertion_text="Claimed brand",
        source_excerpt="Claimed brand",
        extraction_version="test-v1",
        reported_brand_id=brand.pk,
    )
    issuer = Company.objects.create(nickname="Independent-Issuer")
    complete_review(
        event.pk,
        expected_current_review_id=None,
        display_title="Unresolved",
        review_state="unresolved",
        evidence_cutoff_at=timezone.now(),
        method_version="test-v1",
        actor="fixture",
        reason="Wrong product rejected",
        claims=[
            ClaimDecision(item.pk, "rejected", "Wrong identity")
            for item in source.claims.all()
        ],
        product_release=ProductReleaseInput(
            observed_name="Independently observed release",
            release_issuer_company_id=issuer.pk.upper(),
        ),
    )
    row = release_page()["entries"][0]
    assert row["product_key"] is None
    assert row["product_identity_state"] == "pending"
    assert row["category"] is None
    assert row["brand"] is None
    assert row["provider_mapping_present"] is None
    assert row["name"] == "Independently observed release"
    assert row["companies"] == [{"id": issuer.pk, "name": issuer.pk}]
    assert source.claims.filter(pk__in=[claim.pk, brand_claim.pk]).count() == 2


def test_hf_base_product_lineage_is_not_the_released_product_identity():
    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("test", "hf-child")
    )
    post = Post.objects.create(tweet_id="hf-child", text="A derived model is available")
    source = attach_source(event.pk, post_id=post.pk)
    brand = Brand.objects.create(nickname="base-publisher", display_name="Base publisher")
    kind, _ = ProductType.objects.get_or_create(code="model-llm")
    parent = Product.objects.create(
        display_name="Base model", repo_id="publisher/base", brand=brand, product_type=kind
    )
    claim = add_claim(
        source.pk,
        claim_kind="release_context",
        scope_key=f"hf_base_product:{'a' * 64}",
        assertion_text="HF model card reports base model publisher/base; relation finetune",
        source_excerpt="publisher/base",
        source_locator="https://huggingface.co/publisher/child",
        extraction_version="hf-base-product-v1",
        reported_product_id=parent.pk,
    )
    row = release_page()["entries"][0]
    assert row["product_key"] is None
    assert row["product_identity_state"] == "pending"
    assert row["name"] is None
    assert row["category"] is None
    assert row["brand"] is None
    assert row["companies"] == []
    assert row["identity_conflict"] is False
    assert row["sources_count"] == 1
    assert source.claims.get(pk=claim.pk).reported_product_id == parent.pk


def test_github_named_product_is_a_reported_candidate_without_a_review():
    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("test", "github-project")
    )
    post = Post.objects.create(tweet_id="github-project", text="Announcing a named project")
    source = attach_source(event.pk, post_id=post.pk)
    product = Product.objects.create(display_name="Named project")
    github_product_claim(source, product)
    row = release_page()["entries"][0]
    assert row["product_key"] == str(product.product_key)
    assert row["product_identity_state"] == "reported"
    assert row["review_state"] == "pending"
    assert row["review_id"] is None
    assert row["name"] == "Named project"


def test_pulse_self_identity_is_a_reported_candidate_without_a_review():
    event, product, claim = pulse_identity_release("pulse-existing")
    row = release_page()["entries"][0]
    assert row["id"] == str(event.pk)
    assert row["product_key"] == str(product.product_key)
    assert row["product_identity_state"] == "reported"
    assert row["review_id"] is None
    assert row["review_state"] == "pending"
    assert row["name"] == "EXISTING MODEL"
    assert row["category"] == "model-llm"
    assert row["brand"] == {"id": product.brand_id, "name": "Known publisher"}
    assert claim.source_archive_id == event.sources.get().claims.get(
        claim_kind_reference__code="release_report"
    ).source_archive_id


@pytest.mark.parametrize(
    ("claim_kind", "scope_prefix", "extraction_version"),
    [
        ("release_context", "pulse-self-identity-v1", "pulse-product-identity-v2"),
        ("release_context", "pulse-self-identity-v2", "pulse-product-identity-v1"),
        ("release_context", "github_named_product", "pulse-product-identity-v1"),
        ("release_context", "pulse-self-identity-v1", "github-named-product-v1"),
        ("release_signal", "pulse-self-identity-v1", "pulse-product-identity-v1"),
    ],
)
def test_unrecognized_self_identity_conventions_do_not_supply_a_product(
    claim_kind, scope_prefix, extraction_version
):
    event, _, _ = pulse_identity_release(
        "unknown-self-identity",
        claim_kind=claim_kind,
        scope_prefix=scope_prefix,
        extraction_version=extraction_version,
    )
    row = release_page()["entries"][0]
    assert row["id"] == str(event.pk)
    assert row["product_key"] is None
    assert row["product_identity_state"] == "pending"
    assert row["category"] is None
    assert row["provider_mapping_present"] is None
    assert row["name"] == "EXISTING MODEL"


def test_current_review_null_product_overrides_pulse_self_identity():
    event, _, claim = pulse_identity_release("reviewed-pulse-candidate")
    complete_review(
        event.pk,
        expected_current_review_id=None,
        display_title="Identity remains unresolved",
        review_state="unresolved",
        evidence_cutoff_at=timezone.now(),
        method_version="pulse-reader-test-v1",
        actor="fixture",
        reason="Reported candidate rejected",
        claims=[ClaimDecision(claim.pk, "rejected", "Different Product")],
        product_release=ProductReleaseInput(observed_name="Reviewed observed name"),
    )
    row = release_page()["entries"][0]
    assert row["product_key"] is None
    assert row["product_identity_state"] == "pending"
    assert row["review_state"] == "unresolved"
    assert row["name"] == "Reviewed observed name"
    assert row["category"] is None
    assert row["brand"] is None
    assert row["provider_mapping_present"] is None


def test_current_review_overrides_a_different_reported_product():
    product = Product.objects.create(display_name="Reviewed product")
    event = reviewed_release("reviewed-over-reported", product=product)
    candidate = Product.objects.create(display_name="Reported alternative")
    github_product_claim(event.sources.get(), candidate)
    row = release_page()["entries"][0]
    assert row["product_key"] == str(product.product_key)
    assert row["product_identity_state"] == "reviewed"
    assert row["name"] == "Reviewed model"


def test_case_insensitive_brand_and_company_keys_keep_canonical_labels():
    brand = Brand.objects.create(nickname="Mixed-Brand", display_name="Mixed brand")
    owner = Company.objects.create(nickname="Mixed-Owner")
    CompanyLabel.objects.create(company=owner, locale_id="und", label="Mixed owner")
    BrandCompany.objects.create(brand_id=brand.pk.upper(), company_id=owner.pk.lower())
    product = Product.objects.create(display_name="Mixed identity", brand_id=brand.pk.lower())
    event = reviewed_release("mixed-identity", product=product)
    row = release_page()["entries"][0]
    assert row["id"] == str(event.pk)
    assert row["brand"] == {"id": brand.pk, "name": "Mixed brand"}
    assert row["companies"] == [{"id": owner.pk, "name": "Mixed owner"}]


def test_case_insensitive_reported_brand_keeps_its_canonical_key():
    event = pending_release("mixed-reported-brand")
    brand = Brand.objects.create(nickname="Mixed-Reported", display_name="Mixed reported")
    add_claim(
        event.sources.get().pk,
        claim_kind="release_context",
        scope_key="reported-brand",
        assertion_text="A reported publisher",
        source_excerpt="A reported publisher",
        extraction_version="test-v1",
        reported_brand_id=brand.pk.lower(),
    )
    assert release_page()["entries"][0]["brand"] == {
        "id": brand.pk, "name": "Mixed reported"
    }


def test_current_review_retains_an_independently_accepted_reported_brand():
    event = pending_release("accepted-brand")
    brand = Brand.objects.create(nickname="Known-Brand", display_name="Known brand")
    claim = add_claim(
        event.sources.get().pk,
        claim_kind="release_context",
        scope_key="known-brand",
        assertion_text="A known publisher",
        source_excerpt="A known publisher",
        extraction_version="test-v1",
        reported_brand_id=brand.pk.lower(),
    )
    complete_review(
        event.pk,
        expected_current_review_id=None,
        display_title="Known brand, unresolved Product",
        review_state="unresolved",
        evidence_cutoff_at=timezone.now(),
        method_version="test-v1",
        actor="fixture",
        reason="Publisher evidence accepted independently of Product",
        claims=[ClaimDecision(claim.pk, "accepted", "Known publisher")],
        product_release=ProductReleaseInput(observed_name="Observed release"),
    )
    row = release_page()["entries"][0]
    assert row["brand"] == {"id": brand.pk, "name": "Known brand"}
    assert row["product_key"] is None
    assert row["product_identity_state"] == "pending"


def test_populated_identity_queries_do_not_grow_with_each_dossier():
    def populated_release(number):
        brand = Brand.objects.create(nickname=f"query-brand-{number}")
        for suffix in ("a", "b"):
            company = Company.objects.create(nickname=f"query-owner-{number}-{suffix}")
            CompanyLabel.objects.create(company=company, locale_id="und", label=company.pk)
            BrandCompany.objects.create(brand=brand, company=company)
        product = Product.objects.create(display_name=f"Product {number}", brand=brand)
        reviewed_release(f"populated-query-{number}", product=product)

    populated_release(0)
    with CaptureQueriesContext(connection) as one:
        release_page()
    for number in range(1, 25):
        populated_release(number)
    with CaptureQueriesContext(connection) as many:
        page = release_page()
    assert len(page["entries"]) == 25
    assert all(row["brand"] and len(row["companies"]) == 2 for row in page["entries"])
    assert len(many) == len(one)
    assert all(sql["sql"].lstrip().upper().startswith("SELECT") for sql in many)
    artifact = Path(settings.BASE_DIR) / ".local/pulse-p3/query-timings-resolved.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps([
        {"cards": size, "queries": len(queries)}
        for size, queries in [(1, one), (25, many)]
    ], indent=2) + "\n")


@pytest.mark.parametrize("observed_name", ["Qwen4", "通义千问", None])
def test_saved_finding_category_does_not_require_product_or_name(observed_name):
    category_release("saved-category", observed_name=observed_name)
    row = release_page()["entries"][0]
    assert row["product_key"] is None
    assert row["category"] == "model-llm"
    assert row["category_source"] == "saved_finding"
    assert row["name"] == observed_name
    assert row["category_conflict"] is False
    assert row["category_evidence_incomplete"] is False
    assert row["reported_categories"] == ["model-llm"]


def test_saved_observation_finding_category_uses_its_linked_source():
    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("category-test", "observation")
    )
    DataSource.objects.create(id="category-observation", name="Fixture", source_type="model_adoption")
    run = CollectionRun.objects.create(
        job=evidence_job(source_id="category-observation"), ingestion_key="d" * 64,
        status="success", completed_at=timezone.now(),
    )
    observation = CollectionObservation.objects.create(
        run=run, source_identifier="fixture/model", source_subject_kind="model",
        observation_key="e" * 64,
    )
    attach_source(event.pk, observation_id=observation.pk)
    saved_category_claim(event, category="model-other")
    row = release_page()["entries"][0]
    assert row["category"] == "model-other"
    assert row["category_source"] == "saved_finding"
    assert row["category_evidence_incomplete"] is False


def test_conflicting_saved_categories_remain_explicit_without_selecting_one():
    event = category_release("category-conflict", category="agent")
    saved_category_claim(event, category="harness", finding_key="d" * 64)
    row = release_page()["entries"][0]
    assert row["category"] is None
    assert row["category_source"] is None
    assert row["category_conflict"] is True
    assert row["category_evidence_incomplete"] is False
    assert row["reported_categories"] == ["agent", "harness"]


def test_repeated_saved_category_and_unspecified_category_are_not_conflicts():
    event = category_release("repeated-category")
    saved_category_claim(event, finding_key="d" * 64)
    saved_category_claim(event, category=None, finding_key="e" * 64)
    row = release_page()["entries"][0]
    assert row["category"] == "model-llm"
    assert row["category_conflict"] is False
    assert row["category_evidence_incomplete"] is False


def test_absent_saved_category_remains_pending_without_an_incomplete_flag():
    category_release("no-category", category=None)
    row = release_page()["entries"][0]
    assert row["category"] is None
    assert row["category_source"] is None
    assert row["reported_categories"] == []
    assert row["category_evidence_incomplete"] is False


@pytest.mark.parametrize(
    ("reviewed", "product_type", "has_product", "expected_category", "expected_source"),
    [
        (True, None, False, None, None),
        (True, None, True, None, None),
        (True, "agent", True, "agent", "product"),
        (False, "agent", True, "agent", "product"),
        (False, "model", True, None, "product"),
        (False, None, True, "model-llm", "saved_finding"),
    ],
)
def test_saved_category_respects_review_and_product_precedence(
    reviewed, product_type, has_product, expected_category, expected_source
):
    product = None
    if has_product and product_type == "model":
        product = historical_product(display_name="Known model")
    elif has_product:
        kind = ProductType.objects.get_or_create(code=product_type)[0] if product_type else None
        product = Product.objects.create(display_name="Known model", product_type=kind)
    if reviewed:
        event = reviewed_release("category-precedence", product=product)
    else:
        event = pending_release("category-precedence")
        github_product_claim(event.sources.get(), product)
    saved_category_claim(event, observed_name="Observed model")
    row = release_page()["entries"][0]
    assert row["category"] == expected_category
    assert row["category_source"] == expected_source
    assert row["legacy_category"] == ("model" if product_type == "model" else None)
    assert row["reported_categories"] == (["model-llm"] if expected_source == "saved_finding" else [])
    assert row["category_evidence_incomplete"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"packet_updates": {"schema": "pulse-release-intake-v2"}},
        {"packet_updates": {"source": {"kind": "post", "id": "wrong-source"}}},
        {"packet_updates": {"source": {"kind": "observation", "id": 1}}},
        {"packet_updates": {"revision_id": "d" * 64}},
        {"packet_updates": {"content_fingerprint": "invalid"}},
        {"packet_updates": {"unexpected": True}},
        {"finding_updates": {"finding_key": "d" * 64}},
        {"finding_updates": {"category": "model"}},
        {"finding_updates": {"category": ["agent", "harness"]}},
        {"claim_updates": {"scope_key": f"pulse-finding-v2:{'a' * 64}"}},
        {"claim_updates": {"extraction_version": f"pulse-classified-findings-v2:{'b' * 64}"}},
        {"body": b"not-json"},
        {"body": b"[" * 1200 + b"0" + b"]" * 1200},
        {"body": lambda packet: json.dumps(packet, sort_keys=True, separators=(",", ":")).replace(
            '"category":"model-llm"', '"category":"agent","category":"model-llm"'
        ).encode()},
    ],
)
def test_invalid_saved_category_evidence_cannot_select_a_valid_subset(changes):
    event = category_release("invalid-category", **changes)
    saved_category_claim(event, finding_key="f" * 64)
    row = release_page()["entries"][0]
    assert row["category"] is None
    assert row["category_source"] is None
    assert row["category_evidence_incomplete"] is True
    assert row["reported_categories"] == ["model-llm"]


def test_saved_category_packet_bytes_are_bounded_in_sql_before_decoding():
    event = category_release("oversized-category", body=b"x" * (MAX_CATEGORY_PACKET_BYTES * 3))
    saved_category_claim(event, finding_key="f" * 64)
    with (
        patch("core.pulse_readers._saved_category", wraps=_saved_category) as decode,
        CaptureQueriesContext(connection) as queries,
    ):
        row = release_page()["entries"][0]
    projected = [call.args[0] for call in decode.call_args_list]
    assert len(projected) == 2
    assert max(len(item["packet_body"]) for item in projected) == MAX_CATEGORY_PACKET_BYTES + 1
    assert any("SUBSTRING(" in query["sql"] and '"body"' in query["sql"] for query in queries)
    oversized = next(item for item in projected if len(item["packet_body"]) > MAX_CATEGORY_PACKET_BYTES)
    with pytest.raises(ValueError):
        _saved_category({**oversized, "source_archive__byte_count": 1})
    assert row["category"] is None
    assert row["category_evidence_incomplete"] is True
    assert row["reported_categories"] == ["model-llm"]


def test_saved_category_checksum_failure_does_not_discard_the_page():
    category_release("bad-checksum")

    def corrupt_projection(row):
        return _saved_category({**row, "source_archive__content_sha256": "0" * 64})

    with patch("core.pulse_readers._saved_category", side_effect=corrupt_projection):
        row = release_page()["entries"][0]
    assert row["category"] is None
    assert row["category_evidence_incomplete"] is True


def test_saved_category_anchor_overflow_stays_pending_and_bounded():
    event = category_release("many-category-anchors")
    for number in range(CATEGORY_ANCHOR_LIMIT + 3):
        saved_category_claim(event, finding_key=f"{number:064x}")
    with patch("core.pulse_readers._saved_category", wraps=_saved_category) as decode:
        row = release_page()["entries"][0]
    assert decode.call_count == CATEGORY_ANCHOR_LIMIT
    assert row["category"] is None
    assert row["category_evidence_incomplete"] is True
    assert row["reported_categories"] == ["model-llm"]


def test_saved_category_queries_do_not_grow_with_each_dossier():
    category_release("category-query-one")
    with CaptureQueriesContext(connection) as one:
        release_page()
    for number in range(24):
        category_release(f"category-query-{number}")
    with CaptureQueriesContext(connection) as many:
        page = release_page()
    assert len(page["entries"]) == 25
    assert all(row["category"] == "model-llm" for row in page["entries"])
    assert len(many) == len(one)
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in many)
    artifact = Path(settings.BASE_DIR) / ".local/pulse-p3/query-timings-categories.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps([
        {"cards": size, "queries": len(queries)}
        for size, queries in [(1, one), (25, many)]
    ], indent=2) + "\n")



def test_current_family_is_returned_and_conflicting_families_remain_unselected():
    from core.measurement_taxonomy import configure_taxonomy

    event, product, _ = pulse_identity_release("current-family")
    key = str(product.product_key)
    group = {"key": "family:current", "name": "First family", "group_kind": "family", "include": [key]}
    configure_taxonomy({"reviewed_by": "test", "subjects": [{"kind": "product", "key": key}], "groups": [group]})
    first = next(row for row in release_page()["entries"] if row["id"] == str(event.pk))
    assert first["family"]["name"] == "First family"
    assert first["family_conflict"] is False
    group["name"] = "Publisher family"
    configure_taxonomy({"reviewed_by": "test", "subjects": [{"kind": "product", "key": key}], "groups": [group]})
    renamed = next(row for row in release_page()["entries"] if row["id"] == str(event.pk))
    assert renamed["family"] == {"id": first["family"]["id"], "name": "Publisher family"}
    other = {"key": "family:other", "name": "Other family", "group_kind": "family", "include": [key]}
    configure_taxonomy({"reviewed_by": "test", "subjects": [{"kind": "product", "key": key}], "groups": [other]})
    conflict = next(row for row in release_page()["entries"] if row["id"] == str(event.pk))
    assert conflict["family"] is None
    assert conflict["family_conflict"] is True


def test_meta_brand_uses_the_existing_stored_display_name():
    brand = Brand.objects.create(nickname="llama", display_name="Meta")
    kind, _ = ProductType.objects.get_or_create(code="model-llm")
    product = Product.objects.create(display_name="Llama", brand=brand, product_type=kind)
    event = reviewed_release("meta-brand-display", product=product)
    row = next(row for row in release_page()["entries"] if row["id"] == str(event.pk))
    assert row["brand"] == {"id": "llama", "name": "Meta"}
