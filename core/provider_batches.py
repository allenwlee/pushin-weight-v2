"""Durable provider groups, physical request reservations and result import.

All helpers commit before their caller starts HTTP. No source collection lease
or Post claim is held across provider execution. Control HTTP is counted on the
group; inference is charged exactly once on each physical child request.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_UP, Decimal
from typing import Any

from django.db import connection, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from core.models import (
    CollectionJob,
    CollectionObservation,
    OriginalContentCall,
    Post,
    PostEnrichmentState,
    ProviderBatch,
)
from x_monitor.provider_telemetry import normalize_usage


class BatchAdmissionError(RuntimeError):
    pass


class StaleBatchClaim(RuntimeError):
    pass


def enrichment_paused(job_id):
    """The oldest execution record owns mutable campaign control, not instructions."""
    policy = (
        ProviderBatch.objects.filter(source_collection_job_id=job_id)
        .order_by("created_at", "pk").values_list("policy", flat=True).first()
    )
    return bool((policy or {}).get("processing_control", {}).get("paused", False))


def assert_enrichment_admission(job_id):
    # Call while holding the CollectionJob row, before committing a paid start.
    if enrichment_paused(job_id):
        raise BatchAdmissionError("enrichment_paused")


def enrichment_policy_definition(policy):
    """Operator control is mutable; all request/budget/configuration pins remain fixed."""
    return {k: v for k, v in policy.items() if k != "processing_control"}


def enrichment_control_status(job_id):
    job = CollectionJob.objects.get(pk=job_id)
    if (job.source_id, job.purpose, job.operation) != ("x", "content", "x_backfill"):
        raise BatchAdmissionError("enrichment_requires_real_x_backfill_job")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(),current_user")
        name, role = cursor.fetchone()
    if job.definition.get("scope", {}).get("database") != {"name": name, "user": role}:
        raise BatchAdmissionError("enrichment_database_identity_mismatch")
    batches = job.provider_batches.all()
    first = batches.order_by("created_at", "pk").first()
    control = (first.policy if first else {}).get("processing_control", {})
    sent = OriginalContentCall.objects.filter(provider_batch__source_collection_job=job,
                                               state="sent").count()
    claims = batches.filter(claim_expires_at__gt=timezone.now()).count()
    # Local stopping must never masquerade as remote native-batch cancellation.
    native = batches.filter(transport="batch", state__in=[
        "uploading", "uploaded", "submitting", "waiting", "ambiguous", "importing",
    ]).count()
    paused = bool(control.get("paused", False))
    return {
        "source_collection_job": str(job.pk),
        "processing_paused": paused,
        "sent_outstanding": sent,
        "active_processing_claims": claims,
        "native_groups_outstanding": native,
        "safe_to_cancel": paused and sent == 0 and claims == 0 and native == 0,
        "control_generation": control.get("generation", 0),
    }


def set_enrichment_control(job_id, *, action, actor, reason):
    """Pause admission, drain paid work, revoke old claims, then permit cancellation.

    Reissue pause after draining, cancel only the old owned runner, verify it is
    terminal, then resume. No external call or wait occurs inside this transaction.
    """
    if action not in {"pause", "resume"} or not actor.strip() or not reason.strip():
        raise BatchAdmissionError("enrichment_control_requires_action_actor_reason")
    if len(actor) > 160 or len(reason) > 1000:
        raise BatchAdmissionError("enrichment_control_audit_too_large")
    with transaction.atomic():
        job = CollectionJob.objects.select_for_update().get(pk=job_id)
        status = enrichment_control_status(job.pk)
        batches = job.provider_batches.all()
        first = batches.select_for_update().order_by("created_at", "pk").first()
        if first is None:
            raise BatchAdmissionError("enrichment_not_registered")
        paused = action == "pause"
        if paused and status["native_groups_outstanding"]:
            raise BatchAdmissionError("native_batch_requires_remote_drain")
        if action == "resume" and not status["processing_paused"]:
            return status
        if action == "resume" and status["processing_paused"] and (
            status["sent_outstanding"] or status["native_groups_outstanding"]
        ):
            raise BatchAdmissionError("enrichment_not_drained")
        now = timezone.now()
        revoked = 0
        if status["sent_outstanding"] == 0 and status["native_groups_outstanding"] == 0:
            revoked = batches.filter(claim_expires_at__gt=now).update(
                claim_fence=F("claim_fence") + 1, claim_expires_at=now,
            )
        previous = first.policy.get("processing_control", {})
        event = {"action": action, "actor": actor.strip(), "reason": reason.strip(),
                 "at": now.isoformat(), "revoked_claims": revoked}
        first.policy = first.policy | {"processing_control": {
            "paused": paused,
            "generation": previous.get("generation", 0) + (paused != status["processing_paused"]),
            "history": [*previous.get("history", [])[-19:], event],
        }}
        first.save(update_fields=["policy", "updated_at"])
        return enrichment_control_status(job.pk)


@contextmanager
def _locked_batch(batch_id):
    """Every admission/control path locks campaign before group, consistently."""
    with transaction.atomic():
        job_id = ProviderBatch.objects.values_list("source_collection_job_id", flat=True).get(pk=batch_id)
        job = CollectionJob.objects.select_for_update().get(pk=job_id)
        batch = ProviderBatch.objects.select_for_update().get(pk=batch_id)
        if batch.source_collection_job_id != job.pk:
            raise StaleBatchClaim("batch_source_definition_changed")
        yield job, batch


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def record_post_membership(run, scope, post_ids, *, observed_at=None):
    """Call inside the fenced page transaction, after Post writes succeeded."""
    if not transaction.get_connection().in_atomic_block:
        raise BatchAdmissionError("membership_requires_fenced_page_transaction")
    if not run.job_id or run.job.purpose != "content" or run.job.source_id != "x":
        raise BatchAdmissionError("membership_requires_real_x_collection")
    if scope is not None and scope.run_id != run.pk:
        raise BatchAdmissionError("membership_scope_run_mismatch")
    ids = sorted({str(value) for value in post_ids})
    if len(ids) > 10000 or Post.objects.filter(pk__in=ids).count() != len(ids):
        raise BatchAdmissionError("membership_posts_missing_or_page_too_large")
    CollectionObservation.objects.bulk_create(
        [
            CollectionObservation(
                run=run,
                scope_run=scope,
                post_id=post_id,
                source_identifier=post_id,
                source_subject_kind="post",
                observation_key=digest({"post": post_id}),
                observed_at=observed_at or timezone.now(),
            )
            for post_id in ids
        ],
        ignore_conflicts=True,
    )
    now = timezone.now()
    PostEnrichmentState.objects.filter(
        Q(translation_status="pending") | Q(classification_status="pending"),
        Q(claim_expires_at__isnull=True) | Q(claim_expires_at__lte=now),
        post_id__in=ids,
        source_collection_job__isnull=True,
    ).update(source_collection_job_id=run.job_id)


def own_historical_posts(job, post_ids):
    ids = sorted({str(value) for value in post_ids})
    if not 0 < len(ids) <= 100:
        raise BatchAdmissionError("historical_ownership_page_limit")
    with transaction.atomic():
        members = set(
            CollectionObservation.objects.filter(
                run__job=job,
                source_subject_kind="post",
                post_id__in=ids,
            ).values_list("post_id", flat=True)
        )
        if members != set(ids):
            raise BatchAdmissionError("historical_membership_missing")
        states = list(
            PostEnrichmentState.objects.select_for_update().filter(post_id__in=ids)
        )
        now = timezone.now()
        if len(states) != len(ids) or any(
            s.claim_expires_at and s.claim_expires_at > now for s in states
        ):
            raise BatchAdmissionError("historical_state_missing_or_claimed")
        if any(s.source_collection_job_id not in {None, job.pk} for s in states):
            outstanding = OriginalContentCall.objects.filter(
                member_post_ids__overlap=ids,
                import_state="pending",
                state__in=["reserved", "sent", "ambiguous", "completed"],
            )
            if outstanding.exists():
                raise BatchAdmissionError("historical_state_owned_elsewhere")
        PostEnrichmentState.objects.filter(post_id__in=ids).update(
            source_collection_job=job
        )


@dataclass(frozen=True)
class BatchClaim:
    batch_id: Any
    owner: str
    fence: int


def claim_batch(batch_id, *, owner, seconds=180):
    if not owner or len(owner) > 128 or not 1 <= seconds <= 300:
        raise BatchAdmissionError("invalid_batch_claim")
    with _locked_batch(batch_id) as (job, batch):
        assert_enrichment_admission(job.pk)
        now = timezone.now()
        if batch.claim_expires_at and batch.claim_expires_at > now:
            if batch.claim_owner == owner:
                return BatchClaim(batch.pk, owner, batch.claim_fence)
            raise StaleBatchClaim("batch_claim_busy")
        batch.claim_owner = owner
        batch.claim_fence += 1
        batch.claimed_at = now
        batch.claim_expires_at = now + timedelta(seconds=seconds)
        batch.save(
            update_fields=[
                "claim_owner",
                "claim_fence",
                "claimed_at",
                "claim_expires_at",
                "updated_at",
            ]
        )
        return BatchClaim(batch.pk, owner, batch.claim_fence)


@contextmanager
def fenced_batch(claim, *, allow_expired_deadline=False, for_start=False):
    with _locked_batch(claim.batch_id) as (job, batch):
        now = timezone.now()
        if (
            batch.claim_owner != claim.owner
            or batch.claim_fence != claim.fence
            or not batch.claim_expires_at
            or batch.claim_expires_at <= now
        ):
            raise StaleBatchClaim("batch_claim_stale")
        if (
            job.source_id != "x"
            or job.purpose != "content"
            or job.definition_sha256 != batch.source_definition_hash
        ):
            raise StaleBatchClaim("batch_source_definition_changed")
        if not allow_expired_deadline and batch.deadline_at <= now:
            raise BatchAdmissionError("batch_deadline_exhausted")
        if for_start:
            assert_enrichment_admission(job.pk)
        yield batch


def release_batch(claim):
    with fenced_batch(claim, allow_expired_deadline=True) as batch:
        # Keep the increasing fence after release; a stale holder can never
        # become valid again when another worker takes this row.
        batch.claim_expires_at = timezone.now()
        batch.save(update_fields=["claim_expires_at", "updated_at"])


def control_start(claim, method, path):
    with fenced_batch(claim, allow_expired_deadline=method == "GET", for_start=method != "GET") as batch:
        CollectionJob.objects.select_for_update().get(pk=batch.source_collection_job_id)
        count = (
            ProviderBatch.objects.filter(
                source_collection_job=batch.source_collection_job
            ).aggregate(n=Sum("control_requests"))["n"]
            or 0
        )
        if count >= int(batch.policy["max_control_requests"]):
            raise BatchAdmissionError("batch_control_allowance_exhausted")
        batch.control_requests += 1
        batch.control_evidence = [
            *batch.control_evidence[-63:],
            {
                "sequence": batch.control_requests,
                "method": method,
                "path": path,
                "started_at": timezone.now().isoformat(),
            },
        ]
        batch.save(update_fields=["control_requests", "control_evidence", "updated_at"])


def conservative_reservation(body, prices):
    """UTF-8 bytes upper-bound token input; use the full output allowance."""
    if body["model"] not in prices:
        raise BatchAdmissionError("model_price_missing")
    input_rate, output_rate = (Decimal(str(v)) for v in prices[body["model"]])
    input_bound = len(json.dumps(body, ensure_ascii=False).encode()) + 1024
    output_bound = int(body.get("max_tokens", body.get("max_completion_tokens", 0)))
    if output_bound <= 0:
        raise BatchAdmissionError("model_output_allowance_missing")
    cost = (input_bound * input_rate + output_bound * output_rate) / Decimal(1000000)
    return (
        cost.quantize(Decimal("0.000001"), rounding=ROUND_UP),
        input_bound,
        output_bound,
    )


def post_snapshot(post):
    return digest(
        {
            "text": post.text,
            "lang": post.lang,
            "reply": post.in_reply_to_id,
            "quoted": post.quoted_status_id_id,
            "quoted_text": post.quoted_text,
            "brands": sorted(row.brand_id for row in post.brands.all()),
            "entities": post.entities,
        }
    )


def reserve_requests(claim, requests):
    """Register each physical attempt once, retaining failed/unknown charges."""
    requests = list(requests)
    if not 0 < len(requests) <= 2000:
        raise BatchAdmissionError("batch_request_limit")
    with fenced_batch(claim, for_start=True) as batch:
        job = CollectionJob.objects.select_for_update().get(
            pk=batch.source_collection_job_id
        )
        all_members = sorted(
            {str(p) for r in requests for p in r["context"]["post_ids"]}
        )
        if len(all_members) > 2000:
            raise BatchAdmissionError("batch_post_page_limit")
        # Locks also serialize overlapping campaign reservations, rather than
        # relying on an expiring per-Post worker claim for paid deduplication.
        posts = list(
            Post.objects.select_for_update()
            .filter(pk__in=all_members)
            .prefetch_related("brands")
            .order_by("pk")
        )
        snapshots = {str(p.pk): post_snapshot(p) for p in posts}
        members = set(
            CollectionObservation.objects.filter(
                run__job=job, post_id__in=all_members
            ).values_list("post_id", flat=True)
        )
        if len(posts) != len(all_members) or members != set(all_members):
            raise BatchAdmissionError("batch_membership_missing")
        if PostEnrichmentState.objects.filter(
            post_id__in=all_members, source_collection_job=job
        ).count() != len(all_members):
            raise BatchAdmissionError("batch_historical_ownership_missing")
        calls = OriginalContentCall.objects.filter(
            provider_batch__source_collection_job=job
        )
        totals = calls.aggregate(count=Count("pk"), reserved=Sum("reserved_usd"))
        count, reserved = totals["count"], totals["reserved"] or Decimal(0)
        created = []
        for request in requests:
            logical_hash, body, context = (
                request["hash"],
                request["body"],
                request["context"],
            )
            ids = sorted({str(p) for p in context["post_ids"]})
            if not 0 < len(ids) <= 20 or body["model"] != batch.model:
                raise BatchAdmissionError("request_member_or_model_mismatch")
            if request.get("snapshots") != {p: snapshots[p] for p in ids}:
                raise BatchAdmissionError("request_source_changed_before_reservation")
            if (
                OriginalContentCall.objects.filter(
                    request_hash=logical_hash, member_post_ids__overlap=ids
                )
                .exclude(state="failed")
                .exclude(import_state__in=["stale", "error"])
                .exists()
            ):
                raise BatchAdmissionError(
                    "model_request_already_outstanding_or_complete"
                )
            pending = OriginalContentCall.objects.filter(
                model=batch.model,
                stage=context["stage"],
                member_post_ids__overlap=ids,
                import_state="pending",
                state__in=["reserved", "sent", "ambiguous", "completed"],
            )
            for previous in pending.only("provenance", "member_post_ids"):
                old = previous.provenance.get("context", {})
                if any(
                    old.get(k) != context.get(k)
                    for k in ("role", "target_language", "chunk_index", "operation")
                ):
                    continue
                overlap = set(ids) & set(previous.member_post_ids)
                if context["stage"] == "classification":
                    same = any(
                        old.get("input_fingerprints", {}).get(p)
                        == context.get("input_fingerprints", {}).get(p)
                        for p in overlap
                    )
                else:
                    same = old.get("source_fingerprint") == context.get(
                        "source_fingerprint"
                    )
                if same:
                    raise BatchAdmissionError("model_member_work_already_outstanding")
            attempt = calls.filter(request_hash=logical_hash).count() + 1
            if attempt > int(batch.policy["max_attempts"]):
                raise BatchAdmissionError("model_attempt_allowance_exhausted")
            usd, input_bound, output_bound = conservative_reservation(
                body, batch.policy["prices"]
            )
            count += 1
            reserved += usd
            if count > int(batch.policy["max_model_requests"]) or reserved > Decimal(
                batch.policy["max_usd"]
            ):
                raise BatchAdmissionError("model_campaign_allowance_exhausted")
            identity = digest(
                {"job": str(job.pk), "request": logical_hash, "attempt": attempt}
            )
            created.append(
                OriginalContentCall.objects.create(
                    provider_batch=batch,
                    stage=context["stage"],
                    batch_key=f"{logical_hash}:{attempt}",
                    request_identity=identity,
                    request_hash=logical_hash,
                    member_post_ids=ids,
                    import_state="pending",
                    provider=batch.provider,
                    model=batch.model,
                    budget_scope=f"backfill:{job.pk}",
                    budget_day=timezone.now().date(),
                    reserved_usd=usd,
                    reserved_at=timezone.now(),
                    request_packet=body,
                    provenance={
                        "response_kind": request["kind"],
                        "context": context,
                        "attempt": attempt,
                        "input_token_bound": input_bound,
                        "output_token_bound": output_bound,
                        "request_profile": batch.request_profile,
                        "admission_max_usd": batch.policy["max_usd"],
                        "post_snapshots": {p: snapshots[p] for p in ids},
                    },
                )
            )
        batch.request_count += len(created)
        batch.save(update_fields=["request_count", "updated_at"])
        return created


def mark_submitting(claim):
    with fenced_batch(claim, for_start=True) as batch:
        if batch.state != "uploaded" or not batch.input_file_id:
            raise BatchAdmissionError("batch_not_uploaded")
        now = timezone.now()
        batch.calls.filter(state="reserved").update(state="sent", sent_at=now)
        batch.state = "submitting"
        batch.save(update_fields=["state", "updated_at"])


def import_response(claim, output):
    identity = output.get("custom_id")
    with fenced_batch(claim, allow_expired_deadline=True) as batch:
        try:
            call = batch.calls.select_for_update().get(request_identity=identity)
        except OriginalContentCall.DoesNotExist:
            raise BatchAdmissionError("batch_output_identity_unknown") from None
        response_hash = digest(output)
        if call.state == "completed":
            if call.response_hash != response_hash:
                raise BatchAdmissionError("batch_output_duplicate_conflict")
            return False
        if call.state == "failed" and call.import_evidence.get("output_hash"):
            if call.import_evidence["output_hash"] != response_hash:
                raise BatchAdmissionError("batch_output_duplicate_conflict")
            return False
        if call.state not in {"sent", "ambiguous"}:
            raise BatchAdmissionError("batch_output_request_not_sent")
        response = output.get("response") or {}
        body = response.get("body")
        if (
            output.get("error")
            or response.get("status_code") != 200
            or not isinstance(body, dict)
        ):
            call.state = "failed"
            call.import_state = "error"
            call.error_code = "provider_batch_request_failed"
            call.import_evidence = {
                "output_hash": response_hash,
                "status_code": response.get("status_code"),
            }
        else:
            call.state = "completed"
            call.completed_at = timezone.now()
            call.response_hash = response_hash
            call.response_payload = body
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            normalized = normalize_usage(
                {
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "cost_usd": usage.get("estimated_cost", usage.get("cost")),
                }
            )
            call.input_tokens = normalized["input_tokens"] or 0
            call.output_tokens = normalized["output_tokens"] or 0
            actual = normalized["cost_usd"]
            if actual is not None:
                value = Decimal(str(actual))
                if value.is_finite() and value >= 0:
                    call.actual_usd = value
            call.import_evidence = {
                "cost_kind": "unknown"
                if call.actual_usd is None
                else "provider_reported_estimate"
                if "estimated_cost" in usage
                else "provider_reported",
                "usage_unknown": normalized["input_tokens"] is None
                or normalized["output_tokens"] is None,
            }
            snapshots = {
                str(p.pk): post_snapshot(p)
                for p in Post.objects.filter(
                    pk__in=call.member_post_ids
                ).prefetch_related("brands")
            }
            if snapshots != call.provenance.get("post_snapshots"):
                call.import_state = "stale"
                call.import_evidence["reason"] = "source_changed_while_waiting"
        call.save()
        batch.imported_count += 1
        batch.import_cursor = identity
        batch.save(update_fields=["imported_count", "import_cursor", "updated_at"])
        return True
