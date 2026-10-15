"""Stop/resume through real admission, HTTP workers and PostgreSQL imports."""

import threading
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.utils import timezone

from core import provider_batches as ledger
from core.models import OriginalContentCall, ProviderBatch
from monitor import backfill_direct as direct
from tests.test_backfill_direct_enrichment import DirectProvider, run_direct
from tests.test_backfill_native_enrichment import native as native_fixture

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
native = native_fixture


def reserved_group(native, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(direct, "advance_direct", lambda *a, **k: None)
        run_direct(native, DirectProvider(), initial=True)
    return ProviderBatch.objects.order_by("created_at").first()


def control(native, action):
    return ledger.set_enrichment_control(
        native[0].pk, action=action, actor="test-owner", reason="safe handover"
    )


def test_pause_revokes_a_claim_before_real_caller_can_mark_or_send(native, monkeypatch):
    group = reserved_group(native, monkeypatch)
    provider = DirectProvider()
    original = direct.claim_batch
    first = ProviderBatch.objects.order_by("created_at").first()
    original_policy = dict(first.policy)
    saved = list(OriginalContentCall.objects.order_by("pk").values())

    def pause_after_claim(*args, **kwargs):
        claim = original(*args, **kwargs)
        result = control(native, "pause")
        assert result["processing_paused"] and result["safe_to_cancel"]
        return claim

    with monkeypatch.context() as patch:
        patch.setattr(direct, "claim_batch", pause_after_claim)
        with pytest.raises(ledger.StaleBatchClaim):
            direct.advance_direct(group.pk, api_key="test", client_factory=provider.factory)
    assert provider.sent == 0
    assert list(OriginalContentCall.objects.order_by("pk").values()) == saved
    first.refresh_from_db()
    assert {k: v for k, v in first.policy.items() if k != "processing_control"} == original_policy
    with pytest.raises(ledger.BatchAdmissionError, match="enrichment_paused"):
        direct.advance_direct(group.pk, api_key="test", client_factory=provider.factory)

    assert not control(native, "resume")["processing_paused"]
    for _ in range(15):
        result = run_direct(native, provider)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    assert result["persisted_output_invalid_count"] == 0
    sent = provider.sent
    assert run_direct(native, provider)["status"] == "completed"
    assert provider.sent == sent


def test_pause_drains_reply_then_stops_remaining_waves(native, monkeypatch):
    group = reserved_group(native, monkeypatch)
    entered, finish = threading.Event(), threading.Event()
    provider = DirectProvider()
    transport = provider.transport

    def held_reply(body, timeout):
        entered.set()
        assert finish.wait(10), "test did not release the admitted HTTP request"
        return transport(body, timeout)

    provider.transport = held_reply
    errors = []

    def worker():
        try:
            direct.advance_direct(group.pk, api_key="test", concurrency=1,
                                  client_factory=provider.factory)
        except Exception as exc:  # noqa: BLE001 — propagate worker failures to the assertion
            errors.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(10)
        admitted = OriginalContentCall.objects.get(state="sent")
        result = control(native, "pause")
        assert result["processing_paused"] and not result["safe_to_cancel"]
        assert result["sent_outstanding"] == 1
        with pytest.raises(ledger.BatchAdmissionError, match="enrichment_not_drained"):
            control(native, "resume")
    finally:
        finish.set()
        thread.join(15)
    assert not thread.is_alive() and not errors, errors
    admitted.refresh_from_db()
    assert admitted.state == "completed" and admitted.response_payload
    assert provider.sent == 1
    assert OriginalContentCall.objects.filter(state="reserved").exists()
    assert control(native, "pause")["safe_to_cancel"]
    assert not control(native, "resume")["processing_paused"]
    for _ in range(15):
        result = run_direct(native, provider, concurrency=2)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    assert OriginalContentCall.objects.get(pk=admitted.pk).request_identity == admitted.request_identity
    assert provider.sent == result["direct_model_requests_sent"]


def test_control_command_needs_no_provider_keys_and_status_is_read_only(native, monkeypatch):
    reserved_group(native, monkeypatch)
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    for key in ["TWITTERAPI_IO_ON_DEMAND_API_KEY", "TWITTERAPI_IO_SCHEDULED_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    before = list(ProviderBatch.objects.order_by("pk").values())
    out = StringIO()
    call_command("backfill", collection_job=str(native[0].pk),
                 enrichment_control="status", stdout=out)
    assert '"processing_paused": false' in out.getvalue()
    assert list(ProviderBatch.objects.order_by("pk").values()) == before
    with pytest.raises(CommandError, match="actor.*reason"):
        call_command("backfill", collection_job=str(native[0].pk),
                     enrichment_control="pause", stdout=StringIO())
    for action in ["pause", "resume"]:
        call_command("backfill", collection_job=str(native[0].pk),
                     enrichment_control=action, enrichment_actor="test-owner",
                     enrichment_reason="safe handover", stdout=StringIO())
    assert not ledger.enrichment_control_status(native[0].pk)["processing_paused"]


def test_pause_does_not_reclassify_or_refund_an_unknown_request(native, monkeypatch):
    reserved_group(native, monkeypatch)
    call = OriginalContentCall.objects.order_by("pk").first()
    call.state = "ambiguous"
    call.error_code = "direct_outcome_unknown"
    call.sent_at = timezone.now()
    call.save(update_fields=["state", "error_code", "sent_at"])
    before = OriginalContentCall.objects.values().get(pk=call.pk)
    assert control(native, "pause")["safe_to_cancel"]
    control(native, "resume")
    assert OriginalContentCall.objects.values().get(pk=call.pk) == before


def test_paused_real_preparation_does_not_change_posts_or_paid_work(native, monkeypatch):
    from core.models import Post, PostEnrichmentState

    reserved_group(native, monkeypatch)
    control(native, "pause")
    before = [list(model.objects.order_by("pk").values()) for model in
              [Post, PostEnrichmentState, OriginalContentCall, ProviderBatch]]
    provider = DirectProvider()
    result = run_direct(native, provider)
    assert result["processing_paused"] and result["safe_to_cancel"]
    assert provider.sent == 0
    assert before == [list(model.objects.order_by("pk").values()) for model in
                      [Post, PostEnrichmentState, OriginalContentCall, ProviderBatch]]


def test_active_native_batch_pause_is_explicitly_rejected_without_rewriting_it(native):
    from tests.test_backfill_native_enrichment import advance

    advance(native, initial=True)
    before = list(ProviderBatch.objects.order_by("pk").values())
    with pytest.raises(ledger.BatchAdmissionError, match="native_batch_requires_remote_drain"):
        control(native, "pause")
    assert list(ProviderBatch.objects.order_by("pk").values()) == before
    # Existing remote work still imports normally; local pause never pretends
    # that it cancelled a paid remote native batch.
    assert advance(native)["status"] == "completed"
