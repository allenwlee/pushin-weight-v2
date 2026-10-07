"""Reference-week comparisons and a separate, publication-aware Arena panel."""

from datetime import UTC, timedelta
from decimal import Decimal, localcontext

from django.utils import timezone

from core.benchmark_attribution import comparison_attributions
from core.benchmark_metric_operations import collection_health
from core.benchmark_metric_series import metric_points, post_points
from core.benchmark_metric_store import aware_instant, native_date
from core.measurement_taxonomy import digest, require


def dates(first, last):
    return [
        (first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)
    ]


def complete(point):
    return (
        point.get("raw_value") is not None
        and point.get("coverage") == "observed"
        and point.get("observed") is True
    )


def adjacent_differences(points):
    result = []
    for index, point in enumerate(points):
        prior = points[index - 1] if index else None
        valid = prior is not None and complete(point) and complete(prior)
        result.append(
            {
                **point,
                "provider_raw_value": point["raw_value"],
                "raw_value": str(
                    Decimal(point["raw_value"]) - Decimal(prior["raw_value"])
                )
                if valid
                else None,
                "coverage": "observed" if valid else "missing_adjacent_snapshot",
                "observed": valid,
                "transform": "adjacent_snapshot_difference",
                "evidence": [
                    *(
                        {**e, "dependency_role": "prior_snapshot"}
                        for e in prior.get("evidence", [])
                    ),
                    *(
                        {**e, "dependency_role": "current_snapshot"}
                        for e in point.get("evidence", [])
                    ),
                ]
                if valid
                else point.get("evidence", []),
                "adjacent_snapshot_dates": [prior["date"], point["date"]]
                if valid
                else None,
            }
        )
    return result


def describe(contract, line, definition, mappings, points, baseline):
    return {
        **{k: line[k] for k in ("key", "label", "source", "subject_id", "metric_key")},
        "subject": contract.catalog_snapshot["subjects"][line["subject_id"]],
        "scope": line.get("post_policy") or line.get("aggregation", "single"),
        "mapping_ids": mappings,
        "measurement_contract": line.get(
            "measurement_contract",
            {"id": str(contract.pk), "contract_hash": contract.contract_hash},
        ),
        "baseline": baseline,
        "points": points,
        "transform": line.get("transform", "identity"),
        "definition_id": definition.pk if definition else None,
        "definition_version": definition.version if definition else 1,
        "unit": definition.unit if definition else "posts",
        "measurement_kind": definition.measurement_kind if definition else "flow",
        "window_mode": definition.window_mode if definition else "calendar",
        "window_amount": str(definition.window_amount)
        if definition and definition.window_amount is not None
        else None,
        "window_unit": definition.window_unit if definition else "day",
        "source_configuration": {
            "config": contract.source_configuration.get(line["source"], {}).get(
                "config"
            )
        },
    }


def arena_panel(contract, line, window):
    raw, definition, mappings = metric_points(contract, line, window)
    previous_signature, previous_publication, segment = None, None, 0
    points = []
    for point in raw:
        related = point.get("related_values", {})
        metadata = next((e.get("archive") or {} for e in point.get("evidence", [])), {})
        signature = (metadata.get("score_anchor"), metadata.get("methodology_version"))
        known = all(signature)
        publication = point.get("source_date")
        actual = point.get("observed", False) and point["raw_value"] is not None
        if publication and publication != previous_publication:
            if not known or signature != previous_signature:
                segment += 1
            previous_signature, previous_publication = signature, publication
        points.append(
            {
                "date": point["date"],
                "score": point["raw_value"],
                "lower": related.get("rating_lower"),
                "upper": related.get("rating_upper"),
                "battles": related.get("vote_count"),
                "rank": related.get("rank"),
                "variance": related.get("variance"),
                "publication_date": publication,
                "actual_publication": actual,
                "coverage": point["coverage"],
                "segment": segment,
                "comparability": "supported" if known else "unknown",
                "score_anchor": signature[0],
                "methodology_version": signature[1],
                "source_timezone": point.get("source_timezone", "unknown"),
                "temporal_status": point.get("temporal_status", "unknown"),
                "evidence": point.get("evidence", []),
                "value_ids": point.get("related_value_ids", {}),
            }
        )
    description = describe(
        contract,
        line,
        definition,
        mappings,
        raw,
        {"date": None, "value": None, "status": "raw_publications", "evidence": []},
    )
    return {
        "title": "Arena evaluation history",
        "config": "text",
        "category": "overall",
        "subject": description["subject"],
        "source_identifiers": line["mapping_identifiers"],
        "points": points,
        "line": description,
        "battle_semantics": "Reported comparisons in the published sample; not unique people or exact daily new battles.",
        "score_comparability": "Unknown anchor or methodology breaks score segments; publications remain inspectable.",
        "time_alignment": "Arena date-only publications and UTC daily series do not imply identical cutoff instants.",
    }


def build_release_response(contract, preset, start_date=None, end_date=None):
    anchor = preset["launch_anchor"]
    launch = (
        native_date(anchor["announced_date"])
        if anchor["precision"] == "date"
        else aware_instant(anchor["announced_at"]).date()
    )
    today = timezone.now().astimezone(UTC).date()
    start = native_date(start_date) if start_date else launch - timedelta(days=14)
    end = (
        native_date(end_date)
        if end_date
        else min(launch + timedelta(days=28), today - timedelta(days=1))
    )
    coverage = contract.methodology.get("post_coverage")
    if end_date is None and coverage:
        end = min(end, native_date(coverage["end"]))
    require(
        start <= end and (end - start).days < 366 and end < today,
        "release response needs 1–366 completed UTC dates",
    )
    reference_search = preset["reference_search"]
    search_start = native_date(reference_search["start_date"])
    search_end = min(
        native_date(reference_search["end_date"]), today - timedelta(days=1)
    )
    first = min(start - timedelta(days=3), search_start - timedelta(days=1))
    last = max(end, search_end)
    require(
        0 <= (last - first).days < 366,
        "display and reference dependencies exceed 366-day budget",
    )
    read_days = dates(first, last)
    series = []
    for line in preset["lines"]:
        if line["source"] == "x":
            raw, definition, mappings = (
                post_points(contract, line, read_days, allow_missing_coverage=True),
                None,
                [],
            )
        else:
            raw, definition, mappings = metric_points(contract, line, read_days)
        if line.get("transform") == "adjacent_snapshot_difference":
            raw = adjacent_differences(raw)
        series.append((line, raw, definition, mappings))
    reference_dates = []
    indexed_series = [{p["date"]: p for p in raw} for _, raw, _, _ in series]
    for candidate in dates(search_start, search_end):
        week = dates(native_date(candidate), native_date(candidate) + timedelta(days=6))
        if week[-1] > search_end.isoformat():
            break
        if all(
            all(complete(indexed.get(day, {})) for day in week)
            for indexed in indexed_series
        ):
            reference_dates = week
            break
    reference_inputs, lines = {}, []
    with localcontext() as context:
        context.prec = 50
        for line, raw, definition, mappings in series:
            indexed = {p["date"]: p for p in raw}
            reference_points = [indexed[day] for day in reference_dates]
            mean = (
                sum(Decimal(str(p["raw_value"])) for p in reference_points) / 7
                if reference_points
                else None
            )
            valid = mean is not None and mean > 0
            baseline = {
                "policy": "reference_week",
                "status": "reference_week"
                if valid
                else "reference_nonpositive"
                if mean is not None
                else "reference_missing",
                "date": reference_dates[0] if reference_dates else None,
                "dates": reference_dates,
                "value": str(mean) if mean is not None else None,
                "evidence": [
                    e for p in reference_points for e in p.get("evidence", [])
                ],
            }
            reference_inputs[line["key"]] = {
                "mean": baseline["value"],
                "points": reference_points,
            }
            transformed = []
            for index, point in enumerate(raw):
                trailing = raw[max(0, index - 2) : index + 1]
                smooth = (
                    sum(Decimal(str(p["raw_value"])) for p in trailing) / 3
                    if len(trailing) == 3 and all(complete(p) for p in trailing)
                    else None
                )
                transformed.append(
                    {
                        **point,
                        "smoothed_value": str(smooth) if smooth is not None else None,
                        "daily_percent_change": float(
                            (Decimal(str(point["raw_value"])) / mean - 1) * 100
                        )
                        if valid and complete(point)
                        else None,
                        "percent_change": float((smooth / mean - 1) * 100)
                        if valid and smooth is not None
                        else None,
                        "smoothing_dates": [p["date"] for p in trailing]
                        if smooth is not None
                        else [],
                        "smoothing_evidence": [
                            e for p in trailing for e in p.get("evidence", [])
                        ]
                        if smooth is not None
                        else [],
                    }
                )
            lines.append(
                describe(
                    contract,
                    line,
                    definition,
                    mappings,
                    [
                        p
                        for p in transformed
                        if start.isoformat() <= p["date"] <= end.isoformat()
                    ],
                    baseline,
                )
            )
    panel = (
        arena_panel(contract, preset["arena_line"], dates(start, end))
        if preset.get("arena_line")
        else None
    )
    health = collection_health(contract)
    from core.benchmark_measurement_pins import measurement_contract

    parents = {}
    for line in preset["lines"] + (
        [preset["arena_line"]] if preset.get("arena_line") else []
    ):
        if line.get("measurement_contract"):
            parent = measurement_contract(contract, line)
            if parent.pk not in parents:
                parents[parent.pk] = collection_health(parent)
            health[line["source"]] = parents[parent.pk][line["source"]]
    return {
        "schema_version": 1,
        "chart_kind": "release_response_v1",
        "title": preset["title"],
        "contract_id": str(contract.pk),
        "contract_hash": contract.contract_hash,
        "taxonomy_version_id": str(contract.taxonomy_version_id),
        "launch_anchor": anchor,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "display_timezone": "UTC",
        "normalization": "100 * (displayed_value / raw_reference_week_mean - 1)",
        "normalization_label": "Change from reference-week average (%)",
        "default_smoothing_days": 3,
        "reference": {
            "dates": reference_dates,
            "search_range": reference_search,
            "revision": digest([contract.contract_hash, reference_inputs]),
            "raw_means": {
                key: value["mean"] for key, value in reference_inputs.items()
            },
        },
        "dependency_range": {"start": first.isoformat(), "end": last.isoformat()},
        "available_range": preset.get(
            "available_range",
            {
                "start": (launch - timedelta(days=14)).isoformat(),
                "end": min(
                    today - timedelta(days=1), launch + timedelta(days=351)
                ).isoformat(),
            },
        ),
        "usage_provider_options": preset.get("usage_provider_options", {}),
        "lines": lines,
        "arena_panel": panel,
        "attributions": comparison_attributions(
            contract, lines + ([panel["line"]] if panel else [])
        ),
        "collection_health": health,
        "collection_status": {
            source: {
                "status": row["last_attempt"]["status"],
                "last_attempt_at": row["last_attempt"]["started_at"],
                "completed_at": row["last_attempt"]["completed_at"],
                "error_code": row["last_attempt"]["error_code"],
            }
            for source, row in health.items()
            if row["last_attempt"]
        },
        "input_revision": digest(
            [contract.contract_hash, reference_inputs, lines, panel]
        ),
        "generated_at": timezone.now().isoformat(),
    }
