"""Connect a qualified Pulse release to existing reviewed product measurement jobs."""

import logging
from datetime import UTC, datetime, time, timedelta
from itertools import groupby, zip_longest

import httpx
from django.conf import settings
from django.contrib.postgres.aggregates import BoolOr
from django.db import connection
from django.db.models import Exists, F, Max, OuterRef, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.collection_budgets import (
    PlanningDeadline,
    bounded_planning,
    invocation_budget,
)
from core.collection_identity import (
    RELEASE_IDENTIFIER_SCOPES,
    dedicated_product_mapping,
    release_metric_mapping_is_current,
)
from core.collection_jobs import register_job, set_job_state
from core.collection_scheduling import (
    dispatch_due,
    metric_authority,
    take_metric_authority,
)
from core.measurement_taxonomy import digest, require
from core.models import (
    CollectionJob,
    EventDossier,
    EventDossierClaim,
    EventDossierClaimCollectionJob,
    Product,
    SourceSubjectMapping,
)
from core.release_chart_handoff import lock_qualified_release, resolve_release

# GitHub statistics are already collected through catalog/release observations and
# their dedicated projection worker. They are not a direct numeric HTTP adapter.
DIRECT_SOURCES = ("hf", "openrouter", "opencode", "arena")
# One cold release can need X, the publisher article, model identity and a measurement.
RELEASE_REQUEST_LIMIT = 4
CATALOG_REQUEST_LIMIT = 8


def _contract_from_recipe(recipe, product, reviewed_by):
    from core.benchmark_metric_identity import configure_collection
    from core.measurement_taxonomy import configure_taxonomy, resolve_subject_id

    reviewed_by = recipe.get("reviewed_by") or reviewed_by
    taxonomy = configure_taxonomy(
        {
            "reviewed_by": reviewed_by,
            "subjects": [{"kind": "product", "key": str(product.product_key)}],
        }
    )
    row = recipe["mapping"]
    return configure_collection(
        {
            "reviewed_by": reviewed_by,
            "taxonomy_version": str(taxonomy.pk),
            "mappings": [
                {
                    **row,
                    "subject_id": str(
                        resolve_subject_id("product", product.product_key)
                    ),
                }
            ],
            "source_configuration": {row["source"]: recipe["configuration"]},
            "methodology": recipe["methodology"],
        }
    )


def _catalog_recipe(mapping, *, coordinate=None):
    from urllib.parse import urlsplit

    from core.chart_engine import SINGLE_BRAND_METRICS
    from core.collection_identity import (
        qualified_catalog_ownership,
    )

    source = mapping.source_id
    require(
        source in DIRECT_SOURCES
        and mapping.identifier_scope_code == RELEASE_IDENTIFIER_SCOPES[source]
        and dedicated_product_mapping(mapping),
        "catalog mapping does not establish the measurement endpoint",
    )
    require(
        mapping.publisher_account_id
        and qualified_catalog_ownership(mapping.publisher_account, mapping.subject),
        "confirmed catalog publisher required",
    )
    metadata = {
        "role": mapping.identity_snapshot["role"],
        "release_catalog": {
            "mapping_hash": mapping.mapping_hash,
            "publisher_account_key": str(mapping.publisher_account_id),
        },
    }
    if source == "arena":
        fields = (
            coordinate or mapping.identifier_metadata.get("release_endpoint", {})
        ).get("source_fields", {})
        metadata["release_endpoint"] = {
            "source_fields": {
                k: fields[k]
                for k in ("config", "category", "board", "reasoning", "model_name")
                if k in fields
            }
        }
    configuration = {
        "scheduling_enabled": True,
        "metrics": [key for src, key, _, _ in SINGLE_BRAND_METRICS if src == source],
    }
    scope = ""
    fields = (
        coordinate or mapping.identifier_metadata.get("release_endpoint", {})
    ).get("source_fields", {})
    if source == "hf":
        from core.data_source_backfill_hf import catalog_repo_creation

        creation = catalog_repo_creation(
            mapping.subject, mapping.external_identifier, mapping.publisher_account_id
        )
        metadata["archive_row_key"] = creation["hf_archive_row_id"]
        ref = mapping.identifier_metadata.get("release_endpoint") or {}
        metadata["release_catalog"]["hf_receipt"] = digest(
            [
                ref.get("archive_sha256"),
                ref.get("selector"),
                ref.get("url"),
            ]
        )
        configuration["metric_versions"] = {"downloads": 2}
        scope = "model"
    elif source == "opencode":
        from scripts.benchmark_download_collector.sources import opencode_url

        url = mapping.identifier_metadata.get("release_endpoint", {}).get("url", "")
        path = mapping.identifier_metadata.get("endpoint_path") or urlsplit(url).path
        opencode_url(path)
        metadata["endpoint_path"] = path
    elif source == "openrouter":
        configuration["completed_day_lag"] = 1
    elif source == "arena":
        config = fields.get("config") or mapping.identifier_metadata.get("config")
        require(
            config in {"text", "text_style_control"}
            and fields.get("category", "overall") == "overall",
            "Arena board or category has no supported historical numeric adapter",
        )
        configuration.update(
            config=config,
            metric_versions={"rating_lower": 2, "rating_upper": 2, "vote_count": 2},
        )
        metadata["category"] = fields.get("category") or "overall"
    return {
        "mapping": {
            "source": source,
            "external_identifier": mapping.external_identifier,
            "identifier_scope": scope,
            "source_subject_kind": mapping.source_subject_kind,
            "evidence_url": mapping.evidence_url,
            "identifier_metadata": metadata,
            # Some provider metrics name another company's model. Publisher credentials on those
            # catalog entries attest the producer, while the numeric writer expects source accounts.
            "publisher_account_key": str(mapping.publisher_account_id)
            if source == "hf"
            else None,
        },
        "configuration": configuration,
        "methodology": {"aggregation": "fixed_cohort"},
    }


def _release_page(now, *, discovery_enabled=False):
    """Rotate through dated Products. Discovery also accepts an empty crosswalk."""
    from core.chart_engine import single_brand_dates

    start, end = single_brand_dates(now.date())
    # Invert chart offsets: a release qualifies when today's UTC date lies in its chart.
    oldest = now.date() - (end - now.date())
    newest = now.date() + (now.date() - start)
    mapped = SourceSubjectMapping.objects.filter(
        source_id__in=DIRECT_SOURCES,
        subject__subject_kind="product",
    ).values("subject__product_id")
    lookup, eligible = ("__isnull", False) if discovery_enabled else ("__in", mapped)
    member = EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier_id=OuterRef(
            "event_dossier_source__event_dossier_id"
        ),
        scope_key__startswith="pulse-event-member-v1:",
        **{"reported_product__product_key" + lookup: eligible},
    )
    # Start at dated evidence instead of repeatedly scanning every release and
    # counting two separate cohorts. The full resolver still verifies the exact
    # claim, source revision, date, and product before a job can be linked.
    event = "event_dossier_source__event_dossier__"
    recent = Q(effective_date__range=(oldest, newest)) | Q(
        effective_at__gte=datetime.combine(oldest, time.min, UTC),
        effective_at__lt=datetime.combine(newest + timedelta(days=1), time.min, UTC),
    )
    candidates = (
        EventDossierClaim.objects.filter(
            **{
                event + "merged_into__isnull": True,
                event + "event_kind_reference__code": "product_release",
            },
            claim_kind_reference__code__in=[
                "announcement",
                "release_report",
                "source_stated_release",
            ],
            effective_precision__in=["day", "datetime"],
        )
        .filter(
            Q(
                **{
                    event + "current_review__review_state": "confirmed",
                    event + "current_review__product_release__product_id" + lookup: eligible,
                }
            )
            | (Q(**{event + "current_review__isnull": True}) & Exists(member))
        )
        .order_by()
        .values("event_dossier_source__event_dossier_id")
        .annotate(active=BoolOr(recent, default=False))
    )
    query, params = candidates.query.sql_with_params()
    slot = int(now.timestamp()) // 900
    with connection.cursor() as cursor:
        cursor.execute(
            f"""WITH eligible(id, active) AS ({query}), numbered AS (
                SELECT id, active, row_number() OVER (PARTITION BY active ORDER BY id) - 1 AS position,
                       count(*) OVER (PARTITION BY active) AS total,
                       CASE WHEN active THEN 8 ELSE 4 END AS size FROM eligible
            )
            SELECT id FROM numbered WHERE position / size = mod(%s, (total+size-1) / size)
            ORDER BY CASE WHEN mod(%s, 2)=0 THEN active ELSE NOT active END DESC,
                     mod(position + %s, total)""",
            (*params, slot, slot, slot),
        )
        return [row[0] for row in cursor.fetchall()]


def _metric_mappings(release):
    """Reuse independently reviewed contracts before deriving one from a reviewed catalog link."""
    maps = SourceSubjectMapping.objects.filter(
        subject__product_id=release.product_key,
        source_id__in=DIRECT_SOURCES,
        source__enabled=True,
    ).select_related(
        "subject__product",
        "publisher_account",
        "contract",
        "source",
        "identifier_scope",
    )
    maps = (
        maps.filter(purpose__in=["metric", "catalog"])
        .defer(
            "contract__catalog_snapshot",
            "subject__product__raw",
            "subject__product__siblings",
            "subject__product__card_data",
            "subject__product__config",
        )
        .annotate(
            rank_in_source=Window(
                RowNumber(), partition_by=[F("source_id"), F("purpose")], order_by="pk"
            )
        )
        .filter(rank_in_source__lte=101)
        .order_by("source_id", "purpose", "pk")
    )
    by_source = {}
    for (source, purpose), rows in groupby(
        maps, key=lambda row: (row.source_id, row.purpose)
    ):
        subset = list(rows)
        by_source.setdefault(source, {})[purpose] = subset
    # One oversized table (often Arena boards) must not hide a small,
    # independent reviewed provider mapping for the same Product.
    metric, catalog = [], []
    for group in by_source.values():
        if any(len(rows) > 100 for rows in group.values()):
            continue
        metric.extend(group.get("metric", []))
        catalog.extend(group.get("catalog", []))
    catalog = [m for m in catalog if m.identifier_scope_code == RELEASE_IDENTIFIER_SCOPES.get(m.source_id)]
    existing_sources = {m.source_id for m in metric}
    for m in catalog:
        if m.source_id in existing_sources:
            continue
        if sum(other.source_id == m.source_id for other in catalog) != 1:
            continue
        try:
            coordinates = m.identifier_metadata.get("release_endpoint_coordinates") or [
                None
            ]
            if len(coordinates) != 1:
                continue
            recipe = _catalog_recipe(m, coordinate=coordinates[0])
            contract = _contract_from_recipe(
                recipe, m.subject.product, "pulse release " + release.fingerprint
            )
        except (ValueError, KeyError):
            continue
        metric.append(
            contract.mappings.select_related(
                "subject__product",
                "publisher_account",
                "contract",
                "source",
                "identifier_scope",
            ).get()
        )
    return metric


def _source_job(mapping, now):
    source = mapping.source
    contract = mapping.contract
    config = contract.source_configuration[source.pk]
    if (
        not config.get("scheduling_enabled")
        or config.get("eligibility_policy") == SOURCE_STATISTICS_POLICY
        or not release_metric_mapping_is_current(mapping)
    ):
        return None
    # A contract may cover other products or publisher accounts. Never trigger a
    # whole benchmark cohort to populate the selected product's chart.
    if contract.mappings.filter(source=source).exclude(pk=mapping.pk).exists():
        return None
    active = metric_authority(source, contract.pk)
    if active:
        return CollectionJob.objects.filter(pk=active, state="ready").first()
    if CollectionJob.objects.filter(
        source=source, contract=contract, purpose="metric", mode="recurring"
    ).exists():
        return None  # preserve paused/withdrawn or separately managed collection instructions
    from core.benchmark_metric_operations import daily_collection_hour_utc

    hour = daily_collection_hour_utc(source)
    schedule = {"schedule_kind": "interval", "interval_seconds": config["poll_seconds"]}
    if hour is not None:
        schedule = {"schedule_kind": "daily_utc", "daily_utc_hour": hour}
    job = register_job(
        job_key=f"release-metric:{contract.pk}:{source.pk}",
        source=source,
        contract=contract,
        purpose="metric",
        operation="collect_metrics",
        mode="recurring",
        definition={"version": 2, "options": {}},
        settings={
            "owner_kind": "source",
            **schedule,
            "schedule_driver": "shared",
            "max_requests": config["max_requests"],
            "max_seconds": config["max_seconds"],
            "max_bytes": config["max_bytes"],
            "max_items": 100,
        },
    )
    # The old hourly dispatcher also reads this authority and the same successful
    # slot. It cannot independently collect a second copy after registration.
    set_job_state(job.pk, "ready", now=now)
    return take_metric_authority(job.pk)


def release_metric_job_is_current(job, now, *, require_unread=False):
    """The hourly dispatcher may also see this job; honor corrected dossiers and ownership."""
    from core.chart_engine import single_brand_dates

    mappings = list(
        job.contract.mappings.filter(
            purpose="metric",
            source=job.source,
        ).select_related("contract", "subject", "identifier_scope")[:2]
    )
    if len(mappings) != 1 or not release_metric_mapping_is_current(mappings[0]):
        return False
    if require_unread:
        from core.collection_identity import release_metric_catalog_state
        from core.models import MetricValue

        mapping = mappings[0]
        if not release_metric_catalog_state(mapping) or MetricValue.objects.filter(
            observation__mapping__source_id=job.source_id,
            observation__mapping__subject_id=mapping.subject_id,
        ).exists():
            return False
    product_key = mappings[0].subject.product_id
    dates = single_brand_dates(now.astimezone(UTC).date())
    today = now.astimezone(UTC).date()
    oldest, newest = today - (dates[1] - today), today + (today - dates[0])
    linked = job.dossier_claim_links.filter(
        Q(claim__effective_date__range=(oldest, newest))
        | Q(
            claim__effective_at__gte=datetime.combine(oldest, time.min, UTC),
            claim__effective_at__lt=datetime.combine(
                newest + timedelta(days=1), time.min, UTC
            ),
        )
    ).values_list("claim_id", "claim__event_dossier_source__event_dossier_id")
    for claim_id, event_id in linked.order_by("-created_at")[:100]:
        try:
            release = resolve_release(event_id, cutoff=now)
        except ValueError:
            continue
        if release.product_key == product_key and release.claim_id == claim_id:
            return True
    return False


def collect_due_release_metrics(
    *, client, dossier_ids=None, cutoff=None, max_seconds=10, discover_saved_endpoints=None,
    confirm_identities=False,
):
    """Advance one due source job on the existing release worker, across restarts."""
    require(
        type(max_seconds) is int and 1 <= max_seconds <= 30,
        "invalid metric cycle budget",
    )
    result = {
        "selected": 0,
        "qualified": 0,
        "linked_jobs": 0,
        "applied": 0,
        "history_applied": 0,
        "requests": 0,
    }
    measure = settings.BENCHMARK_COLLECTION_ENABLED
    if not measure and not (confirm_identities and settings.PRODUCT_RELEASE_BACKGROUND_ENABLED):
        return {**result, "status": "disabled"}
    budget = invocation_budget(
        client, requests=RELEASE_REQUEST_LIMIT, seconds=max_seconds, max_bytes=4 * 1024**2
    )
    now = (cutoff or timezone.now()).astimezone(UTC)
    # Public identity reads have a separate physical quota so cold catalogs cannot
    # consume the requests reserved for publisher recovery and chart measurements.
    catalog_budget = None
    if confirm_identities and cutoff is None and discover_saved_endpoints is None:
        catalog_budget = invocation_budget(client, requests=CATALOG_REQUEST_LIMIT, seconds=max_seconds, max_bytes=4 * 1024**2)
        # Leave part of the worker deadline to the existing metric writer.
        reserve = min(3, max_seconds / 2) if measure else 0
        catalog_budget.deadline = budget.deadline - reserve
    try:
        _advance_metrics(dossier_ids, now, budget, result, discover_saved_endpoints, live=cutoff is None, measure=measure, catalog_budget=catalog_budget)
    except PlanningDeadline:
        result["status"] = "deferred"
    result["requests"] = RELEASE_REQUEST_LIMIT - budget.remaining
    if catalog_budget is not None:
        result["catalog_requests"] = CATALOG_REQUEST_LIMIT - catalog_budget.remaining
        result["requests"] += result["catalog_requests"]
    return result


def _rotating_dossier_page(ids, slot, size=4):
    count = ids.count()
    if not count:
        return []
    offset = (slot % ((count + size - 1) // size)) * size
    return list(ids[offset:offset + size])


def _recent_publisher_findings(now, *, include_confirmed=False):
    """Admit a just-harvested launch even while its Product or date is pending."""
    dossier_key = "event_dossier_source__event_dossier_id"
    proof = EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier_id=OuterRef(dossier_key),
        extraction_version="pulse-publisher-source-v1",
    )
    pending = EventDossierClaim.objects.filter(
        recorded_at__range=(now - timedelta(days=1), now),
        scope_key__startswith="pulse-novelty-v1:",
        assertion_text__in=("new_release", "historical_release", "availability_update"),
        event_dossier_source__event_dossier__merged_into__isnull=True,
        event_dossier_source__event_dossier__current_review__isnull=True,
    )
    if not include_confirmed:
        pending = pending.filter(~Exists(proof))
    pending = pending.order_by().values(dossier_key).annotate(latest=Max("recorded_at"))
    # Reserve space for new launches and rotate through overflow from prior cycles.
    fresh = list(pending.filter(latest__gte=now - timedelta(minutes=30))
                 .order_by("-latest", dossier_key).values_list(dossier_key, flat=True)[:8])
    overflow = pending.exclude(**{dossier_key + "__in": fresh}).order_by(dossier_key)
    slot = int(now.timestamp()) // 900
    fresh.extend(_rotating_dossier_page(overflow.values_list(dossier_key, flat=True), slot))
    if not include_confirmed:
        return fresh

    # Start from the decision time: an old post can receive its first confirmed
    # model today, even before anyone can establish the launch date.
    reviewed = (
        EventDossier.objects.filter(
            merged_into__isnull=True,
            event_kind_reference__code="product_release",
            current_review__review_state="confirmed",
            current_review__recorded_at__range=(now - timedelta(days=1), now),
            current_review__product_release__product__brand__is_sentinel=False,
            current_review__product_release__product__product_type__code__in=("model-llm", "model-other"),
        )
        .exclude(current_review__product_release__disclosure_state="unannounced")
        .exclude(current_review__product_release__product__private=True)
        .exclude(current_review__product_release__product__disabled=True)
        .order_by("-current_review__recorded_at", "pk")
        .values_list("pk", flat=True)
    )
    reviewed_page = _rotating_dossier_page(reviewed, slot)
    # Alternate first place for tight deadlines and retain each lane's own slots.
    lanes = (reviewed_page, fresh) if slot % 2 else (fresh, reviewed_page)
    return [key for pair in zip_longest(*lanes) for key in pair if key is not None]


def _discover_public_catalogs(release, budget, result, now):
    from core.release_catalog_discovery import discover_release_catalogs
    from core.release_github_identity import discover_github_release

    try:
        if discover_github_release(release, budget=budget):
            result["github_identities_saved"] = result.get("github_identities_saved", 0) + 1
    except (ValueError, TimeoutError, httpx.HTTPError) as exc:
        logging.getLogger(__name__).info("GitHub identity pending for %s: %s", release.dossier_id, type(exc).__name__)
    outcomes = discover_release_catalogs(release, budget, now=now)
    for source, state in outcomes.items():
        counts = result.setdefault("catalog_checks", {}).setdefault(source, {})
        counts[state] = counts.get(state, 0) + 1


def _advance_metrics(dossier_ids, now, budget, result, discover_saved_endpoints, *, live, measure=True, catalog_budget=None):
    from core.benchmark_attribution import UseNotPermitted, enforce_source_collection
    from core.chart_engine import single_brand_dates

    if dossier_ids is None:
        with bounded_planning(budget):
            dossier_ids = _recent_publisher_findings(now, include_confirmed=catalog_budget is not None)
            if measure:
                dossier_ids += _release_page(now, discovery_enabled=True)
    else:
        require(
            isinstance(dossier_ids, (list, tuple)) and len(dossier_ids) <= 25,
            "invalid release metric page",
        )
    from core.release_chart_history import HISTORY_SOURCES, collect_missing_history

    histories = []
    job_ids = set()
    for identifier in dict.fromkeys(dossier_ids):
        if budget.deadline - budget.clock() < 1:
            break
        result["selected"] += 1
        from core.release_provider_identity import discover_verified_hf_model
        from core.release_publisher_recovery import recover_release_publisher

        dossier = EventDossier.objects.filter(pk=identifier).first()
        if dossier is None:
            continue
        evidence_cutoff = now
        recovered = False
        try:
            recovered = recover_release_publisher(dossier, client=budget.client, now=now, budget=budget)
            if recovered and live:
                evidence_cutoff = timezone.now()
        except (ValueError, httpx.HTTPError) as exc:
            logging.getLogger(__name__).warning("Publisher recovery pending for %s: %s", identifier, type(exc).__name__)
        try:
            with bounded_planning(budget):
                release = resolve_release(identifier, cutoff=evidence_cutoff)
        except ValueError:
            # Catalog identity can be confirmed before its launch date is known.
            if catalog_budget is not None:
                from core.release_chart_handoff import resolve_catalog_release

                try:
                    with bounded_planning(budget):
                        identity = resolve_catalog_release(identifier, cutoff=evidence_cutoff)
                except ValueError:
                    continue
                _discover_public_catalogs(identity, catalog_budget, result, now)
            continue
        if not Product.objects.filter(product_key=release.product_key,
                                      product_type__code__in=("model-llm", "model-other")).exists():
            continue
        start, end = single_brand_dates(release.date)
        active = start <= now.date() <= end
        if start > now.date():
            continue
        result["qualified"] += 1
        if discover_saved_endpoints is not None:
            # This operation only reads retained identity evidence. Metric HTTP
            # requests remain under the worker's shared invocation budget.
            with bounded_planning(budget):
                discover_saved_endpoints(release, now)
        elif not recovered:
            try:
                discover_verified_hf_model(release, budget=budget)
            except (ValueError, httpx.HTTPError) as exc:
                logging.getLogger(__name__).warning("HF mapping pending for %s: %s", identifier, type(exc).__name__)
        if catalog_budget is not None:
            _discover_public_catalogs(release, catalog_budget, result, now)
        if not measure:
            continue
        with bounded_planning(budget):
            try:
                lock_qualified_release(
                    release.dossier_id, fingerprint=release.fingerprint
                )
            except ValueError:
                continue
            for mapping in _metric_mappings(release):
                if not release_metric_mapping_is_current(mapping):
                    continue
                try:
                    enforce_source_collection(mapping.contract, mapping.source_id)
                except UseNotPermitted:
                    continue
                if mapping.source_id in HISTORY_SOURCES and (
                    not active or mapping.source_id != "opencode"
                ):
                    histories.append((release, mapping))
                if not active:
                    continue
                job = _source_job(mapping, now)
                if job is None:
                    continue
                EventDossierClaimCollectionJob.objects.get_or_create(
                    claim_id=release.claim_id, job=job
                )
                job_ids.add(job.pk)
    if not measure:
        result["status"] = "identity_only"
        return
    result["linked_jobs"] = len(job_ids)
    # Alternate priority when both lanes have due work; a continuously busy
    # live stream must not keep closed release windows waiting indefinitely.
    history_first = int(now.timestamp()) // 900 % 2 == 0

    def advance_history():
        for release, mapping in histories:
            if budget.deadline - budget.clock() < 1:
                break
            try:
                attempted = collect_missing_history(
                    release, mapping, cutoff=now, budget=budget
                )
            except (ValueError, UseNotPermitted):
                continue
            if attempted:
                result["history_applied"] = 1
                break

    if history_first:
        advance_history()
    if (
        not result["history_applied"]
        and job_ids
        and budget.deadline - budget.clock() >= 1
    ):
        rows = dispatch_due(
            job_ids=job_ids, execute=True, budget=budget, limit=1, now=now, allow_initial_release=live
        )
        result["applied"] = sum(row["applied"] for row in rows)
    if not history_first and not result["applied"]:
        advance_history()
    result["status"] = "checked"
