"""Bounded lookup of saved lineage findings for a newly qualified parent."""

import hashlib
import json
from time import monotonic
from uuid import UUID

from django.db import connection
from django.db.models import Value
from django.db.models.functions import MD5, Upper

# Provisional local work limits, shared with the existing identity sweep.
WAKEUP_BUDGETS = {"requests": 1, "bytes": 1048576, "seconds": 20, "items": 50}


def _find_lineage_dependents(*, parent_claim_id, after=None, limit, max_bytes, max_seconds):
    """Read one page under the caller's transaction; never enqueue or call a provider.

    The caller must commit any resulting enqueue and its page cursor together.
    Names and their hashes are search leads; saved source and Product identity
    are verified separately before returning a row.
    """
    from core.models import (
        EventDossier,
        EventDossierClaim,
        EventDossierReviewClaim,
        Product,
        ProductRelationship,
        ProductReleaseDetail,
    )
    from core.product_identity import _qualified_anchor_name, _resolved_anchor_product
    from core.product_identity_locks import ProductNameBusy, lock_product_evidence_names
    from core.product_release_dossiers import _read_pulse_packet
    from core.product_release_pipeline import canonical_dossier

    if not connection.in_atomic_block:
        raise ValueError("Lineage recovery requires the caller's transaction")
    if type(limit) is not int or limit <= 0 or type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("Explicit positive recovery budgets required")
    if type(max_seconds) not in (int, float) or not 0 < max_seconds <= 3600:
        raise ValueError("Explicit recovery time budget required")
    cursor_id = UUID(str(after)) if after is not None else None
    deadline = monotonic() + max_seconds
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('statement_timeout'), current_setting('lock_timeout'), "
            "(SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout'), "
            "(SELECT setting::bigint FROM pg_settings WHERE name='lock_timeout')"
        )
        statement_before, lock_before, statement_ms, lock_ms = cursor.fetchone()
        budget_ms = max(1, int(max_seconds * 1000))
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [f"{min(statement_ms or budget_ms, budget_ms)}ms", f"{min(lock_ms or budget_ms, budget_ms)}ms"])
    original = EventDossierClaim.objects.select_related("source_archive", "event_dossier_source__event_dossier", "claim_kind_reference").defer("source_archive__body").get(pk=parent_claim_id)
    dossier = canonical_dossier(original.event_dossier_source.event_dossier_id)
    dossier = EventDossier.objects.select_for_update(of=("self",), skip_locked=True).select_related("current_review").filter(pk=dossier.pk).first()
    if dossier is None or dossier.merged_into_id:
        result = {"status": "busy", "next_cursor": after, "more_remaining": True, "posts": [], "observations": [], "invalid": []}
    else:
        product_id = None
        name = None
        parent_bytes = 0
        if original.scope_key.startswith("pulse-finding-v1:"):
            parent_bytes = original.source_archive.byte_count if original.source_archive_id else 0
            if parent_bytes <= max_bytes:
                packet = _read_pulse_packet(original)
                anchor = EventDossierClaim.objects.select_related("source_archive", "event_dossier_source").defer("source_archive__body").filter(
                    event_dossier_source__event_dossier=dossier,
                    event_dossier_source__post_id=original.event_dossier_source.post_id,
                    event_dossier_source__collection_observation_id=original.event_dossier_source.collection_observation_id,
                    scope_key=original.scope_key, source_archive_id=original.source_archive_id,
                ).first()
                if anchor:
                    product_id = _resolved_anchor_product(anchor, dossier, packet=packet)
                    name = _qualified_anchor_name(anchor, dossier, packet=packet)
        elif (dossier.pk == original.event_dossier_source.event_dossier_id
              and dossier.current_review_id and dossier.current_review.review_state == "confirmed"
              and EventDossierReviewClaim.objects.filter(review_id=dossier.current_review_id, claim=original, disposition="accepted").exists()):
            detail = ProductReleaseDetail.objects.select_related("product").filter(review_id=dossier.current_review_id).first()
            if detail and detail.product_id:
                product_id, name = detail.product.pk, detail.observed_name
        latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").values_list("outcome", flat=True).first()
        if parent_bytes > max_bytes:
            result = {"status": "budget", "next_cursor": after, "more_remaining": True, "posts": [], "observations": [], "invalid": [], "bytes_read": 0}
        elif not product_id or not name or latest in {"non_release", "scam", "superseded"}:
            result = {"status": "unresolved", "next_cursor": after, "more_remaining": False, "posts": [], "observations": [], "invalid": []}
        else:
            try:
                lock_product_evidence_names([name])
            except ProductNameBusy:
                result = {"status": "busy", "next_cursor": after, "more_remaining": True, "posts": [], "observations": [], "invalid": []}
            else:
                parent = Product.objects.only("product_key").get(pk=product_id)
                phrases = [f"Classifier-reported {kind}: {name}" for kind in ("new_version", "finetune", "adapter", "quantized", "merge")]
                with connection.cursor() as cursor:
                    cursor.execute("SELECT " + ", ".join(["UPPER(%s)"] * len(phrases)), phrases)
                    normalized_phrases = set(cursor.fetchone())
                ids = []
                for phrase in phrases:
                    leads = EventDossierClaim.objects.annotate(_lineage_hash=MD5(Upper("assertion_text"))).filter(
                        _lineage_hash=MD5(Upper(Value(phrase))),
                        scope_key__startswith="pulse-lineage-v1:", source_archive__isnull=False,
                    )
                    if cursor_id:
                        leads = leads.filter(pk__gt=cursor_id)
                    ids.extend(leads.order_by("pk").values_list("pk", flat=True)[:limit + 1])
                selected_ids = sorted(set(ids))[:limit + 1]
                rows = list(EventDossierClaim.objects.filter(pk__in=selected_ids).annotate(_normalized_text=Upper("assertion_text"))
                            .select_related("source_archive", "event_dossier_source__event_dossier")
                            .defer("source_archive__body").order_by("pk"))
                posts, observations, invalid = set(), set(), []
                consumed, last = parent_bytes, after
                stopped = False
                for lead in rows[:limit]:
                    if monotonic() >= deadline:
                        stopped = True
                        break
                    if lead.event_dossier_source.event_dossier.merged_into_id:
                        last = str(lead.pk)
                        continue
                    if lead._normalized_text not in normalized_phrases:
                        last = str(lead.pk)
                        invalid.append(str(lead.pk))
                        continue
                    parts = lead.scope_key.split(":")
                    if len(parts) != 3:
                        last = str(lead.pk)
                        invalid.append(str(lead.pk))
                        continue
                    if consumed + lead.source_archive.byte_count > max_bytes:
                        stopped = True
                        break
                    consumed += lead.source_archive.byte_count
                    last = str(lead.pk)
                    anchor = EventDossierClaim.objects.select_related("source_archive", "event_dossier_source").filter(
                        event_dossier_source=lead.event_dossier_source, source_archive_id=lead.source_archive_id,
                        scope_key="pulse-finding-v1:" + parts[1],
                    ).first()
                    try:
                        child_packet = _read_pulse_packet(anchor) if anchor else None
                        relations = child_packet["finding"].get("lineage_evidence", []) if child_packet else []
                        relation = next((item for item in relations if hashlib.sha256(json.dumps(
                            item, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                        ).encode()).hexdigest() == parts[2]), None)
                    except (KeyError, TypeError, ValueError):
                        relation = None
                    if (not isinstance(relation, dict) or not isinstance(relation.get("relationship_kind"), str)
                            or not isinstance(relation.get("parent_observed_name"), str)
                            or lead.assertion_text !=
                            f"Classifier-reported {relation['relationship_kind']}: {relation['parent_observed_name']}"):
                        invalid.append(str(lead.pk))
                        continue
                    child_dossier = canonical_dossier(anchor.event_dossier_source.event_dossier_id)
                    child_product_id = _resolved_anchor_product(anchor, child_dossier, packet=child_packet)
                    if child_product_id and ProductRelationship.objects.filter(
                        parent_product_id=parent.product_key,
                        child_product__id=child_product_id,
                        product_relationship_type__code=relation["relationship_kind"],
                        evidence__source_archive_id=str(lead.source_archive_id),
                    ).exists():
                        continue
                    if lead.event_dossier_source.post_id:
                        posts.add(lead.event_dossier_source.post_id)
                    elif lead.event_dossier_source.collection_observation_id:
                        observations.add(lead.event_dossier_source.collection_observation_id)
                result = {"status": "budget" if stopped else "ok", "next_cursor": last,
                          "more_remaining": stopped or len(rows) > limit,
                          "posts": sorted(posts), "observations": sorted(observations),
                          "invalid": invalid, "bytes_read": consumed,
                          "parent_product_id": product_id, "parent_name": name}
    if monotonic() >= deadline:
        raise TimeoutError("Lineage recovery time budget exceeded")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [statement_before, lock_before])
    return result


def find_lineage_dependents(*, parent_claim_id, after=None, limit, max_bytes, max_seconds):
    """Keep lookup failures from changing the caller's transaction settings."""
    from django.db import transaction

    if not connection.in_atomic_block:
        raise ValueError("Lineage recovery requires the caller's transaction")
    with transaction.atomic():
        return _find_lineage_dependents(
            parent_claim_id=parent_claim_id, after=after, limit=limit,
            max_bytes=max_bytes, max_seconds=max_seconds,
        )


def register_lineage_wakeup(*, parent_claim_id, cause_review_id, budgets, only_if_dependents=False):
    """Create a local-only, source-linked wakeup inside the caller's transaction.

    The caller supplies operational budgets. Registration and the qualifying
    identity/review must commit together so a crash cannot lose the wakeup.
    """
    from core.collection_jobs import register_job, set_job_state
    from core.measurement_taxonomy import digest, resolve_subject_id
    from core.models import (
        CollectionJob,
        CollectionObservation,
        DataSource,
        EventDossierClaim,
        EventDossierClaimCollectionJob,
        EventDossierReviewClaim,
        MeasurementSubject,
        Product,
        ProductReleaseDetail,
    )
    from core.product_identity import _qualified_anchor_name, _resolved_anchor_product
    from core.product_release_dossiers import _read_pulse_packet
    from core.product_release_pipeline import canonical_dossier

    if not connection.in_atomic_block:
        raise ValueError("Wakeup registration requires the caller's transaction")
    if (not isinstance(budgets, dict) or set(budgets) != {"requests", "bytes", "seconds", "items"}
            or any(type(value) is not int or value <= 0 for value in budgets.values())):
        raise ValueError("Explicit wakeup budgets required")
    claim = EventDossierClaim.objects.select_related("event_dossier_source").get(pk=parent_claim_id)
    dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
    if str(dossier.current_review_id or "") != str(cause_review_id or ""):
        raise ValueError("Parent review changed before wakeup registration")
    if claim.scope_key.startswith("pulse-finding-v1:"):
        packet = _read_pulse_packet(claim)
        product_id = _resolved_anchor_product(claim, dossier, packet=packet)
        name = _qualified_anchor_name(claim, dossier, packet=packet)
    else:
        detail = ProductReleaseDetail.objects.filter(review_id=dossier.current_review_id).first()
        accepted = dossier.current_review_id and dossier.current_review.review_state == "confirmed" and EventDossierReviewClaim.objects.filter(
            review_id=dossier.current_review_id, claim=claim, disposition="accepted"
        ).exists()
        product_id, name = (detail.product_id, detail.observed_name) if detail and accepted else (None, None)
        if product_id:
            product_id = detail.product.pk
    if not product_id or not name:
        raise ValueError("Wakeup parent must have a qualified Product and name")
    if only_if_dependents:
        phrases = [f"Classifier-reported {kind}: {name}" for kind in ("new_version", "finetune", "adapter", "quantized", "merge")]
        if not EventDossierClaim.objects.annotate(_lineage_hash=MD5(Upper("assertion_text"))).filter(
            _lineage_hash__in=[MD5(Upper(Value(phrase))) for phrase in phrases],
            scope_key__startswith="pulse-lineage-v1:", source_archive__isnull=False,
        ).exists():
            return {"status": "no_dependents", "job_id": None}
    product = Product.objects.get(pk=product_id)
    cause = str(cause_review_id) if cause_review_id else "unreviewed"
    pin = digest(["lineage-wakeup-v1", str(claim.pk), cause, str(product.product_key), name, budgets])
    existing = CollectionJob.objects.filter(job_key="lineage-wakeup:" + pin).first()
    if existing and EventDossierClaimCollectionJob.objects.filter(claim=claim, job=existing).exists():
        return {"status": "registered", "job_id": str(existing.pk)}
    subject, _ = MeasurementSubject.objects.get_or_create(
        pk=resolve_subject_id("product", str(product.product_key)),
        defaults={"subject_kind": "product", "product": product},
    )
    if subject.subject_kind != "product" or subject.product_id != product.product_key:
        raise ValueError("Wakeup Product subject changed")
    source = (DataSource.objects.get(pk="x") if claim.event_dossier_source.post_id else
              CollectionObservation.objects.select_related("run__job__source").get(
                  pk=claim.event_dossier_source.collection_observation_id).run.job.source)
    job = register_job(
        job_key="lineage-wakeup:" + pin, source=source, purpose="content", operation="lineage_wakeup",
        mode="manual", definition={"version": 2, "options": {}},
        targets=[{"target_key": "parent:" + cause, "target_kind": "product", "target_role": "lineage_parent",
                  "resolution_state": "resolved", "subject_id": subject.pk,
                  "native_identifier": name, "selection_sha256": pin}],
        settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                  **{"max_" + key: value for key, value in budgets.items()}},
    )
    EventDossierClaimCollectionJob.objects.get_or_create(claim=claim, job=job)
    if job.state == "paused" and not job.runs.exists():
        job = set_job_state(job.pk, "ready")
    return {"status": "registered", "job_id": str(job.pk)}


def drain_lineage_wakeup(job_id, *, max_seconds=None):
    """Commit one saved-evidence page and its enqueue/checkpoint atomically."""
    from django.db import transaction

    from core.collection_state import BusyJob, claim_job, fenced_run, finish_run
    from core.measurement_taxonomy import digest
    from core.models import CollectionJob, CollectionRun, CollectionScopeRun
    from core.product_release_detection_queue import enqueue_posts
    from core.product_release_pipeline import canonical_dossier

    if max_seconds is not None and (type(max_seconds) not in (int, float) or max_seconds <= 0):
        raise ValueError("A positive time limit is required")
    with transaction.atomic():
        job = CollectionJob.objects.select_for_update().get(pk=job_id, operation="lineage_wakeup")
        if job.last_success_id:
            non_x_pending = job.last_success.scopes.filter(scope_kind="lineage_nonx_pending").count()
            if non_x_pending:
                return {"status": "non_x_pending", "non_x_pending": non_x_pending, "reused": True}
            return {"status": "complete", "reused": True}
        try:
            lease = claim_job(job.pk, typed=True, manual_authorized=True)
        except BusyJob:
            # Move a busy lease behind other ready jobs without changing its work.
            job.save(update_fields=["updated_at"])
            return {"status": "busy", "reused": False}
    run = CollectionRun.objects.get(pk=lease.run_id)
    scope = run.scopes.get(scope_kind="lineage_wakeup", scope_key="execution")
    more = False
    with fenced_run(lease):
        scope = CollectionScopeRun.objects.select_for_update().get(pk=scope.pk)
        links = list(job.dossier_claim_links.select_related("claim__event_dossier_source").all()[:2])
        targets = list(job.targets.select_related("subject").all()[:2])
        if len(links) != 1 or len(targets) != 1:
            raise ValueError("Invalid lineage wakeup ownership")
        claim, target = links[0].claim, targets[0]
        dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
        cause = target.target_key.removeprefix("parent:")
        if cause != str(dossier.current_review_id or "unreviewed"):
            page = {"status": "superseded", "posts": [], "observations": [], "invalid": [], "more_remaining": False}
        else:
            page = find_lineage_dependents(parent_claim_id=claim.pk, after=scope.cursor or None,
                                           limit=job.max_items, max_bytes=job.max_bytes,
                                           max_seconds=min(job.max_seconds, max_seconds) if max_seconds else job.max_seconds)
            if page["status"] in {"ok", "budget"} and page.get("parent_product_id") and (
                page["parent_product_id"] != target.subject.product.pk
                or page["parent_name"] != target.native_identifier
            ):
                page = {"status": "superseded", "posts": [], "observations": [], "invalid": [], "more_remaining": False}
        if page["status"] in {"ok", "budget"} and page.get("next_cursor") != (scope.cursor or None):
            if page["posts"]:
                enqueued = enqueue_posts(page["posts"])
                if enqueued.get("status") == "error" or enqueued.get("failed"):
                    raise ValueError("Lineage wakeup enqueue failed")
            for observation_id in page["observations"]:
                CollectionScopeRun.objects.get_or_create(
                    run=run, scope_kind="lineage_nonx_pending", scope_key=digest([str(claim.pk), observation_id]),
                    defaults={"resource_observation_id": observation_id, "phase": "lineage-nonx-v1",
                              "error_code": "lineage_nonx_worker_missing"},
                )
            for invalid_id in page["invalid"]:
                CollectionScopeRun.objects.get_or_create(
                    run=run, scope_kind="lineage_invalid", scope_key=invalid_id,
                    defaults={"phase": "lineage-invalid-v1", "error_code": "invalid_lineage_evidence"},
                )
            scope.cursor = page["next_cursor"]
            more = page["more_remaining"]
            scope.error_code = "invalid_lineage_evidence" if page["invalid"] else None
        elif page["status"] in {"budget", "busy"}:
            more = True
            scope.error_code = "lineage_wakeup_" + ("budget_blocked" if page["status"] == "budget" else "busy")
        elif page["status"] == "ok":
            scope.error_code = "invalid_lineage_evidence" if page["invalid"] else None
        else:
            scope.error_code = None
        scope.enumeration_complete = not more
        scope.outcome = "pending" if more else "complete"
        scope.save(update_fields=["cursor", "error_code", "enumeration_complete", "outcome"])
    with transaction.atomic():
        finish_run(lease, status="partial" if more else "success", typed=True, request_count=0,
                   selected_count=len(page["posts"]) + len(page["observations"]),
                   success_count=len(page["posts"]), physical_accounting_complete=True)
        if more and scope.error_code == "lineage_wakeup_budget_blocked":
            from core.collection_jobs import set_job_state

            set_job_state(job.pk, "paused")
    non_x_pending = run.scopes.filter(scope_kind="lineage_nonx_pending").count()
    return {"status": "budget_blocked" if more and scope.error_code == "lineage_wakeup_budget_blocked" else "pending" if more else "non_x_pending" if non_x_pending else "complete",
            "posts": len(page["posts"]), "non_x_pending": non_x_pending,
            "invalid": len(page["invalid"]), "reused": False}
