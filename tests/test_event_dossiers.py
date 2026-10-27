"""Dossier evidence and completed history, exercised through real PostgreSQL."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core import models
from core.event_dossiers import (
    ClaimDecision,
    PersonnelChangeInput,
    ProductReleaseInput,
    StaleReview,
    add_claim,
    attach_source,
    complete_review,
    create_dossier,
    identity_key,
    read_dossier,
)
from tests.person_factory import person_with_name

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def dossier(key="model:small", kind="product_release"):
    return create_dossier(event_kind=kind, identity_key=identity_key("test", key))


def test_event_kind_uses_shared_identity_without_changing_dossier_replay():
    event = dossier("model:kind-reference")
    assert event.event_kind_reference.code == "product_release"
    assert read_dossier(event.pk)["dossier"]["event_kind"] == "product_release"
    assert "event_kind_id" not in read_dossier(event.pk)["dossier"]
    assert dossier("model:kind-reference").pk == event.pk
    assert models.EventDossier.objects.count() == 1
    with pytest.raises(ValueError, match="another event kind"):
        dossier("model:kind-reference", kind="personnel_change")


def post(key="announcement", text="Introducing our new model"):
    return models.Post.objects.create(tweet_id=key, text=text)


def claim(event, key="announcement", **kwargs):
    source = attach_source(event.pk, post_id=post(key).pk)
    return add_claim(
        source.pk,
        claim_kind="announcement",
        scope_key="x",
        assertion_text="Model announced",
        source_excerpt="Introducing our new model",
        extraction_version="test-v1",
        **kwargs,
    )


def review(event, evidence, **kwargs):
    values = {
        "expected_current_review_id": None,
        "display_title": "Unannounced model",
        "review_state": "provisional",
        "evidence_cutoff_at": timezone.now(),
        "method_version": "test-v1",
        "actor": "test analyst",
        "reason": "New evidence",
        "claims": [ClaimDecision(evidence.pk, "accepted", "Direct source")],
        "product_release": ProductReleaseInput(
            observed_name="anonymous", native_identifier="test/anonymous"
        ),
    }
    values.update(kwargs)
    return complete_review(event.pk, **values)


def test_atomic_variants_share_source_without_sharing_identity():
    small, large = dossier(), dossier("model:large")
    announcement = post()
    first = attach_source(small.pk, post_id=announcement.pk)
    assert attach_source(small.pk, post_id=announcement.pk).pk == first.pk
    attach_source(large.pk, post_id=announcement.pk)
    assert dossier().pk == small.pk
    assert models.EventDossier.objects.count() == 2
    assert models.EventDossierSource.objects.count() == 2


def test_review_reads_frozen_evidence_after_live_post_changes():
    event = dossier()
    evidence = claim(
        event, effective_precision="month", effective_year=2026, effective_month=9
    )
    saved = review(event, evidence)
    models.Post.objects.filter(pk="announcement").update(text="Changed live wording")
    result = read_dossier(event.pk)
    assert result["review"]["id"] == str(saved.pk)
    assert result["claims"][0]["source_excerpt"] == "Introducing our new model"
    assert result["claims"][0]["effective_precision"] == "month"
    assert result["claims"][0]["effective_at"] is None
    assert result["claims"][0]["effective_date"] is None
    assert result["product_release"]["product_key"] is None


def test_shadow_history_unresolved_then_confirmed_and_exact_retry():
    event = dossier()
    evidence = claim(event)
    first = review(event, evidence)
    second = review(
        event,
        evidence,
        expected_current_review_id=first.pk,
        review_state="unresolved",
        reason="No official confirmation; not false",
    )
    official = claim(event, key="official-confirmation")
    values = {
        "expected_current_review_id": second.pk,
        "evidence_cutoff_at": timezone.now(),
        "review_state": "confirmed",
        "product_release": ProductReleaseInput(
            observed_name="Model Small",
            native_identifier="official/model-small",
            disclosure_state="announced",
            availability_state="available",
        ),
    }
    third = review(event, official, **values)
    assert third.product_release.release_maturity_reference.code == "unknown"
    assert third.product_release.release_availability_reference.code == "available"
    assert third.product_release.disclosure_state == "announced"
    assert read_dossier(event.pk)["product_release"]["release_channel"] == "unknown"
    assert read_dossier(event.pk)["product_release"]["availability_state"] == "available"
    assert read_dossier(event.pk)["product_release"]["disclosure_state"] == "announced"
    assert review(event, official, **values).pk == third.pk
    assert (
        read_dossier(event.pk, review_id=first.pk)["review"]["review_state"]
        == "provisional"
    )
    assert (
        read_dossier(event.pk, review_id=second.pk)["review"]["review_state"]
        == "unresolved"
    )
    assert read_dossier(event.pk)["product_release"]["observed_name"] == "Model Small"
    assert third.revision == 3
    with pytest.raises(StaleReview):
        review(event, evidence, expected_current_review_id=first.pk)
    assert models.EventDossierReview.objects.count() == 3


def test_source_attachment_does_not_create_or_reassess_review():
    event = dossier()
    evidence = claim(event)
    saved = review(event, evidence)
    attach_source(event.pk, post_id=post("later").pk)
    assert read_dossier(event.pk)["review"]["id"] == str(saved.pk)
    assert models.EventDossierReview.objects.count() == 1


def test_claim_cannot_be_added_after_dossier_is_merged():
    event, canonical = dossier(), dossier("canonical")
    linked = attach_source(event.pk, post_id=post().pk)
    models.EventDossier.objects.filter(pk=event.pk).update(merged_into=canonical)

    with pytest.raises(ValueError, match="canonical dossier"):
        add_claim(
            linked.pk,
            claim_kind="announcement",
            scope_key="x",
            assertion_text="Model announced",
            source_excerpt="Introducing our new model",
            extraction_version="test-v1",
        )

    assert models.EventDossierClaim.objects.count() == 0


def test_cutoff_excludes_later_captured_claim_even_with_old_event_date():
    event = dossier()
    cutoff = timezone.now() - timedelta(days=1)
    evidence = claim(event, effective_precision="year", effective_year=2020)
    with pytest.raises(ValueError, match="cutoff"):
        review(event, evidence, evidence_cutoff_at=cutoff)
    assert models.EventDossierReview.objects.count() == 0
    assert read_dossier(event.pk)["review"] is None


@pytest.mark.parametrize(
    "values",
    [
        {"effective_precision": "day"},
        {"effective_precision": "unknown", "effective_year": 2026},
        {"effective_precision": "month", "effective_year": 2026, "effective_month": 13},
        {
            "effective_precision": "range",
            "not_before": timezone.now(),
            "not_after": timezone.now() - timedelta(days=1),
        },
    ],
)
def test_invalid_temporal_representation_is_rejected(values):
    event = dossier()
    with pytest.raises((ValueError, IntegrityError)):
        claim(event, **values)
    assert models.EventDossierClaim.objects.count() == 0


def test_claim_replay_and_separate_milestones():
    event = dossier()
    source = attach_source(event.pk, post_id=post().pk)
    values = {
        "claim_kind": "announcement",
        "scope_key": "x",
        "assertion_text": "Announced",
        "source_excerpt": "Announcement text",
        "extraction_version": "test-v1",
    }
    first = add_claim(source.pk, **values)
    assert first.claim_kind_reference.code == "announcement"
    assert add_claim(source.pk, **values).pk == first.pk
    repository = add_claim(
        source.pk,
        **{**values, "claim_kind": "repository_created", "scope_key": "repository"},
    )
    assert repository.claim_kind_reference.code == "repository_created"
    with pytest.raises(ValueError, match="Unknown dossier claim kind"):
        add_claim(source.pk, **{**values, "claim_kind": "unregistered"})
    assert models.EventDossierClaim.objects.count() == 2


def test_availability_claim_keeps_independent_channel_and_timezone():
    models.TimeZone.objects.get_or_create(code="Asia/Tokyo")
    event = dossier("model:scoped-availability")
    source = attach_source(event.pk, post_id=post("scoped-availability").pk)
    values = {
        "claim_kind": "availability",
        "scope_key": "JP",
        "assertion_text": "API available in Japan",
        "source_excerpt": "Available in Japan",
        "extraction_version": "test-v1",
        "event_timezone": "Asia/Tokyo",
        "access_channel": "api",
    }
    api = add_claim(source.pk, **values)
    weights = add_claim(source.pk, **{**values, "access_channel": "weights"})
    assert api.pk != weights.pk
    assert api.event_timezone_reference.code == "Asia/Tokyo"
    assert api.release_access_channel_reference.code == "api"
    assert weights.release_access_channel_reference.code == "weights"
    review(event, api)
    shown = read_dossier(event.pk)["claims"]
    assert shown[0]["claim_kind"] == "availability"
    assert shown[0]["event_timezone"] == "Asia/Tokyo"
    assert shown[0]["access_channel"] == "api"
    assert "event_timezone_id" not in shown[0]
    assert "access_channel_id" not in shown[0]


def test_post_backed_observation_canonicalizes_to_post_membership():
    from tests.test_benchmark_download_db_models import measurement

    _, _, observation = measurement()
    source_post = post()
    models.CollectionObservation.objects.filter(pk=observation.pk).update(
        source_subject_kind="post",
        post=source_post,
        source_identifier=source_post.pk,
        product=None,
        mapping=None,
    )
    event = dossier()
    first = attach_source(event.pk, observation_id=observation.pk)
    assert first.post_id == source_post.pk
    assert first.collection_observation_id is None
    assert attach_source(event.pk, post_id=source_post.pk).pk == first.pk
    assert models.EventDossierSource.objects.count() == 1


def test_raw_source_xor_and_cross_dossier_pointer_are_rejected():
    event, other = dossier(), dossier("other")
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossierSource.objects.create(event_dossier=event)
    saved = review(other, claim(other))
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossier.objects.filter(pk=event.pk).update(current_review=saved)


def test_cross_dossier_claim_and_wrong_extension_roll_back():
    event, other = dossier(), dossier("other")
    evidence = claim(other)
    with pytest.raises(ValueError, match="dossier"):
        review(event, evidence)
    evidence = claim(event, key="own")
    with pytest.raises(ValueError, match="detail|kind"):
        review(
            event,
            evidence,
            product_release=None,
            personnel_change=PersonnelChangeInput(
                observed_person_name="A", change_kind="move"
            ),
        )
    assert models.EventDossierReview.objects.count() == 0


def test_completed_history_rejects_bulk_updates_deletes_and_late_inputs():
    event = dossier()
    evidence = claim(event)
    saved = review(event, evidence)
    for queryset, values in [
        (
            models.EventDossierClaim.objects.filter(pk=evidence.pk),
            {"source_excerpt": "rewritten"},
        ),
        (
            models.EventDossierReview.objects.filter(pk=saved.pk),
            {"display_title": "rewritten"},
        ),
        (
            models.ProductReleaseDetail.objects.filter(pk=saved.pk),
            {"observed_name": "rewritten"},
        ),
        (
            models.EventDossierReviewClaim.objects.filter(review=saved),
            {"reason": "rewritten"},
        ),
    ]:
        with pytest.raises(IntegrityError), transaction.atomic():
            queryset.update(**values)
        with pytest.raises(IntegrityError), transaction.atomic():
            queryset.delete()
    newer = claim(event, key="later")
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossierReviewClaim.objects.create(
            review=saved, claim=newer, disposition="accepted", reason="Late addition"
        )


def test_raw_incomplete_review_cannot_commit():
    event = dossier()
    with pytest.raises(IntegrityError), transaction.atomic():
        saved = models.EventDossierReview.objects.create(
            event_dossier=event,
            revision=1,
            reviewed_at=timezone.now(),
            evidence_cutoff_at=timezone.now() - timedelta(seconds=1),
            method_version="test",
            actor="test",
            reason="test",
            input_hash="a" * 64,
            display_title="Incomplete",
            review_state="provisional",
        )
        models.EventDossier.objects.filter(pk=event.pk).update(current_review=saved)
    assert models.EventDossierReview.objects.count() == 0


def test_personnel_move_uses_existing_roles_without_changing_them():
    person = person_with_name("Researcher")
    roles = [
        models.PersonBrandAffiliation.objects.create(
            person=person,
            affiliation_type_reference=models.AffiliationType.objects.get(code="employment"),
            observed_organization_name=name,
            brand=models.Brand.objects.create(
                nickname=f"employer-{index}", display_name=name
            ),
            claim_identity=uuid4().hex,
            title_raw="Researcher",
        )
        for index, name in enumerate(["Old employer", "New employer"])
    ]
    event = dossier("person:move", kind="personnel_change")
    evidence = claim(event)
    saved = review(
        event,
        evidence,
        product_release=None,
        personnel_change=PersonnelChangeInput(
            person_id=person.pk,
            observed_person_name="Researcher",
            change_kind="move",
            from_affiliation_id=roles[0].pk,
            to_affiliation_id=roles[1].pk,
            from_organization_name="Old employer",
            to_organization_name="New employer",
        ),
    )
    assert saved.personnel_change.change_type_reference.code == "move"
    assert read_dossier(event.pk)["personnel_change"]["change_kind"] == "move"
    assert "change_kind_id" not in read_dossier(event.pk)["personnel_change"]
    assert read_dossier(event.pk)["personnel_change"]["person_id"] == str(person.pk)
    assert saved.revision == 1
    assert not models.PersonBrandAffiliation.objects.filter(
        superseded_by__isnull=False
    ).exists()


def test_ranking_requires_named_method_and_finite_score():
    event = dossier()
    evidence = claim(event)
    with pytest.raises(ValueError, match="ranking"):
        review(event, evidence, significance_score=Decimal(2))
    assert models.EventDossierReview.objects.count() == 0


def test_two_concurrent_reviewers_cannot_both_replace_the_same_revision():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    event = dossier()
    evidence = claim(event)
    first = review(event, evidence)
    barrier = Barrier(2)

    def submit(actor):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                return review(
                    event, evidence, expected_current_review_id=first.pk, actor=actor
                ).pk
            except StaleReview:
                return "stale"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["analyst-a", "analyst-b"]))
    assert results.count("stale") == 1
    assert models.EventDossierReview.objects.count() == 2
    assert read_dossier(event.pk)["review"]["revision"] == 2


def test_raw_malformed_time_and_canonical_post_membership():
    from tests.test_benchmark_download_db_models import measurement

    event = dossier()
    evidence = claim(event)
    values = {
        field.attname: getattr(evidence, field.attname)
        for field in evidence._meta.concrete_fields
    }
    values.update(
        id=uuid4(), claim_hash="e" * 64, effective_precision="day", effective_year=2026
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossierClaim.objects.create(**values)
    _, _, observation = measurement()
    source_post = post("captured")
    models.CollectionObservation.objects.filter(pk=observation.pk).update(
        source_subject_kind="post",
        post=source_post,
        source_identifier=source_post.pk,
        product=None,
        mapping=None,
    )
    row = models.EventDossierSource.objects.create(
        event_dossier=event, collection_observation=observation
    )
    row.refresh_from_db()
    assert row.post_id == source_post.pk and row.collection_observation_id is None
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossierSource.objects.create(event_dossier=event, post=source_post)


def test_raw_review_with_foreign_claim_or_wrong_detail_cannot_commit():
    event, other = dossier(), dossier("other")
    own, foreign = claim(event), claim(other, key="foreign")
    for used, wrong_kind in [(foreign, False), (own, True)]:
        cutoff = timezone.now()
        reviewed_at = cutoff + timedelta(microseconds=1)
        with pytest.raises(IntegrityError), transaction.atomic():
            saved = models.EventDossierReview.objects.create(
                event_dossier=event,
                revision=1,
                reviewed_at=reviewed_at,
                evidence_cutoff_at=cutoff,
                method_version="test",
                actor="test",
                reason="test",
                input_hash="a" * 64,
                display_title="Invalid",
                review_state="provisional",
            )
            models.EventDossierReviewClaim.objects.create(
                review=saved, claim=used, disposition="accepted", reason="test"
            )
            if wrong_kind:
                models.PersonnelChangeDetail.objects.create(
                    review=saved, observed_person_name="A",
                    change_type_reference=models.PersonnelChangeType.objects.get(
                        code="move"
                    ),
                )
            else:
                models.ProductReleaseDetail.objects.create(
                    review=saved, observed_name="A", native_identifier="test/a",
                    release_maturity_reference=models.ReleaseMaturity.objects.get(
                        code="unknown"
                    ),
                    release_availability_reference=models.ReleaseAvailabilityState.objects.get(
                        code="unknown"
                    ),
                    disclosure_state="unknown",
                )
            models.EventDossier.objects.filter(pk=event.pk).update(current_review=saved)
    assert models.EventDossierReview.objects.count() == 0


def test_raw_sql_cannot_reopen_selected_review_by_clearing_current_pointer():
    event = dossier()
    first_claim = claim(event, key="first")
    second_claim = claim(event, key="second")
    selected = review(event, first_claim)

    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossier.objects.filter(pk=event.pk).update(current_review=None)
        models.EventDossierReviewClaim.objects.create(
            review_id=selected.pk,
            claim=second_claim,
            disposition="accepted",
            reason="late input",
        )
        models.EventDossier.objects.filter(pk=event.pk).update(current_review=selected)

    assert models.EventDossier.objects.get(pk=event.pk).current_review_id == selected.pk
    assert models.EventDossierReviewClaim.objects.filter(review=selected).count() == 1
