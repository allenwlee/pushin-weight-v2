"""Read shared measurements and native posts without blending scopes or windows."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.benchmark_metric_store import native_date
from core.measurement_taxonomy import require, resolve_products
from core.models import (
    MetricCollectionRun,
    MetricObservation,
    MetricValue,
    Post,
    SourceMetric,
)


def normalize_points(points, launch_date, policy):
    require(policy in {"launch", "first_observed"}, "unsupported baseline policy")
    baseline = next(
        (
            p
            for p in points
            if p["date"] == launch_date and p.get("raw_value") is not None
        ),
        None,
    )
    status = "launch_baseline"
    if baseline is None and policy == "first_observed":
        baseline = next(
            (
                p
                for p in points
                if p["date"] >= launch_date and p.get("raw_value") is not None
            ),
            None,
        )
        status = "later_baseline"
    if baseline is None:
        status = "baseline_missing"
    elif Decimal(str(baseline["raw_value"])) == 0:
        status = "baseline_zero"
    base = Decimal(str(baseline["raw_value"])) if baseline else None
    for point in points:
        value = point.get("raw_value")
        point["percent_change"] = (
            float((Decimal(str(value)) / base - 1) * 100)
            if base and value is not None and point["date"] >= baseline["date"]
            else None
        )
    return {
        "status": status,
        "date": baseline["date"] if baseline else None,
        "value": baseline["raw_value"] if baseline else None,
        "evidence": baseline.get("evidence", []) if baseline else [],
        "policy": policy,
    }


def post_points(contract, line, days):
    subject = contract.catalog_snapshot["subjects"][line["subject_id"]]
    policy = line.get("post_policy", "legacy_brand")
    if policy == "legacy_brand":
        require(subject["kind"] == "brand", "legacy post counting requires a brand")
        posts = Post.objects.filter(brands__brand_id=subject["key"])
    else:
        from core.measurement_attribution import subject_posts

        posts = subject_posts(
            contract.taxonomy_version,
            line["subject_id"],
            policy_version=line["post_policy_version"],
        )
    first = native_date(days[0])
    last = native_date(days[-1]) + timedelta(days=1)
    posts = posts.filter(
        created_at__gte=datetime.combine(first, datetime.min.time(), UTC),
        created_at__lt=datetime.combine(last, datetime.min.time(), UTC),
    )
    counts = {
        row["day"].isoformat(): row["count"]
        for row in posts.annotate(day=TruncDate("created_at", tzinfo=UTC))
        .values("day")
        .annotate(count=Count("pk", distinct=True))
    }
    coverage = contract.methodology.get("post_coverage")
    if coverage:
        require(
            coverage["start"] <= days[0] <= days[-1] <= coverage["end"],
            "post dates outside known collection coverage",
        )
    today = timezone.now().astimezone(UTC).date().isoformat()
    return [
        {
            "date": day,
            "raw_value": str(counts.get(day, 0)),
            "coverage": "partial" if day >= today else "observed",
            "observed": True,
            "source_date": day,
            "source_timezone": "UTC",
            "measurement_kind": "flow",
            "window_start_at": day + "T00:00:00+00:00",
            "window_end_at": (native_date(day) + timedelta(days=1)).isoformat()
            + "T00:00:00+00:00",
            "temporal_status": "exact",
            "evidence": [
                {
                    "native_table": "posts",
                    "relationship_table": "posts_brands"
                    if policy == "legacy_brand"
                    else "post_subject_attributions",
                    "counting_policy": policy,
                    "distinct_posts": True,
                }
            ],
        }
        for day in days
    ]


def mapping_scope(contract, line):
    subject = line["subject_id"]
    source = line["source"]
    require(
        subject in contract.catalog_snapshot["subjects"],
        "line subject outside taxonomy",
    )
    identifiers = line.get("mapping_identifiers", [])
    require(
        bool(identifiers) and len(identifiers) == len(set(identifiers)),
        "line needs a fixed unique source cohort",
    )
    mappings = list(
        contract.mappings.filter(
            source_id=source, external_identifier__in=identifiers
        ).select_related("subject")
    )
    require(len(mappings) == len(identifiers), "line mapping missing or ambiguous")
    allowed = resolve_products(contract.taxonomy_version, subject)
    for mapping in mappings:
        require(
            str(mapping.subject_id) == subject
            or (
                mapping.subject.subject_kind == "product"
                and str(mapping.subject.product_id) in allowed
            ),
            "mapping does not belong to line scope",
        )
    return mappings


def _point(value, definition, day):
    observation = value.observation
    run = observation.run
    metadata = observation.source_metadata
    return {
        "date": day,
        "raw_value": str(value.integer_value)
        if value.integer_value is not None
        else value.float_value,
        "coverage": "observed",
        "observed": True,
        "source_date": day,
        "measurement_kind": definition.measurement_kind,
        "temporal_status": value.temporal_status,
        "source_timezone": value.source_timezone,
        **{
            field: (
                getattr(value, field).isoformat()
                if getattr(value, field) is not None
                else None
            )
            for field in (
                "as_of_at",
                "as_of_date",
                "window_start_at",
                "window_end_at",
                "period_label_date",
            )
        },
        "dimensions": observation.dimensions,
        "secondary_source": metadata.get("secondary_source", False),
        "observed_at": observation.observed_at.isoformat(),
        "evidence": [
            {
                "run_id": str(run.pk),
                "observation_id": observation.pk,
                "source_identifier": observation.source_identifier,
                "payload_sha256": run.payload_sha256,
                "source_as_of": run.source_as_of.isoformat()
                if run.source_as_of
                else None,
                "archive": metadata or None,
            }
        ],
    }


def metric_points(contract, line, days):
    source = line["source"]
    settings = contract.source_configuration[source]
    frozen = next(
        (d for d in settings["definitions"] if d["metric_key"] == line["metric_key"]),
        None,
    )
    require(frozen is not None, "line metric not pinned")
    definition = SourceMetric.objects.get(pk=frozen["id"])
    from core.benchmark_metric_identity import definition_snapshot

    require(definition_snapshot(definition) == frozen, "pinned definition changed")
    mappings = mapping_scope(contract, line)
    mapping_ids = {m.pk for m in mappings}
    aggregation = line.get("aggregation", "single")
    require(
        aggregation in {"single", "sum_fixed_cohort", "best_score"},
        "unsupported aggregation",
    )
    require(
        aggregation != "sum_fixed_cohort" or definition.quantity_form == "count",
        "only comparable counts can be summed",
    )
    require(
        aggregation != "single" or len(mappings) == 1,
        "single line requires one mapping",
    )
    require(
        aggregation != "best_score" or source == "arena",
        "best-score selection is Arena-only",
    )
    values = list(
        MetricValue.objects.filter(
            source_metric=definition,
            observation__mapping_id__in=mapping_ids,
            observation__run__contract=contract,
            observation__run__status__in=["success", "partial"],
            observation__status="ok",
        )
        .select_related("observation__run")
        .prefetch_related("observation__values__source_metric")
        .order_by("observation__run__completed_at", "id")[:100001]
    )
    require(len(values) <= 100000, "series row budget exceeded")
    groups = defaultdict(dict)
    revisions = {}
    for value in values:
        observation = value.observation
        run = observation.run
        required_dimensions = line.get("dimensions", {})
        require(
            all(
                observation.dimensions.get(k) == v
                for k, v in required_dimensions.items()
            ),
            "line context differs from source observation",
        )
        if source == "hf":
            day = (
                observation.source_metadata.get("archive_snapshot_date")
                or observation.observed_at.astimezone(UTC).date().isoformat()
            )
        elif definition.measurement_kind == "state":
            day = (
                value.as_of_date.isoformat()
                if value.as_of_date
                else value.as_of_at.astimezone(UTC).date().isoformat()
                if value.as_of_at
                else None
            )
        else:
            day = (
                value.period_label_date.isoformat() if value.period_label_date else None
            )
        if day is None or day > days[-1]:
            continue
        if day < days[0] and source != "arena":
            continue
        key = (day, run.pk)
        require(
            observation.mapping_id not in groups[key],
            "multiple measurements for a subject/date in one run",
        )
        groups[key][observation.mapping_id] = value
        direct = run.source_metadata.get("ingestion_mode") == "direct"
        revisions[key] = (
            1 if source == "hf" and direct else 0,
            run.source_as_of or run.completed_at,
            run.completed_at,
            str(run.pk),
        )
    selected = {}
    selected_revision = {}
    for (day, run_id), cohort in groups.items():
        if aggregation != "best_score" and set(cohort) != mapping_ids:
            continue
        if (
            day in selected_revision
            and revisions[(day, run_id)] <= selected_revision[day]
        ):
            continue
        if aggregation == "best_score":

            def score(value):
                return next(
                    (
                        v.float_value
                        for v in value.observation.values.all()
                        if v.source_metric.metric_key == "rating"
                    ),
                    float("-inf"),
                )

            chosen = max(cohort.values(), key=score)
            point = _point(chosen, definition, day)
            point["selected_source_identifier"] = chosen.observation.source_identifier
        else:
            own = list(cohort.values())
            point = _point(own[0], definition, day)
            if aggregation == "sum_fixed_cohort":
                time_signature = lambda v: (
                    v.temporal_status,
                    v.source_timezone,
                    v.as_of_at,
                    v.as_of_date,
                    v.window_start_at,
                    v.window_end_at,
                    v.period_label_date,
                )
                require(
                    len({time_signature(v) for v in own}) == 1,
                    "cannot sum mixed effective windows",
                )
                point["raw_value"] = str(sum(v.integer_value for v in own))
                point["evidence"] = [
                    e for v in own for e in _point(v, definition, day)["evidence"]
                ]
        point.update(selected_count=len(mapping_ids), reported_count=len(cohort))
        if source == "arena":
            point["related_values"] = {
                v.source_metric.metric_key: (
                    str(v.integer_value)
                    if v.integer_value is not None
                    else v.float_value
                )
                for v in (
                    chosen
                    if aggregation == "best_score"
                    else next(iter(cohort.values()))
                ).observation.values.all()
            }
        selected[day] = point
        selected_revision[day] = revisions[(day, run_id)]
    complete_publications = {}
    if source == "arena":
        publications = MetricObservation.objects.filter(
            run__contract=contract,
            run__source_id=source,
            run__status__in=["success", "partial"],
            status="ok",
            source_metadata__publication_complete=True,
        ).select_related("run")
        for observation in publications:
            day = observation.published_date.isoformat()
            run = observation.run
            revision = (
                0,
                run.source_as_of or run.completed_at,
                run.completed_at,
                str(run.pk),
            )
            if (
                day not in complete_publications
                or revision > complete_publications[day]
            ):
                complete_publications[day] = revision
        for day, revision in complete_publications.items():
            if day in selected_revision and revision > selected_revision[day]:
                selected.pop(day, None)
    observed_dates = set()
    if source == "openrouter":
        observed_dates = set(
            MetricObservation.objects.filter(
                run__contract=contract,
                run__source_id=source,
                run__status__in=["success", "partial"],
                status="ok",
            ).values_list("dimensions__date", flat=True)
        )
    points = []
    prior = max((d for d in selected.keys() | complete_publications.keys() if d < days[0]), default=None)
    last = selected.get(prior)
    for day in days:
        if day in selected:
            last = selected[day]
            points.append(dict(last))
        elif source == "arena" and last and day not in complete_publications:
            points.append(
                {**last, "date": day, "coverage": "carried_forward", "observed": False}
            )
        else:
            if source == "arena" and day in complete_publications:
                last = None
            points.append(
                {
                    "date": day,
                    "raw_value": None,
                    "coverage": "not_reported_top50"
                    if source == "openrouter" and day in observed_dates
                    else "missing",
                    "observed": False,
                    "selected_count": len(mapping_ids),
                    "reported_count": 0,
                    "evidence": [],
                }
            )
    return points, definition, [str(m.pk) for m in mappings]


def build_comparison(contract, preset_key, start_date=None, end_date=None):
    preset = contract.methodology.get("comparisons", {}).get(preset_key)
    require(preset is not None, "unknown comparison preset")
    anchor = preset["launch_anchor"]
    require(
        anchor["product_subject_id"] in contract.catalog_snapshot["subjects"],
        "launch product outside taxonomy",
    )
    if anchor.get("precision") == "date":
        launch = native_date(anchor["announced_date"]).isoformat()
    else:
        from core.benchmark_metric_store import aware_instant

        launch = aware_instant(anchor["announced_at"]).date().isoformat()
    first = native_date(launch)
    default_end = timezone.now().astimezone(UTC).date().isoformat()
    coverage = contract.methodology.get("post_coverage")
    if coverage:
        default_end = min(default_end, coverage["end"])
    end = native_date(end_date or default_end)
    start = native_date(start_date or launch)
    require(
        first <= start <= end and 0 <= (end - first).days < 366,
        "comparison must start at or after reviewed launch and span at most 366 days",
    )
    days = [
        (first + timedelta(days=i)).isoformat() for i in range((end - first).days + 1)
    ]
    lines = []
    require(0 < len(preset.get("lines", [])) <= 20, "invalid line count")
    for line in preset["lines"]:
        subject = contract.catalog_snapshot["subjects"][line["subject_id"]]
        if line["source"] == "x":
            points = post_points(contract, line, days)
            definition = None
            mapping_ids = []
        else:
            points, definition, mapping_ids = metric_points(contract, line, days)
        baseline = normalize_points(points, launch, line.get("baseline", "launch"))
        lines.append(
            {
                "key": line["key"],
                "label": line["label"],
                "source": line["source"],
                "subject": subject,
                "subject_id": line["subject_id"],
                "scope": line.get("post_policy") or line.get("aggregation", "single"),
                "mapping_ids": mapping_ids,
                "metric_key": line["metric_key"],
                "definition_id": definition.pk if definition else None,
                "definition_version": definition.version if definition else 1,
                "unit": definition.unit if definition else "posts",
                "measurement_kind": definition.measurement_kind
                if definition
                else "flow",
                "window_mode": definition.window_mode if definition else "calendar",
                "window_amount": str(definition.window_amount)
                if definition and definition.window_amount is not None
                else None,
                "window_unit": definition.window_unit if definition else "day",
                "direction": "lower_is_better"
                if line["metric_key"] == "rank"
                else None,
                "baseline": baseline,
                "points": [p for p in points if p["date"] >= start.isoformat()],
            }
        )
    latest = {}
    for run in MetricCollectionRun.objects.filter(contract=contract).order_by(
        "started_at"
    ):
        latest[run.source_id] = {
            "status": run.status,
            "last_attempt_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error_code": run.error_code,
        }
    from core.benchmark_metric_operations import collection_health

    return {
        "schema_version": 1,
        "contract_id": str(contract.pk),
        "contract_hash": contract.contract_hash,
        "taxonomy_version_id": str(contract.taxonomy_version_id),
        "title": preset["title"],
        "launch_anchor": anchor,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "display_timezone": "UTC",
        "normalization": "100 * (value / baseline - 1)",
        "lines": lines,
        "collection_status": latest,
        "collection_health": collection_health(contract),
        "generated_at": timezone.now().isoformat(),
    }
