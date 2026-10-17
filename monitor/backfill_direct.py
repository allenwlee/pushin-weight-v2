"""Bounded ordinary inference over the existing durable provider-call ledger."""

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.utils import timezone

from core.models import ProviderBatch
from core.provider_batches import (
    BatchAdmissionError,
    StaleBatchClaim,
    claim_batch,
    enrichment_paused,
    fenced_batch,
    import_response,
    release_batch,
)
from x_monitor.deepinfra import (
    DeepInfraChatCompletionsClient,
    DeepInfraPermanentError,
    DeepInfraRetryableError,
)


def validate_concurrency(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 128:
        raise BatchAdmissionError("direct_concurrency_invalid")


def advance_direct(batch_id, *, api_key, concurrency=32, client_factory=None):
    """Drain at most eight bounded waves before preparing another Post page."""
    validate_concurrency(concurrency)
    for _ in range(8):
        _advance_direct_wave(
            batch_id, api_key=api_key, concurrency=concurrency,
            client_factory=client_factory,
        )
        group = ProviderBatch.objects.only("state", "next_poll_at", "source_collection_job_id").get(pk=batch_id)
        if enrichment_paused(group.source_collection_job_id) or group.state != "registered" or (
            group.next_poll_at and group.next_poll_at > timezone.now()
        ):
            return


def _advance_direct_wave(batch_id, *, api_key, concurrency, client_factory):
    """Send one wave; workers only perform HTTP, the controller owns DB writes.

    Sent requests without a saved reply remain ambiguous after interruption.
    They are never automatically sent again. Unstarted reservations can resume.
    """
    validate_concurrency(concurrency)
    claim = claim_batch(batch_id, owner=f"direct:{uuid.uuid4().hex}", seconds=300)
    try:
        batch = ProviderBatch.objects.get(pk=batch_id)
        if batch.transport != "direct":
            raise BatchAdmissionError("direct_transport_mismatch")
        if batch.next_poll_at and batch.next_poll_at > timezone.now():
            return
        factory = client_factory or DeepInfraChatCompletionsClient
        client = factory(
            api_key=api_key, model=batch.model, request_profile=batch.request_profile
        )
        with fenced_batch(claim, for_start=True) as row:
            # No other controller can own this group's unexpired fence.
            row.calls.filter(state="sent").update(
                state="ambiguous",
                error_code="direct_interrupted_outcome_unknown",
            )
            calls = list(
                row.calls.filter(state="reserved").order_by("request_identity")[
                    :concurrency
                ]
            )
            for call in calls:
                if client.build_request(**call.request_packet) != call.request_packet:
                    raise BatchAdmissionError("direct_request_profile_changed")
            row.calls.filter(pk__in=[c.pk for c in calls], state="reserved").update(
                state="sent",
                sent_at=timezone.now(),
            )
            row.state = "waiting"
            row.next_poll_at = None
            row.save(update_fields=["state", "next_poll_at", "updated_at"])

        # The committed reservations/sent markers precede every network start.
        # At most one wave of response bodies is held in memory. No worker ORM.
        throttled = False
        provider_admission_failure = None
        if calls:
            timeout = max(
                1, min(120, (batch.deadline_at - timezone.now()).total_seconds())
            )
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {
                    pool.submit(
                        client._send_request, c.request_packet, timeout=timeout
                    ): c
                    for c in calls
                }
                for future in as_completed(futures):
                    call = futures[future]
                    try:
                        body = future.result()
                    except (DeepInfraPermanentError, DeepInfraRetryableError) as exc:
                        code = str(exc)
                        prefix = "deepinfra_http_status_"
                        status = (
                            int(code[len(prefix) :])
                            if (
                                code.startswith(prefix)
                                and code[len(prefix) :].isdigit()
                            )
                            else None
                        )
                        if status is None and isinstance(exc, DeepInfraRetryableError):
                            with fenced_batch(
                                claim, allow_expired_deadline=True
                            ) as row:
                                row.calls.filter(pk=call.pk, state="sent").update(
                                    state="ambiguous",
                                    error_code="direct_outcome_unknown",
                                    import_evidence={
                                        "transport": "direct",
                                        "reason": code,
                                    },
                                )
                            continue
                        throttled |= status == 429 or (
                            status is not None and status >= 500
                        )
                        if status in {401, 402, 403}:
                            provider_admission_failure = status
                        envelope = {
                            "custom_id": call.request_identity,
                            "response": {"status_code": status},
                            "error": {"code": code},
                        }
                    else:
                        envelope = {
                            "custom_id": call.request_identity,
                            "response": {"status_code": 200, "body": body},
                        }
                    import_response(claim, envelope)
        with fenced_batch(claim, allow_expired_deadline=True) as row:
            ambiguous = row.calls.filter(state="ambiguous").exists()
            reserved = row.calls.filter(state="reserved").exists()
            if ambiguous:
                row.state = "ambiguous"
                row.error_code = "direct_outcome_unknown"
            elif reserved or throttled:
                row.state = "registered"
            else:
                row.state = (
                    "failed"
                    if row.calls.exclude(state="completed").exists()
                    else "completed"
                )
                row.completed_at = timezone.now()
            if throttled:
                row.next_poll_at = timezone.now() + timedelta(seconds=30)
                row.error_code = "direct_provider_retry_backoff"
            row.save(
                update_fields=[
                    "state",
                    "error_code",
                    "completed_at",
                    "next_poll_at",
                    "updated_at",
                ]
            )
        if provider_admission_failure is not None:
            # Every response from this already-sent wave is durable before the
            # controller stops. No later wave may repeat a bad credential.
            raise BatchAdmissionError(
                f"enrichment_provider_admission_http_{provider_admission_failure}"
            )
    finally:
        try:
            release_batch(claim)
        except StaleBatchClaim:
            # A completed drain may already have invalidated this ownership.
            # Preserve an exception from the actual operation, if there is one.
            pass
