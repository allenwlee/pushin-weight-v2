"""Explicit saved-classifier recovery through real callers and PostgreSQL writers."""
import copy
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import (
    OriginalContentCall,
    Post,
    PostBrandClassificationState,
    PostEnrichmentState,
    ProviderBatch,
)
from core.provider_batches import BatchAdmissionError, digest
from monitor.backfill_enrichment import completion_facts, deferred_enrichment_work
from tests.test_backfill_direct_enrichment import DirectProvider, run_direct
from tests.test_backfill_native_enrichment import native as native_fixture

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
native = native_fixture


def _rejected_packet(native):
    provider = DirectProvider()
    for turn in range(10):
        result = run_direct(native, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    originals = list(OriginalContentCall.objects.filter(stage="classification"))
    assert len(originals) == 2
    latest = []
    for original in originals:
        original.import_state = "error"
        original.import_evidence = {
            "validation": "canonical_validation_failed",
            "invalid_member_ids": list(original.member_post_ids),
        }
        original.save(update_fields=["import_state", "import_evidence"])
        for index in range(2):
            old = copy.deepcopy(original)
            old.pk = None
            old.request_identity = uuid4().hex
            old.batch_key = uuid4().hex
            old.reserved_at = original.reserved_at + timedelta(microseconds=index + 1)
            old.save(force_insert=True)
        latest.append(old.pk)
    PostEnrichmentState.objects.filter(pk="native-1").update(classification_status="pending")
    PostBrandClassificationState.objects.filter(post_id="native-1").update(selected_final_judgment=None)
    assert "native-1" in deferred_enrichment_work(native[0], max_attempts=3)
    return provider, latest


def _paid_history():
    return list(OriginalContentCall.objects.order_by("pk").values(
        "pk", "state", "request_identity", "request_hash", "request_packet",
        "response_hash", "response_payload", "reserved_usd", "actual_usd", "sent_at", "completed_at",
    ))


def _replay(native, ids):
    from monitor.backfill_enrichment import replay_rejected_classifier_packet
    return replay_rejected_classifier_packet(
        native[0].pk, call_ids=ids, post_ids=["native-1"], cfg=native[1], delegates=native[2],
        actor="test", reason="revalidate retained exact classifier packet",
    )


def test_replays_valid_saved_member_after_three_failures_without_payment(native):
    provider, ids = _rejected_packet(native)
    before = _paid_history()
    sibling = Post.objects.filter(pk="native-2").values().get()
    sibling_state = PostBrandClassificationState.objects.filter(post_id="native-2").values().get()
    sent = provider.sent
    result = _replay(native, ids)
    assert result["replayed"] == ["native-1"]
    assert all(f["translation"] and f["classification"] for f in completion_facts(["native-1", "native-2"]).values())
    assert _paid_history() == before and provider.sent == sent
    assert Post.objects.filter(pk="native-2").values().get() == sibling
    assert PostBrandClassificationState.objects.filter(post_id="native-2").values().get() == sibling_state
    for call in OriginalContentCall.objects.filter(pk__in=ids):
        assert call.import_state == "applied"
        audit = call.import_evidence["revalidation_history"][0]
        assert audit["previous_import_evidence"]["validation"] == "canonical_validation_failed"
        assert audit["selected_member_ids"] == ["native-1"]
    assert _replay(native, ids)["replayed"] == []
    assert all(len(c.import_evidence["revalidation_history"]) == 1 for c in OriginalContentCall.objects.filter(pk__in=ids))


@pytest.mark.parametrize("blocker", ["source_changed", "post_claim", "batch_claim", "sent", "unknown"])
def test_classifier_revalidation_rejects_changed_or_active_work(native, blocker):
    _, ids = _rejected_packet(native)
    if blocker == "source_changed":
        Post.objects.filter(pk="native-1").update(text="Changed source")
    elif blocker == "post_claim":
        PostEnrichmentState.objects.filter(pk="native-1").update(
            claim_owner="other", claim_expires_at=timezone.now() + timedelta(minutes=5),
        )
    elif blocker == "batch_claim":
        ProviderBatch.objects.filter(pk=OriginalContentCall.objects.get(pk=ids[0]).provider_batch_id).update(
            claim_expires_at=timezone.now() + timedelta(minutes=5),
        )
    else:
        OriginalContentCall.objects.filter(pk=ids[0]).update(
            state="sent" if blocker == "sent" else "ambiguous", completed_at=None,
        )
    before = _paid_history()
    with pytest.raises(BatchAdmissionError):
        _replay(native, ids)
    assert _paid_history() == before
    assert all(c.import_state == "error" and "revalidation_history" not in c.import_evidence for c in OriginalContentCall.objects.filter(pk__in=ids))


def test_invalid_saved_member_rolls_back_reopening_and_publication(native):
    _, ids = _rejected_packet(native)
    content = OriginalContentCall.objects.get(pk__in=ids, provenance__context__role="content")
    payload = copy.deepcopy(content.response_payload)
    value = json.loads(payload["choices"][0]["message"]["content"])
    value["decisions"]["D01"]["outcome"] = "invalid_outcome"
    payload["choices"][0]["message"]["content"] = json.dumps(value)
    OriginalContentCall.objects.filter(pk=content.pk).update(response_payload=payload, response_hash=digest(payload))
    before = _paid_history()
    with pytest.raises(BatchAdmissionError):
        _replay(native, ids)
    assert _paid_history() == before
    assert PostEnrichmentState.objects.get(pk="native-1").classification_status == "pending"
    assert all(c.import_state == "error" and "revalidation_history" not in c.import_evidence for c in OriginalContentCall.objects.filter(pk__in=ids))


def test_replayed_member_does_not_reset_failed_siblings_allowance(native):
    _, ids = _rejected_packet(native)
    PostEnrichmentState.objects.filter(pk="native-2").update(classification_status="pending")
    PostBrandClassificationState.objects.filter(post_id="native-2").update(selected_final_judgment=None)
    content = OriginalContentCall.objects.get(pk__in=ids, provenance__context__role="content")
    payload = copy.deepcopy(content.response_payload)
    value = json.loads(payload["choices"][0]["message"]["content"])
    value["decisions"]["D02"]["outcome"] = "invalid_outcome"
    payload["choices"][0]["message"]["content"] = json.dumps(value)
    OriginalContentCall.objects.filter(pk=content.pk).update(response_payload=payload, response_hash=digest(payload))
    before = _paid_history()
    assert _replay(native, ids)["remaining_packet_members"] == ["native-2"]
    assert _paid_history() == before
    facts = completion_facts(["native-1", "native-2"])
    assert facts["native-1"]["classification"] and not facts["native-2"]["classification"]
    assert "native-2" in deferred_enrichment_work(native[0], max_attempts=3)
    for call in OriginalContentCall.objects.filter(pk__in=ids):
        assert call.import_state == "error"
        assert call.import_evidence["complete_member_ids"] == ["native-1"]
        assert call.import_evidence["invalid_member_ids"] == ["native-2"]


def _unknown_call(native):
    from x_monitor.deepinfra import DeepInfraRetryableError

    class OneUnknown(DirectProvider):
        unknown = False

        def transport(self, body, timeout):
            with self.lock:
                if not self.unknown:
                    self.unknown = True
                    raise DeepInfraRetryableError("test_transport_outcome_unknown")
            return super().transport(body, timeout)

    provider = OneUnknown()
    run_direct(native, provider, initial=True)
    from monitor.backfill_direct import advance_direct
    for _ in range(4):
        groups = list(ProviderBatch.objects.filter(calls__state="reserved").distinct())
        if not groups:
            break
        for group in groups:
            advance_direct(group.pk, api_key="test", concurrency=2, client_factory=provider.factory)
    assert not OriginalContentCall.objects.filter(state="reserved").exists()
    call = OriginalContentCall.objects.get(state="ambiguous")
    receipt = {
        "id": "job-owned-controller", "status": "succeeded",
        "startedAt": (call.sent_at - timedelta(minutes=1)).isoformat(),
        "finishedAt": timezone.now().isoformat(),
    }
    return call, receipt


def _close_unknown(native, call, receipt):
    from monitor.backfill_enrichment import close_unrecoverable_direct_imports

    return close_unrecoverable_direct_imports(
        native[0].pk, call_ids=[call.pk], terminal_controller=receipt,
        actor="test-operator", reason="No saved reply after owned controller terminated",
    )


def test_explicit_unknown_import_closure_preserves_charge_and_allows_bounded_recovery(native):
    from monitor.backfill_enrichment import execute_enrichment

    call, receipt = _unknown_call(native)
    before = _paid_history()
    post_states = list(PostEnrichmentState.objects.order_by("pk").values())
    assert _close_unknown(native, call, receipt)["closed_imports"] == [call.pk]
    assert _paid_history() == before
    assert list(PostEnrichmentState.objects.order_by("pk").values()) == post_states
    assert _close_unknown(native, call, receipt)["closed_imports"] == []
    call.refresh_from_db()
    assert call.state == "ambiguous" and call.import_state == "error" and call.actual_usd is None
    audit = call.import_evidence["revalidation_history"]
    assert len(audit) == 1 and audit[0]["terminal_controller"] == receipt
    assert call.import_evidence["provider_outcome"] == "unknown"
    provider = DirectProvider()
    for _ in range(10):
        result = execute_enrichment(
            native[0].pk, cfg=native[1], delegates=native[2], api_key="test",
            transport="direct", direct_concurrency=2, direct_client_factory=provider.factory,
            defer_failures=True,
        )
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    assert result["ambiguous_model_requests"] == 1
    assert OriginalContentCall.objects.filter(request_hash=call.request_hash).count() == 2
    call.refresh_from_db()
    assert call.state == "ambiguous" and call.actual_usd is None
    assert all(b.policy["max_attempts"] == 3 for b in ProviderBatch.objects.all())


@pytest.mark.parametrize("blocker", ["post_claim", "group_claim", "response", "source", "live_controller", "wrong_interval"])
def test_unknown_import_closure_rejects_active_or_unverified_work(native, blocker):
    call, receipt = _unknown_call(native)
    if blocker == "post_claim":
        PostEnrichmentState.objects.filter(pk__in=call.member_post_ids).update(
            claim_owner="other", claim_expires_at=timezone.now() + timedelta(minutes=5),
        )
    elif blocker == "group_claim":
        ProviderBatch.objects.filter(pk=call.provider_batch_id).update(
            claim_expires_at=timezone.now() + timedelta(minutes=5),
        )
    elif blocker == "response":
        OriginalContentCall.objects.filter(pk=call.pk).update(response_payload={"saved": True})
    elif blocker == "source":
        Post.objects.filter(pk__in=call.member_post_ids).update(text="Changed source")
    elif blocker == "live_controller":
        receipt["status"] = "running"
    else:
        receipt["finishedAt"] = (call.sent_at - timedelta(seconds=1)).isoformat()
    before = list(OriginalContentCall.objects.order_by("pk").values())
    with pytest.raises(BatchAdmissionError):
        _close_unknown(native, call, receipt)
    assert list(OriginalContentCall.objects.order_by("pk").values()) == before
