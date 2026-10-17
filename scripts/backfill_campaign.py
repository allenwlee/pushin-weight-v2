"""Sequential operator recovery using deployed shared collection/enrichment.

Run through manage.py run_backfill in a Render one-off, with immutable campaign
instructions and database checkpoints. No scheduler is installed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import resource
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import ROUND_UP, Decimal

from django.db import connection, connections, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
from core.collection_jobs import register_job, set_job_state
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    DataSource,
    OriginalContentCall,
    Post,
    PostEnrichmentState,
)
from core.provider_batches import (
    BatchAdmissionError,
    enrichment_control_status,
    own_historical_posts,
    set_enrichment_control,
)
from monitor.backfill_collection import (
    POLICY_ADAPTER_VERSION,
    config_digest,
    execute_job,
    plan_job_definition,
)
from monitor.backfill_direct import validate_concurrency
from monitor.backfill_enrichment import (
    ACTIVE_STATES,
    configuration_pin,
    deferred_enrichment_work,
    execute_enrichment,
    policy_snapshot,
)
from monitor.cycle import plan_calls_for_cycle
from scripts.backfill_targeted import advance_targeted
from scripts.backfill_verify import verify_window
from x_monitor.deepinfra import DEEPINFRA_ON_DEMAND_KEY_ENV, resolve_api_key


def emit(event, value):
    print(
        "BACKFILL_" + event + " " + json.dumps(value, sort_keys=True, default=str),
        flush=True,
    )


def database_identity():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(),current_user")
        name, role = cursor.fetchone()
    return {"name": name, "user": role}


def _utc_epoch(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def manifest(
    cfg,
    *,
    windows,
    campaign_name,
    supplemental_queries=(),
    deadline=None,
    expected_revision=None,
    direct_concurrency=32,
):
    validate_concurrency(direct_concurrency)
    deadline = deadline or timezone.now() + timedelta(hours=72)
    planned = plan_calls_for_cycle(cfg, scheduled_exclusions=True)
    admitted = {"A", "B1", "B2", "B3", "C1", "C2", "C3", "RARE_EXTRA"}
    if not planned or not any(c.call_id == "A" for c in planned) or any(
        c.call_id not in admitted for c in planned
    ):
        raise ValueError("current_collection_route_missing_or_unsupported")
    queries = [(c.call_id, c.query_string) for c in planned]
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,96}", campaign_name):
        raise ValueError("invalid_campaign_name")
    queries.extend(supplemental_queries)
    inputs = list(windows)
    if not inputs:
        raise ValueError("campaign_windows_required")
    output_windows = []
    previous_upper = None
    for index, (since, until) in enumerate(inputs, start=1):
        lower, upper = (_utc_epoch(value) for value in (since, until))
        if lower >= upper or (previous_upper is not None and lower < previous_upper):
            raise ValueError("windows_must_be_ordered_and_nonoverlapping")
        previous_upper = upper
        if any(
            call not in admitted
            or not isinstance(query, str)
            or not query.strip()
            or len(f"{query} since_time:{lower} until_time:{upper}") > 512
            for call, query in queries
        ):
            raise ValueError("invalid_frozen_query")
        ceiling = max(
            Decimal(5),
            (Decimal(upper - lower) / Decimal(86400) * Decimal(25)).quantize(
                Decimal(".01"), rounding=ROUND_UP
            ),
        )
        window = {
                "index": index,
                "since": since,
                "until": until,
                "since_epoch": lower,
                "until_epoch": upper,
                "max_usd": str(ceiling),
                "maximum_api_requests": max(
                    1000, math.ceil((upper - lower) / 86400 * 5000)
                ),
                "maximum_model_requests": max(
                    5000, math.ceil((upper - lower) / 86400 * 50000)
                ),
            }
        definition = plan_job_definition(
            cfg=cfg, since_epoch=lower, until_epoch=upper, brands=list(cfg.enabled_models),
            requests=200, model_requests=500, seconds=300,
            maximum_requests=window["maximum_api_requests"],
            maximum_models=window["maximum_model_requests"],
        )
        definition["scope"]["deadline"] = deadline.isoformat()
        for extra_index, (call, query) in enumerate(supplemental_queries):
            definition["scope"]["units"].append({
                "scope_key": f"{call}:supplement:{extra_index}", "scope_kind": "x_query",
                "ownership": {"call_id": call, "query": query,
                              "since_epoch": lower, "until_epoch": upper},
            })
        window["collection_definition"] = definition
        output_windows.append(window)
    return {
        "schema_version": 1,
        "instruction_format": "x-backfill-campaign/v2",
        "campaign": campaign_name,
        "revision": expected_revision or os.environ.get("RENDER_GIT_COMMIT"),
        "database": database_identity(),
        "configuration_pin": configuration_pin(cfg),
        "deadline": deadline.isoformat(),
        "runtime_config_sha256": config_digest(cfg, version=POLICY_ADAPTER_VERSION),
        "brands": cfg.enabled_models,
        "queries": queries,
        "windows": output_windows,
        "model_reservation_ceiling_usd": str(
            sum(Decimal(w["max_usd"]) for w in output_windows)
        ),
        "direct_concurrency": direct_concurrency,
        "credential_purpose": "on-demand",
    }


def safety_failure(exc):
    """Quality deferral cannot override identity, immutable input or deadline guards."""
    if getattr(exc, "permanent", False):
        return True
    code = str(exc)
    return any(
        token in code
        for token in (
            "database_identity",
            "database_guard",
            "pinned_runtime",
            "configuration_changed",
            "policy_changed",
            "immutable_campaign_manifest",
            "live_cursor_write",
            "source_changed",
            "source_definition_changed",
            "deadline_exhausted",
            "enrichment_paused",
            "enrichment_not_drained",
            "enrichment_provider_admission_http_",
        )
    )


def run_sequence(windows, run_window, *, evaluate_at_end=False):
    """Finish independent windows before assessing quality when explicitly selected."""
    results = []
    for window in windows:
        try:
            result = run_window(window)
        except Exception as exc:
            if not evaluate_at_end or safety_failure(exc):
                raise
            result = {
                "status": "deferred",
                "window": window,
                "error_type": type(exc).__name__,
                "error_code": str(exc)[:200],
            }
            emit("WINDOW_DEFERRED", result)
        if not evaluate_at_end and result.get("status") != "verified":
            raise ValueError("window_not_verified")
        results.append(result)
    return results


def block_live_cursor_writes(execute, sql, params, many, context):
    if re.match(
        r"\s*(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|ALTER|DROP)\b", sql, re.IGNORECASE
    ) and re.search(
        r"\b(call_state|harvest_backlog_windows)\b",
        sql,
        re.IGNORECASE,
    ):
        raise RuntimeError("campaign_live_cursor_write_forbidden")
    return execute(sql, params, many, context)


def prepare_current_contract(job, cfg):
    """Reopen failed/superseded outputs, preserving their prior evidence."""
    observations = CollectionObservation.objects.filter(
        run__job=job, source_subject_kind="post"
    )
    after = ""
    while True:
        ids = list(
            observations.filter(post_id__gt=after)
            .order_by("post_id")
            .values_list("post_id", flat=True)
            .distinct()[:100]
        )
        if not ids:
            return
        after = ids[-1]
        own_historical_posts(job, ids)
        with transaction.atomic():
            CollectionJob.objects.select_for_update().get(pk=job.pk)
            states = {
                s.post_id: s
                for s in PostEnrichmentState.objects.select_for_update().filter(
                    pk__in=ids
                )
            }
            posts = Post.objects.filter(pk__in=ids).prefetch_related(
                "translation_artifacts", "classification_states", "brands"
            )
            for post in posts:
                state = states[post.pk]
                current_translation = any(
                    a.is_current
                    and a.state == "succeeded"
                    and a.model == cfg.llm.translator_model
                    for a in post.translation_artifacts.all()
                )
                classes = list(post.classification_states.all())
                current_classification = (
                    bool(classes)
                    and {s.brand_id for s in classes}
                    == {b.brand_id for b in post.brands.all()}
                    and all(
                        s.model == cfg.llm.classifier_model
                        and s.contract_version == CONTRACT_VERSION
                        and s.taxonomy_version == TAXONOMY_VERSION
                        for s in classes
                    )
                )
                for stage, current in (
                    ("translation", current_translation),
                    ("classification", current_classification),
                ):
                    if not current or getattr(state, stage + "_status") == "failed":
                        setattr(state, stage + "_status", "pending")
                        setattr(state, stage + "_next_attempt_at", None)
                state.save()


def _wait(seconds):
    connections.close_all()
    time.sleep(min(30, max(0.1, seconds)))


def assert_no_provider_failure(job):
    calls = OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=job
    )
    if calls.filter(state__in=["ambiguous", "failed"]).exists():
        raise RuntimeError("provider_failure_or_unknown_outcome")


def execute_window(window, *, frozen, cfg, evaluate_at_end=False):
    resolve_api_key(DEEPINFRA_ON_DEMAND_KEY_ENV)
    identity = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    if frozen.get("instruction_format") != "x-backfill-campaign/v2":
        raise ValueError("current_policy_campaign_manifest_required")
    definition = json.loads(json.dumps(window["collection_definition"]))
    definition["scope"]["provenance"] = {
        "format": frozen["instruction_format"], "manifest_sha256": identity,
    }
    job_key = f"{frozen['campaign']}/{window['index']}"
    existing = CollectionJob.objects.filter(job_key=job_key).first()
    if existing is not None:
        if (
            existing.definition.get("scope", {})
            .get("provenance", {})
            .get("manifest_sha256")
            != identity
        ):
            raise ValueError("immutable_campaign_manifest_changed")
        definition = existing.definition
    job = register_job(
        job_key=job_key,
        source=DataSource.objects.get(pk="x"),
        purpose="content",
        operation="x_backfill",
        mode="historical",
        definition=definition,
    )
    if job.state == "paused":
        set_job_state(job.pk, "ready")
    emit("WINDOW_START", {**window, "job_id": str(job.pk)})
    deadline = datetime.fromisoformat(frozen["deadline"])
    idle_since = time.monotonic()
    issues = []
    while job.state != "completed":
        if timezone.now() >= deadline:
            raise RuntimeError("campaign_deadline_exhausted")
        if job.next_retry_at and job.next_retry_at > timezone.now():
            _wait((job.next_retry_at - timezone.now()).total_seconds())
            job.refresh_from_db()
            continue
        try:
            report = execute_job(job.pk)
        except Exception as exc:
            if not evaluate_at_end or safety_failure(exc):
                raise
            job.refresh_from_db()
            if not job.last_attempt_id or job.last_attempt.status == "running":
                raise
            report = job.last_attempt.report
            emit("COLLECTION_ERRORS_RETAINED", {
                "job_id": str(job.pk), "scope_errors": report.get("scope_errors", []),
            })
        job.refresh_from_db()
        emit(
            "COLLECTION",
            {
                k: v
                for k, v in report.items()
                if k not in {"recovered_post_ids", "usage"}
            },
        )
        if job.state == "completed" or report.get("collection_drained"):
            if report.get("rare_gate_pending"):
                issues.append({"phase": "collection", "error_code": "rare_gate_pending"})
            break
        if job.last_attempt.scopes.filter(outcome="blocked").exists():
            raise RuntimeError("collection_cursor_blocked")
        if report.get("cumulative_api_requests", 0) >= window["maximum_api_requests"]:
            raise RuntimeError("collection_request_allowance_exhausted")
        if report.get("usage", {}).get("api_requests", 0) or report.get("usage", {}).get("llm_requests", 0):
            idle_since = time.monotonic()
        elif time.monotonic() - idle_since > 900:
            raise RuntimeError("collection_no_progress_15_minutes")
        else:
            _wait(2)
    prepare_current_contract(job, cfg)
    first = job.provider_batches.order_by("created_at").first()
    if (
        evaluate_at_end
        and first
        and enrichment_control_status(job.pk)["processing_paused"]
    ):
        set_enrichment_control(
            job.pk,
            action="resume",
            actor=frozen["campaign"],
            reason="Owner requests all windows attempted before aggregate evaluation; retain budgets and paid history",
        )
    policy = (
        None
        if first
        else policy_snapshot(
            max_usd=window["max_usd"],
            deadline=deadline,
            max_model_requests=window["maximum_model_requests"],
            max_control_requests=5000,
        )
    )
    progress, no_progress = None, 0
    while timezone.now() < deadline:
        before = (
            deferred_enrichment_work(job, max_attempts=3, operation_scope="base")
            if evaluate_at_end
            else {}
        )
        try:
            result = execute_enrichment(
                job.pk,
                cfg=cfg,
                api_key=resolve_api_key(DEEPINFRA_ON_DEMAND_KEY_ENV),
                policy=policy,
                transport="direct",
                direct_concurrency=frozen["direct_concurrency"],
                defer_failures=evaluate_at_end,
            )
        except Exception as exc:
            if not evaluate_at_end or safety_failure(exc):
                raise
            issue = {"phase": "enrichment", "error_code": str(exc)[:200]}
            issues.append(issue)
            emit("WORK_DEFERRED", issue)
            if (
                isinstance(exc, BatchAdmissionError)
                and str(exc) == "model_attempt_allowance_exhausted"
            ):
                after = deferred_enrichment_work(
                    job, max_attempts=3, operation_scope="base"
                )
                if set(after) - set(before):
                    continue
            break
        policy = None
        emit("ENRICHMENT", result)
        if not evaluate_at_end:
            assert_no_provider_failure(job)
        if result["status"] == "completed":
            break
        if (
            evaluate_at_end
            and result["actionable_pending_count"] == 0
            and result["active_batches"] == 0
        ):
            break
        signature = tuple(
            result.get(k)
            for k in [
                "pending_count",
                "model_requests_sent",
                "model_responses_received",
                "active_batches",
            ]
        )
        import_signature = list(
            OriginalContentCall.objects.filter(
                provider_batch__source_collection_job=job
            )
            .values("state", "import_state")
            .annotate(n=Count("pk"))
            .order_by("state", "import_state")
        )
        signature += (hashlib.sha256(str(import_signature).encode()).hexdigest(),)
        no_progress = no_progress + 1 if signature == progress else 0
        if no_progress >= 3:
            if not evaluate_at_end:
                raise RuntimeError("enrichment_no_progress")
            issues.append(
                {"phase": "enrichment", "error_code": "enrichment_no_progress"}
            )
            break
        progress = signature
        due = list(
            job.provider_batches.filter(
                state__in=ACTIVE_STATES, next_poll_at__gt=timezone.now()
            ).values_list("next_poll_at", flat=True)
        )
        if due:
            _wait((min(due) - timezone.now()).total_seconds())
    else:
        raise RuntimeError("enrichment_deadline_exhausted")
    for _ in range(1000):
        if timezone.now() >= deadline:
            raise RuntimeError("targeted_deadline_exhausted")
        try:
            targeted = advance_targeted(
                job.pk,
                cfg=cfg,
                api_key=resolve_api_key(DEEPINFRA_ON_DEMAND_KEY_ENV),
                direct_concurrency=frozen["direct_concurrency"],
                defer_failures=evaluate_at_end,
            )
        except Exception as exc:
            if not evaluate_at_end or safety_failure(exc):
                raise
            issue = {"phase": "targeted", "error_code": str(exc)[:200]}
            issues.append(issue)
            emit("WORK_DEFERRED", issue)
            if str(exc) in {
                "model_attempt_allowance_exhausted",
                "targeted_extraction_canonical_publication_failed",
            }:
                continue
            break
        emit("TARGETED", targeted)
        if not evaluate_at_end:
            assert_no_provider_failure(job)
        if targeted["status"] == "completed":
            break
    else:
        if not evaluate_at_end:
            raise RuntimeError("targeted_advance_allowance_exhausted")
        issues.append(
            {"phase": "targeted", "error_code": "targeted_advance_allowance_exhausted"}
        )
    if evaluate_at_end:
        result = {
            "status": "attempted",
            "window": window,
            "source_collection_job": str(job.pk),
            "issues": issues,
            "deferred_post_count": len(deferred_enrichment_work(job, max_attempts=3)),
        }
        save_campaign_report(job, result)
        emit("WINDOW_ATTEMPTED", result)
        return result
    verified = verify_window(job.pk, cfg=cfg)
    totals = OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=job
    ).aggregate(
        reserved_usd=Sum("reserved_usd"),
        provider_reported_usd=Sum("actual_usd"),
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
    )
    verified.update(
        {
            "window": window,
            "usage": totals,
            "peak_memory_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2
            ),
        }
    )
    emit(
        "WINDOW_VERIFIED" if verified["status"] == "verified" else "WINDOW_FAILED",
        verified,
    )
    return verified


def save_campaign_report(job, result):
    """Append execution evidence to the existing run; collection facts stay intact."""
    if not job.last_attempt_id:
        return
    with transaction.atomic():
        run = CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id)
        history = run.report.get("backfill_campaign", {}).get("history", [])
        value = json.loads(json.dumps(result, default=str))
        run.report = run.report | {
            "backfill_campaign": {
                "mode": "evaluate_at_end",
                "latest": value,
                "history": [
                    *history[-19:],
                    {"at": timezone.now().isoformat(), **value},
                ],
            }
        }
        run.save(update_fields=["report", "updated_at"])


def assess_campaign(frozen, cfg, attempts):
    """Read all windows after acquisition/enrichment, retaining unresolved failures."""
    results = []
    for window, attempt in zip(frozen["windows"], attempts, strict=True):
        selected_job = attempt.get("source_collection_job")
        job = CollectionJob.objects.filter(
            **({"pk": selected_job} if selected_job else {
                "job_key": f"{frozen['campaign']}/{window['index']}"
            })
        ).first()
        try:
            if job is None:
                raise ValueError("window_job_missing")
            result = verify_window(job.pk, cfg=cfg)
        except ValueError as exc:
            result = {"status": "failed", "error_code": str(exc)[:200]}
        result.update({"window": window, "attempt": attempt})
        if job is not None:
            result["source_collection_job"] = str(job.pk)
            calls = OriginalContentCall.objects.filter(
                provider_batch__source_collection_job=job
            )
            result["usage"] = calls.aggregate(
                requests_sent=Count("sent_at"),
                responses=Count("completed_at"),
                reserved_usd=Sum("reserved_usd"),
                provider_reported_usd=Sum("actual_usd"),
                input_tokens=Sum("input_tokens"),
                output_tokens=Sum("output_tokens"),
            )
            result["usage"]["twitterapi_requests"] = (
                job.runs.aggregate(n=Sum("request_count"))["n"] or 0
            )
            result["provider_outcomes"] = list(
                calls.values("state", "import_state", "error_code")
                .annotate(count=Count("pk"))
                .order_by("state", "import_state", "error_code")
            )
            result["deferred_reasons"] = dict(
                Counter(
                    deferred_enrichment_work(job, max_attempts=3).values(),
                )
            )
            save_campaign_report(job, result)
        results.append(result)
    report = {
        "status": "verified"
        if all(r["status"] == "verified" for r in results)
        else "incomplete",
        "windows_attempted": len(attempts),
        "windows_verified": sum(r["status"] == "verified" for r in results),
        "checked_posts": sum(r.get("checked_posts", 0) for r in results),
        "windows": results,
    }
    emit("CAMPAIGN_ASSESSMENT", report)
    return report


def run(frozen, cfg, *, evaluate_at_end=False, runtime_revision=None):
    if (
        (runtime_revision or frozen["revision"]) is not None
        and os.environ.get("RENDER_GIT_COMMIT")
        != (runtime_revision or frozen["revision"])
    ) or configuration_pin(cfg) != frozen["configuration_pin"]:
        raise RuntimeError("pinned_runtime_changed")
    if (
        config_digest(cfg, version=POLICY_ADAPTER_VERSION)
        != frozen["runtime_config_sha256"]
    ):
        raise RuntimeError("pinned_runtime_config_changed")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(),current_user")
        if cursor.fetchone() != (
            frozen["database"]["name"],
            frozen["database"]["user"],
        ):
            raise RuntimeError("campaign_database_identity_rejected")
    # A dedicated session keeps this campaign lock while ordinary connections
    # close between waits. No application row or transaction remains locked.
    import psycopg

    guard = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    if not guard.execute(
        "SELECT pg_try_advisory_lock(%s)",
        [
            int(
                hashlib.sha256(
                    (frozen["campaign"] + str(frozen["database"])).encode()
                ).hexdigest()[:15],
                16,
            )
        ],
    ).fetchone()[0]:
        guard.close()
        raise RuntimeError("campaign_controller_already_running")
    try:
        emit(
            "CAMPAIGN_START",
            {
                **frozen,
                "evaluate_at_end": evaluate_at_end,
                "runtime_revision": os.environ.get("RENDER_GIT_COMMIT"),
            },
        )
        with connection.execute_wrapper(block_live_cursor_writes):
            results = run_sequence(
                frozen["windows"],
                lambda w: execute_window(
                    w,
                    frozen=frozen,
                    cfg=cfg,
                    evaluate_at_end=evaluate_at_end,
                ),
                evaluate_at_end=evaluate_at_end,
            )
            if evaluate_at_end:
                return assess_campaign(frozen, cfg, results)
        emit(
            "CAMPAIGN_VERIFIED",
            {
                "windows": len(results),
                "posts": sum(r["checked_posts"] for r in results),
            },
        )
    except Exception as exc:
        for job in CollectionJob.objects.filter(
            job_key__startswith=frozen["campaign"] + "/", state="ready"
        ):
            set_job_state(job.pk, "paused")
        for job in (
            CollectionJob.objects.filter(job_key__startswith=frozen["campaign"] + "/")
            .exclude(provider_batches=None)
            .distinct()
        ):
            set_enrichment_control(
                job.pk,
                action="pause",
                actor=frozen["campaign"],
                reason="stop-on-failure; inspect saved campaign evidence before restart",
            )
        emit(
            "CAMPAIGN_STOPPED",
            {"error_type": type(exc).__name__, "error_code": str(exc)[:200]},
        )
        raise
    finally:
        guard.close()
        connections.close_all()
