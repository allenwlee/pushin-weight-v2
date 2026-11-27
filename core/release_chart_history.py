"""Plan gaps for one product and run them through the ordinary source writer."""

from datetime import UTC, date, datetime, time, timedelta

from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.collection_budgets import bounded_planning, charge, job_budget
from core.collection_jobs import register_job, set_job_state
from core.collection_scheduling import execute_due_job
from core.collection_state import BusyJob
from core.measurement_taxonomy import require
from core.models import (
    CollectionJob,
    CollectionJobTarget,
    CollectionObservation,
    EventDossierClaimCollectionJob,
)
from scripts.benchmark_download_collector.sources import SourceError

HISTORY_SOURCES = ("opencode", "openrouter", "arena")
DAY = timedelta(days=1)


def midnight(day):
    return datetime.combine(day, time.min, UTC)


def _days(start, end):
    require(
        type(start) is date and type(end) is date and 0 <= (end - start).days < 366,
        "release history requires 1 to 366 inclusive calendar days",
    )
    return [start + i * DAY for i in range((end - start).days + 1)]


def _population_absence(mapping, days, config, category, cache):
    """A full source population proves publication and membership independently."""
    from django.db.models import Sum

    from core.model_history_publications import WINDOW_CAPTURE, observation_documents

    if mapping.source_id not in {"openrouter", "arena"} or category not in {
        None,
        "overall",
    }:
        return set(), set()
    key = (mapping.pk, days[0], days[-1], config, category)
    if key in cache:
        return cache[key]
    matches = CollectionObservation.objects.filter(
        run__job__source_id=mapping.source_id,
        projection_kind=WINDOW_CAPTURE,
        observation_kind="publication_window",
        scope_run__requested_start_date__lte=days[-1],
        scope_run__requested_end_date__gte=days[0],
        run__payload_archive__byte_count__lte=4 * 1024 * 1024,
    ).annotate(wire_bytes=Sum("inputs__input_request__archive__byte_count"))
    if mapping.source_id == "arena":
        matches = matches.filter(config_key=config)
    absent, unpublished, present = set(), set(), set()
    # Check sizes before loading bodies. A busy board can have many large
    # population snapshots plus the physical pages used to verify each one.
    remaining = 4 * 1024 * 1024
    for obs in (
        matches.select_related(
            "run__job", "scope_run", "source_dataset", "run__payload_archive"
        )
        .defer("run__payload_archive__body")
        .order_by("-observed_at")[:20]
    ):
        size = obs.run.payload_archive.byte_count + (obs.wire_bytes or 0)
        if size > remaining:
            continue
        remaining -= size
        payload = observation_documents(obs)[0]
        if payload.get("coverage") not in {
            "publication_window",
            "top_50_public_models",
        }:
            continue
        requested = {
            d.isoformat()
            for d in days
            if obs.scope_run.requested_start_date
            <= d
            <= obs.scope_run.requested_end_date
        }
        if mapping.source_id == "arena":
            field, date_field = "model_name", "leaderboard_publish_date"
        else:
            field, date_field = "model_permaslug", "date"
        rows = [
            r
            for r in payload["rows"]
            if r.get(date_field) in requested
            and (mapping.source_id != "arena" or r.get("category") == category)
        ]
        pub_days = {r[date_field] for r in rows}
        included = {
            r[date_field] for r in rows if r.get(field) == mapping.external_identifier
        }
        absent.update(pub_days - included)
        present.update(included)
        unpublished.update(requested - pub_days)
    cache[key] = absent - present, unpublished - absent - present
    return cache[key]


def _missing_dates(request, resolved, index, mapping, days, publication_cache):
    from core.chart_engine import (
        _single_brand_values,
        _unmapped_exact_values,
        metric_series,
    )

    key = resolved.metrics[index].selection.metric_key
    source = mapping.source_id
    split = source == "arena"
    scopes = [(None, None)]
    series = metric_series(
        resolved,
        index,
        source_use_override=True,
        single_template=True,
        split_arena=split,
    )
    if series.get("status") == "unavailable":
        return
    retained = _unmapped_exact_values(
        mapping, key, request.start, min(request.end, request.cutoff), split_arena=split
    )
    if split:
        configured = mapping.contract.source_configuration[source].get(
            "config", "text_style_control"
        )
        # A collection job owns one reviewed board. Other boards may be
        # present in the chart, but this adapter cannot fill their windows.
        scopes = [(configured, mapping.identifier_metadata.get("category", "overall"))]
    for config, category in scopes:
        current = (
            series["arena_scopes"].get((config, category), {}) if split else series
        )
        legacy = retained.get((config, category), {}) if split else retained
        values, evidence, _ = _single_brand_values(current, legacy, days[0])
        publications = set()
        if split:
            from django.db.models import Q

            configured = mapping.contract.source_configuration["arena"].get(
                "config", "text_style_control"
            )
            board = Q(config_key=config, category_key=category)
            if (config, category) == (configured, "overall"):
                board |= Q(
                    observation_kind="publication_marker",
                    config_key__isnull=True,
                    category_key__isnull=True,
                )
            publications = set(
                CollectionObservation.objects.filter(
                    run__job__contract=mapping.contract,
                    run__job__source_id="arena",
                    publication_complete=True,
                    published_date__range=(days[0], days[-1]),
                )
                .filter(board)
                .values_list("published_date", flat=True)
            )
        absent, unpublished = _population_absence(
            mapping, days, config, category, publication_cache
        )
        for day_index, day in enumerate(days):
            label = day.isoformat()
            coverage = (evidence.get(day_index) or {}).get("coverage", "")
            if (
                midnight(day) + DAY <= request.cutoff
                and values.get(day_index) is None
                and coverage not in {"partial_source", "partial_window", "conflict"}
                and not coverage.startswith("ambiguous")
                and day not in publications
                and label not in absent
                and label not in unpublished
            ):
                yield label


def _windows(dates):
    days = sorted({date.fromisoformat(day) for day in dates})
    if not days:
        return
    first = prior = days[0]
    for day in days[1:]:
        if day != prior + DAY:
            yield midnight(first), midnight(prior + DAY)
            first = day
        prior = day
    yield midnight(first), midnight(prior + DAY)


def _prepare_history_job(release, mapping, *, cutoff, budget):
    """Try one missing contiguous window. Completed targets remember terminal empty results."""
    from core.chart_engine import (
        ChartRequest,
        MetricSelection,
        ReleaseAnchor,
        single_brand_dates,
        validate_request,
    )
    from core.release_chart_handoff import lock_qualified_release

    source = mapping.source_id
    config = mapping.contract.source_configuration[source]
    if (
        source not in HISTORY_SOURCES
        or not config.get("scheduling_enabled")
        or config.get("eligibility_policy") == SOURCE_STATISTICS_POLICY
        or mapping.contract.mappings.filter(source=mapping.source)
        .exclude(pk=mapping.pk)
        .exists()
    ):
        return None
    start, end = single_brand_dates(release.date)
    end = min(
        end, cutoff.date() - timedelta(days=max(1, config.get("completed_day_lag", 1)))
    )
    if source == "openrouter":
        start = max(start, date(2025, 1, 1))
    if end < start:
        return None
    days = _days(start, end)
    request = ChartRequest(
        target=ReleaseAnchor.from_qualified(release),
        start=midnight(start),
        end=midnight(end) + DAY,
        cutoff=cutoff,
        history_mode="hindsight",
        metrics=tuple(
            MetricSelection(
                release.product_key, mapping.contract_id, mapping.pk, metric
            )
            for metric in config["metrics"]
        ),
    )
    resolved = validate_request(request, source_use_override=True, single_template=True)
    gaps, publications = set(), {}
    for i, metric in enumerate(resolved.metrics):
        if metric.mapping is None or budget.deadline - budget.clock() < 1:
            return None
        gaps.update(
            _missing_dates(request, resolved, i, metric.mapping, days, publications)
        )
    if not gaps:
        return None
    # Published windows with no matching product row are complete attempts.
    # Later renders continue to show their observed absence, never zero.
    checked = CollectionJobTarget.objects.filter(
        mapping=mapping,
        job__mode="historical",
        job__operation="collect_metrics",
        job__state="completed",
        requested_start_at__lt=midnight(end) + DAY,
        requested_end_at__gt=midnight(start),
    ).values_list("requested_start_at", "requested_end_at")
    for first, last in checked:
        gaps.difference_update(
            d.isoformat() for d in days if first.date() <= d < last.date()
        )
    for first, last in _windows(gaps):
        if budget.deadline - budget.clock() < 1:
            return None
        # The source adapter caps its own date range. Advance the oldest missing
        # piece first; each target supplies the inclusive/exclusive time bounds.
        if source != "opencode":
            last = min(
                last, first + timedelta(days=min(7, config.get("recheck_days", 7)))
            )
        key = f"release-history:{mapping.pk}:{first.date()}:{last.date()}"
        with transaction.atomic():
            lock_qualified_release(release.dossier_id, fingerprint=release.fingerprint)
            job = CollectionJob.objects.filter(job_key=key).first()
            if job is None:
                job = register_job(
                    job_key=key,
                    source=mapping.source,
                    purpose="metric",
                    operation="collect_metrics",
                    mode="historical",
                    contract=mapping.contract,
                    definition={"version": 2, "options": {}},
                    settings={
                        "owner_kind": "source",
                        "schedule_kind": "manual",
                        "schedule_driver": "manual",
                        "max_requests": config["max_requests"],
                        "max_bytes": config["max_bytes"],
                        "max_seconds": config["max_seconds"],
                        "max_items": 100,
                    },
                    targets=[
                        {
                            "target_key": str(mapping.pk),
                            "subject_id": mapping.subject_id,
                            "mapping_id": mapping.pk,
                            "native_identifier": mapping.external_identifier,
                            "target_kind": "metric_subject",
                            "target_role": "history",
                            "resolution_state": "resolved",
                            "requested_start_at": first,
                            "requested_end_at": last,
                        }
                    ],
                )
                job = set_job_state(job.pk, "ready")
            EventDossierClaimCollectionJob.objects.get_or_create(
                claim_id=release.claim_id, job=job
            )
        if job.state != "ready" or job.next_retry_at and job.next_retry_at > cutoff:
            continue
        return job
    return None


def collect_missing_history(release, mapping, *, cutoff, budget):
    """Run one eligible target after the bounded planning transaction commits."""
    with bounded_planning(budget):
        job = _prepare_history_job(release, mapping, cutoff=cutoff, budget=budget)
    if job is None:
        return False
    config = mapping.contract.source_configuration[mapping.source_id]
    try:
        child = job_budget(budget, job)
    except SourceError:
        return False
    before = child.remaining
    preceding = job.last_attempt_id
    try:
        run = execute_due_job(job, {"slot": None}, child)
    except (BusyJob, CommandError, SourceError):
        job.refresh_from_db()
        run = job.last_attempt if job.last_attempt_id != preceding else None
    finally:
        charge(budget, child, before)
    if run is None or run.status == "running":
        return False
    if run.status != "success":
        # A concurrent success/lease cannot be overwritten by a failed worker.
        CollectionJob.objects.filter(
            pk=job.pk, state="ready", active_run__isnull=True
        ).update(
            next_retry_at=timezone.now() + timedelta(seconds=config["poll_seconds"])
        )
    return True
