"""Resumable enrichment of stored members over native or ordinary model HTTP."""

from __future__ import annotations

import hashlib
import inspect
import json
import threading
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.postgres.expressions import ArraySubquery
from django.db import connection, transaction
from django.db.models import Q, Sum
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
    BatchAdmissionError,
    claim_batch,
    control_start,
    digest,
    fenced_batch,
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
                PostEnrichmentState.objects.select_for_update().filter(pk__in=ids)
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
                    state.source_collection_job = job
                    state.save()


def policy_snapshot(
    *,
    max_usd,
    deadline,
    selection=None,
    max_model_requests=20000,
    max_control_requests=5000,
):
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
    return {
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
            source = _split_translation_chunks(source, chunk_size=2000)[context["chunk_index"]]
        target = context["target_language"]
        _, quantities = protect_translation_spans(source, target)
        text, _, _ = _restore_and_validate(source, target, text, quantities, {}, 0)
        return text is not None
    except DeepInfraPermanentError:
        return False


def prepare_page(job, ids, cfg, *, delegates=None):
    """Replay exact shared callers; missing replies roll back every Post write."""
    own_historical_posts(job, ids)
    calls = list(
        OriginalContentCall.objects.filter(
            provider_batch__source_collection_job=job,
            member_post_ids__overlap=ids,
            state="completed",
            import_state__in=["pending", "applied"],
        ).select_related("provider_batch").order_by("reserved_at")
    )
    cached = {call.request_hash: call for call in calls}
    outstanding = set(
        OriginalContentCall.objects.filter(
            provider_batch__source_collection_job=job,
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
                if _cached_reply_valid(call, delegates[context["stage"]], sources[call.member_post_ids[0]]):
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
        "translation": build_translator_client_from_env(cfg),
        "classification": build_classifier_client_from_env(cfg),
    }
    if any(client is None for client in delegates.values()):
        raise BatchAdmissionError("enrichment_role_credentials_missing")
    clients = {
        stage: DeferredInferenceClient(
            client,
            resolve=resolve,
            reply_transport=lambda identity: cached[identity].provider_batch.transport,
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
        )
        snapshots = {
            str(p.pk): post_snapshot(p)
            for p in Post.objects.filter(pk__in=ids).prefetch_related("brands")
        }
        for request in prepared.values():
            request["snapshots"] = {
                p: snapshots[p] for p in request["context"]["post_ids"]
            }
        if missing:
            transaction.set_rollback(True)
        else:
            states = {
                str(s.pk): s for s in PostEnrichmentState.objects.filter(pk__in=ids)
            }
            for call in calls:
                if call.pk not in consumed:
                    continue
                prefix = call.stage
                success = all(
                    getattr(states[p], f"{prefix}_status") == "succeeded"
                    for p in call.member_post_ids
                )
                call.import_state = "applied" if success else "error"
                call.import_evidence = {
                    **call.import_evidence,
                    "published_at": timezone.now().isoformat(),
                    "validation": "passed"
                    if success
                    else "canonical_validation_failed",
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
                pk__in=rejected, state="completed", import_state__in=["pending", "applied"],
            ):
                call.import_state = "error"
                call.error_code = "cached_response_validation_failed"
                call.import_evidence = {
                    **call.import_evidence, "validation": "failed",
                    "reason": "canonical_cached_reply_rejected",
                    "validated_at": timezone.now().isoformat(),
                }
                call.save(update_fields=["import_state", "error_code", "import_evidence", "updated_at"])
    return list(prepared.values()), result, bool(missing)


def _replay_pending_classifier_packets(job, cfg, *, selection, delegates, limit):
    """Consume paid replies in their original packets before regrouping Posts."""
    pending = PostEnrichmentState.objects.filter(
        source_collection_job=job, classification_status="pending",
    ).order_by().values("post_id")
    replies = OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=job,
        stage="classification", state="completed", import_state="pending",
        member_post_ids__overlap=ArraySubquery(pending),
    )
    if selection:
        replies = replies.filter(member_post_ids__overlap=selection)
    packets = list(replies.order_by("reserved_at").values_list(
        "member_post_ids", flat=True,
    )[:40])
    requests, seen = [], set()
    for ids in packets:
        packet = tuple(sorted(ids))
        if packet in seen:
            continue
        seen.add(packet)
        prepared, _, missing = prepare_page(job, list(packet), cfg, delegates=delegates)
        requests.extend(prepared)
        if not missing and replies.filter(member_post_ids=list(packet)).exists():
            # The canonical caller no longer consumes this saved context. Keep
            # its evidence and report it instead of deferring fresh work forever.
            raise BatchAdmissionError("cached_classifier_packet_not_consumed")
        if len(seen) >= 20 or len(requests) >= limit:
            break
    # A saved packet may still need another reply. Keep its identity and let
    # those dependencies finish instead of buying a differently packed copy.
    return requests, replies.exists()


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


def _register_requests(job, requests, policy, cfg, *, transport="batch"):
    models = defaultdict(list)
    for request in requests:
        models[request["body"]["model"]].append(request)
    created = []
    for model, members in models.items():
        if ProviderBatch.objects.filter(
            source_collection_job=job, model=model, state__in=ACTIVE_STATES
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
            if existing and existing.policy != policy:
                raise BatchAdmissionError("enrichment_policy_changed")
            if ProviderBatch.objects.filter(
                source_collection_job=job, model=model, state__in=ACTIVE_STATES
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
            reserve_requests(claim, selected)
            release_batch(claim)
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
):
    from monitor.backfill_direct import advance_direct, validate_concurrency

    if transport not in {"batch", "direct"}:
        raise BatchAdmissionError("enrichment_transport_invalid")
    validate_concurrency(direct_concurrency)

    def advance(group):
        if group.transport == "direct":
            advance_direct(
                group.pk, api_key=api_key, concurrency=direct_concurrency,
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
    pinned_database = job.definition.get("scope", {}).get("database", {})
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user")
        name, role = cursor.fetchone()
    if pinned_database != {"name": name, "user": role}:
        raise BatchAdmissionError("enrichment_database_identity_mismatch")
    existing = job.provider_batches.order_by("created_at").first()
    pin = configuration_pin(cfg)
    if existing:
        if (
            policy is not None
            and (policy | {"configuration_pin": pin}) != existing.policy
        ):
            raise BatchAdmissionError("enrichment_policy_changed")
        policy = existing.policy
        if not read_only and policy.get("configuration_pin") != pin:
            raise BatchAdmissionError("enrichment_configuration_changed")
    elif policy is not None:
        policy = policy | {"configuration_pin": pin}
    if policy is None and not read_only:
        raise BatchAdmissionError("enrichment_policy_required")
    if not read_only:
        adopt_completed_membership(job)
    observations = CollectionObservation.objects.filter(
        run__job=job, source_subject_kind="post"
    )
    selection = (policy or {}).get("selection")
    if selection:
        observations = observations.filter(post_id__in=selection)
        if observations.values("post_id").distinct().count() != len(selection):
            raise BatchAdmissionError("pilot_selection_membership_missing")
    if not read_only:
        if existing is None:
            reopen_incomplete_successes(job, observations)
        for batch in list(
            job.provider_batches.filter(state__in=ACTIVE_STATES).order_by("created_at")[
                :2
            ]
        ):
            advance(batch)
        request_limit = direct_concurrency * 2 if transport == "direct" else 2000
        requests, cached_packets_remain = _replay_pending_classifier_packets(
            job, cfg, selection=selection, delegates=delegates, limit=request_limit,
        )
        after = ""
        work = observations.filter(
            Q(post__enrichment_state__translation_status="pending")
            | Q(post__enrichment_state__classification_status="pending")
        )
        for _ in range(0 if cached_packets_remain else 20):
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
            job, requests, policy, cfg,
            transport=transport,
        ):
            advance(ProviderBatch.objects.get(pk=batch_id))
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
    cohort_count = observations.values("post_id").distinct().count()
    invalid = verify_cohort(observations)[1] if pending_count == 0 else None
    return {
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
        "persisted_output_invalid_count": len(invalid) if invalid is not None else None,
        "model_requests_reserved": calls.count(),
        "model_requests_sent": calls.exclude(sent_at=None).count(),
        "model_responses_received": calls.filter(state="completed").count(),
        "ambiguous_model_requests": calls.filter(state="ambiguous").count(),
        "direct_model_requests_sent": calls.filter(provider_batch__transport="direct").exclude(sent_at=None).count(),
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
    run = CollectionRun.objects.only("id", "job_id", "status", "purpose").get(
        pk=job.last_success_id
    )
    if run.job_id != job.pk or run.status != "success" or run.purpose != "content":
        raise BatchAdmissionError("historical_membership_success_run_mismatch")
    marker = CollectionRun.objects.filter(pk=run.pk).values_list(
        "report__post_membership", flat=True
    ).get()
    if marker is not None:
        if (
            not isinstance(marker, dict)
            or marker.get("version") != 1
            or type(marker.get("distinct_posts")) is not int
            or marker["distinct_posts"] < 0
        ):
            raise BatchAdmissionError("historical_membership_marker_invalid")
        count = (
            CollectionObservation.objects.filter(run__job=job, source_subject_kind="post")
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
