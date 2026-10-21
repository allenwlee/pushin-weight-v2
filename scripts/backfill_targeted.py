"""Run the harvester's targeted extractors using the existing paid-call ledger.

This operator adapter prepares and replays the shared extractors; it has no
extraction prompts, response parsers or domain-record writers of its own.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.models import (
    CollectionJob,
    CollectionObservation,
    OriginalContentCall,
    PersonBrandAffiliationEvidence,
    Post,
    ProfileMovementCandidate,
    RareTypeSearchHit,
)
from core.provider_batches import (
    BatchAdmissionError,
    assert_enrichment_admission,
    digest,
    own_historical_posts,
    post_snapshot,
)
from core.targeted_extraction import (
    TYPE_TO_ROLE,
    _hash,
    _prompts,
    build_targeted_extraction_calls,
    run_targeted_extractions,
)
from monitor.backfill_direct import advance_direct
from monitor.backfill_enrichment import (
    ACTIVE_STATES,
    _register_requests,
    deferred_enrichment_work,
)
from x_monitor.deferred_inference import DeferredInferenceClient
from x_monitor.reattribute import build_relevancy_client_from_env

OPERATION = "post_targeted_extraction"


def requirements(post, cfg):
    """Read exact shared prompt identities; use the harvester's role mapping."""
    if not cfg.targeted_extraction.enabled:
        return {}
    types = set(post.signals.values_list("post_type_id", flat=True))
    rare = set(
        RareTypeSearchHit.objects.filter(
            post=post,
            gate_state="kept",
            decision__derived_types__contains=["model_releases"],
        )
        .values_list("decision__derived_types", flat=True)
        .first()
        or []
    )
    roles = {
        TYPE_TO_ROLE[t]
        for t in types
        if t in TYPE_TO_ROLE and (t != "releases_updates" or "model_releases" in rare)
    }
    if (
        PersonBrandAffiliationEvidence.objects.filter(
            source_profile_snapshot__first_source_post=post,
            extracted_claim_data__candidate_role="unknown",
        ).exists()
        or ProfileMovementCandidate.objects.filter(
            source_post=post, status__in=["pending", "failed"]
        ).exists()
    ):
        roles.add("profile_affiliation_extraction")
    output = {}
    for role in sorted(roles):
        spec = cfg.targeted_extraction.roles[role]
        system, user = _prompts(role, post)
        output[role] = _hash(
            {
                "post": str(post.pk),
                "role": role,
                "system": system,
                "user": user,
                "model": spec.model,
                "prompt_version": spec.prompt_version,
            }
        )
    return output


def incomplete_roles(post, cfg):
    states = {s.role: s for s in post.targeted_extraction_states.all()}
    return [
        role
        for role, identity in requirements(post, cfg).items()
        if role not in states
        or states[role].status != "succeeded"
        or states[role].content_identity != identity
        or not states[role].result_hash
    ]


def _prepare(job, post, cfg, delegate):
    """Shared extractor writes publish only with complete, saved paid replies."""
    own_historical_posts(job, [post.pk])
    cached = {
        c.request_hash: c
        for c in OriginalContentCall.objects.filter(
            member_post_ids__contains=[str(post.pk)],
            provenance__context__operation=OPERATION,
            state="completed",
            import_state__in=["pending", "applied"],
        )
        if c.provenance.get("post_snapshots", {}).get(str(post.pk)) == post_snapshot(post)
    }
    outstanding = set(
        OriginalContentCall.objects.filter(
            member_post_ids__contains=[str(post.pk)],
            provenance__context__operation=OPERATION,
            state__in=["reserved", "sent", "ambiguous"],
            import_state="pending",
        ).values_list("request_hash", flat=True)
    )
    prepared, consumed, missing = {}, set(), False

    def resolve(identity, body, kind, context):
        nonlocal missing
        if identity in cached:
            consumed.add(cached[identity].pk)
            return cached[identity].response_payload
        missing = True
        if identity not in outstanding:
            prepared[identity] = {
                "hash": identity,
                "body": body,
                "kind": kind,
                "context": context,
                "snapshots": {str(post.pk): post_snapshot(post)},
            }
        return None

    class ContextClient:
        def __init__(self, role):
            self.role = role
            self.client = DeferredInferenceClient(
                delegate, resolve=resolve, reply_transport=lambda _: "direct",
                context_transform=getattr(delegate, "context_for_request", None),
            )

        def messages_create(self, **kwargs):
            kwargs["_batch_context"] = {
                "stage": "classification",
                "operation": OPERATION,
                "role": self.role,
                "post_ids": [str(post.pk)],
                "input_fingerprints": {str(post.pk): digest(kwargs)},
            }
            return self.client.messages_create(**kwargs)

    calls = {
        role: build_targeted_extraction_calls(
            client=ContextClient(role),
            roles={role: spec},
            timeout_seconds=cfg.targeted_extraction.request_timeout_seconds,
        )[role]
        for role, spec in cfg.targeted_extraction.roles.items()
    }
    types = set(post.signals.values_list("post_type_id", flat=True))
    rare = set(
        RareTypeSearchHit.objects.filter(
            post=post,
            gate_state="kept",
            decision__derived_types__contains=["model_releases"],
        )
        .values_list("decision__derived_types", flat=True)
        .first()
        or []
    )
    with transaction.atomic():
        CollectionJob.objects.select_for_update().get(pk=job.pk)
        assert_enrichment_admission(job.pk)
        Post.objects.select_for_update().get(pk=post.pk)
        result = run_targeted_extractions(
            post=post,
            post_types=types,
            config=cfg.targeted_extraction,
            calls=calls,
            max_calls=len(calls),
            eligible_rare_types=rare,
        )
        if missing:
            transaction.set_rollback(True)
        else:
            applied = not result.failed_roles and not result.deferred_roles
            OriginalContentCall.objects.filter(
                pk__in=consumed, provider_batch__source_collection_job=job,
            ).update(
                import_state="applied" if applied else "error",
                import_evidence={
                    "validation": "passed"
                    if applied
                    else "canonical_targeted_validation_failed",
                    "published_at": timezone.now().isoformat(),
                },
            )
    if not missing and (result.failed_roles or result.deferred_roles):
        raise ValueError("targeted_extraction_canonical_publication_failed")
    return list(prepared.values())


def advance_targeted(
    job_id,
    *,
    cfg,
    api_key,
    direct_concurrency=32,
    delegate=None,
    client_factory=None,
    defer_failures=False,
    post_ids=None,
):
    """Advance a job or explicit member subset through shared paid admission."""
    job = CollectionJob.objects.get(pk=job_id)
    first = job.provider_batches.order_by("created_at").first()
    if first is None:
        raise ValueError("base_enrichment_policy_missing")
    observations = CollectionObservation.objects.filter(
        run__job=job, source_subject_kind="post"
    )
    if post_ids is not None:
        selected = sorted({str(identifier) for identifier in post_ids})
        observations = observations.filter(post_id__in=selected)
        if not selected or observations.values("post_id").distinct().count() != len(selected):
            raise BatchAdmissionError("targeted_selection_membership_missing")
    delegate = delegate or build_relevancy_client_from_env(
        cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND",
    )
    if delegate is None:
        raise ValueError("targeted_extraction_role_client_missing")
    groups = job.provider_batches.filter(state__in=ACTIVE_STATES)
    for group in list(groups.order_by("created_at")[:2]):
        advance_direct(
            group.pk,
            api_key=api_key,
            concurrency=direct_concurrency,
            client_factory=client_factory,
        )
    prepared, pending, scanned, after = [], 0, 0, ""
    deferred = {}
    if defer_failures:
        deferred = deferred_enrichment_work(
            job,
            max_attempts=int(first.policy["max_attempts"]),
            operation_scope="targeted",
        )
        observations = observations.exclude(post_id__in=deferred).filter(
            post__enrichment_state__translation_status="succeeded",
            post__enrichment_state__classification_status="succeeded",
        )
    while True:
        ids = list(
            observations.filter(post_id__gt=after)
            .order_by("post_id")
            .values_list("post_id", flat=True)
            .distinct()[:100]
        )
        if not ids:
            break
        after = ids[-1]
        for post in Post.objects.filter(pk__in=ids).order_by("pk"):
            scanned += 1
            if incomplete_roles(post, cfg):
                pending += 1
                try:
                    prepared.extend(_prepare(job, post, cfg, delegate))
                except ValueError as exc:
                    if not defer_failures or str(exc) != "targeted_extraction_canonical_publication_failed":
                        raise
                    deferred[post.pk] = "canonical_targeted_validation_failed"
                if len(prepared) >= direct_concurrency * 2:
                    break
        if len(prepared) >= direct_concurrency * 2:
            break
    for identifier in _register_requests(
        job,
        prepared,
        first.policy,
        cfg,
        transport="direct",
        allow_drained_ambiguous=defer_failures,
        deferred=deferred if defer_failures else None,
    ):
        advance_direct(
            identifier,
            api_key=api_key,
            concurrency=direct_concurrency,
            client_factory=client_factory,
        )
    return {
        "scanned_posts": scanned,
        "pending_posts_seen": pending,
        "prepared_requests": len(prepared),
        "status": "completed" if pending == 0 else "partial",
    }
