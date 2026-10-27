from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import PostEnrichmentState
from monitor.enrichment_recovery import apply_manifest, build_manifest, manifest_digest
from tests.test_post_enrichment_queue import _state

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _manifest():
    return build_manifest(
        since=timezone.now() - timedelta(days=1),
        until=timezone.now() + timedelta(seconds=1),
    )


def test_preview_is_read_only_and_reapply_preserves_successes_and_attempts():
    state = _state("recover-expired")
    PostEnrichmentState.objects.filter(pk=state.pk).update(
        translation_status="succeeded",
        classification_status="failed",
        classification_error_code="age_exhausted",
        classification_attempts=2,
    )
    manifest = _manifest()
    state.refresh_from_db()
    created = state.created_at
    assert state.classification_status == "failed"
    first = apply_manifest(manifest)
    assert [row["post_id"] for row in first["requeued"]] == [state.pk]
    assert first["requeued"][0]["before"]["classification"]["attempts"] == 2
    assert apply_manifest(manifest)["requeued"] == []
    state.refresh_from_db()
    assert state.created_at == created
    assert state.translation_status == "succeeded"
    assert state.classification_status == "pending"
    assert state.classification_attempts == 2


def test_recovery_rechecks_lease_and_concurrent_success():
    states = [_state("recover-leased"), _state("recover-completed")]
    PostEnrichmentState.objects.filter(pk__in=[state.pk for state in states]).update(
        classification_status="failed",
        classification_error_code="age_exhausted",
    )
    manifest = _manifest()
    PostEnrichmentState.objects.filter(pk=states[0].pk).update(
        claim_expires_at=timezone.now() + timedelta(minutes=1)
    )
    PostEnrichmentState.objects.filter(pk=states[1].pk).update(
        classification_status="succeeded"
    )
    result = apply_manifest(manifest)
    assert result["requeued"] == []
    assert result["skipped"][states[0].pk] == "active_lease"
    states[1].refresh_from_db()
    assert states[1].classification_status == "succeeded"


def test_digest_or_malformed_later_entry_cannot_partially_apply():
    for post_id in ("manifest-a", "manifest-b"):
        state = _state(post_id)
        PostEnrichmentState.objects.filter(pk=state.pk).update(
            classification_status="failed", classification_error_code="age_exhausted"
        )
    manifest = _manifest()
    manifest["entries"][1]["classification_attempts"] = "not-an-integer"
    with pytest.raises(ValueError, match="digest"):
        apply_manifest(manifest)
    manifest["sha256"] = manifest_digest(manifest)
    with pytest.raises(ValueError, match="entry_invalid"):
        apply_manifest(manifest)
    assert (
        PostEnrichmentState.objects.filter(classification_status="failed").count() == 2
    )


def test_attempt_exhaustion_requires_an_exact_reviewed_reset():
    state = _state("reset-one")
    PostEnrichmentState.objects.filter(pk=state.pk).update(
        classification_status="failed",
        classification_error_code="attempts_exhausted",
        classification_attempts=8,
    )
    assert apply_manifest(_manifest())["requeued"] == []
    manifest = build_manifest(
        since=timezone.now() - timedelta(days=1),
        until=timezone.now() + timedelta(seconds=1),
        reset_post_ids=[state.pk],
        reset_reason="Reviewed tracked-promotion rejection fixed by this release",
    )
    receipt = apply_manifest(manifest)
    assert receipt["requeued"][0]["before"]["classification"]["attempts"] == 8
    state.refresh_from_db()
    assert state.classification_attempts == 0


def test_receipt_write_failure_rolls_back_recovery(tmp_path, monkeypatch):
    import json

    from django.core.management import call_command
    from django.core.management.base import CommandError

    from monitor.management.commands import recover_enrichment

    state = _state("receipt-failure")
    PostEnrichmentState.objects.filter(pk=state.pk).update(
        classification_status="failed",
        classification_error_code="age_exhausted",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()))

    def failed_sync(_fd):
        raise OSError("receipt disk failure")

    monkeypatch.setattr(recover_enrichment.os, "fsync", failed_sync)
    with pytest.raises(CommandError, match="receipt disk failure"):
        call_command(
            "recover_enrichment",
            manifest=manifest_path,
            apply=True,
            receipt=tmp_path / "receipt.json",
        )
    state.refresh_from_db()
    assert state.classification_status == "failed"
    assert state.classification_error_code == "age_exhausted"
