"""Explicit corrected-input recovery over the shared backfill paid-call ledger.

``canonical-contract-recovery-v1`` specs carry per-Post validation feedback.
A ``final-attempt-grant-v1`` document gives listed exhausted, still-incomplete
Posts exactly one more physical request per request hash. The grant's checksum,
actor and reason are recorded in each new call's provenance; the frozen policy,
earlier attempts and campaign limits stay unchanged.
"""

from __future__ import annotations

import functools
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from core.models import CollectionJob, OriginalContentCall, Post
from core.provider_batches import (
    BatchAdmissionError,
    conservative_reservation,
    digest,
    post_snapshot,
)
from monitor.backfill_direct import advance_direct, validate_concurrency
from monitor.backfill_enrichment import (
    _cached_reply_valid,
    _locked_drained_revalidation_job,
    _register_requests,
    completion_facts,
    configuration_pin,
    deferred_enrichment_work,
    prepare_page,
)
from scripts.backfill_targeted import OPERATION, _prepare, incomplete_roles
from x_monitor.corrected_inference import (
    GRANT_VERSION,
    VERSION,
    CorrectedInferenceClient,
    body_digest,
)
from x_monitor.reattribute import (
    build_classifier_client_from_env,
    build_relevancy_client_from_env,
    build_translator_client_from_env,
)

_GRANT_FIELDS = frozenset({"version", "job_id", "phase", "posts"})
_GRANT_OPTIONAL_FIELDS = frozenset({"actor", "reason", "feedback"})
_GRANT_POST_FIELDS = frozenset({"post_id", "prior_call_ids", "source_snapshot"})
# One wave never prepares more requests than corrected recovery admits.
_WAVE_REQUESTS = 64


def grant_specs(grant):
    """Validate one final-attempt grant document without reading the database.

    Returns an internal per-Post spec for every listed Post and the grant
    header (checksum, actor, reason) that each granted request records.
    Unknown keys are refused, so any schema change needs a new version.
    """
    if (
        not isinstance(grant, dict) or grant.get("version") != GRANT_VERSION
        or not _GRANT_FIELDS <= set(grant)
        or not set(grant) <= _GRANT_FIELDS | _GRANT_OPTIONAL_FIELDS
        or not isinstance(grant["job_id"], str) or not grant["job_id"]
        or grant["phase"] not in {"base", "targeted"}
    ):
        raise BatchAdmissionError("final_attempt_grant_spec_invalid")
    actor, reason = grant.get("actor"), grant.get("reason")
    if not all(isinstance(value, str) and value.strip() for value in (actor, reason)):
        raise BatchAdmissionError("final_attempt_grant_requires_actor_and_reason")
    if len(actor) > 160 or len(reason) > 1000:
        raise BatchAdmissionError("final_attempt_grant_audit_too_large")
    posts = grant["posts"]
    if not isinstance(posts, list) or not 0 < len(posts) <= 50:
        raise BatchAdmissionError("final_attempt_grant_requires_bounded_distinct_posts")
    feedback = grant.get("feedback")
    if "feedback" in grant and (
        not isinstance(feedback, str) or not feedback.strip() or len(feedback) > 12_000
    ):
        raise BatchAdmissionError("final_attempt_grant_spec_invalid")
    for entry in posts:
        ids = entry.get("prior_call_ids") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict) or set(entry) != _GRANT_POST_FIELDS
            or not isinstance(entry["post_id"], str) or not entry["post_id"]
            or not isinstance(ids, list) or not 0 < len(ids) <= 100
            or any(isinstance(i, bool) or not isinstance(i, int) for i in ids)
            or len(set(ids)) != len(ids)
            or not isinstance(entry["source_snapshot"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry["source_snapshot"])
        ):
            raise BatchAdmissionError("final_attempt_grant_spec_invalid")
    if len({entry["post_id"] for entry in posts}) != len(posts):
        raise BatchAdmissionError("final_attempt_grant_requires_bounded_distinct_posts")
    header = {
        "version": GRANT_VERSION, "grant_sha256": digest(grant), "job_id": grant["job_id"],
        "phase": grant["phase"], "actor": actor.strip(), "reason": reason.strip(),
        "feedback": feedback,
    }
    specs = [
        {
            "version": GRANT_VERSION, "job_id": grant["job_id"], "phase": grant["phase"],
            **entry, **({"feedback": feedback} if feedback is not None else {}),
        }
        for entry in posts
    ]
    return specs, header


def _refusal(code, post_id):
    return BatchAdmissionError(code, member_ids=[post_id])


def _validate_grant_post(job, spec, *, grant_sha256, cfg, deferred):
    """Admit one listed Post into a grant; every refusal names that Post."""
    identifier = spec["post_id"]
    post = Post.objects.prefetch_related("brands").filter(pk=identifier).first()
    if post is None:
        raise _refusal("final_attempt_grant_spec_invalid", identifier)
    if post_snapshot(post) != spec["source_snapshot"]:
        raise _refusal("contract_recovery_source_changed", identifier)
    previous = list(OriginalContentCall.objects.filter(
        pk__in=spec["prior_call_ids"], provider_batch__source_collection_job=job,
    ))
    if any(c.provenance.get("context", {}).get("recovery") for c in previous):
        # No recovery chains from an earlier recovery without a new decision.
        raise _refusal("final_attempt_grant_chained_recovery", identifier)
    if len(previous) != len(spec["prior_call_ids"]) or any(
        identifier not in c.member_post_ids or c.state not in {"completed", "failed"}
        or c.import_state != "error"
        or c.provenance.get("post_snapshots", {}).get(identifier) != spec["source_snapshot"]
        for c in previous
    ):
        raise _refusal("contract_recovery_prior_failure_invalid", identifier)
    granted = OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=job, member_post_ids__contains=[identifier],
        provenance__context__recovery__version=GRANT_VERSION,
    )
    if granted.filter(
        state__in=["reserved", "sent", "ambiguous"], import_state="pending",
    ).exists():
        raise _refusal("final_attempt_grant_outstanding", identifier)
    if granted.filter(provenance__context__recovery__grant_sha256=grant_sha256).exists():
        # Admitted when this grant first ran; its one-request cap now decides.
        return post, previous
    if deferred.get(identifier) == "provider_outcome_unknown":
        raise _refusal("final_attempt_grant_provider_outcome_unknown", identifier)
    complete = completion_facts([identifier])[identifier]
    if (
        spec["phase"] == "base" and complete["translation"] and complete["classification"]
        or spec["phase"] == "targeted" and not incomplete_roles(post, cfg)
    ):
        raise _refusal("final_attempt_grant_post_complete", identifier)
    if deferred.get(identifier) != "model_attempt_allowance_exhausted":
        raise _refusal("final_attempt_grant_post_not_exhausted", identifier)
    identical_body = spec["phase"] == "targeted" or not complete["translation"]
    if identical_body and "feedback" not in spec and not any(
        c.state == "failed" and (
            c.provenance.get("context", {}).get("operation") == OPERATION
            if spec["phase"] == "targeted" else c.stage == "translation"
        )
        for c in previous
    ):
        # Translation and targeted retries resend an identical body. Without
        # feedback, only a provider-side failure makes that retry informative.
        raise _refusal("final_attempt_grant_requires_feedback", identifier)
    return post, previous


def _validate_spec(job, spec, *, admission=None):
    if spec.get("version") == GRANT_VERSION and admission is not None:
        return _validate_grant_post(job, spec, **admission)
    if (
        spec.get("version") != VERSION or spec.get("job_id") != str(job.pk)
        or spec.get("phase") not in {"base", "targeted"}
        or not isinstance(spec.get("feedback"), str)
        or not spec["feedback"].strip() or len(spec["feedback"]) > 12_000
        or "translation_feedback" in spec and (
            not isinstance(spec["translation_feedback"], str)
            or not spec["translation_feedback"].strip() or len(spec["translation_feedback"]) > 12_000
        )
        or not 0 < len(set(spec.get("prior_call_ids", []))) <= 100
        or spec.get("output_tokens") is not None and (
            isinstance(spec["output_tokens"], bool) or not isinstance(spec["output_tokens"], int)
            or not 1 <= spec["output_tokens"] <= 8192
        )
    ):
        raise BatchAdmissionError("contract_recovery_spec_invalid")
    post = Post.objects.prefetch_related("brands").get(pk=spec["post_id"])
    if post_snapshot(post) != spec["source_snapshot"]:
        raise BatchAdmissionError("contract_recovery_source_changed")
    previous = list(OriginalContentCall.objects.filter(
        pk__in=spec["prior_call_ids"], provider_batch__source_collection_job=job,
    ))
    if len(previous) != len(set(spec["prior_call_ids"])) or any(
        str(post.pk) not in c.member_post_ids or c.state not in {"completed", "failed"}
        or c.import_state != "error"
        or c.provenance.get("context", {}).get("recovery")
        or c.provenance.get("post_snapshots", {}).get(str(post.pk)) != spec["source_snapshot"]
        for c in previous
    ):
        raise BatchAdmissionError("contract_recovery_prior_failure_invalid")
    return post, previous


def _fit_wave(requests):
    """Keep each Post's requests whole; Posts that do not fit wait for the next wave."""
    groups = {}
    for request in requests:
        groups.setdefault(tuple(sorted(request["context"]["post_ids"])), []).append(request)
    kept, waiting = [], set()
    for members, group in groups.items():
        if kept and len(kept) + len(group) > _WAVE_REQUESTS:
            waiting.update(members)
        else:
            kept.extend(group)
    return kept, sorted(waiting)


def _grant_report(job, header, entries, requests, deferred, waiting, cfg):
    """Per-Post outcomes and this grant's paid usage, for receipts and output."""
    ids = [str(post.pk) for _, post, _ in entries]
    requested = {p for r in requests for p in r["context"]["post_ids"]}
    if header["phase"] == "base":
        facts = completion_facts(ids)
        done = {p for p in ids if facts[p]["translation"] and facts[p]["classification"]}
    else:
        done = {str(post.pk) for _, post, _ in entries if not incomplete_roles(post, cfg)}
    usage = OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=job,
        provenance__context__recovery__grant_sha256=header["grant_sha256"],
    ).aggregate(
        requests=Count("pk"), requests_sent=Count("sent_at"), responses=Count("completed_at"),
        reserved_usd=Sum("reserved_usd"), provider_reported_usd=Sum("actual_usd"),
    )
    return {
        "version": GRANT_VERSION, "grant_sha256": header["grant_sha256"],
        "grant_phase": header["phase"], "actor": header["actor"], "reason": header["reason"],
        "with_feedback": header["feedback"] is not None,
        "posts": {
            p: deferred.get(p) or (
                "waiting" if p in waiting else "requested" if p in requested
                else "complete" if p in done else "pending"
            )
            for p in ids
        },
        "waiting_posts": waiting,
        "usage": {k: str(v) if isinstance(v, Decimal) else v for k, v in usage.items()},
    }


def advance_contract_recovery(
    job_id, *, specs=None, grant=None, cfg, api_key, delegates=None, targeted_delegate=None,
    client_factory=None, direct_concurrency=32, prepare_only=False,
):
    """Advance one bounded wave; unknown/exhausted inputs remain deferred.

    The caller supplies immutable, explicitly selected repair specifications
    (``specs``) or one final-attempt grant document (``grant``). Old provider
    state, attempts, costs, policy and source instructions are never rewritten.
    All new starts still use the existing reservation admission. A grant gives
    each request hash it prepares one physical request; an executing caller
    holds the campaign controller lock (``backfill --enrichment-attempt-grant``).
    A grant preview (``prepare_only``) rolls back every preparation write.
    """
    wave = functools.partial(
        _advance_wave, job_id, specs=specs, grant=grant, cfg=cfg, api_key=api_key,
        delegates=delegates, targeted_delegate=targeted_delegate,
        client_factory=client_factory, direct_concurrency=direct_concurrency,
        prepare_only=prepare_only,
    )
    if grant is None or not prepare_only:
        return wave()
    with transaction.atomic():
        result = wave()
        transaction.set_rollback(True)
    return result


def _advance_wave(
    job_id, *, specs, grant, cfg, api_key, delegates, targeted_delegate,
    client_factory, direct_concurrency, prepare_only,
):
    validate_concurrency(direct_concurrency)
    header = None
    if grant is not None:
        if specs is not None:
            raise BatchAdmissionError("contract_recovery_spec_invalid")
        specs, header = grant_specs(grant)
    elif specs is None:
        raise BatchAdmissionError("contract_recovery_spec_invalid")
    if not 0 < len(specs) <= 50 or len({s.get("post_id") for s in specs}) != len(specs):
        raise BatchAdmissionError("contract_recovery_requires_bounded_distinct_posts")
    job = CollectionJob.objects.get(pk=job_id)
    first = job.provider_batches.order_by("created_at").first()
    if first is None or first.policy["configuration_pin"] != configuration_pin(cfg):
        raise BatchAdmissionError("contract_recovery_policy_or_configuration_changed")
    if header is not None:
        if header["job_id"] != str(job.pk):
            raise BatchAdmissionError("final_attempt_grant_spec_invalid")
        # Every start is fenced by the frozen deadline; refuse before preparing.
        if datetime.fromisoformat(first.policy["deadline"]) <= timezone.now():
            raise BatchAdmissionError("batch_deadline_exhausted")
    delegates = delegates or {
        "translation": build_translator_client_from_env(cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND"),
        "classification": build_classifier_client_from_env(cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND"),
    }
    if any(c is None for c in delegates.values()):
        raise BatchAdmissionError("enrichment_role_credentials_missing")
    with transaction.atomic():
        _locked_drained_revalidation_job(job.pk)
        admission = None if header is None else {
            "grant_sha256": header["grant_sha256"], "cfg": cfg,
            "deferred": deferred_enrichment_work(
                job, max_attempts=int(first.policy["max_attempts"]),
                operation_scope=header["phase"],
            ),
        }
        entries = [(spec, *_validate_spec(job, spec, admission=admission)) for spec in specs]
    if header is None:
        cap = first.policy["max_attempts"]
        unknown, spent = "corrected_request_outcome_unknown", "corrected_request_allowance_exhausted"
    else:
        # The grant limits itself; the frozen policy's max_attempts is unchanged.
        cap = 1
        unknown, spent = "final_attempt_grant_outcome_unknown", "final_attempt_grant_exhausted"
    requests, deferred, issues = [], {}, []
    pending = []
    for spec, post, previous in entries:
        identifier = str(post.pk)
        spec_hash = digest(spec) if header is None else header["grant_sha256"]
        complete = completion_facts([identifier])[identifier]
        if spec["phase"] == "base" and complete["translation"] and complete["classification"]:
            continue
        if spec["phase"] == "targeted" and not incomplete_roles(post, cfg):
            continue
        pending.append(identifier)
        current = list(OriginalContentCall.objects.filter(
            provider_batch__source_collection_job=job,
            **({"provenance__context__recovery__spec_sha256": spec_hash} if header is None else {
                "provenance__context__recovery__grant_sha256": spec_hash,
                "member_post_ids__contains": [identifier],
            }),
        ))
        if any(c.state in {"reserved", "sent", "ambiguous"} for c in current):
            deferred[identifier] = unknown
            continue
        counts = Counter(c.request_hash for c in current)
        if any(n >= cap for n in counts.values()) and all(
            c.import_state == "error" for c in current
        ):
            deferred[identifier] = spent
            continue
        context = {
            "version": VERSION, "spec_sha256": spec_hash,
            "prior_call_ids": spec["prior_call_ids"],
        } if header is None else {
            "version": GRANT_VERSION, "grant_sha256": spec_hash,
            "actor": header["actor"], "reason": header["reason"],
            "prior_call_ids": spec["prior_call_ids"],
        }
        if spec["phase"] == "base":
            failed_translation_bodies = {
                body_digest(c.request_packet) for c in previous if c.stage == "translation"
            }
            # A body can have an old rejected attempt and a later valid reply
            # whose import is still pending on a different chunk. Preserve that
            # exact successful cache entry instead of correcting/reserving it.
            reusable_translation_bodies = {
                body_digest(c.request_packet)
                for c in OriginalContentCall.objects.filter(
                    provider_batch__source_collection_job=job,
                    member_post_ids__contains=[identifier], stage="translation",
                    state="completed", import_state__in=["pending", "applied"],
                )
                if body_digest(c.request_packet) in failed_translation_bodies
                and c.provenance.get("post_snapshots", {}).get(identifier) == spec["source_snapshot"]
                and _cached_reply_valid(c, delegates["translation"], post.text)
            }
            clients = {
                stage: CorrectedInferenceClient(
                    client, feedback=spec.get("translation_feedback", spec.get("feedback"))
                    if stage == "translation" else spec.get("feedback"), context=context,
                    body_hashes=failed_translation_bodies - reusable_translation_bodies
                    if stage == "translation" else None,
                )
                for stage, client in delegates.items()
            }
            prepared, _, _ = prepare_page(job, [identifier], cfg, delegates=clients)
        else:
            delegate = targeted_delegate or build_relevancy_client_from_env(
                cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND",
            )
            client = CorrectedInferenceClient(
                delegate, feedback=spec.get("feedback"), context=context,
                output_tokens=spec.get("output_tokens"),
            )
            try:
                prepared = _prepare(job, post, cfg, client)
            except ValueError as exc:
                issues.append({"post_id": identifier, "error": str(exc)[:200]})
                prepared = []
        requests.extend(prepared)
    exhausted = {
        p for r in requests for p in r["context"]["post_ids"]
        if OriginalContentCall.objects.filter(
            provider_batch__source_collection_job=job, request_hash=r["hash"],
        ).count() >= cap
    }
    deferred.update({p: spent for p in exhausted})
    requests = [r for r in requests if not set(r["context"]["post_ids"]) & exhausted]
    waiting = []
    if header is not None:
        requests, waiting = _fit_wave(requests)
    if len(requests) > _WAVE_REQUESTS:
        raise BatchAdmissionError("contract_recovery_wave_too_large")
    if prepare_only:
        result = {"pending_posts": len(pending), "requests": requests, "deferred": deferred, "issues": issues}
        if header is None:
            return result
        reservation = sum(
            (conservative_reservation(r["body"], first.policy["prices"])[0] for r in requests),
            Decimal(0),
        )
        return result | _grant_report(job, header, entries, requests, deferred, waiting, cfg) | {
            "reservation_usd": str(reservation),
        }
    if header is None:
        group_ids = _register_requests(
            job, requests, first.policy, cfg, transport="direct", allow_drained_ambiguous=True,
        )
    else:
        with transaction.atomic():
            # Re-check the one-request cap under the campaign row lock, and
            # register all-or-nothing: a refused reservation leaves no group.
            CollectionJob.objects.select_for_update().get(pk=job.pk)
            raced = set()
            for request in requests:
                if OriginalContentCall.objects.filter(
                    provider_batch__source_collection_job=job, request_hash=request["hash"],
                ).exists():
                    raced.update(request["context"]["post_ids"])
            deferred.update({p: spent for p in raced})
            requests = [r for r in requests if not set(r["context"]["post_ids"]) & raced]
            group_ids = _register_requests(
                job, requests, first.policy, cfg, transport="direct", allow_drained_ambiguous=True,
            )
    for group_id in group_ids:
        advance_direct(group_id, api_key=api_key, concurrency=direct_concurrency, client_factory=client_factory)
    result = {
        "pending_posts": len(pending), "prepared_requests": len(requests),
        "deferred": deferred, "issues": issues,
        "status": "completed" if not pending else "partial",
    }
    if header is None:
        return result
    return result | _grant_report(job, header, entries, requests, deferred, waiting, cfg)
