"""Bounded planning and durable telemetry for optional discovery lanes."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db.models import Sum

from core.models import JobDiscoveryRun, PersonnelDiscoveryRun, SearchQuery
from x_monitor.config import Config, DiscoveryLaneConfig
from x_monitor.query_plan import PlannedCall, XQuerySpec, plan_calls

_RUN_MODELS = {
    "jobs": JobDiscoveryRun,
    "personnel": PersonnelDiscoveryRun,
}


def remaining_discovery_result_capacity(
    call: PlannedCall, *, now: datetime | None = None
) -> int | None:
    """Return the largest affordable result cap, or ``None`` for normal calls."""

    run_model = _RUN_MODELS.get(call.discovery_lane or "")
    if run_model is None:
        return None
    if (
        call.daily_credit_ceiling is None
        or call.credits_per_result is None
        or call.minimum_credits_per_call is None
    ):
        return call.max_results
    now = now or datetime.now(UTC)
    day_start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    used_credits = int(
        run_model.objects.filter(created_at__gte=day_start).aggregate(
            value=Sum("provider_credit_count")
        )["value"]
        or 0
    )
    remaining_credits = int(call.daily_credit_ceiling or 0) - used_credits
    minimum = int(call.minimum_credits_per_call or 0)
    if remaining_credits < minimum:
        return 0
    credits_per_result = int(call.credits_per_result or 1)
    return min(int(call.max_results or 0), remaining_credits // credits_per_result)


def _calls_for_lane(
    *, lane_name: str, lane: DiscoveryLaneConfig, list_id: int, now: datetime
) -> list[PlannedCall]:
    if not lane.enabled:
        return []
    run_model = _RUN_MODELS[lane_name]
    day_start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    used_credits = int(
        run_model.objects.filter(created_at__gte=day_start).aggregate(
            value=Sum("provider_credit_count")
        )["value"]
        or 0
    )
    if used_credits >= lane.daily_credit_ceiling:
        return []

    candidates: list[tuple[datetime, Any]] = []
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    for query in lane.queries:
        last = (
            run_model.objects.filter(query__query_id=query.query_id)
            .order_by("-window_end")
            .values_list("window_end", flat=True)
            .first()
        )
        if last is not None and last > now - timedelta(minutes=lane.cadence_minutes):
            continue
        candidates.append((last or epoch, query))
    candidates.sort(key=lambda value: (value[0], value[1].query_id))
    selected = [query for _last, query in candidates[: lane.per_cycle_call_ceiling]]
    if not selected:
        return []

    specs = [
        XQuerySpec(
            call_id=query.query_id,
            brands={f"_discovery_{lane_name}": list(query.primary_terms)},
            co_occurrence=list(query.co_occurrence),
            min_faves=0,
            not_include=list(query.not_include),
        )
        for query in selected
    ]
    planned = plan_calls(list_id, specs)[1:]
    config_by_id = {query.query_id: query for query in selected}
    remaining_credits = lane.daily_credit_ceiling - used_credits
    bounded: list[PlannedCall] = []
    for call in planned:
        query = config_by_id[call.call_id]
        if remaining_credits < lane.minimum_credits_per_call:
            break
        allocation = min(
            lane.max_results,
            remaining_credits // lane.credits_per_result,
        )
        if allocation < 1:
            break
        call.brand_id = f"*{lane_name}"
        call.discovery_lane = lane_name
        call.query_family = query.query_family
        call.language = query.language
        call.query_pack_version = lane.query_pack_version
        call.cadence_minutes = lane.cadence_minutes
        call.max_lookback_hours = lane.max_lookback_hours
        call.max_results = allocation
        call.max_pages = lane.max_pages
        call.max_per_page = lane.max_per_page
        call.request_timeout_seconds = lane.request_timeout_seconds
        call.daily_credit_ceiling = lane.daily_credit_ceiling
        call.credits_per_result = lane.credits_per_result
        call.minimum_credits_per_call = lane.minimum_credits_per_call
        remaining_credits -= max(
            allocation * lane.credits_per_result,
            lane.minimum_credits_per_call,
        )
        bounded.append(call)
    return bounded


def plan_discovery_calls(
    cfg: Config, *, list_id: int, now: datetime | None = None
) -> list[PlannedCall]:
    now = now or datetime.now(UTC)
    return [
        *_calls_for_lane(
            lane_name="jobs", lane=cfg.discovery.jobs, list_id=list_id, now=now
        ),
        *_calls_for_lane(
            lane_name="personnel",
            lane=cfg.discovery.personnel,
            list_id=list_id,
            now=now,
        ),
    ]


def record_discovery_run(
    *,
    call: PlannedCall,
    run_id: str,
    window: tuple[int, int],
    outcome: str,
    reviewed_post_count: int,
    accepted_post_count: int,
    excluded_count: int = 0,
    exclusion_reasons: dict[str, int] | None = None,
    extracted_count: int = 0,
    extracted_evidence_count: int = 0,
    discovered_organization_count: int = 0,
    provider_call_count: int = 0,
    provider_credit_count: int = 0,
    observed_at: datetime | None = None,
) -> JobDiscoveryRun | PersonnelDiscoveryRun | None:
    if call.discovery_lane not in _RUN_MODELS:
        return None
    query, _ = SearchQuery.objects.update_or_create(
        query_id=call.call_id,
        defaults={
            "keywords": {
                "lane": call.discovery_lane,
                "family": call.query_family,
                "language": call.language,
                "query_pack_version": call.query_pack_version,
                "query": call.query_string,
            },
            "plan_calls_run_id": run_id,
        },
    )
    since_epoch, until_epoch = window
    observed_at = observed_at or datetime.now(UTC)
    identity_payload = {
        "lane": call.discovery_lane,
        "run_id": run_id,
        "query_id": call.call_id,
        "since": since_epoch,
        "until": until_epoch,
    }
    run_identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    query_hash = hashlib.sha256(call.query_string.encode("utf-8")).hexdigest()
    statuses = {
        "ok": "completed",
        "truncated": "truncated",
        "error": "failed",
        "length_cap_exceeded": "blocked",
        "daily_credit_ceiling": "blocked",
    }
    defaults: dict[str, Any] = {
        "run_id": run_id,
        "cycle_id": run_id,
        "query": query,
        "query_text": call.query_string,
        "query_hash": query_hash,
        "query_pack_version": call.query_pack_version or "unknown",
        "provider_boundary": "twitterapi.io/advanced_search",
        "tool_boundary": "CycleRunner._fetch_tweets",
        "language": call.language or "unknown",
        "query_family": call.query_family or "unknown",
        "window_start": datetime.fromtimestamp(since_epoch, tz=UTC),
        "window_end": datetime.fromtimestamp(until_epoch, tz=UTC),
        "reviewed_post_count": reviewed_post_count,
        "accepted_post_count": accepted_post_count,
        "excluded_count": excluded_count,
        "exclusion_reasons": exclusion_reasons or {},
        "discovered_organization_count": discovered_organization_count,
        "provider_capabilities": {
            "pagination": True,
            "since_time": True,
            "until_time": True,
            "max_results": call.max_results,
            "max_pages": call.max_pages,
        },
        "provider_call_count": provider_call_count,
        "provider_credit_count": provider_credit_count,
        "telemetry": {
            "call_id": call.call_id,
            "query_length": call.query_length,
            "daily_credit_ceiling": call.daily_credit_ceiling,
            "credits_per_result": call.credits_per_result,
            "minimum_credits_per_call": call.minimum_credits_per_call,
        },
        "limitations": [
            "query recall is not measurable from provider results alone",
            "unknown organizations require review before brand creation",
        ],
        "status": statuses.get(outcome, "failed"),
        "completed_at": observed_at,
        "completion_reason": outcome,
    }
    if call.discovery_lane == "jobs":
        defaults["extracted_listing_count"] = extracted_count
    else:
        defaults["extracted_affiliation_count"] = extracted_count
        defaults["extracted_evidence_count"] = extracted_evidence_count
    run_model = _RUN_MODELS[call.discovery_lane]
    row, _ = run_model.objects.update_or_create(
        run_identity=run_identity,
        defaults=defaults,
        create_defaults={**defaults, "started_at": observed_at},
    )
    return row
