"""Frozen query identities for the existing scheduled X cycle."""

from __future__ import annotations

import hashlib

from django.db import transaction

from core.collection_jobs import register_job
from core.measurement_taxonomy import digest, require
from core.models import DataSource, SearchQuery


@transaction.atomic
def register_scheduled_cycle(calls, *, limits):
    """Register one recurring job for an unchanged ordered query plan.

    Query identity is fixed on each target. Request windows belong to each
    scope run, because the seven scheduled calls move on every invocation.
    Registration does not dispatch a provider call or activate the job.
    """
    calls = tuple(calls)
    require(calls and len(calls) == len({call.call_id for call in calls}),
            "scheduled calls require unique roles")
    require(set(limits) == {"requests", "bytes", "seconds", "items"},
            "scheduled limits require four finite bounds")
    source, _ = DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"},
    )
    targets = []
    for call in calls:
        query_text = call.query_string
        require(isinstance(query_text, str) and query_text,
                "scheduled query wording required")
        query_id = "x-cycle:" + hashlib.sha256(query_text.encode()).hexdigest()
        query, _ = SearchQuery.objects.get_or_create(
            query_id=query_id, defaults={"query_text": query_text},
        )
        require(query.query_text == query_text, "scheduled query identity changed")
        targets.append({
            "target_key": call.call_id,
            "target_kind": "query",
            "target_role": call.call_id,
            "resolution_state": "resolved",
            "search_query_id": query.pk,
        })
    identity = digest({
        "queries": [(call.call_id, call.query_string) for call in calls],
        "limits": limits,
    })
    return register_job(
        job_key="x-cycle:" + identity,
        source=source, purpose="content", operation="x_cycle",
        mode="recurring",
        definition={"version": 2, "options": {
            "adapter": "twitterapi", "credential_purpose": "scheduled",
        }},
        settings={
            "owner_kind": "source", "schedule_kind": "interval",
            "schedule_driver": "external_render_cron", "interval_seconds": 900,
            "max_requests": limits["requests"], "max_bytes": limits["bytes"],
            "max_seconds": limits["seconds"], "max_items": limits["items"],
        },
        targets=targets,
    )
