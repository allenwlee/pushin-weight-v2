"""Resumable enrichment of stored members over native or ordinary model HTTP."""

from __future__ import annotations

import hashlib
import inspect
import json
import threading
import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.postgres.expressions import ArraySubquery
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q, Sum
from django.utils import timezone

from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    OriginalContentCall,
    Post,
    PostEnrichmentState,
    ProviderBatch,
)
from core.provider_batches import (
    SPEND_BASES,
    BatchAdmissionError,
    assert_enrichment_admission,
    claim_batch,
    control_start,
    digest,
    enrichment_control_status,
    enrichment_policy_definition,
    fenced_batch,
    historical_ownership_conflicts,
    import_response,
    mark_submitting,
    own_historical_posts,
    post_snapshot,
    record_post_membership,
    release_batch,
    reserve_requests,
)
from monitor.backfill_resources import bounded_backfill_config
from monitor.cycle import CycleRunner, _parse_published_classifications
from monitor.post_artifacts import literal_translation_artifact_complete
from x_monitor.deepinfra import (
    DEEPSEEK_0731_MODEL,
    GEMMA_4_31B_MODEL,
    DeepInfraPermanentError,
)
from x_monitor.deepinfra_batch import (
    BatchHTTPError,
    BatchProtocolError,
    BatchTransportError,
    DeepInfraBatchClient,
    encode_requests,
)
from x_monitor.deferred_inference import DeferredInferenceClient
from x_monitor.reattribute import (
    build_classifier_client_from_env,
    build_translator_client_from_env,
)

DEFAULT_PRICES = {
    GEMMA_4_31B_MODEL: ["0.09", "0.34"],
    DEEPSEEK_0731_MODEL: ["0.06", "0.18"],
}
ACTIVE_STATES = {
    "registered",
    "uploading",
    "uploaded",
    "submitting",
    "ambiguous",
    "waiting",
    "importing",
}
TERMINAL_PROVIDER = {"completed", "expired", "failed", "cancelled"}


def configuration_pin(cfg):
    from x_monitor import attribution, literal_translation
    from x_monitor.classifier_0731_prompts import BRAND_PROMPT, CONTENT_PROMPT

    return digest(
        {
            "llm": cfg.llm.model_dump(mode="json"),
            "literal_source": inspect.getsource(literal_translation),
            "classifier_source": inspect.getsource(
                attribution.classify_batch_pragmatics_full
            ),
            "content_prompt": CONTENT_PROMPT,
            "brand_prompt": BRAND_PROMPT,
        }
    )


def completion_facts(ids):
    """Inspect canonical persisted outputs in one bounded prefetched page."""
    if len(ids) > 100:
        raise BatchAdmissionError("completion_verification_page_limit")
    facts = {}
    posts = Post.objects.filter(pk__in=ids).prefetch_related(
        "brands",
        "signals",
        "product_label_edges",
        "translation_artifacts__texts",
        "classification_states__selected_final_judgment__content_judgment",
        "classification_states__selected_final_judgment__brand_interpretation_judgment",
    )
    for post in posts:
        expected = {row.brand_id for row in post.brands.all()}
        states = {row.brand_id: row for row in post.classification_states.all()}
        by_brand = {}
        for brand, state in states.items():
            final = state.selected_final_judgment
            if (
                final is None
                or final.stage != "final"
                or final.validation_state != "validated"
                or final.post_id != post.pk
                or final.brand_id != brand
                or final.input_context_fingerprint != state.input_context_fingerprint
                or final.contract_version != state.contract_version
                or final.taxonomy_version != state.taxonomy_version
            ):
                continue
            if final.content_judgment_id or final.brand_interpretation_judgment_id:
                siblings = [
                    (final.content_judgment, "content"),
                    (final.brand_interpretation_judgment, "brand_interpretation"),
                ]
                if any(
                    sibling is None
                    or sibling.stage != role
                    or sibling.post_id != post.pk
                    or sibling.brand_id != brand
                    or sibling.revision_id != final.revision_id
                    or sibling.input_context_fingerprint
                    != final.input_context_fingerprint
                    or sibling.validation_state != "validated"
                    for sibling, role in siblings
                ):
                    continue
            by_brand[brand] = final.canonical_judgment
        canonical = (
            _parse_published_classifications(by_brand, expected)
            if expected == set(states) and expected
            else None
        )
        classified = canonical is not None
        if canonical is not None:
            signals = list(post.signals.all())
            labels = list(post.product_label_edges.all())
            for brand, row in canonical.items():
                state = states[brand]
                classified &= (
                    state.outcome == row["outcome"]
                    and state.sentiment_id == row["sentiment"]
                )
                classified &= {
                    s.post_type_id for s in signals if s.brand_id == brand
                } == set(row["post_types"])
                classified &= {
                    s.product_label_id for s in labels if s.brand_id == brand
                } == set(row["product_labels"])
        facts[str(post.pk)] = {
            "translation": literal_translation_artifact_complete(
                post, artifacts=post.translation_artifacts.all()
            ),
            "classification": bool(classified),
        }
    return facts


def verify_cohort(observations):
    invalid, after, total = {}, "", 0
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
        total += len(ids)
        for identifier, fact in completion_facts(ids).items():
            if not all(fact.values()):
                invalid[identifier] = fact
    return total, invalid


def reopen_incomplete_successes(job, observations):
    """A source page can add brands after an earlier successful assessment."""
    after = ""
    candidates = observations.filter(
        Q(post__enrichment_state__translation_status="succeeded")
        | Q(post__enrichment_state__classification_status="succeeded")
    )
    while True:
        ids = list(
            candidates.filter(post_id__gt=after)
            .order_by("post_id")
            .values_list("post_id", flat=True)
            .distinct()[:100]
        )
        if not ids:
            break
        after = ids[-1]
        with transaction.atomic():
            states = list(
                PostEnrichmentState.objects.select_for_update().filter(pk__in=ids).order_by("pk")
            )
            list(Post.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
            facts = completion_facts(ids)
            now = timezone.now()
            for state in states:
                if state.claim_expires_at and state.claim_expires_at > now:
                    continue
                reopened = False
                for stage in ("translation", "classification"):
                    if (
                        getattr(state, f"{stage}_status") == "succeeded"
                        and not facts[str(state.pk)][stage]
                    ):
                        setattr(state, f"{stage}_status", "pending")
                        setattr(
                            state, f"{stage}_error_code", "persisted_output_incomplete"
                        )
                        reopened = True
                if reopened:
                    state.save()
            own_historical_posts(job, ids, defer_conflicts=True)


def policy_snapshot(
    *,
    max_usd,
    deadline,
    selection=None,
    max_model_requests=20000,
    max_control_requests=5000,
    spend_basis=None,
):
    """Freeze a campaign's enrichment limits on its first ProviderBatch.

    ``spend_basis`` decides what the ``max_usd`` limit counts: ``"reservation"``
    (conservative reservations) or ``"settled"`` (provider-reported cost for
    finished requests, reservations for the rest). ``None`` omits the key, so
    the snapshot equals one frozen before the option existed and admission
    counts reservations.
    """
    if spend_basis is not None and spend_basis not in SPEND_BASES:
        raise BatchAdmissionError("enrichment_spend_basis_invalid")
    dollars = Decimal(str(max_usd))
    if not dollars.is_finite() or not Decimal(0) < dollars <= Decimal(10000):
        raise BatchAdmissionError("enrichment_spend_limit_invalid")
    if not timezone.now() < deadline <= timezone.now() + timedelta(days=365):
        raise BatchAdmissionError("enrichment_deadline_invalid")
    if (
        not 0 < max_model_requests <= 10000000
        or not 0 < max_control_requests <= 1000000
    ):
        raise BatchAdmissionError("enrichment_request_limit_invalid")
    selection = sorted({str(v) for v in (selection or [])})
    if len(selection) > 110:
        raise BatchAdmissionError("pilot_selection_limit")
    snapshot = {
        "version": 1,
        "max_usd": str(max_usd),
        "deadline": deadline.isoformat(),
        "max_model_requests": max_model_requests,
        "max_control_requests": max_control_requests,
        "max_attempts": 3,
        "prices": DEFAULT_PRICES,
        "selection": selection,
        "max_file_requests": 2000,
        "max_file_bytes": 16 * 1024 * 1024,
    }
    if spend_basis is not None:
        snapshot["spend_basis"] = spend_basis
    return snapshot


def _classifier_ready(body):
    for message in body.get("messages", []):
        if message.get("role") != "user":
            continue
        try:
            packet = json.loads(message.get("content", ""))
        except (ValueError, TypeError):
            return False
        cases = packet.get("cases", {})
        return bool(cases) and all(
            case.get("evidence", {}).get("english_translation", "").strip()
            for case in cases.values()
        )
    return False


def _cached_reply_valid(call, client, source):
    """Use the canonical response and literal validators before offering a cache hit."""
    from x_monitor.literal_translation import (
        _parse_detected_language,
        _restore_and_validate,
        _split_translation_chunks,
    )
    from x_monitor.translation_invariants import protect_translation_spans

    try:
        if call.provenance["response_kind"] == "json":
            client.parse_response(call.response_payload)
            return True
        text = client.parse_text_response(call.response_payload).text
        context = call.provenance["context"]
        if context.get("operation") == "post_literal_language_detection":
            return _parse_detected_language(text) is not None
        if hashlib.sha256(source.encode()).hexdigest() != context["source_fingerprint"]:
            raise BatchAdmissionError("cached_translation_source_mismatch")
        if context.get("chunk_index") is not None:
            source = _split_translation_chunks(source, chunk_size=2000)[
                context["chunk_index"]
            ]
        target = context["target_language"]
        _, quantities = protect_translation_spans(source, target)
        text, _, _ = _restore_and_validate(
            source, target, text, quantities, {}, 0,
            source_language=context.get("source_language"),
        )
        return text is not None
    except DeepInfraPermanentError:
        return False


def _locked_drained_revalidation_job(job_id):
    """Call inside atomic; share the admission barrier for saved-reply repairs."""
    job = CollectionJob.objects.select_for_update().get(pk=job_id)
    status = enrichment_control_status(job.pk)
    if any(status[k] for k in (
        "sent_outstanding", "active_processing_claims", "native_groups_outstanding",
    )) or OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=job, state="reserved",
    ).exists():
        raise BatchAdmissionError("cached_revalidation_requires_drained_work")
    return job


def _revalidation_evidence(call, *, actor, reason, validator, **details):
    previous = dict(call.import_evidence)
    history = previous.pop("revalidation_history", [])
    event = {
        "actor": actor.strip(), "reason": reason.strip(),
        "at": timezone.now().isoformat(), "validator": validator,
        "previous_import_state": call.import_state,
        "previous_error_code": call.error_code,
        "previous_import_evidence": previous, **details,
    }
    return {
        **call.import_evidence, "validation": "revalidated",
        "revalidation_history": [*history, event],
    }


def revalidate_cached_translations(job_id, *, call_ids, delegate, actor, reason):
    """Explicitly reopen valid saved replies after a shared validator correction.

    This performs no inference or publication and never changes physical-call
    state, costs or attempts. The caller must first stop its owned controller.
    """
    ids = sorted(set(call_ids))
    if not 0 < len(ids) <= 100 or not actor.strip() or not reason.strip():
        raise BatchAdmissionError("cached_revalidation_requires_bounded_ids_and_audit")
    if len(actor) > 160 or len(reason) > 1000:
        raise BatchAdmissionError("cached_revalidation_audit_too_large")
    reopened, rejected = [], []
    with transaction.atomic():
        job = _locked_drained_revalidation_job(job_id)
        calls = list(OriginalContentCall.objects.filter(
            pk__in=ids, provider_batch__source_collection_job=job,
        ))
        if len(calls) != len(ids) or any(
            c.stage != "translation" or c.state != "completed"
            or c.provenance.get("context", {}).get("operation") != "post_literal_translation"
            or len(c.member_post_ids) != 1
            or c.response_payload is None
            or c.model != delegate.model
            for c in calls
        ):
            raise BatchAdmissionError("cached_revalidation_ineligible_call")
        members = sorted({p for c in calls for p in c.member_post_ids})
        states = list(PostEnrichmentState.objects.select_for_update().filter(pk__in=members))
        if len(states) != len(members) or any(
            s.claim_expires_at and s.claim_expires_at > timezone.now() for s in states
        ):
            raise BatchAdmissionError("cached_revalidation_post_missing_or_claimed")
        posts = {str(p.pk): p for p in Post.objects.select_for_update().filter(
            pk__in=members,
        ).prefetch_related("brands")}
        for call in OriginalContentCall.objects.select_for_update().filter(pk__in=ids).order_by("pk"):
            if call.import_state != "error":
                continue
            if call.error_code != "cached_response_validation_failed":
                raise BatchAdmissionError("cached_revalidation_unrelated_error")
            if {p: post_snapshot(posts[p]) for p in call.member_post_ids} != call.provenance.get("post_snapshots"):
                raise BatchAdmissionError("cached_revalidation_source_changed")
            if not _cached_reply_valid(call, delegate, posts[call.member_post_ids[0]].text):
                rejected.append(call.pk)
                continue
            call.import_evidence = _revalidation_evidence(
                call, actor=actor, reason=reason, validator="literal_quantity_source_forms_v1",
            )
            call.import_state = "pending"
            call.error_code = ""
            call.save(update_fields=["import_state", "error_code", "import_evidence", "updated_at"])
            reopened.append(call.pk)
    return {"reopened": reopened, "rejected": rejected}


def replay_rejected_classifier_packet(
    job_id, *, call_ids, post_ids, cfg, delegates, actor, reason,
):
    """Publish selected members of an exact saved pair, with no new inference.

    Any missing reply or invalid selected output rolls back the entire repair.
    Unresolved siblings retain their failure evidence and retry accounting.
    """
    ids, selected = sorted(set(call_ids)), sorted({str(p) for p in post_ids})
    if len(ids) != 2 or not 0 < len(selected) <= 20 or not actor.strip() or not reason.strip():
        raise BatchAdmissionError("classifier_revalidation_requires_pair_members_and_audit")
    if len(actor) > 160 or len(reason) > 1000:
        raise BatchAdmissionError("cached_revalidation_audit_too_large")
    with transaction.atomic():
        job = _locked_drained_revalidation_job(job_id)
        assert_enrichment_admission(job.pk)
        calls = list(OriginalContentCall.objects.filter(
            pk__in=ids, provider_batch__source_collection_job=job,
        ).select_related("provider_batch").order_by("pk"))
        if len(calls) != 2 or any(
            c.state != "completed" or c.stage != "classification"
            or c.provenance.get("response_kind") != "json"
            or c.model != delegates["classification"].model
            or c.provider_batch.request_profile != delegates["classification"].request_profile
            for c in calls
        ) or {c.provenance.get("context", {}).get("role") for c in calls} != {"content", "brand_interpretation"}:
            raise BatchAdmissionError("classifier_revalidation_ineligible_pair")
        def user_packet(call):
            return next(m["content"] for m in call.request_packet["messages"] if m["role"] == "user")
        members = sorted(set(calls[0].member_post_ids))
        if (
            not set(selected) <= set(members)
            or calls[0].member_post_ids != calls[1].member_post_ids
            or calls[0].provenance["context"]["post_ids"] != calls[1].provenance["context"]["post_ids"]
            or user_packet(calls[0]) != user_packet(calls[1])
            or calls[0].provenance["post_snapshots"] != calls[1].provenance["post_snapshots"]
        ):
            raise BatchAdmissionError("classifier_revalidation_packet_mismatch")
        states = list(PostEnrichmentState.objects.select_for_update().filter(pk__in=members))
        if len(states) != len(members) or any(
            s.claim_expires_at and s.claim_expires_at > timezone.now() for s in states
        ):
            raise BatchAdmissionError("cached_revalidation_post_missing_or_claimed")
        list(Post.objects.select_for_update().filter(pk__in=members).order_by("pk"))
        snapshot = saved_classifier_input(calls[0])
        facts = completion_facts(selected)
        if all(facts[p]["translation"] and facts[p]["classification"] for p in selected):
            return {"replayed": [], "already_complete": selected}
        locked = list(OriginalContentCall.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
        for call in locked:
            if not _cached_reply_valid(call, delegates["classification"], ""):
                raise BatchAdmissionError("classifier_revalidation_response_invalid")
            call.import_evidence = _revalidation_evidence(
                call, actor=actor, reason=reason, validator="classifier_packet_canonical_replay_v1",
                selected_member_ids=selected,
            )
            call.import_state, call.error_code = "pending", ""
            call.save(update_fields=["import_state", "error_code", "import_evidence", "updated_at"])
        prepared, _, missing = prepare_page(
            job, selected, cfg, delegates=delegates, classification_input_snapshot=snapshot,
        )
        if prepared or missing:
            raise BatchAdmissionError("classifier_revalidation_requires_unsaved_reply")
        facts = completion_facts(members)
        succeeded = set(PostEnrichmentState.objects.filter(
            pk__in=selected, translation_status="succeeded", classification_status="succeeded",
        ).values_list("post_id", flat=True))
        if succeeded != set(selected) or any(
            not facts[p]["translation"] or not facts[p]["classification"] for p in selected
        ):
            raise BatchAdmissionError("classifier_revalidation_publication_incomplete")
        complete = sorted(p for p in members if facts[p]["classification"])
        remaining = sorted(set(members) - set(complete))
        for call in locked:
            call.refresh_from_db()
            call.import_state = "error" if remaining else "applied"
            call.import_evidence = {
                **call.import_evidence,
                "validation": "canonical_validation_failed" if remaining else "passed",
                "complete_member_ids": complete, "remaining_member_ids": remaining,
                "invalid_member_ids": remaining, "revalidated_member_ids": selected,
            }
            call.save(update_fields=["import_state", "import_evidence", "updated_at"])
        return {"replayed": selected, "remaining_packet_members": remaining}


def close_unrecoverable_direct_imports(
    job_id, *, call_ids, terminal_controller, actor, reason,
):
    """Explicitly abandon missing imports; provider outcomes and charges stay unknown.

    The operator must independently verify the supplied owned-controller receipt.
    This never sends a replacement, changes physical attempts or refunds a call.
    """
    ids = sorted(set(call_ids))
    if not 0 < len(ids) <= 20 or not actor.strip() or not reason.strip():
        raise BatchAdmissionError("unknown_import_closure_requires_ids_and_audit")
    if len(actor) > 160 or len(reason) > 1000:
        raise BatchAdmissionError("cached_revalidation_audit_too_large")
    try:
        started = timezone.datetime.fromisoformat(terminal_controller["startedAt"].replace("Z", "+00:00"))
        finished = timezone.datetime.fromisoformat(terminal_controller["finishedAt"].replace("Z", "+00:00"))
        valid_receipt = (
            isinstance(terminal_controller["id"], str)
            and terminal_controller["id"].startswith("job-")
            and terminal_controller["status"] in {"succeeded", "failed", "canceled", "cancelled"}
            and timezone.is_aware(started) and timezone.is_aware(finished)
            and started <= finished <= timezone.now() + timedelta(seconds=5)
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        valid_receipt = False
    if not valid_receipt:
        raise BatchAdmissionError("unknown_import_terminal_controller_required")
    closed, already_closed = [], []
    with transaction.atomic():
        job = _locked_drained_revalidation_job(job_id)
        calls = list(OriginalContentCall.objects.filter(
            pk__in=ids, provider_batch__source_collection_job=job,
        ).select_related("provider_batch"))
        if len(calls) != len(ids) or any(
            c.state != "ambiguous" or c.provider_batch.transport != "direct"
            or c.response_payload is not None or c.response_hash
            or c.completed_at is not None or c.actual_usd is not None
            or c.sent_at is None or not started <= c.sent_at <= finished
            for c in calls
        ):
            raise BatchAdmissionError("unknown_import_closure_ineligible_call")
        members = sorted({p for c in calls for p in c.member_post_ids})
        states = list(PostEnrichmentState.objects.select_for_update().filter(pk__in=members))
        if len(states) != len(members) or any(
            s.claim_expires_at and s.claim_expires_at > timezone.now() for s in states
        ):
            raise BatchAdmissionError("cached_revalidation_post_missing_or_claimed")
        snapshots = {
            str(p.pk): post_snapshot(p)
            for p in Post.objects.select_for_update().filter(pk__in=members).prefetch_related("brands")
        }
        for call in OriginalContentCall.objects.select_for_update().filter(pk__in=ids).order_by("pk"):
            if call.provenance.get("post_snapshots") != {p: snapshots[p] for p in call.member_post_ids}:
                raise BatchAdmissionError("cached_revalidation_source_changed")
            if call.import_state == "error" and call.import_evidence.get("validation") == "operator_closed_missing_import":
                already_closed.append(call.pk)
                continue
            if call.import_state != "pending":
                raise BatchAdmissionError("unknown_import_closure_unrelated_import_state")
            call.import_evidence = {
                **_revalidation_evidence(
                    call, actor=actor, reason=reason, validator="operator_unknown_import_closure_v1",
                    terminal_controller=terminal_controller,
                ),
                "validation": "operator_closed_missing_import",
                "provider_outcome": "unknown", "cost_unknown": True,
                "replacement_policy": "original_attempt_request_usd_and_deadline_limits",
            }
            call.import_state = "error"
            call.save(update_fields=["import_state", "import_evidence", "updated_at"])
            closed.append(call.pk)
    return {"closed_imports": closed, "already_closed": already_closed}


def prepare_page(job, ids, cfg, *, delegates=None, classification_input_snapshot=None):
    """Replay exact shared callers; missing replies roll back every Post write."""
    own_historical_posts(job, ids)
    stage_targets = {
        stage: set(
            PostEnrichmentState.objects.filter(
                pk__in=ids,
                **{stage + "_status": "pending"},
            ).values_list("post_id", flat=True)
        )
        for stage in ("translation", "classification")
    }
    calls = list(
        OriginalContentCall.objects.filter(
            member_post_ids__overlap=ids,
            state="completed",
            import_state__in=["pending", "applied"],
        )
        .select_related("provider_batch")
        .order_by("reserved_at")
    )
    current_snapshots = {
        str(p.pk): post_snapshot(p)
        for p in Post.objects.filter(pk__in=ids).prefetch_related("brands")
    }
    # An exact paid reply can outlive its source job. Its original ownership,
    # charge and full packet remain attached to the original call.
    calls = [call for call in calls if all(
        call.provenance.get("post_snapshots", {}).get(p) == current_snapshots[p]
        for p in set(call.member_post_ids).intersection(current_snapshots)
    )]
    cached = {call.request_hash: call for call in calls}
    outstanding = set(
        OriginalContentCall.objects.filter(
            member_post_ids__overlap=ids,
            state__in=["reserved", "sent", "ambiguous"],
            import_state="pending",
        ).values_list("request_hash", flat=True)
    )
    prepared, consumed, missing = {}, set(), set()
    rejected = set()
    sources = dict(Post.objects.filter(pk__in=ids).values_list("pk", "text"))
    lock = threading.Lock()

    def resolve(identity, body, kind, context):
        with lock:
            if identity in cached:
                call = cached[identity]
                if _cached_reply_valid(
                    call,
                    delegates[context["stage"]],
                    sources[next(p for p in call.member_post_ids if p in sources)],
                ):
                    consumed.add(call.pk)
                    return call.response_payload
                rejected.add(call.pk)
            missing.add(identity)
            if identity not in outstanding and (
                context["stage"] != "classification" or _classifier_ready(body)
            ):
                prepared[identity] = {
                    "hash": identity,
                    "body": body,
                    "kind": kind,
                    "context": context,
                }
        return None

    delegates = delegates or {
        "translation": build_translator_client_from_env(
            cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND",
        ),
        "classification": build_classifier_client_from_env(
            cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND",
        ),
    }
    if any(client is None for client in delegates.values()):
        raise BatchAdmissionError("enrichment_role_credentials_missing")
    clients = {
        stage: DeferredInferenceClient(
            client,
            resolve=resolve,
            reply_transport=lambda identity: cached[identity].provider_batch.transport,
            context_transform=getattr(client, "context_for_request", None),
        )
        for stage, client in delegates.items()
    }
    bounded = bounded_backfill_config(cfg, enrichment_limit=len(ids))
    if not bounded.llm.literal_translation_v2_enabled:
        raise BatchAdmissionError("native_enrichment_requires_literal_translation_v2")
    runner = CycleRunner(
        cfg=bounded,
        cycle_kind="backfill",
        _post_fetch_clients=clients,
        _max_llm_calls=2000,
    )
    with transaction.atomic():
        result = runner._run_post_fetch(
            [],
            run_id=f"batch-replay-{uuid.uuid4().hex}",
            post_ids=set(ids),
            source_collection_job_id=job.pk,
            classification_input_snapshot=classification_input_snapshot,
        )
        snapshot_ids = set(ids) | {
            p for request in prepared.values() for p in request["context"]["post_ids"]
        }
        snapshots = {
            str(p.pk): post_snapshot(p)
            for p in Post.objects.filter(pk__in=snapshot_ids).prefetch_related("brands")
        }
        for request in prepared.values():
            request["snapshots"] = {
                p: snapshots[p] for p in request["context"]["post_ids"]
            }
        if missing:
            transaction.set_rollback(True)
        else:
            member_ids = set(ids) | {p for call in calls for p in call.member_post_ids}
            states = {
                str(s.pk): s
                for s in PostEnrichmentState.objects.filter(pk__in=member_ids)
            }
            for call in calls:
                if call.pk not in consumed:
                    continue
                if call.provider_batch.source_collection_job_id != job.pk:
                    # Reuse does not rewrite another campaign's import audit.
                    continue
                prefix = call.stage
                claimed_ids = set(
                    result.get("enrichment_current_cycle_post_ids", [])
                ) | set(result.get("enrichment_carryover_post_ids", []))
                processed = (
                    set(call.member_post_ids) & stage_targets[prefix] & claimed_ids
                )
                applied = {
                    p
                    for p in call.member_post_ids
                    if getattr(states[p], f"{prefix}_status") == "succeeded"
                }
                success = applied == set(call.member_post_ids)
                partial = not success and processed <= applied
                call.import_state = (
                    "applied" if success else "pending" if partial else "error"
                )
                call.import_evidence = {
                    **call.import_evidence,
                    "published_at": timezone.now().isoformat(),
                    "validation": "passed"
                    if success
                    else "partial"
                    if partial
                    else "canonical_validation_failed",
                    "complete_member_ids": sorted(applied),
                    "processed_member_ids": sorted(processed),
                    "already_complete_member_ids": sorted(applied - processed),
                    "remaining_member_ids": sorted(set(call.member_post_ids) - applied),
                    "invalid_member_ids": sorted(processed - applied),
                }
                call.save(
                    update_fields=["import_state", "import_evidence", "updated_at"]
                )
    # A missing dependency rolls back Post publication, not evidence that a
    # particular saved reply failed validation. Otherwise it would replay forever.
    if rejected:
        with transaction.atomic():
            CollectionJob.objects.select_for_update().get(pk=job.pk)
            for call in OriginalContentCall.objects.select_for_update().filter(
                pk__in=rejected,
                provider_batch__source_collection_job=job,
                state="completed",
                import_state__in=["pending", "applied"],
            ):
                call.import_state = "error"
                call.error_code = "cached_response_validation_failed"
                call.import_evidence = {
                    **call.import_evidence,
                    "validation": "failed",
                    "reason": "canonical_cached_reply_rejected",
                    "validated_at": timezone.now().isoformat(),
                }
                call.save(
                    update_fields=[
                        "import_state",
                        "error_code",
                        "import_evidence",
                        "updated_at",
                    ]
                )
    return list(prepared.values()), result, bool(missing)


def deferred_enrichment_work(job, *, max_attempts, operation_scope="all"):
    """Derive unresolved work from retained attempts, without changing their state.

    Packet regrouping must not reset a Post's retry allowance. Saved replies
    retain their complete positional packet, while publication can proceed for
    independent members without reissuing the paid request.
    """
    failures, usable, latest_failure = defaultdict(int), {}, {}
    deferred = historical_ownership_conflicts(
        job, PostEnrichmentState.objects.filter(
            post__collection_observations__run__job=job,
            post__collection_observations__source_subject_kind="post",
        ).distinct(),
    )
    calls = (
        OriginalContentCall.objects.filter(
            provider_batch__source_collection_job=job,
        )
        .order_by("reserved_at", "pk")
        .values(
            "member_post_ids",
            "model",
            "stage",
            "state",
            "import_state",
            "import_evidence",
            "provenance",
        )
    )
    for index, call in enumerate(calls.iterator(chunk_size=200)):
        context = call["provenance"].get("context", {})
        targeted = context.get("operation") == "post_targeted_extraction"
        if (operation_scope == "base" and targeted) or (
            operation_scope == "targeted" and not targeted
        ):
            continue
        ids = call["member_post_ids"]
        if call["state"] == "ambiguous" and call["import_state"] == "pending":
            deferred.update({p: "provider_outcome_unknown" for p in ids})
        for post_id in ids:
            key = (
                post_id,
                call["model"],
                call["stage"],
                context.get("operation"),
                context.get("role"),
                context.get("target_language"),
                context.get("chunk_index"),
                context.get("input_fingerprints", {}).get(post_id)
                or context.get("source_fingerprint"),
            )
            evidence = call["import_evidence"]
            if (
                call["state"] == "completed"
                and evidence.get("validation") != "failed"
                and post_id
                in evidence.get(
                    "complete_member_ids", evidence.get("applied_member_ids", [])
                )
            ):
                usable[key] = index
            elif call["state"] == "failed" or (
                call["import_state"] == "error"
                and (
                    evidence.get("validation") == "failed"
                    or post_id in evidence.get("invalid_member_ids", ids)
                )
            ):
                failures[key] += 1
                latest_failure[key] = index
            elif call["state"] == "completed" and call["import_state"] in {
                "pending",
                "applied",
            }:
                usable[key] = index
    for key, count in failures.items():
        if count >= max_attempts and latest_failure[key] > usable.get(key, -1):
            deferred.setdefault(key[0], "model_attempt_allowance_exhausted")
    return deferred


def saved_classifier_input(call, *, post_ids=None):
    """Recover the submitted positional packet, keeping source and slots pinned."""
    from x_monitor.attribution import _validated_tracked_brand_catalog_snapshot

    packet = json.loads(
        next(
            m["content"] for m in call.request_packet["messages"] if m["role"] == "user"
        )
    )
    catalog = _validated_tracked_brand_catalog_snapshot(packet["tracked_brands"])
    ids = call.provenance["context"]["post_ids"]
    cases = packet["cases"]
    if len(ids) != len(cases) or set(ids) != set(call.member_post_ids):
        raise BatchAdmissionError("saved_classifier_packet_members_mismatch")
    inputs = {}
    for post_id, case in zip(ids, cases.values(), strict=True):
        evidence = case["evidence"]
        inputs[post_id] = {
            "text": evidence["source_text"],
            "brand_ids": list(case["brand_decision_slots"].values()),
            "created_at": evidence["created_at"],
            "source_language": evidence["source_language"],
            "english_translation": evidence["english_translation"],
            "context": evidence["context"],
            "affiliations": evidence["author_affiliations"],
        }
    selected = set(ids) if post_ids is None else set(post_ids)
    if not selected <= set(ids):
        raise BatchAdmissionError("saved_classifier_packet_members_mismatch")
    snapshots = {p: call.provenance["post_snapshots"][p] for p in selected}
    current = {
        str(p.pk): post_snapshot(p)
        for p in Post.objects.filter(pk__in=selected).prefetch_related("brands")
    }
    if current != snapshots:
        raise BatchAdmissionError("saved_classifier_packet_source_changed")
    return {"catalog": catalog, "inputs": inputs}


def _replay_pending_classifier_packets(
    job,
    cfg,
    *,
    selection,
    delegates,
    limit,
    excluded_post_ids=(),
    defer_failures=False,
):
    """Consume paid replies in their original packets before regrouping Posts."""
    pending = (
        PostEnrichmentState.objects.filter(
            source_collection_job=job,
            classification_status="pending",
        )
        .exclude(post_id__in=excluded_post_ids)
        .order_by()
        .values("post_id")
    )
    replies = OriginalContentCall.objects.filter(
        stage="classification",
        state="completed",
        import_state__in=["pending", "applied"],
        member_post_ids__overlap=ArraySubquery(pending),
    )
    replies = replies.filter(
        provenance__context__role__in=["content", "brand_interpretation"]
    )
    if selection:
        replies = replies.filter(member_post_ids__overlap=selection)
    requests, seen, stale = [], set(), []
    for reply in replies.order_by("reserved_at").iterator(chunk_size=40):
        ids = reply.member_post_ids
        packet = tuple(sorted(ids))
        if packet in seen:
            continue
        members = set(CollectionObservation.objects.filter(
            run__job=job, post_id__in=packet, source_subject_kind="post",
        ).values_list("post_id", flat=True))
        selected = [
            p
            for p in packet
            if p in members and p not in excluded_post_ids and (not selection or p in selection)
        ]
        if not selected:
            continue
        try:
            saved_input = saved_classifier_input(reply, post_ids=selected)
        except BatchAdmissionError as exc:
            if str(exc) != "saved_classifier_packet_source_changed" or (
                not defer_failures and reply.import_state == "pending"
            ):
                raise
            # This saved packet cannot authorize publication of changed
            # members. Fresh preparation retains normal paid deduplication.
            stale.append(reply.pk)
            continue
        seen.add(packet)
        prepared, _, _ = prepare_page(
            job,
            selected,
            cfg,
            delegates=delegates,
            classification_input_snapshot=saved_input,
        )
        requests.extend(prepared)
        # Publication can reject a newer attempt while an older paid reply is
        # still available. Let the next advance try it; the campaign's progress
        # guard bounds genuinely stuck work without discarding either reply.
        if len(seen) >= 20 or len(requests) >= limit:
            break
    # A saved packet may still need another reply. Keep its identity and let
    # those dependencies finish instead of buying a differently packed copy.
    blocked = {p for ids in replies.exclude(pk__in=stale)
               .values_list("member_post_ids", flat=True) for p in ids}
    return requests, blocked.intersection(pending.values_list("post_id", flat=True))


def _update(claim, **values):
    with fenced_batch(claim, allow_expired_deadline=True) as batch:
        for key, value in values.items():
            setattr(batch, key, value)
        batch.save(update_fields=[*values, "updated_at"])


def _accept_submission(claim, receipt):
    identifier = receipt.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise BatchProtocolError("batch_submission_identity_missing")
    _update(
        claim,
        provider_batch_id=identifier,
        provider_status=receipt.get("status", ""),
        state="waiting",
        next_poll_at=timezone.now() + timedelta(seconds=60),
        error_code="",
    )


def advance_batch(batch_id, *, client_factory=None, api_key):
    """One bounded group advancement; no sleeping or lock across HTTP."""
    claim = claim_batch(batch_id, owner=f"backfill:{uuid.uuid4().hex}")
    batch = ProviderBatch.objects.get(pk=batch_id)
    if batch.next_poll_at and batch.next_poll_at > timezone.now():
        release_batch(claim)
        return
    client = (client_factory or DeepInfraBatchClient)(
        api_key=api_key,
        before_request=lambda method, path: control_start(claim, method, path),
    )
    try:
        if batch.state in {"registered", "uploading"}:
            # An interrupted upload cannot have started inference. Re-uploading
            # is safe, counted, and retains any previous child reservations.
            rows = [
                (c.request_identity, c.request_packet)
                for c in batch.calls.order_by("request_identity")
            ]
            content = encode_requests(
                rows,
                max_requests=batch.policy["max_file_requests"],
                max_bytes=batch.policy["max_file_bytes"],
            )
            _update(claim, state="uploading")
            receipt = client.upload(content)
            identifier = receipt.get("id")
            if not isinstance(identifier, str) or not identifier:
                raise BatchProtocolError("batch_input_file_identity_missing")
            _update(claim, state="uploaded", input_file_id=identifier)
            batch.refresh_from_db()
        if batch.state == "uploaded":
            mark_submitting(claim)
            receipt = client.submit(batch.input_file_id, identity=batch.group_key)
            _accept_submission(claim, receipt)
            return
        if batch.state in {"submitting", "ambiguous"}:
            # Reconcile uncertain acceptance; never blindly re-submit an input.
            after = None
            for _ in range(10):
                page = client.list_batches(after=after)
                found = [
                    r
                    for r in page.get("data", [])
                    if r.get("input_file_id") == batch.input_file_id
                    and (r.get("metadata") or {}).get("request_identity")
                    == batch.group_key
                ]
                if len(found) > 1:
                    raise BatchProtocolError("batch_duplicate_submission_detected")
                if found:
                    _accept_submission(claim, found[0])
                    return
                if not page.get("has_more"):
                    break
                data = page.get("data") or []
                if not data or data[-1].get("id") == after:
                    raise BatchProtocolError("batch_reconciliation_cursor_invalid")
                after = data[-1]["id"]
            _update(
                claim,
                state="ambiguous",
                error_code="submission_acceptance_unknown",
                next_poll_at=timezone.now() + timedelta(minutes=5),
            )
            return
        if batch.state == "waiting":
            receipt = client.retrieve(batch.provider_batch_id)
            if (
                receipt.get("id") != batch.provider_batch_id
                or receipt.get("input_file_id") != batch.input_file_id
            ):
                raise BatchProtocolError("batch_poll_identity_mismatch")
            status = receipt.get("status")
            if status not in TERMINAL_PROVIDER:
                delay = min(900, max(60, 60 * batch.control_requests))
                _update(
                    claim,
                    provider_status=status or "",
                    next_poll_at=timezone.now() + timedelta(seconds=delay),
                )
                return
            _update(
                claim,
                state="importing",
                provider_status=status,
                output_file_id=receipt.get("output_file_id") or "",
                error_file_id=receipt.get("error_file_id") or "",
            )
            batch.refresh_from_db()
        if batch.state == "importing":
            for file_id in (batch.output_file_id, batch.error_file_id):
                if file_id:
                    for index, output in enumerate(client.outputs(file_id), start=1):
                        import_response(claim, output)
                        if index % 100 == 0:
                            with fenced_batch(
                                claim, allow_expired_deadline=True
                            ) as current:
                                current.claim_expires_at = timezone.now() + timedelta(
                                    seconds=180
                                )
                                current.save(
                                    update_fields=["claim_expires_at", "updated_at"]
                                )
            with fenced_batch(claim, allow_expired_deadline=True) as row:
                row.calls.filter(state__in=["sent", "ambiguous"]).update(
                    state="failed",
                    import_state="error",
                    error_code="provider_terminal_result_missing",
                )
                row.state = (
                    "completed"
                    if not row.calls.exclude(state="completed").exists()
                    else "failed"
                )
                row.completed_at = timezone.now()
                row.next_poll_at = None
                row.save(
                    update_fields=[
                        "state",
                        "completed_at",
                        "next_poll_at",
                        "updated_at",
                    ]
                )
    except (BatchHTTPError, BatchTransportError) as exc:
        current = ProviderBatch.objects.get(pk=batch_id)
        delay = max(60, getattr(exc, "retry_after_seconds", 60))
        state = "ambiguous" if current.state == "submitting" else current.state
        _update(
            claim,
            state=state,
            error_code=str(exc)[:64],
            next_poll_at=timezone.now() + timedelta(seconds=delay),
        )
        if isinstance(exc, BatchHTTPError) and not exc.retryable:
            raise BatchAdmissionError("batch_provider_rejected_request") from None
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
        release_batch(claim)


def _blocking_model_groups(job, model, *, allow_drained_ambiguous):
    groups = ProviderBatch.objects.filter(
        source_collection_job=job,
        model=model,
        state__in=ACTIVE_STATES,
    )
    if allow_drained_ambiguous:
        groups = groups.annotate(
            unfinished=Exists(
                OriginalContentCall.objects.filter(
                    provider_batch_id=OuterRef("pk"),
                    state__in=["reserved", "sent"],
                )
            )
        ).exclude(
            state="ambiguous",
            transport="direct",
            unfinished=False,
            claim_expires_at__lte=timezone.now(),
        )
    return groups


def _register_requests(
    job, requests, policy, cfg, *, transport="batch", allow_drained_ambiguous=False,
    deferred=None,
):
    models = defaultdict(list)
    for request in requests:
        models[request["body"]["model"]].append(request)
    created = []
    for model, members in models.items():
        if _blocking_model_groups(
            job, model, allow_drained_ambiguous=allow_drained_ambiguous
        ).exists():
            continue
        # Stable order bounds both the uploaded manifest and request membership.
        members = sorted(members, key=lambda r: r["hash"])
        selected, file_bytes = [], 0
        group_limit = policy["max_file_requests"]
        for request in members:
            size = len(
                encode_requests(
                    [(request["hash"], request["body"])],
                    max_bytes=policy["max_file_bytes"],
                )
            )
            if (
                len(selected) >= group_limit
                or file_bytes + size > policy["max_file_bytes"]
            ):
                if not selected:
                    raise BatchProtocolError("batch_request_file_limit")
                break
            selected.append(request)
            file_bytes += size
        manifest = digest([r["hash"] for r in selected])
        attempt = (
            ProviderBatch.objects.filter(
                source_collection_job=job, manifest_hash=manifest
            ).count()
            + 1
        )
        group_key = digest({"manifest": manifest, "attempt": attempt})
        with transaction.atomic():
            CollectionJob.objects.select_for_update().get(pk=job.pk)
            existing = job.provider_batches.order_by("created_at").first()
            assert_enrichment_admission(job.pk)
            if existing and enrichment_policy_definition(
                existing.policy
            ) != enrichment_policy_definition(policy):
                raise BatchAdmissionError("enrichment_policy_changed")
            if _blocking_model_groups(
                job, model, allow_drained_ambiguous=allow_drained_ambiguous
            ).exists():
                continue
            profile = (
                cfg.llm.translator_deepinfra_request_profile
                if model == cfg.llm.translator_model
                else cfg.llm.classifier_deepinfra_request_profile
            )
            batch = ProviderBatch.objects.create(
                source_collection_job=job,
                group_key=group_key,
                transport=transport,
                source_definition_hash=job.definition_sha256,
                cohort_hash=digest(
                    sorted({p for r in selected for p in r["context"]["post_ids"]})
                ),
                manifest_hash=manifest,
                provider="deepinfra",
                model=model,
                endpoint="/v1/chat/completions",
                request_profile=profile,
                policy=policy,
                deadline_at=timezone.datetime.fromisoformat(policy["deadline"]),
            )
            claim = claim_batch(batch.pk, owner=f"register:{uuid.uuid4().hex}")
            if deferred is None:
                reserve_requests(claim, selected)
            else:
                # Each child retains the same fenced, Post-locked admission.
                # A duplicate racing preparation cannot roll back siblings.
                for request in selected:
                    try:
                        with transaction.atomic():
                            reserve_requests(claim, [request])
                    except BatchAdmissionError as exc:
                        if str(exc) not in {
                            "model_request_already_outstanding_or_complete",
                            "model_member_work_already_outstanding",
                            "model_attempt_allowance_exhausted",
                        }:
                            raise
                        deferred.update({p: str(exc) for p in exc.member_ids})
                admitted = list(batch.calls.order_by("request_hash"))
                admitted_manifest = digest([c.request_hash for c in admitted])
                if admitted_manifest != manifest:
                    admitted_attempt = ProviderBatch.objects.filter(
                        source_collection_job=job, manifest_hash=admitted_manifest,
                    ).exclude(pk=batch.pk).count() + 1
                    batch.manifest_hash = admitted_manifest
                    batch.group_key = digest({"manifest": admitted_manifest, "attempt": admitted_attempt})
                    batch.cohort_hash = digest(sorted({p for c in admitted for p in c.member_post_ids}))
                    batch.save(update_fields=["manifest_hash", "group_key", "cohort_hash", "updated_at"])
                if not admitted:
                    # Retain the policy anchor after an all-duplicate race.
                    # This zero-send group is terminal and never reaches HTTP.
                    batch.state = "completed"
                    batch.completed_at = timezone.now()
                    batch.save(update_fields=["state", "completed_at", "updated_at"])
            release_batch(claim)
        if batch.calls.exists():
            created.append(batch.pk)
    return created


def execute_enrichment(
    job_id,
    *,
    cfg,
    api_key,
    policy=None,
    delegates=None,
    client_factory=None,
    read_only=False,
    transport="batch",
    direct_concurrency=32,
    direct_client_factory=None,
    defer_failures=False,
):
    from monitor.backfill_direct import advance_direct, validate_concurrency

    if transport not in {"batch", "direct"}:
        raise BatchAdmissionError("enrichment_transport_invalid")
    validate_concurrency(direct_concurrency)

    def advance(group):
        if group.transport == "direct":
            advance_direct(
                group.pk,
                api_key=api_key,
                concurrency=direct_concurrency,
                client_factory=direct_client_factory,
            )
        else:
            advance_batch(group.pk, client_factory=client_factory, api_key=api_key)

    job = CollectionJob.objects.get(pk=job_id)
    if (
        job.source_id != "x"
        or job.purpose != "content"
        or job.operation != "x_backfill"
    ):
        raise BatchAdmissionError("enrichment_requires_real_x_backfill_job")
    with connection.cursor() as cursor:
        # Match the login saved by the collector, including SET ROLE sessions.
        cursor.execute("SELECT current_database(), session_user")
        name, role = cursor.fetchone()
    from monitor.backfill_database import job_database_matches
    if not job_database_matches(job, {"name": name, "user": role}):
        raise BatchAdmissionError("enrichment_database_identity_mismatch")
    existing = job.provider_batches.order_by("created_at").first()
    pin = configuration_pin(cfg)
    if existing:
        if policy is not None and enrichment_policy_definition(
            policy | {"configuration_pin": pin}
        ) != enrichment_policy_definition(existing.policy):
            raise BatchAdmissionError("enrichment_policy_changed")
        policy = existing.policy
        if not read_only and policy.get("configuration_pin") != pin:
            raise BatchAdmissionError("enrichment_configuration_changed")
    elif policy is not None:
        policy = policy | {"configuration_pin": pin}
    if policy is None and not read_only:
        raise BatchAdmissionError("enrichment_policy_required")
    control = enrichment_control_status(job.pk)
    if not read_only and not control["processing_paused"]:
        adopt_completed_membership(job)
    observations = CollectionObservation.objects.filter(
        run__job=job, source_subject_kind="post"
    )
    selection = (policy or {}).get("selection")
    deferred = (
        deferred_enrichment_work(
            job, max_attempts=int(policy["max_attempts"]), operation_scope="base"
        )
        if defer_failures and policy
        else {}
    )
    if selection:
        observations = observations.filter(post_id__in=selection)
        if observations.values("post_id").distinct().count() != len(selection):
            raise BatchAdmissionError("pilot_selection_membership_missing")
    if not read_only and not control["processing_paused"]:
        try:
            if existing is None:
                reopen_incomplete_successes(job, observations)
                if defer_failures:
                    deferred = deferred_enrichment_work(
                        job, max_attempts=int(policy["max_attempts"]), operation_scope="base",
                    )
            for batch in list(
                job.provider_batches.filter(state__in=ACTIVE_STATES).order_by(
                    "created_at"
                )[:2]
            ):
                advance(batch)
            request_limit = direct_concurrency * 2 if transport == "direct" else 2000
            requests, cached_packet_members = _replay_pending_classifier_packets(
                job,
                cfg,
                selection=selection,
                delegates=delegates,
                limit=request_limit,
                excluded_post_ids=deferred,
                defer_failures=defer_failures,
            )
            after = ""
            work = observations.filter(
                Q(post__enrichment_state__translation_status="pending")
                | Q(post__enrichment_state__classification_status="pending")
            )
            if deferred:
                work = work.exclude(post_id__in=deferred)
            if cached_packet_members:
                work = work.exclude(post_id__in=cached_packet_members)
            for _ in range(20):
                ids = list(
                    work.filter(post_id__gt=after)
                    .order_by("post_id")
                    .values_list("post_id", flat=True)
                    .distinct()[:100]
                )
                if not ids:
                    break
                after = ids[-1]
                pending = list(
                    PostEnrichmentState.objects.filter(pk__in=ids)
                    .exclude(
                        translation_status="succeeded",
                        classification_status="succeeded",
                    )
                    .values_list("post_id", flat=True)
                )
                if not pending:
                    continue
                prepared, _, _ = prepare_page(job, pending, cfg, delegates=delegates)
                requests.extend(prepared)
                if len(requests) >= request_limit:
                    break
            for batch_id in _register_requests(
                job,
                requests,
                policy,
                cfg,
                transport=transport,
                allow_drained_ambiguous=defer_failures,
                deferred=deferred if defer_failures else None,
            ):
                advance(ProviderBatch.objects.get(pk=batch_id))
        except BatchAdmissionError as exc:
            if str(exc) != "enrichment_paused":
                raise
    states = PostEnrichmentState.objects.filter(
        post__collection_observations__in=observations
    ).distinct()
    calls = OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=job
    )
    totals = calls.aggregate(
        reserved_usd=Sum("reserved_usd"),
        provider_reported_usd=Sum("actual_usd"),
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
    )
    pending_count = states.exclude(
        translation_status="succeeded", classification_status="succeeded"
    ).count()
    actionable_pending_count = (
        states.exclude(post_id__in=deferred)
        .exclude(
            translation_status="succeeded",
            classification_status="succeeded",
        )
        .count()
    )
    cohort_count = observations.values("post_id").distinct().count()
    invalid = verify_cohort(observations)[1] if pending_count == 0 else None
    control = enrichment_control_status(job.pk)
    return {
        **control,
        "phase": "enrichment",
        "source_collection_job": str(job.pk),
        "twitterapi_requests": 0,
        "scope": "pilot" if selection else "source_cohort",
        "cohort_count": cohort_count,
        "source_cohort_count": CollectionObservation.objects.filter(
            run__job=job, source_subject_kind="post"
        )
        .values("post_id")
        .distinct()
        .count(),
        "collection_status": job.state,
        "pending_count": pending_count,
        "actionable_pending_count": actionable_pending_count,
        "deferred_post_count": len(deferred),
        "deferred_reasons": dict(Counter(deferred.values())),
        "persisted_output_invalid_count": len(invalid) if invalid is not None else None,
        "model_requests_reserved": calls.count(),
        "model_requests_sent": calls.exclude(sent_at=None).count(),
        "model_responses_received": calls.filter(state="completed").count(),
        "ambiguous_model_requests": calls.filter(state="ambiguous").count(),
        "direct_model_requests_sent": calls.filter(provider_batch__transport="direct")
        .exclude(sent_at=None)
        .count(),
        "cost_unknown_requests": calls.filter(actual_usd=None)
        .exclude(state="reserved")
        .count(),
        "control_requests": job.provider_batches.aggregate(n=Sum("control_requests"))[
            "n"
        ]
        or 0,
        "usage": {
            k: str(v) if isinstance(v, Decimal) else v for k, v in totals.items()
        },
        "active_batches": job.provider_batches.filter(state__in=ACTIVE_STATES).count(),
        "status": "completed"
        if cohort_count > 0
        and pending_count == 0
        and invalid == {}
        and states.count() == observations.values("post_id").distinct().count()
        else "partial",
    }


def adopt_completed_membership(job):
    """Adopt genuine pre-0085 stored-page evidence without rewriting history."""
    if job.state != "completed" or not job.last_success_id:
        return
    run = CollectionRun.objects.select_related("job").only("id", "job_id", "status", "job__purpose").get(
        pk=job.last_success_id
    )
    if run.job_id != job.pk or run.status != "success" or run.job.purpose != "content":
        raise BatchAdmissionError("historical_membership_success_run_mismatch")
    marker = (
        CollectionRun.objects.filter(pk=run.pk)
        .values_list("report__post_membership", flat=True)
        .get()
    )
    if marker is not None:
        if (
            not isinstance(marker, dict)
            or marker.get("version") != 1
            or type(marker.get("distinct_posts")) is not int
            or marker["distinct_posts"] < 0
        ):
            raise BatchAdmissionError("historical_membership_marker_invalid")
        count = (
            CollectionObservation.objects.filter(
                run__job=job, source_subject_kind="post"
            )
            .values("post_id")
            .distinct()
            .count()
        )
        if count != marker["distinct_posts"]:
            raise BatchAdmissionError("historical_typed_membership_count_changed")
        return
    reported = run.report.get("recovered_post_ids")
    if not isinstance(reported, list) or len(reported) > 100000:
        raise BatchAdmissionError("historical_membership_legacy_receipt_invalid")
    expected = {str(value) for value in reported}
    existing = set(
        CollectionObservation.objects.filter(
            run=run, source_subject_kind="post"
        ).values_list("post_id", flat=True)
    )
    if existing == expected:
        return
    witnessed = set()
    for scope in run.scopes.order_by("scope_key").iterator(chunk_size=10):
        for envelope in scope.envelopes:
            witnessed.update(str(value) for value in envelope.get("post_ids", []))
    if witnessed != expected:
        raise BatchAdmissionError("historical_membership_receipt_reconciliation_failed")
    for scope in run.scopes.order_by("scope_key").iterator(chunk_size=10):
        for envelope in scope.envelopes:
            ids = sorted({str(value) for value in envelope.get("post_ids", [])})
            observed = envelope.get("observed_at")
            observed = (
                timezone.datetime.fromisoformat(observed)
                if observed
                else run.completed_at
            )
            if observed is None or observed.tzinfo is None:
                raise BatchAdmissionError(
                    "historical_membership_observation_time_missing"
                )
            for offset in range(0, len(ids), 100):
                with transaction.atomic():
                    record_post_membership(
                        run, scope, ids[offset : offset + 100], observed_at=observed
                    )


def finish_pilot(job_id, *, cfg):
    """Expand a verified pilot to its source cohort without resetting charges."""
    with transaction.atomic():
        job = CollectionJob.objects.select_for_update().get(pk=job_id)
        first = job.provider_batches.order_by("created_at").first()
        if first is None or not first.policy.get("selection"):
            raise BatchAdmissionError("verified_pilot_required")
        if first.policy.get("configuration_pin") != configuration_pin(cfg):
            raise BatchAdmissionError("enrichment_configuration_changed")
        if job.provider_batches.filter(state__in=ACTIVE_STATES).exists():
            raise BatchAdmissionError("pilot_provider_work_outstanding")
        selected = first.policy["selection"]
        observations = CollectionObservation.objects.filter(
            run__job=job, post_id__in=selected, source_subject_kind="post"
        )
        total, invalid = verify_cohort(observations)
        if total != len(selected) or invalid:
            raise BatchAdmissionError("pilot_persisted_verification_failed")
        reopen_incomplete_successes(
            job,
            CollectionObservation.objects.filter(
                run__job=job, source_subject_kind="post"
            ),
        )
        policy = first.policy | {
            "selection": [],
            "max_usd": "25",
            "verified_pilot": selected,
            "pilot_verified_at": timezone.now().isoformat(),
            "pilot_max_usd": first.policy["max_usd"],
        }
        job.provider_batches.update(policy=policy)
        return policy
