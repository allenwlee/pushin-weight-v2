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
from django.db.models import Count, Q, Sum
from django.utils import timezone

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
from core.collection_jobs import register_job, set_job_state
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    DataSource,
    Event,
    Opportunity,
    OriginalContentCall,
    Post,
    PostEnrichmentState,
)
from core.provider_batches import (
    SPEND_BASES,
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
from scripts.backfill_verify import verify_collection_window, verify_window
from x_monitor.deepinfra import DEEPINFRA_ON_DEMAND_KEY_ENV, resolve_api_key
from x_monitor.provider_telemetry import normalize_usage


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


def validate_storage_schema():
    """Check shared timezone storage before starting any paid historical work."""
    required = {
        (model._meta.db_table, model._meta.get_field("source_timezone_reference").column)
        for model in (Event, Opportunity)
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name,column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name IN (%s,%s)",
            [Event._meta.db_table, Opportunity._meta.db_table],
        )
        present = set(cursor.fetchall())
    if not required <= present:
        raise RuntimeError("backfill_storage_schema_incompatible")


def _utc_epoch(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


ADMITTED_CALL_IDS = frozenset({"A", "B1", "B2", "B3", "C1", "C2", "C3", "C4", "RARE_EXTRA"})
WINDOW_FIELDS = frozenset({
    "since", "until", "call_ids", "slice_seconds", "routes", "author_list_ids", "ceilings", "spend_basis",
})
ROUTE_FIELDS = frozenset({"name", "host_call_id", "query", "not_include"})
CEILING_FIELDS = frozenset({"maximum_api_requests", "max_usd", "maximum_model_requests"})
ROUTE_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,31}")
LIST_SEARCH = re.compile(r"\(list:(\d+)\) ")
QUERY_BOUND_TOKENS = ("since:", "until:", "since_time:", "until_time:", "since_id:", "max_id:")


def _positive_int(value):
    return type(value) is int and value > 0


def _window_input(item):
    """Return (since, until, options); options is None for a plain bounds pair."""
    if not isinstance(item, dict):
        since, until = item
        return since, until, None
    if set(item) - WINDOW_FIELDS:
        raise ValueError("unknown_window_field")
    if not {"since", "until"} <= set(item):
        raise ValueError("window_bounds_required")
    options = {key: value for key, value in item.items() if key not in {"since", "until"}}
    if "call_ids" in options:
        values = options["call_ids"]
        if not (isinstance(values, list) and values and all(isinstance(v, str) for v in values)
                and len(values) == len(set(values)) and set(values) <= ADMITTED_CALL_IDS):
            raise ValueError("invalid_call_ids")
    if "slice_seconds" in options and not _positive_int(options["slice_seconds"]):
        raise ValueError("invalid_slice_seconds")
    if "author_list_ids" in options:
        values = options["author_list_ids"]
        if not (isinstance(values, list) and values and all(_positive_int(v) for v in values)
                and len(values) == len(set(values))):
            raise ValueError("invalid_author_list_ids")
    if "ceilings" in options:
        ceilings = options["ceilings"]
        if not (isinstance(ceilings, dict) and ceilings and set(ceilings) <= CEILING_FIELDS
                and all(_positive_int(ceilings[k]) for k in ceilings if k != "max_usd")):
            raise ValueError("invalid_ceilings")
        if "max_usd" in ceilings:
            try:
                dollars = Decimal(ceilings["max_usd"]) if isinstance(ceilings["max_usd"], str) else None
            except ArithmeticError:
                dollars = None
            if dollars is None or not dollars.is_finite() or dollars <= 0:
                raise ValueError("invalid_ceilings")
    if "spend_basis" in options and options["spend_basis"] not in SPEND_BASES:
        raise ValueError("invalid_spend_basis")
    if "routes" in options:
        routes = options["routes"]
        if not isinstance(routes, list):
            raise ValueError("invalid_route")
        names = set()
        for route in routes:
            if not isinstance(route, dict) or set(route) != ROUTE_FIELDS:
                raise ValueError("invalid_route")
            name = route["name"]
            if not isinstance(name, str) or not ROUTE_NAME.fullmatch(name):
                raise ValueError("invalid_route_name")
            if name in ADMITTED_CALL_IDS:
                raise ValueError("route_name_collides_with_call")
            if name in names:
                raise ValueError("duplicate_route_name")
            names.add(name)
            if not isinstance(route["host_call_id"], str) or route["host_call_id"] not in ADMITTED_CALL_IDS:
                raise ValueError("route_host_not_planned")
            query = route["query"]
            if (not isinstance(query, str) or not query.strip()
                    or any(token in query.lower() for token in QUERY_BOUND_TOKENS)):
                raise ValueError("invalid_route_query")
            if route["host_call_id"] == "A" and not LIST_SEARCH.match(query):
                raise ValueError("route_list_search_required")
            if not (isinstance(route["not_include"], list)
                    and all(isinstance(term, str) and term.strip() for term in route["not_include"])):
                raise ValueError("invalid_route")
    return item["since"], item["until"], options or None


def _expand_window_units(scope, options, lower, upper):
    """Slice every unit and add named routes on their host calls (scope_key route:since:until)."""
    step = options.get("slice_seconds")
    slices = [(lower, upper)] if step is None else [(at, at + step) for at in range(lower, upper, step)]
    routes = options.get("routes", [])
    planned = set(scope["required_call_ids"])
    author_scope = scope.get("author_scope", {})
    author_lists = author_scope.get("list_ids") or [author_scope.get("list_id")]
    for route in routes:
        if route["host_call_id"] not in planned:
            raise ValueError("route_host_not_planned")
        if route["host_call_id"] == "A" and int(LIST_SEARCH.match(route["query"]).group(1)) not in author_lists:
            raise ValueError("route_author_list_unfrozen")
    units = list(scope["units"]) if step is None else [
        {**unit, "scope_key": f"{unit['ownership']['call_id']}:{lo}:{hi}",
         "ownership": {**unit["ownership"], "since_epoch": lo, "until_epoch": hi}}
        for unit in scope["units"] for lo, hi in slices
    ]
    metadata = {}
    for route in routes:
        for lo, hi in slices:
            key = f"{route['name']}:{lo}:{hi}"
            units.append({"scope_key": key, "scope_kind": "x_query", "ownership": {
                "call_id": route["host_call_id"], "query": route["query"],
                "since_epoch": lo, "until_epoch": hi,
            }})
            metadata[key] = {"name": route["name"], "host_call_id": route["host_call_id"],
                             "not_include": list(route["not_include"])}
    scope["units"] = units
    if metadata:
        scope["route_metadata"] = metadata


def manifest(
    cfg,
    *,
    windows,
    campaign_name,
    supplemental_queries=(),
    deadline=None,
    expected_revision=None,
    direct_concurrency=32,
    response_storage="archive",
):
    if response_storage not in {"archive", "staging", "database"}:
        raise ValueError("unsupported_response_storage")
    if response_storage in {"staging", "database"}:
        from django.conf import settings

        from monitor.backfill_staging import validate_staging
        staging_host = settings.DATABASES["default"].get("HOST")
        storage_scope = {"response_storage": response_storage,
                         "staging_host" if response_storage == "staging" else "database_host": staging_host}
        validate_staging(storage_scope)
    validate_concurrency(direct_concurrency)
    deadline = deadline or timezone.now() + timedelta(hours=72)
    planned = plan_calls_for_cycle(cfg, scheduled_exclusions=True)
    if not planned or not any(c.call_id == "A" for c in planned) or any(
        c.call_id not in ADMITTED_CALL_IDS for c in planned
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
    for index, item in enumerate(inputs, start=1):
        since, until, options = _window_input(item)
        lower, upper = (_utc_epoch(value) for value in (since, until))
        if lower >= upper or (previous_upper is not None and lower < previous_upper):
            raise ValueError("windows_must_be_ordered_and_nonoverlapping")
        previous_upper = upper
        if any(
            call not in ADMITTED_CALL_IDS
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
        planning = {}
        if options is not None:
            step = options.get("slice_seconds")
            if step is not None and (upper - lower) % step:
                raise ValueError("invalid_slice_seconds")
            if any(len(f"{route['query']} since_time:{lower} until_time:{upper}") > 512
                   for route in options.get("routes", [])):
                raise ValueError("invalid_route_query")
            for key, value in options.get("ceilings", {}).items():
                window[key] = str(Decimal(value)) if key == "max_usd" else value
            if "spend_basis" in options:
                window["spend_basis"] = options["spend_basis"]
            planning = {key: options[key] for key in ("call_ids", "author_list_ids") if key in options}
        definition = plan_job_definition(
            cfg=cfg, since_epoch=lower, until_epoch=upper, brands=list(cfg.enabled_models),
            requests=200, model_requests=500, seconds=300,
            maximum_requests=window["maximum_api_requests"],
            maximum_models=window["maximum_model_requests"],
            **planning,
        )
        definition["scope"]["deadline"] = deadline.isoformat()
        if options is not None:
            _expand_window_units(definition["scope"], options, lower, upper)
        if response_storage in {"staging", "database"}:
            definition["scope"].update(storage_scope)
        for extra_index, (call, query) in enumerate(supplemental_queries):
            definition["scope"]["units"].append({
                "scope_key": f"{call}:supplement:{extra_index}", "scope_kind": "x_query",
                "ownership": {"call_id": call, "query": query,
                              "since_epoch": lower, "until_epoch": upper},
            })
        if options is not None and len(definition["scope"]["units"]) >= window["maximum_api_requests"]:
            # Every unit needs at least one request (scripts/backfill_month.py daily_manifest).
            raise ValueError("window_units_exceed_request_allowance")
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
    if getattr(exc, "collection_phase", False) or getattr(exc, "permanent", False):
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
            "backfill_storage_schema_incompatible",
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
        with transaction.atomic():
            CollectionJob.objects.select_for_update().get(pk=job.pk)
            states = {
                s.post_id: s
                for s in PostEnrichmentState.objects.select_for_update().filter(
                    pk__in=ids
                ).order_by("pk")
            }
            list(Post.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
            posts = Post.objects.filter(pk__in=ids).prefetch_related(
                "translation_artifacts", "classification_states", "brands"
            )
            for post in posts:
                state = states[post.pk]
                if state.claim_expires_at and state.claim_expires_at > timezone.now():
                    continue
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
            # Leave genuinely outstanding foreign work with its original
            # owner. Aggregate execution derives these member deferrals again
            # from the retained state and calls after every restart.
            own_historical_posts(job, ids, defer_conflicts=True)


def _wait(seconds):
    connections.close_all()
    time.sleep(min(30, max(0.1, seconds)))


def assert_no_provider_failure(job):
    calls = OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=job
    )
    if calls.filter(state__in=["ambiguous", "failed"]).exists():
        raise RuntimeError("provider_failure_or_unknown_outcome")


def _window_job(window, frozen):
    if frozen.get("instruction_format") != "x-backfill-campaign/v2":
        raise ValueError("current_policy_campaign_manifest_required")
    job = CollectionJob.objects.filter(job_key=f"{frozen['campaign']}/{window['index']}").first()
    if job is None:
        raise ValueError("window_job_missing")
    identity = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    if job.scope.get("provenance", {}).get("manifest_sha256") != identity:
        raise ValueError("immutable_campaign_manifest_changed")
    return job


def _collection_model_usage(job):
    """Known inline-gate usage; missing outcomes remain explicit, never zero-cost."""
    usage = {"requests_started": 0, "responses_recorded": 0, "known_input_tokens": 0,
             "known_output_tokens": 0, "responses_missing_usage": 0}
    cost = Decimal(0)
    for starts, responses in job.runs.values_list("report__model_requests", "report__model_responses").iterator():
        usage["requests_started"] += starts or 0
        for response in responses or []:
            usage["responses_recorded"] += 1
            reported = normalize_usage(response.get("usage"))
            for field in ("input_tokens", "output_tokens"):
                usage["known_" + field] += reported[field] or 0
            amount = Decimal(str(reported["cost_usd"])) if reported["cost_usd"] is not None else None
            if amount is not None and amount.is_finite():
                cost += amount
            if any(reported[field] is None for field in ("input_tokens", "output_tokens", "cost_usd")) or (amount is not None and not amount.is_finite()):
                usage["responses_missing_usage"] += 1
    usage["known_cost_usd"] = str(cost)
    usage["outcomes_unrecorded"] = max(0, usage["requests_started"] - usage["responses_recorded"])
    return usage


def _phase_receipt(job, phase, result, *, frozen, window, started_at,
                   runtime_revision=None, enrichment_concurrency=None):
    calls = OriginalContentCall.objects.filter(provider_batch__source_collection_job=job)
    receipt = {
        **result, "schema_version": 1, "phase": phase,
        "window": window, "source_collection_job": str(job.pk),
        "manifest_sha256": hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest(),
        "recipe_sha256": frozen.get("month_instruction", {}).get("recipe_sha256"),
        "runtime_revision": runtime_revision or os.environ.get("RENDER_GIT_COMMIT"),
        "effective_enrichment_concurrency": enrichment_concurrency,
        "started_at": started_at, "completed_at": timezone.now().isoformat(),
        "phase_usage_scope": "job_cumulative",
        "phase_usage": {
            "collection_gate": _collection_model_usage(job),
            "post_enrichment": calls.aggregate(requests_sent=Count("sent_at"),
                responses=Count("completed_at"), reserved_usd=Sum("reserved_usd"),
                requests_ambiguous=Count("pk", filter=Q(state="ambiguous")),
                requests_without_reported_cost=Count("pk", filter=Q(
                    sent_at__isnull=False, actual_usd__isnull=True)),
                provider_reported_usd=Sum("actual_usd"), input_tokens=Sum("input_tokens"),
                output_tokens=Sum("output_tokens")),
        },
    }
    receipt["phase_usage"]["twitterapi_requests"] = job.runs.aggregate(n=Sum("request_count"))["n"] or 0
    save_campaign_report(job, receipt, phase=phase)
    return receipt


def collect_window(window, *, frozen, cfg, runtime_revision=None, collection_options=None):
    """Collect and verify source storage; never start ordinary enrichment."""
    from monitor.backfill_prefetch import PrefetchOptions

    PrefetchOptions.parse(collection_options)
    started_at = timezone.now().isoformat()
    try:
        job, result = _collect_window(window, frozen=frozen, cfg=cfg, collection_options=collection_options)
    except Exception as exc:
        exc.collection_phase = True
        # A receipt complements durable checkpoints; it never decides completion.
        job = CollectionJob.objects.filter(job_key=f"{frozen.get('campaign')}/{window.get('index')}").first()
        if job is not None:
            _phase_receipt(job, "collection", {"status": "failed", "error_code": str(exc)[:200]},
                frozen=frozen, window=window, started_at=started_at, runtime_revision=runtime_revision)
        raise
    return _phase_receipt(job, "collection", result, frozen=frozen, window=window,
        started_at=started_at, runtime_revision=runtime_revision)


def enrich_window(window, *, frozen, cfg, evaluate_at_end=False, runtime_revision=None,
                  enrichment_concurrency=None):
    """Resume saved members only; this path cannot register or recollect a job."""
    ceiling = frozen["direct_concurrency"]
    selected = min(8, ceiling) if enrichment_concurrency is None else enrichment_concurrency
    if isinstance(selected, bool) or not isinstance(selected, int) or not 1 <= selected <= min(32, ceiling):
        raise ValueError("enrichment_concurrency_invalid")
    job = _window_job(window, frozen)
    started_at = timezone.now().isoformat()
    try:
        collection = verify_collection_window(job.pk, cfg=cfg)
        if collection["status"] != "verified":
            raise ValueError("collection_not_verified")
        result = _enrich_window(job, window, frozen=frozen, cfg=cfg,
            evaluate_at_end=evaluate_at_end, enrichment_concurrency=selected)
    except Exception as exc:
        _phase_receipt(job, "enrichment", {"status": "failed", "error_code": str(exc)[:200]},
            frozen=frozen, window=window, started_at=started_at, runtime_revision=runtime_revision,
            enrichment_concurrency=selected)
        raise
    return _phase_receipt(job, "enrichment", result, frozen=frozen, window=window,
        started_at=started_at, runtime_revision=runtime_revision, enrichment_concurrency=selected)


def execute_window(window, *, frozen, cfg, evaluate_at_end=False):
    """Retain legacy interleaving, deferrals and the saved concurrency preference."""
    resolve_api_key(DEEPINFRA_ON_DEMAND_KEY_ENV)
    job, issues = _collect_window(window, frozen=frozen, cfg=cfg,
                                 legacy_evaluate_at_end=evaluate_at_end)
    result = _enrich_window(job, window, frozen=frozen, cfg=cfg, evaluate_at_end=evaluate_at_end,
                            enrichment_concurrency=frozen["direct_concurrency"], initial_issues=issues)
    if evaluate_at_end:
        save_campaign_report(job, result)
    return result


def _collect_window(window, *, frozen, cfg, collection_options=None, legacy_evaluate_at_end=None):
    from monitor.backfill_prefetch import PrefetchOptions

    options = PrefetchOptions.parse(collection_options)
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
            existing.scope
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
    deadline = None if options.no_deadline else datetime.fromisoformat(frozen["deadline"])
    idle_since = time.monotonic()
    issues = []
    while job.state != "completed":
        if deadline is not None and timezone.now() >= deadline:
            raise RuntimeError("campaign_deadline_exhausted")
        if job.next_retry_at and job.next_retry_at > timezone.now():
            _wait((job.next_retry_at - timezone.now()).total_seconds())
            # A recorded provider cooldown is intentional waiting, like live
            # writer priority. Respect the selected calendar-expiry policy.
            idle_since = time.monotonic()
            job.refresh_from_db()
            continue
        try:
            report = execute_job(job.pk, **(
                {"collection_options": collection_options} if collection_options is not None else {}
            ))
        except Exception as exc:
            if not legacy_evaluate_at_end or safety_failure(exc):
                raise
            job.refresh_from_db()
            if not job.last_attempt_id or job.last_attempt.status == "running":
                raise
            report = job.last_attempt.report
            emit("COLLECTION_ERRORS_RETAINED", {
                "job_id": str(job.pk), "scope_errors": report.get("scope_errors", []),
            })
        job.refresh_from_db()
        if legacy_evaluate_at_end is None and (report.get("scope_errors") or report.get("global_failure")):
            raise RuntimeError("collection_scope_errors")
        if report.get("state") == "waiting_for_live_writer":
            emit("WAITING_FOR_LIVE_WRITER", {"job_id": str(job.pk)})
            # A first invocation has no last_attempt yet. Intentional yielding
            # is not a stalled collection; any selected deadline still applies.
            _wait(15)
            idle_since = time.monotonic()
            continue
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
                if legacy_evaluate_at_end is None:
                    raise RuntimeError("collection_rare_gate_pending")
                issues.append({"phase": "collection", "error_code": "rare_gate_pending"})
            break
        if job.last_attempt.scopes.filter(outcome="blocked").exists():
            raise RuntimeError("collection_cursor_blocked")
        if not options.unlimited_requests and report.get("cumulative_api_requests", 0) >= window["maximum_api_requests"]:
            raise RuntimeError("collection_request_allowance_exhausted")
        if report.get("usage", {}).get("api_requests", 0) or report.get("usage", {}).get("llm_requests", 0):
            idle_since = time.monotonic()
        elif time.monotonic() - idle_since > 900:
            raise RuntimeError("collection_no_progress_15_minutes")
        else:
            _wait(2)
    if legacy_evaluate_at_end is not None:
        return job, issues
    result = verify_collection_window(job.pk, cfg=cfg)
    if result["status"] != "verified":
        raise ValueError("collection_not_verified")
    return job, result


def _enrich_window(job, window, *, frozen, cfg, evaluate_at_end, enrichment_concurrency, initial_issues=()):
    resolve_api_key(DEEPINFRA_ON_DEMAND_KEY_ENV)
    deadline = datetime.fromisoformat(frozen["deadline"])
    issues = list(initial_issues)
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
            # Saved July windows carry no basis and keep today's policy.
            **({"spend_basis": window["spend_basis"]} if "spend_basis" in window else {}),
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
                direct_concurrency=enrichment_concurrency,
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
                direct_concurrency=enrichment_concurrency,
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


def save_campaign_report(job, result, *, phase=None):
    """Append execution evidence to the existing run; collection facts stay intact."""
    if not job.last_attempt_id:
        return
    with transaction.atomic():
        run = CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id)
        previous = run.report.get("backfill_campaign", {})
        history = previous.get("history", [])
        value = json.loads(json.dumps(result, default=str))
        run.report = run.report | {
            "backfill_campaign": {
                **previous,
                **({phase: value} if phase is not None else {}),
                "mode": previous.get("mode", "evaluate_at_end"),
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
    from monitor.backfill_database import campaign_database_matches
    if not campaign_database_matches(frozen, database_identity()):
        raise RuntimeError("campaign_database_identity_rejected")
    validate_storage_schema()
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
