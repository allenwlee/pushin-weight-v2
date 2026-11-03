"""Internal, read-only requests for product-release charts."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from django.core.exceptions import ValidationError

from core.benchmark_attribution import UseNotPermitted, enforce_use
from core.classification_contract import (
    AUDIENCE_TOPIC_KEYS,
    CANONICAL_POST_TYPE_KEYS,
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
    try:
        requested_product = UUID(str(selection.product_key))
    except ValueError:
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
    metrics = tuple(_resolve_metric(metric, product_keys) for metric in request.metrics)
    return ResolvedRequest(request, target, comparison, metrics)
