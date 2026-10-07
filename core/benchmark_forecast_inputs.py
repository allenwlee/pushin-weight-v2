"""Bounded G3 evidence reader; retrospective charts are not historical forecasts."""

from datetime import datetime

from django.db.models import Q

from core.benchmark_attribution import enforce_use
from core.benchmark_metric_store import aware_instant
from core.measurement_taxonomy import require
from core.models import MetricValue


def evidence_selection(contract, mapping_ids, cutoff):
    """Follow frozen history pins while retaining today's identity review boundary."""
    from core.benchmark_measurement_pins import measurement_contract

    mappings = contract.mappings.all()
    if mapping_ids is not None:
        require(0 < len(mapping_ids) <= 1000, "bounded mapping selection required")
        mappings = mappings.filter(pk__in=mapping_ids)
    if cutoff is not None:
        if (
            max(
                contract.reviewed_at,
                contract.created_at,
                contract.taxonomy_version.created_at,
            )
            > cutoff
        ):
            return Q(pk__in=[])
        mappings = mappings.filter(reviewed_at__lte=cutoff)
    selected = list(mappings)
    require(len(selected) <= 1000, "bounded mapping selection required")
    selection = Q(
        observation__run__contract=contract,
        observation__mapping_id__in=[m.pk for m in selected],
    )
    seen = set()
    for preset in contract.methodology.get("comparisons", {}).values():
        lines = [*preset["lines"]]
        if preset.get("arena_line"):
            lines.append(preset["arena_line"])
        for line in lines:
            if not line.get("measurement_contract"):
                continue
            parent = measurement_contract(contract, line)
            key = (
                parent.pk,
                line["source"],
                line["metric_key"],
                tuple(line["mapping_identifiers"]),
            )
            if key in seen:
                continue
            seen.add(key)
            for mapping in selected:
                if (
                    mapping.source_id != line["source"]
                    or mapping.external_identifier not in line["mapping_identifiers"]
                ):
                    continue
                retained = parent.mappings.get(
                    source_id=mapping.source_id,
                    external_identifier=mapping.external_identifier,
                    source_subject_kind=mapping.source_subject_kind,
                    identifier_scope=mapping.identifier_scope,
                    subject_id=mapping.subject_id,
                )
                selection |= Q(
                    observation__run__contract=parent, observation__mapping=retained
                )
    return selection


def forecast_inputs(
    contract,
    cutoff,
    *,
    mapping_ids=None,
    mode="operational",
    use="forecast_fitting",
    isolated_review=False,
    limit=10000,
):
    cutoff = aware_instant(
        cutoff.isoformat() if isinstance(cutoff, datetime) else cutoff
    )
    require(
        mode in {"operational", "retrospective_research"},
        "invalid forecast evidence mode",
    )
    require(type(limit) is int and 1 <= limit <= 10000, "invalid evidence limit")
    values = MetricValue.objects.filter(
        observation__run__status__in=["success", "partial"],
        observation__status="ok",
        observation__mapping__isnull=False,
    )
    values = values.filter(
        evidence_selection(
            contract, mapping_ids, cutoff if mode == "operational" else None
        )
    )
    if mode == "operational":
        # Observed/imported locally is a conservative availability boundary. Never
        # promote a date-only archive label into a precise availability instant.
        values = (
            values.filter(
                observation__observed_at__lte=cutoff,
                observation__run__completed_at__lte=cutoff,
                observation__mapping__reviewed_at__lte=cutoff,
                observation__run__contract__reviewed_at__lte=cutoff,
                observation__run__contract__created_at__lte=cutoff,
                observation__run__contract__taxonomy_version__created_at__lte=cutoff,
            )
            .filter(
                Q(observation__run__source_as_of__isnull=True)
                | Q(observation__run__source_as_of__lte=cutoff)
            )
            .filter(
                Q(observation__source_metadata__history_basis__isnull=True)
                | ~Q(
                    observation__source_metadata__history_basis="reconstructed_current_relationships"
                )
            )
        )
    if mode == "operational":
        for field in ("as_of_at", "window_end_at"):
            values = values.filter(
                Q(**{field + "__isnull": True}) | Q(**{field + "__lte": cutoff})
            )
        for field in ("as_of_date", "period_label_date"):
            values = values.filter(
                Q(**{field + "__isnull": True}) | Q(**{field + "__lte": cutoff.date()})
            )
    selected = list(
        values.select_related(
            "observation__run", "observation__mapping", "source_metric"
        )
        .defer("observation__run__raw_payload")
        .order_by("id")[: limit + 1]
    )
    require(
        len(selected) <= limit,
        "forecast input budget exceeded; select a smaller mapping cohort",
    )
    rows, datasets = [], set()
    for value in selected:
        observation, definition = value.observation, value.source_metric
        run = observation.run
        metadata = observation.source_metadata
        rows.append(
            {
                "value_id": value.pk,
                "observation_id": observation.pk,
                "run_id": str(run.pk),
                "mapping_id": str(observation.mapping_id),
                "subject_id": str(observation.mapping.subject_id),
                "source": run.source_id,
                "source_identifier": observation.source_identifier,
                "metric": definition.metric_key,
                "metric_definition_id": definition.pk,
                "value": str(value.integer_value)
                if value.integer_value is not None
                else value.float_value,
                "unit": definition.unit,
                "measurement_kind": definition.measurement_kind,
                "window_mode": definition.window_mode,
                "source_timezone": value.source_timezone,
                "temporal_status": value.temporal_status,
                "dimensions": observation.dimensions,
                "source_metadata": metadata,
                "first_local_observed_at": observation.observed_at.isoformat(),
                "import_completed_at": run.completed_at.isoformat(),
                "provider_as_of": run.source_as_of.isoformat()
                if run.source_as_of
                else None,
                "availability_basis": "first_local_observation_and_completed_import",
                "mapping_reviewed_at": observation.mapping.reviewed_at.isoformat(),
                "payload_sha256": run.payload_sha256,
                **{
                    field: getattr(value, field).isoformat()
                    if getattr(value, field)
                    else None
                    for field in (
                        "as_of_at",
                        "as_of_date",
                        "window_start_at",
                        "window_end_at",
                        "period_label_date",
                    )
                },
            }
        )
        datasets.add((run.source_id, metadata.get("dataset_id")))
    enforce_use(
        contract,
        {
            "lines": [{"source": s} for s, _ in datasets],
            "attributions": [{"source": s, "dataset_id": d} for s, d in datasets],
        },
        use,
        isolated_review=isolated_review,
    )
    return {
        "schema_version": 1,
        "contract_id": str(contract.pk),
        "contract_hash": contract.contract_hash,
        "taxonomy_version_id": str(contract.taxonomy_version_id),
        "cutoff": cutoff.isoformat(),
        "mode": mode,
        "not_past_known_evidence": mode != "operational",
        "revision_policy": "eligible immutable observations retained; consumer must pin selected IDs",
        "native_posts": "excluded: current post classifications cannot establish past knowledge",
        "values": rows,
    }
