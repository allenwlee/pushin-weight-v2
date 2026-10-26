"""Database-backed campaign facade over the shared collection services.

Definitions are reviewed inputs, never local checkpoints. Adapters retain ownership
of their actual run, lease, evidence and checkpoints. Replay uses the shared saved-evidence projector and can never fall through to acquisition.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Case, F, Q, Sum, When

from core.collection_jobs import (
    register_job,
    set_job_state,
    validate_definition,
    validate_job,
)
from core.collection_reports import job_status
from core.collection_scheduling import execute_due_job
from core.measurement_taxonomy import require
from core.model_history_cohort import HISTORY_SOURCES
from core.models import (
    CollectionAttempt,
    CollectionCampaign,
    CollectionJob,
    CollectionRun,
    DataSource,
    MetricCollectionContract,
)


def validate_campaign(definition, *, contract_id):
    campaign = definition.get("campaign")
    require(
        isinstance(campaign, dict)
        and campaign.get("kind") == "backfiller-data-source-v1",
        "typed campaign instructions required",
    )
    require(
        isinstance(campaign.get("key"), str) and 0 < len(campaign["key"]) <= 128,
        "campaign key required",
    )
    cohort = campaign.get("cohort_hash")
    require(
        isinstance(cohort, str)
        and len(cohort) == 64
        and all(c in "0123456789abcdef" for c in cohort),
        "cohort hash required",
    )
    require(
        campaign.get("role") in {"inventory", "history", "projection"},
        "invalid campaign role",
    )
    require(campaign.get("phase") in {"acquire", "replay"}, "invalid campaign phase")
    require(
        campaign.get("contract_partition")
        == (str(contract_id) if contract_id else None),
        "immutable contract partition mismatch",
    )
    for name in ("max_invocations", "max_requests"):
        require(
            type(campaign.get(name)) is int and 0 < campaign[name] <= 1000000,
            f"invalid campaign {name}",
        )
    require(
        campaign["max_requests"] >= definition["budgets"]["requests"],
        "campaign request limit below invocation budget",
    )
    scope_hash = definition["scope"].get("cohort_hash")
    require(scope_hash in (None, cohort), "frozen scope/cohort mismatch")
    return campaign


def campaign_fields(definition, *, contract_id):
    if not definition.get("campaign"):
        return {}
    specification = validate_campaign(definition, contract_id=contract_id)
    fields = {
        "cohort_hash": specification["cohort_hash"],
        "policy_version": specification["kind"],
        "max_attempts": specification["max_invocations"],
        "max_requests": specification["max_requests"],
    }
    campaign, _ = CollectionCampaign.objects.get_or_create(
        campaign_key=specification["key"], defaults=fields
    )
    require(
        all(getattr(campaign, name) == value for name, value in fields.items()),
        "immutable campaign cohort changed",
    )
    return {
        "campaign_id": campaign.pk,
        "campaign_role": specification["role"],
        "campaign_phase": specification["phase"],
    }


def prepare_campaign(specifications):
    """Resolve reviewed source/contract records without creating anything."""
    require(
        isinstance(specifications, list) and 0 < len(specifications) <= 1000,
        "bounded source job specifications required",
    )
    prepared, identities, keys = [], set(), set()
    for spec in specifications:
        require(isinstance(spec, dict), "source job specification required")
        require(spec.get("source") in HISTORY_SOURCES, "unsupported campaign source")
        require(spec.get("job_key") not in keys, "duplicate job key")
        keys.add(spec.get("job_key"))
        source = DataSource.objects.get(pk=spec["source"])
        contract = (
            MetricCollectionContract.objects.get(pk=spec["contract"])
            if spec.get("contract")
            else None
        )
        definition = spec["definition"]
        validate_definition(
            source_id=source.pk,
            purpose=spec["purpose"],
            operation=spec["operation"],
            mode="historical",
            contract_id=contract.pk if contract else None,
            definition=definition,
        )
        campaign = validate_campaign(
            definition, contract_id=contract.pk if contract else None
        )
        require(
            (campaign["role"] != "inventory" or spec["operation"] != "model_history"),
            "inventory cannot own deep history",
        )
        identities.add(
            (
                campaign["key"],
                campaign["cohort_hash"],
                campaign["max_invocations"],
                campaign["max_requests"],
            )
        )
        prepared.append(
            {
                "job_key": spec["job_key"],
                "source": source,
                "contract": contract,
                "purpose": spec["purpose"],
                "operation": spec["operation"],
                "mode": "historical",
                "definition": definition,
            }
        )
    require(len(identities) == 1, "mixed campaign keys or cohorts")
    key, cohort, maximum_invocations, maximum_requests = next(iter(identities))
    for existing in CollectionJob.objects.filter(
        Q(campaign__campaign_key=key)
        | Q(campaign__isnull=True, definition__campaign__key=key)
    ):
        validate_job(existing)
        require(
            (
                existing.campaign_settings["cohort_hash"],
                existing.campaign_settings["max_invocations"],
                existing.campaign_settings["max_requests"],
            )
            == (cohort, maximum_invocations, maximum_requests),
            "immutable campaign cohort changed",
        )
    return prepared


@transaction.atomic
def register_campaign(specifications):
    """Register paused source phases atomically; identical re-registration is safe."""
    # Existing source rows serialize concurrent initial registrations as well as
    # later additions, when no campaign job exists yet to lock.
    list(
        DataSource.objects.select_for_update()
        .filter(pk__in=HISTORY_SOURCES)
        .order_by("pk")
    )
    return [register_job(**spec) for spec in prepare_campaign(specifications)]


def campaign_jobs(*, campaign_key=None, job_id=None):
    jobs = CollectionJob.objects.filter(
        Q(campaign__policy_version="backfiller-data-source-v1")
        | Q(
            campaign__isnull=True,
            definition__campaign__kind="backfiller-data-source-v1",
        )
    )
    if campaign_key:
        jobs = jobs.filter(
            Q(campaign__campaign_key=campaign_key)
            | Q(campaign__isnull=True, definition__campaign__key=campaign_key)
        )
    if job_id:
        jobs = jobs.filter(pk=job_id)
    return jobs.select_related("source", "contract", "campaign").order_by("created_at", "job_key")


def report_campaign(*, campaign_key=None, job_id=None):
    cells = []
    for job in campaign_jobs(campaign_key=campaign_key, job_id=job_id):
        validate_job(job)
        campaign = validate_campaign(job.instructions, contract_id=job.contract_id)
        cells.append(
            {**job_status(job.pk), "campaign": campaign, "usage": campaign_usage(job)}
        )
    require(not job_id or len(cells) == 1, "campaign job not found")
    return {
        "schema_version": 1,
        "job_count": len(cells),
        "cells": cells,
        "complete_public_history_claimed": False,
    }


def campaign_usage(job):
    """Reservations bound crash exposure; request_count remains actual usage."""
    if job.campaign_id:
        attempts = CollectionAttempt.objects.filter(
            run__job__campaign_id=job.campaign_id,
            imported_at__isnull=True,
        )
        newly_reserved = (
            attempts.aggregate(
                total=Sum(
                    Case(
                        When(accounting_complete=True, then=F("actual_requests")),
                        default=F("reserved_requests"),
                    )
                )
            )["total"]
            or 0
        )
        return {
            "invocations": CollectionAttempt.objects.filter(
                run__job__campaign_id=job.campaign_id,
            ).count(),
            "reserved_requests": (
                job.campaign.imported_reserved_requests + newly_reserved
            ),
            "recorded_requests": CollectionRun.objects.filter(
                job__campaign_id=job.campaign_id
            ).aggregate(total=Sum("request_count"))["total"]
            or 0,
        }
    # Transition only: legacy campaigns are materialized before JSON retirement.
    usage = {"invocations": 0, "reserved_requests": 0, "recorded_requests": 0}
    for run in CollectionRun.objects.filter(
        job__definition__campaign__kind="backfiller-data-source-v1",
        job__definition__campaign__key=job.campaign_settings["key"],
    ):
        reservation = run.report.get("campaign_usage", {})
        usage["invocations"] += reservation.get("invocations", 0)
        usage["reserved_requests"] += reservation.get("reserved_requests", 0)
        usage["recorded_requests"] += run.request_count
    return usage


@transaction.atomic
def project_legacy_campaigns(*, verify_only=False):
    """Adopt known campaign ceilings without inventing attempt reservations.

    The old run report knows the reservation total, while its imported attempts
    know only their order and start time. A campaign-owned baseline preserves
    that total; later physical attempts are counted separately.
    """
    candidates = list(CollectionJob.objects.filter(
        instruction_version=1,
        definition__campaign__kind="backfiller-data-source-v1",
    ).order_by("pk")[:1001])
    require(len(candidates) <= 1000, "legacy campaign adoption needs a smaller cohort")
    grouped = {}
    job_keys = {}
    for job in candidates:
        specification = validate_campaign(
            job.definition, contract_id=job.contract_id,
        )
        key = specification["key"]
        job_keys[job.pk] = key
        prior = grouped.setdefault(key, {"specification": specification, "jobs": []})
        require(
            all(prior["specification"][field] == specification[field] for field in (
                "kind", "cohort_hash", "max_invocations", "max_requests",
            )),
            "campaign identity differs among frozen jobs",
        )
        prior["jobs"].append(job)

    # The campaign instruction row is sealed against UPDATE/DELETE. Derive the
    # baseline before creating it, then recheck the locked source rows below.
    initial_reserved = dict.fromkeys(grouped, 0)
    for job_id, report in CollectionRun.objects.filter(
        job_id__in=job_keys,
    ).values_list("job_id", "report"):
        usage = report.get("campaign_usage")
        if usage is not None:
            require(
                isinstance(usage, dict)
                and type(usage.get("reserved_requests")) is int
                and usage["reserved_requests"] >= 0,
                "legacy campaign reservation receipt is invalid",
            )
            initial_reserved[job_keys[job_id]] += usage["reserved_requests"]

    campaigns = {}
    for key, group in sorted(grouped.items()):
        specification = group["specification"]
        require(
            initial_reserved[key] <= specification["max_requests"],
            "historical reservation exceeds campaign cap",
        )
        fields = {
            "cohort_hash": specification["cohort_hash"],
            "policy_version": specification["kind"],
            "max_attempts": specification["max_invocations"],
            "max_requests": specification["max_requests"],
        }
        if verify_only:
            campaign = CollectionCampaign.objects.filter(campaign_key=key).first()
            require(campaign is not None, "legacy campaign has no typed owner")
        else:
            campaign, _ = CollectionCampaign.objects.get_or_create(
                campaign_key=key,
                defaults={**fields, "imported_reserved_requests": initial_reserved[key]},
            )
        campaign = CollectionCampaign.objects.select_for_update().get(pk=campaign.pk)
        require(
            all(getattr(campaign, field) == value for field, value in fields.items()),
            "typed campaign identity differs from frozen instructions",
        )
        campaigns[key] = campaign

    locked = list(CollectionJob.objects.select_for_update().filter(
        pk__in=[job.pk for job in candidates],
    ).order_by("pk"))
    require(
        [job.pk for job in locked] == [job.pk for job in candidates],
        "legacy campaign job cohort changed",
    )
    job_ids = [job.pk for job in locked]
    runs = list(CollectionRun.objects.select_for_update().filter(
        job_id__in=job_ids,
    ).order_by("pk")[:10001])
    require(len(runs) <= 10000, "legacy campaign run cohort needs batching")
    attempts = {}
    for attempt in CollectionAttempt.objects.filter(run__job_id__in=job_ids).only(
        "run_id", "imported_at",
    ):
        attempts.setdefault(attempt.run_id, []).append(attempt)
    reserved_by_key = dict.fromkeys(grouped, 0)
    imported_count = 0
    for run in runs:
        usage = run.report.get("campaign_usage")
        related = attempts.get(run.pk, [])
        if usage is None:
            require(
                not any(attempt.imported_at is not None for attempt in related),
                "imported campaign attempt lacks its aggregate receipt",
            )
            continue
        require(
            run.status != "running" and run.completed_at is not None
            and isinstance(usage, dict)
            and type(usage.get("invocations")) is int
            and usage["invocations"] == len(related)
            and type(usage.get("reserved_requests")) is int
            and usage["reserved_requests"] >= 0
            and type(usage.get("recorded_requests")) is int
            and usage["recorded_requests"] == run.request_count
            and all(attempt.imported_at is not None for attempt in related),
            "legacy campaign aggregate does not match imported attempts",
        )
        reserved_by_key[job_keys[run.job_id]] += usage["reserved_requests"]
        imported_count += len(related)

    for key, group in sorted(grouped.items()):
        campaign = campaigns[key]
        baseline = reserved_by_key[key]
        member_ids = {job.pk for job in group["jobs"]}
        require(baseline <= campaign.max_requests, "historical reservation exceeds campaign cap")
        require(
            campaign.imported_reserved_requests == baseline,
            "typed campaign baseline differs from frozen receipts",
        )
        for job in locked:
            if job.pk not in member_ids:
                continue
            specification = validate_campaign(
                job.definition, contract_id=job.contract_id,
            )
            require(
                job.campaign_id in (None, campaign.pk)
                and job.campaign_role in (None, specification["role"])
                and job.campaign_phase in (None, specification["phase"]),
                "legacy job campaign attribution differs",
            )
            if verify_only:
                require(
                    job.campaign_id == campaign.pk
                    and job.campaign_role == specification["role"]
                    and job.campaign_phase == specification["phase"],
                    "legacy job campaign attribution has not been adopted",
                )
            elif job.campaign_id is None:
                job.campaign = campaign
                job.campaign_role = specification["role"]
                job.campaign_phase = specification["phase"]
                job.save(update_fields=["campaign", "campaign_role", "campaign_phase"])
        representative = next(job for job in locked if job.pk in member_ids)
        representative.campaign = campaign
        require(
            campaign_usage(representative)["reserved_requests"] <= campaign.max_requests,
            "adopted campaign exceeds request cap",
        )
    return {
        "campaigns": len(campaigns),
        "jobs": len(locked),
        "legacy_runs": sum(run.report.get("campaign_usage") is not None for run in runs),
        "imported_attempts": imported_count,
        "imported_reserved_requests": sum(reserved_by_key.values()),
    }


def execute_phase(job_id, *, budget=None, executor=None, replay=False, projector=None):
    """Run one explicitly selected phase; adapter acquires the shared fenced claim.

    Acquisition executors follow execute_due_job(job, decision, budget). Projectors
    follow projector(job_id), acquire the same claim and consume saved evidence only.
    No invocation here takes normal scheduling authority or alters X jobs.
    """
    job = campaign_jobs(job_id=job_id).get()
    validate_job(job)
    campaign = validate_campaign(job.instructions, contract_id=job.contract_id)
    require(replay == (campaign["phase"] == "replay"), "campaign replay phase mismatch")
    if replay and projector is None:
        from core.source_metric_projection import replay_saved_evidence

        projector = replay_saved_evidence
    require(
        executor is not None or replay or job.operation != "collect_metrics",
        "direct metric acquisition hook is unavailable",
    )
    usage = campaign_usage(job)
    require(
        usage["invocations"] < campaign["max_invocations"]
        and usage["reserved_requests"] + job.budgets["requests"]
        <= campaign["max_requests"],
        "campaign invocation/request limit exhausted",
    )
    # Activation is explicit. claim_job rechecks state, limits and lease under lock.
    if job.state == "paused":
        set_job_state(job.pk, "ready")
    if replay:
        return projector(job.pk)
    if budget is None:
        import httpx

        from core.collection_budgets import invocation_budget

        limits = job.budgets
        with httpx.Client(trust_env=False) as client:
            budget = invocation_budget(
                client,
                requests=limits["requests"],
                seconds=limits["seconds"],
                max_bytes=limits["bytes"],
            )
            return (executor or execute_due_job)(job, {"slot": None}, budget)
    return (executor or execute_due_job)(job, {"slot": None}, budget)
