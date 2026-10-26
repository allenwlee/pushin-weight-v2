"""Bounded two-pass orchestration over immutable backfill instructions.

Recipe expansion deliberately retains the original month operator's JSON bytes
and identities. Execution preferences and runtime attestations are separate.
No provider, ingestion or enrichment implementation lives here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

LEGACY_ROUTES = {"A", "B1", "B2", "B3", "C1", "C2", "C3", "RARE_EXTRA"}
RUNTIME_MODULES = {
    "scripts/backfill_month.py",
    "scripts/backfill_campaign.py",
    "monitor/management/commands/run_backfill.py",
    "monitor/backfill_prefetch.py",
    "x_monitor/apify.py",
    "scripts/backfill_verify.py",
}


ROUTES = LEGACY_ROUTES | {"C4"}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def days(spec):
    lower, upper = (datetime.fromisoformat(spec[k]) for k in ("since", "until"))
    if lower.tzinfo is None or upper.tzinfo is None or lower >= upper:
        raise ValueError("invalid_month_bounds")
    if lower.time().isoformat() != "00:00:00" or upper.time().isoformat() != "00:00:00":
        raise ValueError("whole_calendar_days_required")
    output = []
    while lower < upper:
        end = lower + timedelta(days=1)
        if end > upper:
            raise ValueError("partial_calendar_day")
        output.append((lower, end))
        lower = end
    if len(output) > 31:
        raise ValueError("month_controller_day_allowance")
    return output


def daily_manifest(recipe, index):
    """Expand only one day's instructions; never rebuild queries/author roles."""
    spec = recipe["spec"]
    lower, upper = days(spec)[index]
    frozen = copy.deepcopy(recipe["template"])
    base = frozen["windows"][0]
    routes = {
        u["ownership"]["call_id"]
        for u in base["collection_definition"]["scope"]["units"]
    }
    if routes not in (LEGACY_ROUTES, ROUTES) or len(base["collection_definition"]["scope"]["units"]) != len(routes):
        raise ValueError("month_route_inventory_changed")
    frozen["campaign"] = spec["campaign"] + "-" + lower.date().isoformat()
    frozen["month_instruction"] = {
        "recipe_sha256": digest(recipe),
        "day_index": index + 1,
        "calendar_timezone": spec["calendar_timezone"],
        "query_seconds": 300,
        "historical_keyword_search_completeness": "provider_filtered_not_exhaustive",
    }
    output = []
    for offset in range(4):
        start = lower + timedelta(hours=offset * 6)
        stop = start + timedelta(hours=6)
        window = copy.deepcopy(base)
        lo, hi = int(start.timestamp()), int(stop.timestamp())
        window.update(
            index=offset + 1,
            since=start.isoformat(),
            until=stop.isoformat(),
            since_epoch=lo,
            until_epoch=hi,
        )
        scope = window["collection_definition"]["scope"]
        scope.update(since_epoch=lo, until_epoch=hi)
        units = []
        for original in scope["units"]:
            route = original["ownership"]["call_id"]
            for at in range(lo, hi, 300):
                unit = copy.deepcopy(original)
                unit["scope_key"] = f"{route}:{at}:{at + 300}"
                unit["ownership"].update(since_epoch=at, until_epoch=at + 300)
                units.append(unit)
        scope["units"] = units
        if len(units) != len(routes) * 72 or len(units) >= window["maximum_api_requests"]:
            raise ValueError("month_scope_or_request_allowance_invalid")
        output.append(window)
    frozen["windows"] = output
    frozen["model_reservation_ceiling_usd"] = str(
        sum(Decimal(w["max_usd"]) for w in output)
    )
    if output[-1]["until_epoch"] != int(upper.timestamp()):
        raise ValueError("month_day_boundary_mismatch")
    return frozen


def iter_manifests(instructions):
    """Re-expand one bounded day at a time on each pass."""
    if instructions.get("format") == "x-month-recipe/v1":
        for index in range(len(days(instructions["spec"]))):
            yield daily_manifest(instructions, index)
    else:
        yield instructions


def validate_recipe(recipe):
    if recipe.get("format") != "x-month-recipe/v1":
        raise ValueError("month_recipe_format_invalid")
    spec, template = recipe["spec"], recipe["template"]
    if not days(spec) or len(template["windows"]) != 1:
        raise ValueError("month_recipe_template_invalid")
    if (
        spec["deadline"] != template["deadline"]
        or spec["database"] != template["database"]
    ):
        raise ValueError("month_recipe_identity_invalid")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,85}", spec["campaign"]):
        raise ValueError("invalid_campaign_name")
    for frozen in iter_manifests(recipe):
        if frozen["deadline"] != spec["deadline"]:
            raise ValueError("month_deadline_changed")
    return recipe


def execution_options(
    instructions,
    *,
    phase,
    enrichment_concurrency=None,
    collection_concurrency=1,
    collection_starts_per_second=10,
    collection_unlimited_requests=False,
    collection_no_deadline=False,
):
    """Validate preferences before runtime checks, writes, locks or provider calls."""
    if phase not in {"collect", "enrich", "all"}:
        raise ValueError("phase_invalid")
    if type(collection_unlimited_requests) is not bool or type(collection_no_deadline) is not bool:
        raise ValueError("collection_limit_overrides_invalid")
    if (collection_unlimited_requests or collection_no_deadline) and phase != "collect":
        raise ValueError("collection_limit_overrides_require_collect_phase")
    frozen = (
        instructions["template"]
        if instructions.get("format") == "x-month-recipe/v1"
        else instructions
    )
    from monitor.backfill_database import scope_relocated
    if phase != "collect" and any(
        window.get("collection_definition", {}).get("scope", {}).get("response_storage") == "staging"
        and not scope_relocated(window["collection_definition"]["scope"])
        for window in frozen.get("windows", [])
    ):
        raise ValueError("staging acquisition requires collect phase; promote before enrichment")
    ceiling = frozen["direct_concurrency"]
    if (
        isinstance(ceiling, bool)
        or not isinstance(ceiling, int)
        or not 1 <= ceiling <= 32
    ):
        raise ValueError("saved_enrichment_concurrency_invalid")
    selected = (
        min(8, ceiling) if enrichment_concurrency is None else enrichment_concurrency
    )
    if (
        isinstance(selected, bool)
        or not isinstance(selected, int)
        or not 1 <= selected <= ceiling
    ):
        raise ValueError("enrichment_concurrency_invalid")
    if (
        isinstance(collection_concurrency, bool)
        or not isinstance(collection_concurrency, int)
        or not 1 <= collection_concurrency <= 20
    ):
        raise ValueError("collection_concurrency_invalid")
    if (
        isinstance(collection_starts_per_second, bool)
        or not isinstance(collection_starts_per_second, (float, int))
        or not math.isfinite(collection_starts_per_second)
        or not 0 < collection_starts_per_second <= 20
    ):
        raise ValueError("collection_starts_per_second_invalid")
    return {
        "phase": phase,
        "enrichment_concurrency": selected,
        "collection_options": {
            "concurrency": collection_concurrency,
            "starts_per_second": collection_starts_per_second,
            **({"unlimited_requests": True} if collection_unlimited_requests else {}),
            **({"no_deadline": True} if collection_no_deadline else {}),
        },
    }


def selected_runtime(recipe, runtime=None):
    """Attest reviewed code without modifying frozen recipe hashes or job keys."""
    spec = copy.deepcopy(recipe["spec"])
    staging = any(w["collection_definition"]["scope"].get("response_storage") in {"staging", "database"}
                  for w in recipe["template"]["windows"])
    required = RUNTIME_MODULES | ({"monitor/backfill_staging.py", "monitor/backfill_collection.py", "monitor/run_lock.py"} if staging else set())
    if runtime is not None:
        if set(runtime) != {"runtime_revision", "source_sha256"}:
            raise ValueError("month_runtime_override_fields_invalid")
        if not isinstance(runtime["runtime_revision"], str) or not re.fullmatch(
            r"[a-f0-9]{40}", runtime["runtime_revision"]
        ):
            raise ValueError("month_runtime_override_revision_invalid")
        sources = runtime["source_sha256"]
        if not isinstance(sources, dict) or not (
            set(spec["source_sha256"]) | required
        ) <= set(sources):
            raise ValueError("month_runtime_override_sources_invalid")
        for path, signature in sources.items():
            if (
                not isinstance(path, str)
                or Path(path).is_absolute()
                or ".." in Path(path).parts
                or not isinstance(signature, str)
                or not re.fullmatch(r"[a-f0-9]{64}", signature)
            ):
                raise ValueError("month_runtime_override_sources_invalid")
        spec.update(copy.deepcopy(runtime))
    if staging and not required <= set(spec["source_sha256"]):
        raise ValueError("staging runtime attestation missing")
    return spec


def verify_sources(spec):
    if os.environ.get("RENDER_GIT_COMMIT") != spec["runtime_revision"]:
        raise RuntimeError("month_runtime_revision_changed")
    if not RUNTIME_MODULES <= set(spec["source_sha256"]):
        raise RuntimeError("month_runtime_attestation_required")
    for path, expected in spec["source_sha256"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError("month_runtime_source_changed:" + path)


def check_deadline(value):
    deadline = datetime.fromisoformat(value)
    if deadline.tzinfo is None or datetime.now(deadline.tzinfo) >= deadline:
        raise ValueError("backfill_deadline_exhausted_or_invalid")


def check_active_lease(job, *, now):
    """Leave expired pointers intact for collection_state's fenced reclaim."""
    if job.active_run_id:
        run = job.active_run
        if run.status == "running" and (
            run.lease_expires_at is None or run.lease_expires_at > now
        ):
            raise RuntimeError("month_saved_run_active")


def compact_result(result):
    """Keep bounded progress; full receipts already belong to CollectionRun."""
    keys = {
        "status",
        "source_collection_job",
        "phase",
        "schema_version",
        "checked_posts",
        "scopes_complete",
        "scopes_total",
        "failure_counts",
        "error_code",
        "error_type",
        "usage",
        "phase_usage",
        "phase_usage_scope",
        "manifest_sha256",
        "recipe_sha256",
        "runtime_revision",
        "effective_enrichment_concurrency",
        "started_at",
        "completed_at",
    }
    return {key: value for key, value in result.items() if key in keys}


def phase_sequence(
    manifests,
    *,
    phase,
    cfg,
    collect,
    enrich,
    verify,
    collection_options=None,
    enrichment_concurrency=None,
    runtime_revision=None,
    evaluate_at_end=False,
    assess=None,
):
    """Two bounded passes; verify the entire range before its first enrichment."""
    if phase not in {"collect", "enrich", "all"}:
        raise ValueError("phase_invalid")
    results = []
    if phase in {"collect", "all"}:
        for frozen in manifests():
            for window in frozen["windows"]:
                result = collect(
                    window,
                    frozen=frozen,
                    cfg=cfg,
                    runtime_revision=runtime_revision,
                    collection_options=collection_options,
                )
                if result.get("status") != "verified":
                    raise ValueError("collection_not_verified")
                results.append(compact_result(result))
    if phase in {"enrich", "all"}:
        for frozen in manifests():
            for window in frozen["windows"]:
                verify(window, frozen=frozen, cfg=cfg)
        for frozen in manifests():
            # Existing campaign policy defers only known enrichment failures.
            from scripts.backfill_campaign import run_sequence

            rows = run_sequence(
                frozen["windows"],
                lambda window, frozen=frozen: enrich(
                    window,
                    frozen=frozen,
                    cfg=cfg,
                    evaluate_at_end=evaluate_at_end,
                    runtime_revision=runtime_revision,
                    enrichment_concurrency=enrichment_concurrency,
                ),
                evaluate_at_end=evaluate_at_end,
            )
            if evaluate_at_end and assess is not None:
                report = assess(frozen, cfg, rows)
                results.extend(
                    compact_result(row.get("attempt", {})) | compact_result(row)
                    for row in report["windows"]
                )
            else:
                results.extend(compact_result(row) for row in rows)
    return results


def _validate_campaign_runtime(frozen, cfg, revision, *, no_deadline=False):
    from monitor.backfill_collection import POLICY_ADAPTER_VERSION, config_digest
    from monitor.backfill_enrichment import configuration_pin
    from scripts import backfill_campaign as campaign

    if (
        (revision or frozen["revision"]) is not None
        and os.environ.get("RENDER_GIT_COMMIT") != (revision or frozen["revision"])
    ) or configuration_pin(cfg) != frozen["configuration_pin"]:
        raise RuntimeError("pinned_runtime_changed")
    if (
        config_digest(cfg, version=POLICY_ADAPTER_VERSION)
        != frozen["runtime_config_sha256"]
    ):
        raise RuntimeError("pinned_runtime_config_changed")
    from monitor.backfill_database import campaign_database_matches
    if not campaign_database_matches(frozen, campaign.database_identity()):
        raise RuntimeError("campaign_database_identity_rejected")
    if not no_deadline:
        check_deadline(frozen["deadline"])
    from core.collection_jobs import validate_definition
    from core.models import CollectionJob
    from monitor.backfill_collection import validate_scope

    for window in frozen["windows"]:
        definition = window["collection_definition"]
        signature = validate_definition(
            source_id="x",
            purpose="content",
            operation="x_backfill",
            mode="historical",
            contract_id=None,
            definition=definition,
        )
        job = CollectionJob(
            job_key=f"{frozen['campaign']}/{window['index']}",
            source_id="x",
            purpose="content",
            operation="x_backfill",
            mode="historical",
            definition=definition,
            definition_sha256=signature,
        )
        validate_scope(job, cfg)


def _check_saved_jobs(frozen):
    from django.utils import timezone

    from core.models import CollectionJob, CollectionRun

    now = timezone.now()
    # A running row with an expired lease is recoverable, not a permanent veto.
    if CollectionRun.objects.filter(
        job__source_id="x",
        job__mode="historical",
        status="running",
        lease_expires_at__gt=now,
    ).exists():
        raise RuntimeError("month_another_historical_run_active")
    for job in CollectionJob.objects.select_related("active_run").filter(
        job_key__startswith=frozen["campaign"] + "/"
    ):
        if job.scope.get("provenance", {}).get("manifest_sha256") != digest(frozen):
            raise RuntimeError("month_immutable_saved_manifest_changed")
        check_active_lease(job, now=now)


def _verify_saved_collection(window, *, frozen, cfg):
    from scripts.backfill_campaign import _window_job
    from scripts.backfill_verify import verify_collection_window

    result = verify_collection_window(_window_job(window, frozen).pk, cfg=cfg)
    if result["status"] != "verified":
        raise ValueError("collection_not_verified")
    return result


def _pause_failed_campaign(frozen):
    from core.collection_jobs import set_job_state
    from core.models import CollectionJob
    from core.provider_batches import set_enrichment_control

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


def run_phases(
    instructions,
    cfg,
    *,
    phase,
    enrichment_concurrency=None,
    collection_concurrency=1,
    collection_starts_per_second=10,
    collection_unlimited_requests=False,
    collection_no_deadline=False,
    runtime_revision=None,
    runtime_attestation=None,
    evaluate_at_end=False,
):
    """Run a campaign or compact month under its original controller lock."""
    options = execution_options(
        instructions,
        phase=phase,
        enrichment_concurrency=enrichment_concurrency,
        collection_concurrency=collection_concurrency,
        collection_starts_per_second=collection_starts_per_second,
        collection_unlimited_requests=collection_unlimited_requests,
        collection_no_deadline=collection_no_deadline,
    )
    is_month = instructions.get("format") == "x-month-recipe/v1"
    if is_month:
        validate_recipe(instructions)
        spec = selected_runtime(instructions, runtime_attestation)
        if (
            runtime_revision is not None
            and runtime_revision != spec["runtime_revision"]
        ):
            raise ValueError("month_runtime_attestation_revision_mismatch")
        verify_sources(spec)
        runtime_revision = spec["runtime_revision"]
        database = spec["database"]
        namespace = "x-manual-month-controller:" + str(database)
    else:
        if runtime_attestation is not None:
            raise ValueError("runtime_attestation_requires_month_recipe")
        database = instructions["database"]
        namespace = "x-manual-month-controller:" + str(database)
    manifests = lambda: iter_manifests(instructions)
    for frozen in manifests():
        _validate_campaign_runtime(frozen, cfg, runtime_revision, no_deadline=collection_no_deadline)
    import psycopg
    from django.db import connection, connections

    from scripts import backfill_campaign as campaign

    campaign.validate_storage_schema()
    guard = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    try:
        lock = int(hashlib.sha256(namespace.encode()).hexdigest()[:15], 16)
        if not guard.execute("SELECT pg_try_advisory_lock(%s)", [lock]).fetchone()[0]:
            raise RuntimeError(
                "month_controller_already_running"
                if is_month
                else "campaign_controller_already_running"
            )
        # Preserve campaign exclusion against older, interleaved controllers too.
        # At most31 campaign keys are held alongside the single month key.
        for frozen in manifests():
            campaign_key = int(
                hashlib.sha256(
                    (frozen["campaign"] + str(database)).encode()
                ).hexdigest()[:15],
                16,
            )
            if not guard.execute(
                "SELECT pg_try_advisory_lock(%s)", [campaign_key]
            ).fetchone()[0]:
                raise RuntimeError("campaign_controller_already_running")
        # Complete every preflight before the first job write or paid admission.
        for frozen in manifests():
            _check_saved_jobs(frozen)

        def boundary():
            for frozen in manifests():
                if not collection_no_deadline:
                    check_deadline(frozen["deadline"])
                guard.execute("SELECT 1")
                yield frozen

        try:
            with connection.execute_wrapper(campaign.block_live_cursor_writes):
                return phase_sequence(
                    boundary,
                    cfg=cfg,
                    collect=campaign.collect_window,
                    enrich=campaign.enrich_window,
                    verify=_verify_saved_collection,
                    runtime_revision=runtime_revision,
                    evaluate_at_end=evaluate_at_end,
                    assess=campaign.assess_campaign,
                    **options,
                )
        except Exception as exc:
            for frozen in manifests():
                _pause_failed_campaign(frozen)
            campaign.emit(
                "CAMPAIGN_STOPPED",
                {"error_type": type(exc).__name__, "error_code": str(exc)[:200]},
            )
            raise
    finally:
        guard.close()
        connections.close_all()
