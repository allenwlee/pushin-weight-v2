"""Historical product-release transfer preserves evidence and replay cursors."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction

from core.collection_capture import read_document
from core.management.commands.sync_product_release_dossiers import parity_counts
from core.models import (
    Account,
    Brand,
    EventDossier,
    EventDossierClaim,
    ModelRelease,
    ModelReleaseEvidence,
    Post,
    ProductVerificationProposal,
    ReleaseMaturity,
)
from core.product_release_dossiers import pending_release_ids, transfer_pending

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_transfer_preserves_pending_evidence_owner_clocks_and_proposal():
    account = Account.objects.create(author_id="rg7-transfer-author")
    post = Post.objects.create(
        tweet_id="rg7-transfer-post", author=account, text="Acme M1"
    )
    brand = Brand.objects.create(nickname="rg7-acme", display_name="Acme")
    release = ModelRelease.objects.create(
        brand=brand,
        observed_model_name="Acme M1",
        version="M1",
        release_maturity_reference=ReleaseMaturity.objects.get(code="preview"),
        release_value="2026-10-01",
        release_precision="day",
        release_identity="a" * 64,
        first_seen_at=post.fetched_at,
        last_seen_at=post.fetched_at,
        extraction_version="saved-v1",
    )
    observed_claim = {
        "model_name": "Acme M1",
        "version": "M1",
        "categories": ["llm-model"],
    }
    evidence = ModelReleaseEvidence.objects.create(
        release=release,
        source_post=post,
        observed_at=post.fetched_at,
        source_url="https://example.org/release",
        observed_claim=observed_claim,
        evidence_hash="b" * 64,
        extraction_version="saved-v1",
    )
    proposal = ProductVerificationProposal.objects.create(
        proposal_key="c" * 64,
        source_post=post,
        source_release=release,
        proposed_brand=brand,
        account=account,
        observed_name="Acme M1",
        policy_version="rg7-test",
    )
    assert pending_release_ids() == [release.pk]
    assert transfer_pending()["claims_created"] == 1
    release.refresh_from_db()
    evidence.refresh_from_db()
    proposal.refresh_from_db()
    dossier = EventDossier.objects.get(pk=release.rg7_dossier_id)
    claim = EventDossierClaim.objects.select_related("source_archive").get(
        pk=evidence.rg7_claim_id
    )
    packet = read_document(claim.source_archive)
    assert packet["schema"] == "product-release-legacy-v1"
    assert packet["release"]["brand_id"] == brand.pk
    assert packet["release"]["release_identity"] == release.release_identity
    assert packet["evidence"]["observed_claim"] == observed_claim
    assert packet["evidence"]["evidence_hash"] == evidence.evidence_hash
    assert claim.recorded_at == evidence.created_at
    assert claim.event_dossier_source.post_id == post.pk
    assert claim.reported_brand_id == brand.pk
    assert proposal.source_dossier_id == dossier.pk
    assert dossier.current_review_id is None
    assert pending_release_ids() == []
    assert parity_counts()["bad_evidence"] == 0
    assert transfer_pending()["claims_created"] == 0
    assert EventDossierClaim.objects.count() == 1

    # An old writer changes its source. The trigger invalidates the durable cursor.
    release.last_seen_at += timedelta(minutes=1)
    release.save(update_fields=["last_seen_at", "updated_at"])
    release.refresh_from_db()
    assert release.rg7_dossier_id is None
    assert pending_release_ids() == [release.pk]
    transfer_pending()
    assert EventDossierClaim.objects.count() == 2
    assert pending_release_ids() == []

    evidence.source_url = "https://example.org/corrected-release"
    evidence.save(update_fields=["source_url"])
    evidence.refresh_from_db()
    assert evidence.rg7_claim_id is None
    transfer_pending()
    assert EventDossierClaim.objects.count() == 3

    proposal.source_release = None
    proposal.save(update_fields=["source_release"])
    proposal.refresh_from_db()
    assert proposal.source_dossier_id is None
    proposal.source_release = release
    proposal.save(update_fields=["source_release"])
    transfer_pending()
    proposal.refresh_from_db()
    assert proposal.source_dossier_id == dossier.pk
    assert parity_counts()["bad_evidence"] == 0

    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM model_release_evidence WHERE id=%s", [evidence.pk])
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM model_releases WHERE id=%s", [release.pk])
