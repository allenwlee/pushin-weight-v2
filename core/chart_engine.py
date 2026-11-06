"""Internal, read-only requests for product-release charts."""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from django.core.exceptions import ValidationError

from core.benchmark_attribution import UseNotPermitted, enforce_use
from core.classification_contract import (
    AUDIENCE_TOPIC_KEYS,
    CANONICAL_POST_TYPE_KEYS,
    COMPATIBLE_TAXONOMY_VERSIONS,
    CONTRACT_VERSION,
    GEOPOLITICAL_MODE_KEYS,
    SENTIMENT_KEYS,
    TAXONOMY_KEY_CROSSWALK,
)
from core.models import (
    EventDossierClaim,
    Product,
    ProductReleaseDetail,
    SourceSubjectMapping,
)


@dataclass(frozen=True)
class ReleaseAnchor:
    product_key: UUID | str
    date: date
    source: str
    review_id: UUID | None = None
    claim_id: UUID | None = None


@dataclass(frozen=True)
class MetricSelection:
    product_key: UUID | str
    contract_id: UUID | str
    mapping_id: UUID | str
    metric_key: str
    release: str | None = None


@dataclass(frozen=True)
class ChartRequest:
    target: ReleaseAnchor
    start: datetime
    end: datetime
    cutoff: datetime
    comparison: ReleaseAnchor | None = None
    comparison_start: datetime | None = None
    comparison_end: datetime | None = None
    classifications: tuple[tuple[str, str], ...] = ()
    metrics: tuple[MetricSelection, ...] = ()
    history_mode: str = "strict"
    comparable_collection_accounting: bool = False


@dataclass(frozen=True)
class ResolvedRelease:
    product: Product
    date: date
    anchor_source: str
    reviewed: bool
    claim_id: UUID | None = None


@dataclass(frozen=True)
class ResolvedRequest:
    request: ChartRequest
    target: ResolvedRelease
    comparison: ResolvedRelease | None
    metrics: tuple["ResolvedMetric", ...]


@dataclass(frozen=True)
class ResolvedMetric:
    selection: MetricSelection
    mapping: SourceSubjectMapping | None
    unavailable_reason: str | None = None


def _resolve_metric(
    selection: MetricSelection, product_keys: set[UUID], *, source_use_override=False
) -> ResolvedMetric:
    if not isinstance(selection, MetricSelection):
        raise TypeError("invalid metric selection")
    if selection.release not in {None, "target", "comparison"}:
        raise ValueError("unknown release selection")
    try:
        mapping = (
            SourceSubjectMapping.objects.select_related("subject", "contract")
            .filter(
                pk=selection.mapping_id,
                contract_id=selection.contract_id,
                purpose="metric",
            )
            .first()
        )
    except (ValidationError, ValueError):
        mapping = None
    if mapping is None or mapping.contract is None:
        return ResolvedMetric(selection, None, "mapping_unavailable")
    if (
        not mapping.reviewed_by.strip()
        or not mapping.evidence_url.strip()
        or not mapping.contract.reviewed_by.strip()
    ):
        return ResolvedMetric(selection, None, "mapping_unreviewed")
    try:
        requested_product = UUID(str(selection.product_key))
    except (TypeError, ValueError):
        return ResolvedMetric(selection, None, "product_unavailable")
    if (
        requested_product not in product_keys
        or mapping.subject.subject_kind != "product"
        or mapping.subject.product_id != requested_product
    ):
        return ResolvedMetric(selection, None, "mapping_product_mismatch")
    configured = mapping.contract.source_configuration.get(mapping.source_id, {})
    if not any(
        row.get("metric_key") == selection.metric_key
        for row in configured.get("definitions", [])
    ):
        return ResolvedMetric(selection, None, "metric_not_in_contract")
    if not source_use_override:
        try:
            enforce_use(
                mapping.contract,
                {"lines": [{"source": mapping.source_id}]},
                "internal_analysis",
            )
        except UseNotPermitted:
            return ResolvedMetric(selection, None, "source_use_not_permitted")
    return ResolvedMetric(selection, mapping)


def _discover_metrics(product_keys: set[UUID]) -> tuple[MetricSelection, ...]:
    mappings = list(
        SourceSubjectMapping.objects.filter(
            purpose="metric",
            contract__isnull=False,
            subject__subject_kind="product",
            subject__product_id__in=product_keys,
        )
        .select_related("subject", "contract")
        .order_by("source_id", "pk")[:101]
    )
    if len(mappings) > 100:
        raise ValueError("too many reviewed source mappings; select metrics explicitly")
    selections = []
    for mapping in mappings:
        config = mapping.contract.source_configuration.get(mapping.source_id, {})
        for definition in config.get("definitions", []):
            if definition.get("metric_key"):
                selections.append(
                    MetricSelection(
                        mapping.subject.product_id,
                        mapping.contract_id,
                        mapping.pk,
                        definition["metric_key"],
                    )
                )
    if len(selections) > 100:
        raise ValueError("too many metrics; select a smaller set")
    return tuple(selections)


def _resolve_anchor(
    anchor: ReleaseAnchor, *, cutoff: datetime, history_mode: str
) -> ResolvedRelease:
    if not isinstance(anchor.date, date) or isinstance(anchor.date, datetime):
        raise TypeError("release anchor requires a date")
    if not anchor.source or not anchor.source.strip():
        raise ValueError("release anchor requires a source")
    try:
        product = Product.objects.get(product_key=anchor.product_key)
    except (Product.DoesNotExist, ValidationError, ValueError) as exc:
        raise ValueError("unknown product") from exc
    if (anchor.review_id is None) != (anchor.claim_id is None):
        raise ValueError("review and claim must be provided together")
    if anchor.review_id is None:
        return ResolvedRelease(product, anchor.date, anchor.source, False)

    release = (
        ProductReleaseDetail.objects.filter(review_id=anchor.review_id, product=product)
        .select_related("review")
        .first()
    )
    claim = (
        EventDossierClaim.objects.filter(
            pk=anchor.claim_id,
            claim_kind_reference__code__in=("announcement", "release_report"),
            event_dossier_source__event_dossier_id=release.review.event_dossier_id,
            review_decisions__review=release.review,
            review_decisions__disposition="accepted",
        ).first()
        if release
        else None
    )
    if claim is None or (
        claim.reported_product_id is not None
        and claim.reported_product_id != product.pk
    ):
        raise ValueError("release claim does not match product review")
    claim_date = claim.effective_date or (
        claim.effective_at.date() if claim.effective_at else None
    )
    if claim_date != anchor.date:
        raise ValueError("release claim date does not match anchor")
    if history_mode == "strict" and (
        claim.recorded_at > cutoff
        or claim.event_dossier_source.linked_at > cutoff
        or release.review.recorded_at > cutoff
    ):
        raise ValueError("release claim or review was recorded after cutoff")
    return ResolvedRelease(product, anchor.date, anchor.source, True, claim.pk)


def validate_request(
    request: ChartRequest, *, source_use_override=False
) -> ResolvedRequest:
    """Validate exact half-open bounds and resolve named Products without writes."""
    if not isinstance(request.comparable_collection_accounting, bool):
        raise TypeError("collection accounting declaration must be boolean")
    timestamps = [request.start, request.end, request.cutoff]
    if any(
        not isinstance(value, datetime) or value.utcoffset() is None
        for value in timestamps
    ):
        raise ValueError("window and cutoff must be timezone-aware")
    if any(value.utcoffset() != timedelta(0) for value in timestamps):
        raise ValueError("window and cutoff must use UTC")
    if request.start >= request.end:
        raise ValueError("window end must follow start")
    if request.end - request.start > timedelta(days=366):
        raise ValueError("window may not exceed 366 days")
    if request.history_mode not in {"strict", "hindsight"}:
        raise ValueError("unknown history mode")
    if request.comparison is None:
        if request.comparison_start is not None or request.comparison_end is not None:
            raise ValueError("comparison window requires a comparison release")
    else:
        start, end = request.comparison_start, request.comparison_end
        if (
            not all(
                isinstance(value, datetime) and value.utcoffset() == timedelta(0)
                for value in (start, end)
            )
            or start >= end
            or end - start > timedelta(days=366)
        ):
            raise ValueError("invalid comparison window")
    categories = {
        "post_type": set(CANONICAL_POST_TYPE_KEYS)
        | {
            canonical
            for dimension, _, canonical in TAXONOMY_KEY_CROSSWALK
            if dimension == "post_type"
        },
        "sentiment": set(SENTIMENT_KEYS),
        "audience": set(AUDIENCE_TOPIC_KEYS),
        "geopolitics": set(GEOPOLITICAL_MODE_KEYS),
    }
    if any(
        not isinstance(item, (tuple, list))
        or len(item) != 2
        or item[0] not in categories
        or item[1] not in categories[item[0]]
        for item in request.classifications
    ):
        raise ValueError("invalid classification filter")
    target = _resolve_anchor(
        request.target, cutoff=request.cutoff, history_mode=request.history_mode
    )
    comparison = (
        _resolve_anchor(
            request.comparison, cutoff=request.cutoff, history_mode=request.history_mode
        )
        if request.comparison
        else None
    )
    product_keys = {target.product.product_key}
    if comparison:
        product_keys.add(comparison.product.product_key)
    selections = request.metrics or _discover_metrics(product_keys)
    if (
        not request.metrics
        and comparison
        and comparison.product.product_key == target.product.product_key
    ):
        selections = tuple(
            replace(selection, release=role)
            for selection in selections
            for role in ("target", "comparison")
        )
    if len(selections) > 100:
        raise ValueError("too many metrics; select a smaller set")
    metrics = tuple(
        _resolve_metric(metric, product_keys, source_use_override=source_use_override)
        for metric in selections
    )
    for metric in metrics:
        expected = comparison if metric.selection.release == "comparison" else target
        if metric.selection.release is not None and (
            expected is None
            or str(metric.selection.product_key) != str(expected.product.product_key)
        ):
            raise ValueError("metric selection does not match its release")
    return ResolvedRequest(request, target, comparison, metrics)


def brand_discussion(resolved: ResolvedRequest, *, comparison: bool = False) -> dict:
    """Count current brand discussion without writing persistent snapshots.

    Post-brand memberships and current classification projections do not retain
    enough history for strict as-known replay. Hindsight is explicitly labeled.
    """
    from collections import Counter

    from core.discussion_windows import _calculate, _inputs
    from core.models import Post

    request = resolved.request
    release = resolved.comparison if comparison else resolved.target
    if release is None:
        raise ValueError("comparison release is unavailable")
    if not release.product.brand_id:
        return {
            "scope": "brand_discussion",
            "status": "brand_unavailable",
            "post_count": None,
        }
    if request.history_mode == "strict":
        return {
            "scope": "brand_discussion",
            "status": "historical_membership_unavailable",
            "post_count": None,
            "warning": "Stored brand membership and classifications lack complete as-known history.",
        }
    start = request.comparison_start if comparison else request.start
    end = request.comparison_end if comparison else request.end
    end = min(end, request.cutoff)
    if end <= start:
        return {
            "scope": "brand_discussion",
            "status": "outside_cutoff",
            "post_count": None,
            "warning": "The requested window begins at or after the evidence cutoff.",
        }
    if (
        Post.objects.filter(
            brands__brand_id=release.product.brand_id,
            created_at__gte=start,
            created_at__lt=end,
        )
        .values("pk")[:100001]
        .count()
        > 100000
    ):
        return {
            "scope": "brand_discussion",
            "status": "window_too_large",
            "post_count": None,
            "warning": "Narrow the window to at most 100,000 stored posts.",
        }
    posts, states, projections = _inputs(release.product.brand_id, start, end)
    requested = set(request.classifications)
    counts = Counter()
    daily = Counter()
    selected = 0
    for post in posts:
        post_id = post["tweet_id"]
        state = states.get(post_id)
        if state is None:
            counts["unclassified"] += 1
            counts["legacy"] += 1
        elif not (
            state["contract_version"] == CONTRACT_VERSION
            and state["taxonomy_version"] in COMPATIBLE_TAXONOMY_VERSIONS
        ):
            counts["excluded"] += 1
        elif state["outcome"] != "classified":
            counts["unclassified"] += 1
        else:
            counts["classified"] += 1
        if requested:
            categories = {
                (row["dimension"], row["category"])
                for row in _calculate(
                    [post], states, projections, "historical_inclusive"
                )
                if row["count"]
            }
            if not categories.intersection(requested):
                continue
        selected += 1
        daily[post["created_at"].date().isoformat()] += 1
    bucket = datetime.combine(start.date(), datetime.min.time(), tzinfo=UTC)
    while bucket < end:
        daily.setdefault(bucket.date().isoformat(), 0)
        bucket += timedelta(days=1)
    return {
        "scope": "brand_discussion",
        "status": "stored_only",
        "post_count": selected,
        "total_post_count": len(posts),
        "classification": dict(counts),
        "daily": dict(sorted(daily.items())),
        "history_mode": "hindsight",
        "coverage": "historical_completeness_unknown",
        "warning": "Current stored projections may include later evidence; historical collection may be incomplete.",
    }


def _single_chart_definition(mapping, key):
    """Resolve the reviewed frozen definition, rejecting drift and wrong windows."""
    from decimal import Decimal, InvalidOperation

    from core.benchmark_metric_identity import definition_snapshot
    from core.models import SourceMetric

    definitions = [
        d
        for d in mapping.contract.source_configuration.get(mapping.source_id, {}).get(
            "definitions", []
        )
        if d.get("metric_key") == key
    ]
    if len(definitions) != 1:
        return None
    frozen = definitions[0]
    obj = SourceMetric.objects.filter(pk=frozen.get("id")).first()
    if obj is None or definition_snapshot(obj) != frozen:
        return None
    try:
        rolling_days = Decimal(str(frozen.get("window_amount")))
    except (InvalidOperation, TypeError, ValueError):
        rolling_days = None
    if (
        mapping.source_id == "hf"
        and key == "downloads"
        and not (
            frozen.get("unit") == "downloads"
            and frozen.get("window_mode") == "rolling"
            and rolling_days == Decimal(30)
            and frozen.get("window_unit") == "day"
        )
    ):
        return None
    return frozen


def _exact_utc_day(value, day):
    """Check a provider row's actual half-open UTC day, not its date label."""
    try:
        midnight = datetime.combine(
            date.fromisoformat(day), datetime.min.time(), tzinfo=UTC
        )
        start = value["window_start_at"]
        end = value["window_end_at"]
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        return (
            value.get("temporal_status") == "exact"
            and value.get("source_timezone") == "UTC"
            and start == midnight
            and end == midnight + timedelta(days=1)
        )
    except (KeyError, ValueError, TypeError):
        return False


def metric_series(
    resolved: ResolvedRequest,
    index: int,
    *,
    source_use_override=False,
    single_template=False,
) -> dict:
    """Read retained metric evidence with source rights and availability checks."""
    import json
    from collections import defaultdict
    from decimal import Decimal

    from core.benchmark_forecast_inputs import forecast_inputs

    metric = resolved.metrics[index]
    if metric.mapping is None:
        return {
            "status": "unavailable",
            "reason": metric.unavailable_reason,
            "product_key": str(metric.selection.product_key),
            "mapping_id": str(metric.selection.mapping_id),
            "metric": metric.selection.metric_key,
            "points": [],
        }
    request = resolved.request
    mapping = metric.mapping
    release_is_comparison = metric.selection.release == "comparison" or (
        metric.selection.release is None
        and resolved.comparison is not None
        and resolved.comparison.product.product_key
        != resolved.target.product.product_key
        and str(metric.selection.product_key)
        == str(resolved.comparison.product.product_key)
    )
    if release_is_comparison and resolved.comparison is None:
        return {
            "status": "unavailable",
            "reason": "comparison_unavailable",
            "points": [],
        }
    start = request.comparison_start if release_is_comparison else request.start
    end = request.comparison_end if release_is_comparison else request.end
    if single_template and start >= min(end, request.cutoff):
        return {"status": "unavailable", "reason": "outside_cutoff", "points": []}
    definition = (
        _single_chart_definition(mapping, metric.selection.metric_key)
        if single_template
        else None
    )
    if single_template and definition is None:
        return {
            "status": "unavailable",
            "reason": "definition_incompatible",
            "source": mapping.source_id,
            "metric": metric.selection.metric_key,
            "points": [],
        }
    try:
        packet = forecast_inputs(
            mapping.contract,
            request.cutoff,
            mapping_ids=[mapping.pk],
            mode="operational"
            if request.history_mode == "strict"
            else "retrospective_research",
            use="internal_analysis",
            chart_source_use_override=source_use_override,
            **(
                {
                    "chart_metric_key": metric.selection.metric_key,
                    "chart_window_start": start,
                    "chart_window_end": min(end, request.cutoff),
                }
                if single_template and start < min(end, request.cutoff)
                else {}
            ),
        )
    except (UseNotPermitted, ValueError) as exc:
        return {
            "status": "unavailable",
            "reason": str(exc),
            "source": mapping.source_id,
            "metric": metric.selection.metric_key,
            "mapping_id": str(mapping.pk),
            "points": [],
        }
    opencode_rows = None
    if mapping.source_id == "opencode":
        from core.benchmark_opencode import selected_rows

        opencode_rows = selected_rows(
            mapping.contract,
            [mapping.pk],
            (start.date() - timedelta(days=1)).isoformat(),
            end.date().isoformat(),
            cutoff=request.cutoff if request.history_mode == "strict" else None,
            canonical=True,
        )
    direct_runs = set()
    if mapping.source_id == "hf":
        from core.models import CollectionRun

        direct_runs = {
            str(run_id)
            for run_id in CollectionRun.objects.filter(
                pk__in=[row["run_id"] for row in packet["values"]],
                direct_ingestion=True,
            ).values_list("pk", flat=True)
        }
    candidates = defaultdict(list)
    for value in packet["values"]:
        if value["metric"] != metric.selection.metric_key:
            continue
        if single_template and str(value.get("metric_definition_id")) != str(
            definition["id"]
        ):
            continue
        if (
            single_template
            and mapping.source_id == "arena"
            and (
                value.get("dimensions", {}).get("config") != "text"
                or value.get("dimensions", {}).get("category") != "overall"
            )
        ):
            continue
        metadata = value["source_metadata"]
        day = (
            (
                value["period_label_date"]
                if single_template and mapping.source_id in {"opencode", "openrouter"}
                else None
            )
            or metadata.get("archive_snapshot_date")
            or metadata.get("reconstruction_date")
            or value["period_label_date"]
            or value["as_of_date"]
            or (value["as_of_at"] or "")[:10]
            or (
                (value["first_local_observed_at"] or "")[:10]
                if mapping.source_id == "hf"
                else None
            )
        )
        if not day:
            continue
        if (
            single_template
            and mapping.source_id in {"openrouter", "opencode"}
            and not _exact_utc_day(value, day)
        ):
            continue
        if opencode_rows is not None:
            chosen = opencode_rows.get((mapping.external_identifier, day))
            if chosen is None or chosen["observation_id"] != value["observation_id"]:
                continue
        bucket_start = datetime.fromisoformat(day).replace(tzinfo=UTC)
        bucket_end = bucket_start + timedelta(days=1)
        if (
            bucket_end <= start - timedelta(days=1)
            or bucket_start >= end
            or bucket_start >= request.cutoff
        ):
            continue
        candidates[day].append(value)
    selected = {}
    for day, values in sorted(candidates.items()):
        bucket_start = datetime.fromisoformat(day).replace(tzinfo=UTC)
        complete = bucket_start + timedelta(days=1) <= request.cutoff
        if (
            single_template
            and mapping.source_id == "arena"
            and any(row.get("revision_conflict") for row in values)
        ):
            selected[day] = {
                "date": day,
                "value": None,
                "coverage": "ambiguous_observations",
            }
            continue
        dimensions = {json.dumps(row["dimensions"], sort_keys=True) for row in values}
        if len(dimensions) != 1:
            selected[day] = {
                "date": day,
                "value": None,
                "coverage": "ambiguous_dimensions",
            }
            continue
        value = max(
            values,
            key=lambda row: (
                mapping.source_id == "hf" and row["run_id"] in direct_runs,
                row["provider_as_of"] or row["import_completed_at"],
                row["import_completed_at"],
                row["run_id"],
                row["value_id"],
            ),
        )
        same_revision = [
            row
            for row in values
            if row["run_id"] == value["run_id"]
            and row["provider_as_of"] == value["provider_as_of"]
            and row["import_completed_at"] == value["import_completed_at"]
        ]
        if len({(row["value"], row["unit"]) for row in same_revision}) > 1:
            selected[day] = {
                "date": day,
                "value": None,
                "coverage": "ambiguous_observations",
            }
            continue
        partial_source = value["source_metadata"].get("period_status") == "partial"
        selected[day] = {
            "date": day,
            "value": value["value"] if complete and not partial_source else None,
            "coverage": "partial_source"
            if partial_source
            else "observed"
            if complete
            else "partial_window",
            "evidence": {
                "value_id": value["value_id"],
                "observation_id": value["observation_id"],
            },
            "unit": value["unit"],
            "window_mode": value["window_mode"],
            "measurement_kind": value["measurement_kind"],
        }
    points = []
    bucket = datetime.combine(start.date(), datetime.min.time(), tzinfo=UTC)
    while bucket < min(end, request.cutoff):
        day = bucket.date().isoformat()
        point = dict(
            selected.get(day, {"date": day, "value": None, "coverage": "missing"})
        )
        if bucket < start or bucket + timedelta(days=1) > min(end, request.cutoff):
            point.update(value=None, coverage="partial_window")
        if mapping.source_id == "hf" and metric.selection.metric_key == "downloads":
            previous = selected.get((bucket.date() - timedelta(days=1)).isoformat(), {})
            point["net_change"] = (
                str(Decimal(str(point["value"])) - Decimal(str(previous["value"])))
                if point["value"] is not None and previous.get("value") is not None
                else None
            )
        points.append(point)
        bucket += timedelta(days=1)
    return {
        "status": "available"
        if any(point["value"] is not None for point in points)
        else "no_observations",
        "source": mapping.source_id,
        "metric": metric.selection.metric_key,
        "history_mode": request.history_mode,
        "points": points,
        "warning": "Hindsight may include later-recovered evidence."
        if request.history_mode == "hindsight"
        else None,
    }


SINGLE_BRAND_METRICS = (
    ("github", "stars", "GitHub stars", "stars"),
    ("github", "forks", "GitHub forks", "forks"),
    ("github", "open_issues", "GitHub open issues", "issues"),
    ("github", "subscribers", "GitHub subscribers", "subscribers"),
    ("github", "repository_size_kb", "GitHub repository size", "kilobytes"),
    ("github", "asset_downloads", "GitHub release asset downloads", "downloads"),
    ("github", "asset_size_bytes", "GitHub release asset size", "bytes"),
    ("openrouter", "total_tokens", "OpenRouter tokens", "tokens / day"),
    ("hf", "downloads", "Hugging Face rolling downloads", "rolling 30-day downloads"),
    ("opencode", "tokens", "OpenCode tokens", "tokens / day"),
    ("opencode", "unique_users", "OpenCode users", "users / day"),
    ("opencode", "sessions", "OpenCode sessions", "sessions / day"),
    ("arena", "rating", "Arena rating", "rating"),
    ("arena", "rank", "Arena rank · last published", "rank · lower is better"),
    ("arena", "rating_lower", "Arena rating lower bound", "rating"),
    ("arena", "rating_upper", "Arena rating upper bound", "rating"),
    ("arena", "variance", "Arena variance", "variance"),
    ("arena", "vote_count", "Arena votes", "votes"),
)


def _unmapped_exact_values(mapping, key, start, end):
    """Read pre-crosswalk evidence only through a reviewed, exact product mapping."""
    from collections import defaultdict
    from decimal import Decimal

    from django.db.models import Q

    from core.benchmark_metric_identity import definition_snapshot
    from core.models import MetricValue, SourceSubjectMapping

    source = mapping.source_id
    if source not in {"hf", "openrouter", "opencode", "arena"}:
        return {}
    frozen = _single_chart_definition(mapping, key)
    if frozen is None:
        return {}
    identity_ambiguous = (
        SourceSubjectMapping.objects.filter(
            source_id=source,
            source_subject_kind=mapping.source_subject_kind,
            normalized_identifier=mapping.normalized_identifier,
        )
        .exclude(subject_id=mapping.subject_id)
        .exists()
    )
    rows = MetricValue.objects.filter(
        source_metric__source_id=source,
        source_metric__metric_key=key,
        observation__source_identifier=mapping.external_identifier,
        observation__source_subject_kind=mapping.source_subject_kind,
        observation__run__job__source_id=source,
        observation__mapping__isnull=True,
        observation__status="ok",
        observation__run__status__in=["success", "partial"],
    ).filter(
        Q(observation__product__isnull=True)
        | Q(observation__product__product_key=mapping.subject.product_id)
    )
    if identity_ambiguous:
        # An unscoped observation may still be attributed when the existing
        # product relation independently identifies this exact product.
        rows = rows.filter(observation__product__product_key=mapping.subject.product_id)
    rows = rows.filter(
        Q(period_label_date__gte=start.date(), period_label_date__lt=end.date())
        | Q(as_of_date__gte=start.date(), as_of_date__lt=end.date())
        | Q(as_of_at__gte=start, as_of_at__lt=end)
        | Q(
            observation__archive_snapshot_date__gte=start.date(),
            observation__archive_snapshot_date__lt=end.date(),
        )
        | Q(
            observation__reconstruction_date__gte=start.date(),
            observation__reconstruction_date__lt=end.date(),
        )
    )
    if source == "arena":
        rows = rows.filter(
            observation__config_key="text", observation__category_key="overall"
        )
    rows = list(
        rows.select_related("source_metric", "observation__run__job").order_by("pk")[
            :10001
        ]
    )
    if len(rows) > 10000:
        raise ValueError("source evidence exceeds the bounded read")
    grouped = defaultdict(list)
    invalid_days = set()
    for row in rows:
        obs = row.observation
        day = (
            row.period_label_date
            or row.as_of_date
            or obs.archive_snapshot_date
            or obs.reconstruction_date
            or (row.as_of_at.date() if row.as_of_at else None)
        )
        if day is None or not start.date() <= day < end.date():
            continue
        bucket_start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        if bucket_start < start or bucket_start + timedelta(days=1) > end:
            continue
        if obs.revision_conflict or obs.period_status == "partial":
            if source == "arena":
                invalid_days.add(day)
            continue
        if source in {"openrouter", "opencode"} and not _exact_utc_day(
            {
                "temporal_status": row.temporal_status,
                "source_timezone": row.source_timezone_reference_id,
                "window_start_at": row.window_start_at,
                "window_end_at": row.window_end_at,
            },
            day.isoformat(),
        ):
            continue
        definition = row.source_metric
        if definition_snapshot(definition) != frozen:
            if source == "arena":
                invalid_days.add(day)
            continue
        grouped[day].append(row)
    result = {}
    epoch = datetime.min.replace(tzinfo=UTC)
    for day, candidates in grouped.items():
        def revision(row):
            run = row.observation.run
            return (
                source == "hf" and bool(run.direct_ingestion),
                run.source_as_of or run.completed_at or epoch,
                run.completed_at or epoch,
            )

        newest = max(revision(row) for row in candidates)
        latest = [row for row in candidates if revision(row) == newest]
        numbers = {
            Decimal(
                str(
                    row.integer_value
                    if row.integer_value is not None
                    else row.float_value
                )
            )
            for row in latest
        }
        if len(numbers) != 1:
            invalid_days.add(day)
            continue
        row = max(latest, key=lambda value: value.pk)
        result[day.isoformat()] = {
            "value": next(iter(numbers)),
            "evidence": {
                "value_id": row.pk,
                "observation_id": row.observation_id,
                "mapping_id": None,
                "identity_mapping_id": str(mapping.pk),
            },
        }
    for day in invalid_days:
        result[day.isoformat()] = {
            "value": None,
            "coverage": "conflict",
            "evidence": None,
        }
    return result


def _complete_utc_window(start, end, cutoff):
    start_day = datetime.combine(start.date(), datetime.min.time(), tzinfo=UTC)
    if start_day < start:
        start_day += timedelta(days=1)
    end_boundary = min(end, cutoff)
    end_day = datetime.combine(end_boundary.date(), datetime.min.time(), tzinfo=UTC)
    return start_day, end_day


def _single_brand_discussion(resolved):
    """Aggregate an unfiltered chart without loading each post into Python."""
    if resolved.request.history_mode != "hindsight":
        return brand_discussion(resolved)
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    from core.models import Post

    product = resolved.target.product
    if not product.brand_id:
        return {"status": "brand_unavailable", "daily": {}}
    request = resolved.request
    start, end = _complete_utc_window(request.start, request.end, request.cutoff)
    if end <= start:
        return {"status": "outside_cutoff", "daily": {}}
    rows = (
        Post.objects.filter(
            brands__brand_id=product.brand_id,
            created_at__gte=start,
            created_at__lt=end,
        )
        .annotate(day=TruncDate("created_at", tzinfo=UTC))
        .values("day")
        .annotate(count=Count("pk", distinct=True))
        .order_by("day")
    )
    counts = {row["day"].isoformat(): row["count"] for row in rows}
    if request.classifications:
        filtered = brand_discussion(resolved)
        if filtered.get("status") != "stored_only":
            return filtered
        # A zero is observable only on a day with retained source posts.
        selected = filtered.get("daily", {})
        counts = {day: selected.get(day, 0) for day in counts}
    return {"status": "stored_only", "daily": counts}


def build_single_brand_chart(request: ChartRequest, *, start_day=-14, end_day=29):
    """Build the public, read-only single-brand-comp result from stored evidence.

    The owner's temporary source-use override is limited to this template. It
    changes no source policy or review record, and does not authorize identity
    guesses or affect existing ChartEngine callers.
    """
    from collections import defaultdict

    from core.chart_engine_view import single_brand_line

    if request.comparison is not None:
        raise ValueError("single-brand-comp accepts one product")
    if (
        type(start_day) is not int
        or type(end_day) is not int
        or start_day >= end_day
        or end_day - start_day > 366
    ):
        raise ValueError("invalid display range")
    resolved = validate_request(request, source_use_override=True)
    anchor = resolved.target.date
    discussion = _single_brand_discussion(resolved)
    discussion_values = {
        (date.fromisoformat(day) - anchor).days: value
        for day, value in discussion.get("daily", {}).items()
        if value is not None
    }
    lines = []

    def line(source, metric, label, unit, values, evidence, *, status, identifier=None):
        output = single_brand_line(
            source, metric, values, evidence, anchor, start_day, end_day
        )
        output.update(
            key=f"{source}:{metric}",
            source=source,
            metric=metric,
            label=label,
            unit=unit,
            identifier=identifier,
            status=status,
        )
        return output

    lines.append(
        line(
            "discussion",
            "posts",
            "Brand posts",
            "posts",
            discussion_values,
            {},
            status=discussion.get("status", "unavailable"),
            identifier=resolved.target.product.brand_id,
        )
    )
    candidates = defaultdict(list)
    for index, metric in enumerate(resolved.metrics):
        if metric.mapping is not None:
            if metric.mapping.source_id == "github":
                roles = {
                    getattr(metric.mapping, "identity_snapshot", {}).get("role"),
                    getattr(metric.mapping, "identifier_metadata", {}).get("role"),
                } - {None, ""}
                if not roles or not roles <= {"dedicated_model", "dedicated_product"}:
                    continue
            candidates[(metric.mapping.source_id, metric.selection.metric_key)].append(
                (index, metric)
            )
    for source, key, label, unit in SINGLE_BRAND_METRICS:
        choices = candidates[(source, key)]
        if len(choices) != 1:
            lines.append(
                line(
                    source,
                    key,
                    label,
                    unit,
                    {},
                    {},
                    status="mapping_ambiguous" if choices else "mapping_unavailable",
                )
            )
            continue
        index, metric = choices[0]
        series = metric_series(
            resolved, index, source_use_override=True, single_template=True
        )
        values = {}
        evidence = {}
        for point in series.get("points", []):
            day = (date.fromisoformat(point["date"]) - anchor).days
            if point.get("value") is not None:
                values[day] = point["value"]
                evidence[day] = point.get("evidence")
            elif point.get("coverage") not in {None, "missing"}:
                evidence[day] = {"coverage": point["coverage"]}
        if (
            request.history_mode == "hindsight"
            and series.get("status") != "unavailable"
        ):
            try:
                retained = _unmapped_exact_values(
                    metric.mapping, key, request.start, min(request.end, request.cutoff)
                )
            except ValueError:
                retained = {}
                values = {}
                evidence = {}
                series["status"] = "unavailable"
                series["reason"] = "source_evidence_limit_exceeded"
            for day, item in retained.items():
                offset = (date.fromisoformat(day) - anchor).days
                # Conflicting independently sourced values are not silently pooled.
                if item.get("coverage") == "conflict":
                    values.pop(offset, None)
                    evidence[offset] = {"coverage": "conflict"}
                elif (evidence.get(offset) or {}).get("coverage") not in {
                    None,
                    "missing",
                }:
                    continue
                elif offset in values and str(values[offset]) != str(item["value"]):
                    values.pop(offset)
                    evidence[offset] = {"coverage": "conflict"}
                elif offset not in values:
                    values[offset] = item["value"]
                    evidence[offset] = item["evidence"]
            if values:
                series["status"] = "available"
        lines.append(
            line(
                source,
                key,
                label,
                unit,
                values,
                evidence,
                status=series.get("reason", series.get("status", "unavailable")),
                identifier=metric.mapping.external_identifier,
            )
        )
    return {
        "product": {
            "key": str(resolved.target.product.product_key),
            "label": resolved.target.product.display_name
            or resolved.target.product.repo_id,
            "release_date": anchor.isoformat(),
            "anchor_source": resolved.target.anchor_source,
            "anchor_reviewed": resolved.target.reviewed,
        },
        "as_of": request.cutoff.isoformat(),
        "start_date": (anchor + timedelta(days=start_day)).isoformat(),
        "end_date": (anchor + timedelta(days=end_day - 1)).isoformat(),
        "lines": lines,
        "notes": [
            "Brand posts represent broader brand discussion; historical collection may be incomplete.",
            "Arena rank carries the last published rank only between recorded snapshots.",
            "Hugging Face downloads represent the source's rolling 30-day count.",
        ],
    }


def build_chart(
    request: ChartRequest,
    *,
    start_day=-14,
    end_day=29,
    smoothing=False,
    normalized=True,
    selected_lines=None,
    include_preview=True,
    selected_day=None,
):
    """Return one in-memory numerical result and SVG for an internal caller."""
    from core.chart_engine_svg import render_svg
    from core.chart_engine_view import prepare_line

    if (
        not isinstance(start_day, int)
        or not isinstance(end_day, int)
        or start_day >= end_day
        or end_day - start_day > 366
    ):
        raise ValueError("invalid display range")
    resolved = validate_request(request)
    discussions = {"target": brand_discussion(resolved)}
    if resolved.comparison:
        discussions["comparison"] = brand_discussion(resolved, comparison=True)
    releases = {"target": resolved.target, "comparison": resolved.comparison}

    def release_label(role):
        release = releases[role]
        product = release.product
        name = (
            product.display_name
            or getattr(product, "repo_id", None)
            or str(product.product_key)
        )
        return f"{name} ({role}, {release.date.isoformat()})"

    raw_lines = []
    for role, discussion in discussions.items():
        release = releases[role]
        raw_lines.append(
            {
                "role": role,
                "key": ("discussion", "posts"),
                "label": f"{release_label(role)} brand discussion",
                "values": {
                    (date.fromisoformat(day) - release.date).days: count
                    for day, count in discussion.get("daily", {}).items()
                },
            }
        )
    measurements = []
    for index, metric in enumerate(resolved.metrics):
        data = metric_series(resolved, index)
        measurements.append(data)
        if metric.mapping is None:
            continue
        selection = metric.selection
        role = selection.release or (
            "comparison"
            if resolved.comparison
            and resolved.comparison.product.product_key
            != resolved.target.product.product_key
            and str(selection.product_key)
            == str(resolved.comparison.product.product_key)
            else "target"
        )
        release = releases[role]
        key = (metric.mapping.source_id, selection.metric_key)
        value_key = "net_change" if key == ("hf", "downloads") else "value"
        definitions = metric.mapping.contract.source_configuration.get(key[0], {}).get(
            "definitions", []
        )
        definition = next(
            (item for item in definitions if item.get("metric_key") == key[1]), {}
        )
        compatibility = tuple(
            definition.get(field)
            for field in (
                "version",
                "unit",
                "value_kind",
                "quantity_form",
                "value_role",
                "measurement_kind",
                "window_mode",
                "window_amount",
                "window_unit",
                "window_duration_basis",
                "window_alignment",
                "source_timezone",
            )
        )
        raw_lines.append(
            {
                "role": role,
                "key": key,
                "compatibility": compatibility,
                "label": f"{release_label(role)} {key[0]} {key[1]} ({getattr(metric.mapping, 'external_identifier', 'mapped subject')})",
                "values": {
                    (date.fromisoformat(point["date"]) - release.date).days: point.get(
                        value_key
                    )
                    for point in data["points"]
                },
            }
        )
    lines = []
    for line in raw_lines:
        reference_role = "comparison" if resolved.comparison else "target"
        candidates = [
            item["values"]
            for item in raw_lines
            if item["role"] == reference_role
            and item["key"] == line["key"]
            and item.get("compatibility") == line.get("compatibility")
        ]
        reference = candidates[0] if len(candidates) == 1 else {}
        lines.append(
            {
                "label": line["label"],
                "role": line["role"],
                "source": line["key"][0],
                "metric": line["key"][1],
                "points": prepare_line(
                    line["values"],
                    reference,
                    start=start_day,
                    end=end_day,
                    smoothing=smoothing,
                    normalized=normalized,
                ),
            }
        )
        for point in lines[-1]["points"]:
            point["date"] = (
                releases[line["role"]].date + timedelta(days=point["day"])
            ).isoformat()
    previews = []
    if resolved.comparison and request.comparable_collection_accounting:
        from core.benchmark_forecast_inputs import forecast_inputs
        from core.chart_prediction_preview import temporary_preview

        def complete_posts(role, start, end):
            raw = next(
                line["values"]
                for line in raw_lines
                if line["role"] == role and line["key"] == ("discussion", "posts")
            )
            anchor = releases[role].date
            return {
                day: count
                for day, count in raw.items()
                if start
                <= datetime.combine(
                    anchor + timedelta(days=day), datetime.min.time(), tzinfo=UTC
                )
                and datetime.combine(
                    anchor + timedelta(days=day + 1), datetime.min.time(), tzinfo=UTC
                )
                <= min(end, request.cutoff)
            }

        target_posts = complete_posts("target", request.start, request.end)
        prior_posts = complete_posts(
            "comparison", request.comparison_start, request.comparison_end
        )
        completed_day = (request.cutoff.date() - resolved.target.date).days - 1
        for prior in (
            line
            for line in raw_lines
            if line["role"] == "comparison"
            and line["key"] in {("hf", "downloads"), ("openrouter", "total_tokens")}
        ):
            if (
                sum(
                    item["role"] == "comparison" and item["key"] == prior["key"]
                    for item in raw_lines
                )
                != 1
                or sum(
                    item["role"] == "target" and item["key"] == prior["key"]
                    for item in raw_lines
                )
                != 1
            ):
                continue
            target = next(
                (
                    line
                    for line in raw_lines
                    if line["role"] == "target" and line["key"] == prior["key"]
                ),
                None,
            )
            if target is None:
                continue
            if prior.get("compatibility") != target.get("compatibility"):
                continue
            permitted = True
            matching = [
                metric
                for metric in resolved.metrics
                if metric.mapping is not None
                and (metric.mapping.source_id, metric.selection.metric_key)
                == prior["key"]
            ]
            try:
                for metric in matching:
                    enforce_use(
                        metric.mapping.contract,
                        {"lines": [{"source": metric.mapping.source_id}]},
                        "forecast_fitting",
                    )
                    forecast_inputs(
                        metric.mapping.contract,
                        request.cutoff,
                        mapping_ids=[metric.mapping.pk],
                        mode="operational"
                        if request.history_mode == "strict"
                        else "retrospective_research",
                        use="forecast_fitting",
                    )
            except (UseNotPermitted, ValueError):
                permitted = False
            source, key = prior["key"]
            preview = temporary_preview(
                target_posts=target_posts,
                historical_posts=prior_posts,
                historical_metrics=prior["values"],
                completed_day=completed_day,
                cutoff=request.cutoff,
                target_launch=resolved.target.date,
                source=source,
                metric="net_download_change" if source == "hf" else key,
                comparable=True,
                accounting_known=all(
                    item["status"] == "stored_only" for item in discussions.values()
                ),
                forecast_permitted=permitted,
                history_mode=request.history_mode,
                horizon=28,
            )
            if preview["status"] == "available":
                preview["calibration_dates"] = {
                    role: [
                        (release.date + timedelta(days=day)).isoformat()
                        for day in range(completed_day - 2, completed_day + 1)
                    ]
                    for role, release in releases.items()
                    if release
                }
            previews.append(preview)
            if preview["status"] == "available":
                values = {
                    day: point["smoothed" if smoothing else "value"]
                    for day, point in preview["points"].items()
                }
                lines.append(
                    {
                        "label": f"Temporary prediction {source} {key}",
                        "role": "target",
                        "source": source,
                        "metric": key,
                        "forecast": True,
                        "points": prepare_line(
                            values,
                            prior["values"],
                            start=start_day,
                            end=end_day,
                            smoothing=False,
                            normalized=normalized,
                        ),
                    }
                )
                for point in lines[-1]["points"]:
                    point["date"] = (
                        resolved.target.date + timedelta(days=point["day"])
                    ).isoformat()
    if selected_lines is not None:
        lines = [
            line
            for line in lines
            if (line["role"], line["source"], line["metric"]) in selected_lines
        ]
    if not include_preview:
        lines = [line for line in lines if not line.get("forecast")]
    if not normalized and len({(line["source"], line["metric"]) for line in lines}) > 1:
        raise ValueError("raw charts require a single metric; select compatible lines")
    warnings = [
        discussion["warning"]
        for discussion in discussions.values()
        if discussion.get("warning")
    ]
    warnings = list(dict.fromkeys(warnings))
    warnings.extend(
        preview["warning"] for preview in previews if preview.get("warning")
    )
    for preview in previews:
        if preview["status"] == "available":
            dates = preview["calibration_dates"]
            warnings.append(
                f"Collected-post ratio {preview['ratio']:.2f}x: {dates['target'][0]}–{dates['target'][-1]} versus {dates['comparison'][0]}–{dates['comparison'][-1]}."
            )
    warnings = list(dict.fromkeys(warnings))
    result = {
        "version": "chart-engine-v1",
        "lines": lines,
        "discussion": discussions,
        "measurements": measurements,
        "warnings": warnings,
        "preview": previews
        or [
            {
                "status": "unavailable",
                "reason": "comparable collection accounting and forecast permissions not established",
            }
        ],
        "anchors": {
            role: {
                "product_key": str(release.product.product_key),
                "date": release.date.isoformat(),
                "reviewed": release.reviewed,
                "source": release.anchor_source,
            }
            for role, release in releases.items()
            if release
        },
    }
    result["svg"] = render_svg(
        {
            "title": "Product release comparison"
            if resolved.comparison
            else "Product release",
            "lines": lines,
            "warnings": warnings,
            "unit": "Change from reference (%)"
            if normalized
            else "Raw value (see series units)",
            "day_range": (start_day, end_day - 1),
            "selected_day": selected_day,
        }
    )
    return result
