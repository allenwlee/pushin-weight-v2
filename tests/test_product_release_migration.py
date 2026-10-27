"""The RG7 rename retains selected historical review detail and kind identity."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
EXPAND = ("core", "0202_rg7_expand")
CUTOVER = ("core", "0203_rg7_product_release_cutover")


@pytest.mark.parametrize("migration_rehearsal_schema", [EXPAND], indirect=True)
def test_product_release_detail_rename_keeps_completed_review(
    migration_rehearsal_schema,
):
    old = MigrationExecutor(connection).loader.project_state([EXPAND]).apps
    kinds = old.get_model("core", "EventKind")
    kind, _ = kinds.objects.get_or_create(code="model_release")
    claim_kind, _ = old.get_model("core", "EventClaimKind").objects.get_or_create(
        code="announcement"
    )
    maturity, _ = old.get_model("core", "ReleaseMaturity").objects.get_or_create(
        code="unknown"
    )
    availability, _ = old.get_model(
        "core", "ReleaseAvailabilityState"
    ).objects.get_or_create(code="unknown")
    now = timezone.now()
    with transaction.atomic():
        dossier = old.get_model("core", "EventDossier").objects.create(
            event_kind_reference=kind,
            identity_key="a" * 64,
            first_seen_at=now,
            last_seen_at=now,
        )
        post = old.get_model("core", "Post").objects.create(
            tweet_id="rg7-renamed-detail", text="Release source"
        )
        source = old.get_model("core", "EventDossierSource").objects.create(
            event_dossier=dossier, post=post, linked_at=now
        )
        claim = old.get_model("core", "EventDossierClaim").objects.create(
            event_dossier_source=source,
            claim_kind_reference=claim_kind,
            scope_key="source",
            claim_hash="b" * 64,
            extraction_version="test-v1",
            recorded_at=now,
            assertion_text="Release report",
            source_excerpt="Release source",
            source_hash="c" * 64,
        )
        review = old.get_model("core", "EventDossierReview").objects.create(
            event_dossier=dossier,
            revision=1,
            reviewed_at=now,
            evidence_cutoff_at=now,
            method_version="test-v1",
            actor="reviewer",
            reason="Direct source",
            input_hash="d" * 64,
            display_title="Model",
            review_state="provisional",
        )
        old.get_model("core", "EventDossierReviewClaim").objects.create(
            review=review, claim=claim, disposition="accepted", reason="Direct source"
        )
        old.get_model("core", "ModelReleaseDetail").objects.create(
            review=review,
            observed_name="Model",
            native_identifier="org/model",
            release_maturity_reference=maturity,
            release_availability_reference=availability,
        )
        dossier.current_review_id = review.pk
        dossier.save(update_fields=["current_review"])
    old_kind_id = kind.pk
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM model_release_details")
        assert cursor.fetchone()[0] == 1

    MigrationExecutor(connection).migrate([CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([CUTOVER]).apps
    new_kind = current.get_model("core", "EventKind").objects.get(pk=old_kind_id)
    detail = current.get_model("core", "ProductReleaseDetail").objects.get(pk=review.pk)
    assert new_kind.code == "product_release"
    assert detail.observed_name == "Model"
    assert detail.native_identifier == "org/model"
    assert detail.review_id == review.pk
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM product_release_details")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT ed_validate_review_v1(%s)", [review.pk])
        cursor.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid="
            "'product_release_details'::regclass AND tgname='ed_frozen'"
        )
        assert cursor.fetchone() == ("O",)
    with pytest.raises(IntegrityError), transaction.atomic():
        current.get_model("core", "ProductReleaseDetail").objects.filter(
            pk=review.pk
        ).update(observed_name="Mutated")
