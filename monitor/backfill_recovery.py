"""Explicit corrected-input recovery over the shared backfill paid-call ledger."""

from __future__ import annotations

from collections import Counter

from django.db import transaction

from core.models import CollectionJob, OriginalContentCall, Post
from core.provider_batches import BatchAdmissionError, digest, post_snapshot
from monitor.backfill_direct import advance_direct, validate_concurrency
from monitor.backfill_enrichment import (
    _cached_reply_valid,
    _locked_drained_revalidation_job,
    _register_requests,
    completion_facts,
    configuration_pin,
    prepare_page,
)
from scripts.backfill_targeted import _prepare, incomplete_roles
from x_monitor.corrected_inference import VERSION, CorrectedInferenceClient, body_digest
from x_monitor.reattribute import (
    build_classifier_client_from_env,
    build_relevancy_client_from_env,
    build_translator_client_from_env,
)


def _validate_spec(job, spec):
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


def advance_contract_recovery(
    job_id, *, specs, cfg, api_key, delegates=None, targeted_delegate=None,
    client_factory=None, direct_concurrency=32, prepare_only=False,
):
    """Advance one bounded wave; unknown/exhausted inputs remain deferred.

    The caller supplies immutable, explicitly selected repair specifications.
    Old provider state, attempts, costs, policy and source instructions are never
    rewritten. All new starts still use the existing reservation admission.
    """
    validate_concurrency(direct_concurrency)
    if not 0 < len(specs) <= 50 or len({s.get("post_id") for s in specs}) != len(specs):
        raise BatchAdmissionError("contract_recovery_requires_bounded_distinct_posts")
    job = CollectionJob.objects.get(pk=job_id)
    first = job.provider_batches.order_by("created_at").first()
    if first is None or first.policy["configuration_pin"] != configuration_pin(cfg):
        raise BatchAdmissionError("contract_recovery_policy_or_configuration_changed")
    delegates = delegates or {
        "translation": build_translator_client_from_env(cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND"),
        "classification": build_classifier_client_from_env(cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND"),
    }
    if any(c is None for c in delegates.values()):
        raise BatchAdmissionError("enrichment_role_credentials_missing")
    with transaction.atomic():
        _locked_drained_revalidation_job(job.pk)
        entries = [(spec, *_validate_spec(job, spec)) for spec in specs]
    requests, deferred, issues = [], {}, []
    pending = []
    for spec, post, previous in entries:
        identifier, spec_hash = str(post.pk), digest(spec)
        complete = completion_facts([identifier])[identifier]
        if spec["phase"] == "base" and complete["translation"] and complete["classification"]:
            continue
        if spec["phase"] == "targeted" and not incomplete_roles(post, cfg):
            continue
        pending.append(identifier)
        current = list(OriginalContentCall.objects.filter(
            provider_batch__source_collection_job=job,
            provenance__context__recovery__spec_sha256=spec_hash,
        ))
        if any(c.state in {"reserved", "sent", "ambiguous"} for c in current):
            deferred[identifier] = "corrected_request_outcome_unknown"
            continue
        counts = Counter(c.request_hash for c in current)
        if any(n >= first.policy["max_attempts"] for n in counts.values()) and all(
            c.import_state == "error" for c in current
        ):
            deferred[identifier] = "corrected_request_allowance_exhausted"
            continue
        context = {
            "version": VERSION, "spec_sha256": spec_hash,
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
                    client, feedback=spec.get("translation_feedback", spec["feedback"])
                    if stage == "translation" else spec["feedback"], context=context,
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
                delegate, feedback=spec["feedback"], context=context,
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
        ).count() >= first.policy["max_attempts"]
    }
    deferred.update({p: "corrected_request_allowance_exhausted" for p in exhausted})
    requests = [r for r in requests if not set(r["context"]["post_ids"]) & exhausted]
    if len(requests) > 64:
        raise BatchAdmissionError("contract_recovery_wave_too_large")
    if prepare_only:
        return {"pending_posts": len(pending), "requests": requests, "deferred": deferred, "issues": issues}
    for group_id in _register_requests(
        job, requests, first.policy, cfg, transport="direct", allow_drained_ambiguous=True,
    ):
        advance_direct(group_id, api_key=api_key, concurrency=direct_concurrency, client_factory=client_factory)
    return {
        "pending_posts": len(pending), "prepared_requests": len(requests),
        "deferred": deferred, "issues": issues,
        "status": "completed" if not pending else "partial",
    }
