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
    selection: MetricSelection, product_keys: set[UUID]
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


def validate_request(request: ChartRequest) -> ResolvedRequest:
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
    metrics = tuple(_resolve_metric(metric, product_keys) for metric in selections)
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


def metric_series(resolved: ResolvedRequest, index: int) -> dict:
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
    try:
        packet = forecast_inputs(
            mapping.contract,
            request.cutoff,
            mapping_ids=[mapping.pk],
            mode="operational"
            if request.history_mode == "strict"
            else "retrospective_research",
            use="internal_analysis",
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
        metadata = value["source_metadata"]
        day = (
            metadata.get("archive_snapshot_date")
            or metadata.get("reconstruction_date")
            or value["period_label_date"]
            or value["as_of_date"]
            or (value["as_of_at"] or "")[:10]
        )
        if not day:
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
