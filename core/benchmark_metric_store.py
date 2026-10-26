"""Atomic numeric ingestion with explicit precision and retained retrieval evidence."""

from __future__ import annotations

import json
import math
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY, definition_snapshot
from core.benchmark_metric_timing import (
    TIME_FIELDS as TIME_FIELDS,  # noqa: PLC0414 - preserve existing import path
)
from core.benchmark_metric_timing import (
    aware_instant,
    calendar_window,
    native_date,
    timing_storage,
    value_times,
)
from core.measurement_taxonomy import digest, require
from core.models import (
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
    DataSource,
    MetricValue,
    SourceMetric,
)

SECRET_FIELDS = {
    "authorization",
    "api_key",
    "access_token",
    "headers",
    "cookie",
    "password",
    "secret",
}


def safe_payload(value, depth=0):
    require(depth <= 30, "payload_depth")
    if isinstance(value, dict):
        require(
            not SECRET_FIELDS.intersection(str(k).casefold() for k in value),
            "secret_fields_forbidden",
        )
        for item in value.values():
            safe_payload(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            safe_payload(item, depth + 1)
    elif isinstance(value, float):
        require(math.isfinite(value), "nonfinite_payload")
    elif value is not None:
        require(type(value) in (str, int, bool), "unsupported_payload_type")


def metric_request_coordinates(params):
    """Restrict persisted metric request options to existing typed scope fields."""
    require(isinstance(params, dict) and set(params) <= {"start_date", "end_date", "cursor"},
            "unsupported metric request option")
    require(
        ("start_date" in params) == ("end_date" in params),
        "metric request dates must be paired",
    )
    coordinates = {}
    if "start_date" in params:
        start, end = params["start_date"], params["end_date"]
        require(
            isinstance(start, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", start)
            and isinstance(end, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end),
            "metric request dates must be ISO calendar days",
        )
        coordinates["requested_start_date"] = date.fromisoformat(start)
        coordinates["requested_end_date"] = date.fromisoformat(end)
        require(
            coordinates["requested_start_date"] <= coordinates["requested_end_date"],
            "metric request dates are reversed",
        )
    if "cursor" in params:
        require(isinstance(params["cursor"], str) and params["cursor"],
                "metric request cursor must be nonempty text")
        coordinates["cursor"] = params["cursor"]
    return coordinates


def save_metric_request_coordinates(run, coordinates):
    if not coordinates:
        return
    ownership = {"contract_id": str(run.job.contract_id)}
    scope, _ = CollectionScopeRun.objects.get_or_create(
        run=run, scope_kind="metric_fetch", scope_key="source",
        defaults={"ownership": ownership},
    )
    require(scope.ownership == ownership, "metric request owner changed")
    for field, value in coordinates.items():
        require(getattr(scope, field) in (None, value), "metric request option changed")
        setattr(scope, field, value)
    scope.save(update_fields=list(coordinates))


def numeric_value(definition, value):
    if definition.value_kind == "integer":
        if definition.source_id == "openrouter":
            require(
                isinstance(value, str) and re.fullmatch(r"[0-9]{1,30}", value),
                "invalid token integer",
            )
        elif definition.source_id == "hf":
            require(type(value) is int and 0 <= value < 2**63, "invalid HF count")
        elif definition.source_id == "arena":
            require(
                type(value) in (int, float)
                and math.isfinite(value)
                and value == int(value)
                and 0 <= value <= 2**53 - 1,
                "invalid Arena count",
            )
        else:
            require(
                type(value) is int
                or (isinstance(value, str) and re.fullmatch(r"[0-9]{1,30}", value)),
                "invalid integer",
            )
        number = Decimal(value)
        require(
            number.is_finite()
            and number == number.to_integral_value()
            and 0 <= number < 10**30,
            "invalid numeric count",
        )
        return {"integer_value": number}
    require(
        type(value) in (int, float) and math.isfinite(value),
        "finite numeric score required",
    )
    if definition.quantity_form in {"count", "rank", "variance", "ratio"}:
        require(value >= 0, "negative quantity")
    return {"float_value": float(value)}


def native_rows(source, payload):
    """Translate native fields; generic storage validates all definitions afterwards."""
    require(payload.get("status") in {"ok", "partial"}, "source retrieval failed")
    rows = payload.get("rows")
    require(isinstance(rows, list) and len(rows) <= 100000, "invalid rows or row cap")
    if source == "openrouter":
        require(
            payload.get("meta", {}).get("version") == "v1", "unknown OpenRouter version"
        )
        counts = {}
        others = set()
        seen = set()
        for row in rows:
            key = (row["date"], row["model_permaslug"])
            require(key not in seen, "duplicate OpenRouter row")
            seen.add(key)
            require(
                row["model_permaslug"] == "other" or "/" in row["model_permaslug"],
                "invalid OpenRouter identity",
            )
            counts[row["date"]] = counts.get(row["date"], 0) + 1
            if row["model_permaslug"] == "other":
                others.add(row["date"])
        require(
            all(n - int(day in others) <= 50 for day, n in counts.items()),
            "incomplete OpenRouter source population",
        )
    for row in rows:
        metadata = dict(row.get("_source_metadata", {}))
        if source == "hf":
            out = {
                "source_identifier": row.get("account_identifier") or row["repo_id"],
                "source_subject_kind": "account"
                if "account_identifier" in row
                else "repository",
                "identifier_scope": row.get("account_kind", "model"),
                "source_metadata": metadata,
                "dimensions": {},
                "metrics": {},
            }
            if row.get("status") == "error":
                out.update(status="error", error_code="source_subject_error")
            else:
                raw = row["raw"]
                for wire, key in [
                    ("downloads", "downloads"),
                    ("downloadsAllTime", "downloads_all_time"),
                    ("likes", "likes"),
                    ("numFollowers", "followers"),
                    ("trendingScore", "trending_score"),
                    ("numModels", "models_count"),
                    ("numDatasets", "datasets_count"),
                    ("numSpaces", "spaces_count"),
                ]:
                    if wire in raw:
                        out["metrics"][key] = {"value": raw[wire]}
                if (
                    metadata.get("history_basis")
                    == "reconstructed_current_relationships"
                ):
                    require(
                        set(out["metrics"]) <= {"likes", "followers"},
                        "reconstruction only supports engagement",
                    )
                    require(
                        metadata.get("includes_removed_relationships") is False,
                        "reconstruction removal coverage required",
                    )
                    day = native_date(metadata["reconstruction_date"])
                    for point in out["metrics"].values():
                        point.update(
                            temporal_status="date_only", as_of_date=day.isoformat()
                        )
            if row.get("observed_at"):
                out["observed_at"] = row["observed_at"]
        elif source == "github":
            raw = row.get("raw", row)
            out = {
                "source_identifier": str(row.get("repository_id", raw["id"])),
                "source_subject_kind": "repository",
                "identifier_scope": "repository_id",
                "dimensions": row.get("dimensions", {}),
                "source_metadata": metadata,
                "metrics": {
                    key: {"value": raw[wire]}
                    for wire, key in (
                        ("stargazers_count", "stars"),
                        ("forks_count", "forks"),
                        ("open_issues_count", "open_issues"),
                        ("subscribers_count", "subscribers"),
                        ("download_count", "asset_downloads"),
                    )
                    if wire in raw
                },
            }
            if "account_identifier" in row:
                out.update(
                    source_identifier=row["account_identifier"],
                    source_subject_kind="account",
                    identifier_scope=row.get("account_kind", "unknown"),
                    metrics={
                        key: {"value": raw[key]}
                        for key in ("followers", "following", "public_repos")
                        if key in raw
                    },
                )
            if "size" in raw and "account_identifier" not in row:
                size_key = (
                    "asset_size_bytes"
                    if "asset_id" in out["dimensions"]
                    else "repository_size_kb"
                )
                out["metrics"][size_key] = {"value": raw["size"]}
            if row.get("observed_at"):
                out["observed_at"] = row["observed_at"]
        elif source == "openrouter":
            day = row["date"]
            start, end = calendar_window(day, "UTC")
            out = {
                "source_identifier": row["model_permaslug"],
                "source_subject_kind": "aggregate"
                if row["model_permaslug"] == "other"
                else "model",
                "dimensions": {"date": day},
                "source_metadata": metadata,
                "metrics": {
                    "total_tokens": {
                        "value": row["total_tokens"],
                        "temporal_status": "exact",
                        "window_start_at": start,
                        "window_end_at": end,
                        "period_label_date": day,
                    }
                },
            }
        elif source == "opencode":
            out = {
                "source_identifier": row["model_id"],
                "source_subject_kind": "model",
                "dimensions": {},
                "source_metadata": metadata,
                "metrics": {},
            }
            if row.get("status") == "error":
                out.update(status="error", error_code="source_subject_error")
            else:
                label = native_date(row["date"])
                revision = aware_instant(metadata["updated_at"])
                require(label <= revision.date(), "OpenCode future row")
                partial = label == revision.date()
                require(
                    metadata["period_status"]
                    == ("partial" if partial else "completed"),
                    "OpenCode period mismatch",
                )
                start, end = calendar_window(label.isoformat(), "UTC")
                metadata["nominal_window_end_at"] = end.isoformat()
                out["dimensions"] = {"date": label.isoformat()}
                for wire, metric in (
                    ("tokens", "tokens"),
                    ("uniqueUsers", "unique_users"),
                    ("sessions", "sessions"),
                ):
                    if wire in row:
                        require(
                            type(row[wire]) is int and 0 <= row[wire] < 10**30,
                            "invalid OpenCode count",
                        )
                        out["metrics"][metric] = {
                            "value": row[wire],
                            "temporal_status": "date_only" if partial else "exact",
                            "window_start_at": start,
                            "window_end_at": None if partial else end,
                            "period_label_date": label.isoformat(),
                        }
                semantic = {
                    "model_id": row["model_id"],
                    "date": label.isoformat(),
                    "period_status": metadata["period_status"],
                    "scope": metadata.get("traffic_scope"),
                    "values": {k: v["value"] for k, v in out["metrics"].items()},
                }
                metadata["row_semantic_hash"] = digest(semantic)
        elif source == "arena":
            metadata["publication_complete"] = payload.get("coverage") in {
                "latest_publication_only",
                "publication_window",
            }
            day = row["leaderboard_publish_date"]
            require(row["category"] == "overall", "Arena category mismatch")
            config = payload.get("config")
            require(
                config in {"text", "text_style_control", "agent"},
                "Arena configuration mismatch",
            )
            if config == "agent":
                row = {
                    **row,
                    **{
                        key: row[wire]
                        for key, wire in (
                            ("agent_score", "score"),
                            ("agent_score_ci_lower", "score_ci_lower"),
                            ("agent_score_ci_upper", "score_ci_upper"),
                        )
                        if wire in row
                    },
                }
            out = {
                "source_identifier": row["model_name"],
                "source_subject_kind": "model",
                "dimensions": {"category": "overall", "config": config},
                "published_date": day,
                "publication_precision": "date",
                "source_metadata": metadata,
                "metrics": {
                    key: {
                        "value": row[key],
                        "temporal_status": "date_only",
                        "as_of_date": day,
                    }
                    for key in (
                        (
                            "agent_score",
                            "agent_score_ci_lower",
                            "agent_score_ci_upper",
                            "observation_count",
                            "session_count",
                            "rank",
                        )
                        if config == "agent"
                        else (
                            "rating",
                            "rating_lower",
                            "rating_upper",
                            "vote_count",
                            "rank",
                            "variance",
                        )
                    )
                    if row.get(key) is not None
                },
            }
            if row.get("rating_lower") is not None:
                require(row["rating_lower"] <= row["rating"], "Arena interval mismatch")
            if row.get("rating_upper") is not None:
                require(row["rating"] <= row["rating_upper"], "Arena interval mismatch")
        else:
            raise ValueError("unsupported native adapter")
        if source in {"hf", "github"} and row.get("status") != "error":
            from core.benchmark_metric_timing import native_origin

            out["native_created_at"] = native_origin(row.get("raw", row))
        yield out


@contextmanager
def collection_lock(contract, source):
    key = int(digest(["benchmark-metrics-v1", str(contract.pk), source])[:15], 16)
    with connection.cursor() as c:
        c.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = c.fetchone()[0]
    require(acquired, "metric collection is already running")
    try:
        yield
    finally:
        with connection.cursor() as c:
            c.execute("SELECT pg_advisory_unlock(%s)", [key])


def prepare_rows(contract, source, payload, *, adapter=None):
    settings = contract.source_configuration[source]
    statistics = settings.get("eligibility_policy") == SOURCE_STATISTICS_POLICY
    if source == "arena":
        require(
            payload.get("config") == settings.get("config", "text_style_control"),
            "Arena contract configuration mismatch",
        )
    definitions = {
        obj.metric_key: obj
        for obj in SourceMetric.objects.filter(
            pk__in=[row["id"] for row in settings["definitions"]]
        )
    }
    require(
        len(definitions) == len(settings["definitions"]), "missing pinned definition"
    )
    for frozen in settings["definitions"]:
        require(
            definition_snapshot(definitions[frozen["metric_key"]]) == frozen,
            "pinned definition changed",
        )
    mappings = {
        (m.source_subject_kind, m.identifier_scope_code, m.normalized_identifier): m
        for m in contract.mappings.filter(purpose="metric", source_id=source).select_related("identifier_scope")
    }
    required = {key for key, obj in definitions.items() if obj.required}
    result = []
    seen = {}
    from core.benchmark_metric_timing import catalog_origins, reported_times

    rows = list(adapter(payload) if adapter else native_rows(source, payload))
    origins = (
        catalog_origins([row["source_identifier"] for row in rows])
        if source == "hf" and "downloads_all_time" in definitions
        else {}
    )
    retained_clocks = (
        {
            row["observation_key"]: row
            for row in CollectionObservation.objects.filter(
                observation_key__in=[
                    row["projection_key"] for row in rows if row.get("projection_key")
                ],
                source_metadata__projection_kind=SOURCE_STATISTICS_POLICY,
            ).values("observation_key", "observed_at", "source_metadata")
        }
        if statistics
        else {}
    )
    for row in rows:
        identity = row["source_identifier"]
        kind = row["source_subject_kind"]
        scope = row.get("identifier_scope", "")
        require(
            isinstance(identity, str)
            and 0 < len(identity) <= 256
            and identity == identity.strip(),
            "invalid subject identifier",
        )
        mapping = mappings.get(
            (kind, scope, identity.casefold() if source == "hf" else identity)
        )
        if statistics and mapping:
            from core.source_metric_projection import validate_statistics_mapping

            validate_statistics_mapping(
                mapping.subject,
                {
                    "external_identifier": mapping.external_identifier,
                    "source_subject_kind": mapping.source_subject_kind,
                    "publisher_account_key": str(mapping.publisher_account_id),
                    "identifier_metadata": mapping.identifier_metadata,
                },
                source,
                contract.taxonomy_version,
            )
        if (
            statistics
            and mapping
            and mapping.subject.subject_kind == "product"
            and mapping.identifier_metadata.get("role") != "dedicated_model"
        ):
            mapping = None
        metadata = dict(row.get("source_metadata", {}))
        dimensions = row.get("dimensions", {})
        key = digest(
            [
                kind,
                scope,
                identity,
                dimensions,
                row.get("published_at"),
                row.get("published_date"),
                metadata.get("archive_snapshot_date"),
                metadata.get("reconstruction_date"),
                metadata.get("history_basis"),
                metadata.get("immutable_revision"),
            ]
        )
        if statistics and row.get("projection_key"):
            key = row["projection_key"]
            require(re.fullmatch(r"[0-9a-f]{64}", key), "invalid projection key")
        # A repeated exact row is one observation; conflicting same-context rows fail.
        fingerprint = digest(
            {k: v for k, v in row.items() if k not in {"observed_at", "metrics"}}
            | {
                "metrics": {
                    k: {
                        f: (v.isoformat() if isinstance(v, (datetime, date)) else v)
                        for f, v in point.items()
                    }
                    for k, point in row.get("metrics", {}).items()
                }
            }
        )
        if key in seen:
            require(seen[key] == fingerprint, "conflicting duplicate source row")
            continue
        seen[key] = fingerprint
        observation = {
            "mapping": mapping,
            "source_identifier": identity,
            "source_subject_kind": kind,
            "observation_key": key,
            "dimensions": dimensions,
            "source_metadata": metadata,
            "status": row.get("status", "ok"),
            "observed_at": aware_instant(row.get("observed_at") or timezone.now()),
            "publication_precision": row.get("publication_precision", "unknown"),
            "published_at": aware_instant(row["published_at"])
            if row.get("published_at")
            else None,
            "published_date": native_date(row["published_date"])
            if row.get("published_date")
            else None,
            "error_code": row.get("error_code"),
        }
        values = []
        try:
            if observation["status"] == "ok":
                applicable_required = set() if statistics else required
                if source == "hf" and (
                    kind == "account"
                    or metadata.get("history_basis")
                    == "reconstructed_current_relationships"
                ):
                    applicable_required = required - {"downloads", "downloads_all_time"}
                require(
                    applicable_required <= row.get("metrics", {}).keys(),
                    "required metric absent",
                )
                for metric, point in row.get("metrics", {}).items():
                    if metric not in definitions:
                        continue
                    definition = definitions[metric]
                    try:
                        timing_context = observation
                        retained = retained_clocks.get(key)
                        if retained:
                            timing_context = {
                                **observation,
                                "observed_at": retained["observed_at"],
                                "source_metadata": {
                                    **metadata,
                                    "original_retrieved_at": retained[
                                        "source_metadata"
                                    ].get("original_retrieved_at"),
                                },
                            }
                        point, basis = reported_times(
                            definition,
                            point,
                            timing_context,
                            native_created=row.get("native_created_at"),
                            catalog_created=origins.get(identity.casefold()),
                        )
                        if basis:
                            metadata.setdefault(
                                "reported_time",
                                {"policy": "reported-time-v1", "metrics": {}},
                            )["metrics"][metric] = basis
                        value = dict(
                            source_metric=definition,
                            **numeric_value(definition, point["value"]),
                            **value_times(definition, point),
                        )
                        from core.collection_resources import metric_time_provenance

                        value.update(metric_time_provenance(definition, point, basis))
                    except (ValueError, TypeError, KeyError, OverflowError) as exc:
                        if not statistics:
                            raise
                        metadata.setdefault("metric_rejections", []).append(
                            {"metric": metric, "reason": str(exc)}
                        )
                        continue
                    values.append(value)
            else:
                require(
                    observation["status"] == "error" and observation["error_code"],
                    "invalid observation error",
                )
        except (ValueError, TypeError, KeyError):
            if source != "hf":
                raise
            observation.update(status="error", error_code="invalid_subject_data")
            values = []
        if statistics:
            observation.update(
                resource_key=row.get("resource_key"),
                product_id=(
                    mapping.subject.product.pk
                    if mapping and mapping.subject.subject_kind == "product"
                    else None
                ),
            )
            metadata["native_only"] = (
                mapping is None or mapping.subject.subject_kind != "product"
            )
        result.append((observation, values))
    return result


@transaction.atomic
def commit_prepared_rows(run, prepared, *, reuse_snapshots=False):
    """Commit validated rows inside the caller's source lock and live claim fence.

    Legacy imports keep per-run observations. Statistics use a DB-enforced key
    across jobs and never change the original observation's owning run.
    """
    require(
        run.job.purpose == "metric"
        and run.job.contract_id is not None
        and run.status == "running",
        "active metric-purpose run required",
    )
    observations, reused, pending_values = [], [], []
    if not reuse_snapshots:
        observations = CollectionObservation.objects.bulk_create(
            [CollectionObservation(run=run, **data) for data, _ in prepared],
            batch_size=1000,
        )
    else:
        for data, values in prepared:
            require(
                data["source_metadata"].get("projection_kind")
                == SOURCE_STATISTICS_POLICY,
                "snapshot reuse requires source statistics",
            )
            observation, created = (
                CollectionObservation.objects.select_related("run__job")
                .defer("run__raw_payload", "run__job__definition")
                .get_or_create(
                    observation_key=data["observation_key"],
                    source_metadata__projection_kind=SOURCE_STATISTICS_POLICY,
                    defaults={"run": run, **data},
                )
            )
            if not created:
                require(
                    observation.run.job.contract_id == run.job.contract_id
                    and observation.run.job.source_id == run.job.source_id,
                    "projection lineage conflict",
                )
                for field in (
                    "mapping_id",
                    "product_id",
                    "source_identifier",
                    "source_subject_kind",
                    "dimensions",
                    "published_at",
                    "published_date",
                    "publication_precision",
                ):
                    expected = (
                        data.get("mapping").pk
                        if field == "mapping_id" and data.get("mapping")
                        else data.get(field)
                    )
                    require(
                        getattr(observation, field) == expected,
                        "immutable snapshot conflict: " + field,
                    )
                if data["source_metadata"].get("snapshot_kind") == "capture":
                    require(
                        observation.observed_at == data["observed_at"],
                        "immutable snapshot clock conflict",
                    )
                require(
                    observation.source_metadata.get("clocks")
                    == data["source_metadata"].get("clocks"),
                    "immutable snapshot clock conflict",
                )
                reused.append(observation.pk)
            observations.append(observation)
    for observation, (_, values) in zip(observations, prepared, strict=True):
        existing = (
            {v.source_metric_id: v for v in observation.values.all()}
            if reuse_snapshots
            else {}
        )
        for value in values:
            previous = existing.get(value["source_metric"].pk)
            if previous:
                for field, expected in value.items():
                    if field == "source_metric":
                        actual, expected = previous.source_metric_id, expected.pk
                    elif field == "source_timezone":
                        actual = previous.source_timezone_reference_id or "unknown"
                    else:
                        actual = getattr(previous, field)
                    require(
                        actual == expected,
                        "immutable numeric snapshot conflict: " + field,
                    )
            else:
                pending_values.append(MetricValue(observation=observation, **timing_storage(value)))
    MetricValue.objects.bulk_create(pending_values, batch_size=1000)
    from core.collection_resources import attach_numeric_evidence

    attach_numeric_evidence(
        run,
        observations,
        prepared,
        reused_ids=reused,
        supplemented_ids={v.observation_id for v in pending_values} & set(reused),
    )
    from core.collection_capture import attach_metric_requests

    attach_metric_requests(run, observations)
    return observations, {
        "reused_observation_ids": reused,
        "written_values": len(pending_values),
        "written_observations": len(observations) - len(reused),
    }


def record_arena_publications(run, dates):
    """Keep a publication occurrence even when no selected model has a row."""
    require(run.observed_at is not None, "publication observation time required")
    inserted = 0
    for day in dates:
        published_date = date.fromisoformat(day)
        marker, created = CollectionObservation.objects.get_or_create(
            run=run,
            observation_key=digest(["arena-publication-v1", str(run.pk), day]),
            defaults={
                "source_identifier": "arena:publication",
                "source_subject_kind": "aggregate",
                "observed_at": run.observed_at,
                "published_date": published_date,
                "publication_precision": "date",
                "observation_kind": "publication_marker",
                "source_dataset": run.source_dataset,
                "publication_complete": True,
                "dimensions": {"kind": "publication_marker"},
                "source_metadata": {"publication_complete": True},
            },
        )
        require(
            marker.source_identifier == "arena:publication"
            and marker.source_subject_kind == "aggregate"
            and marker.observed_at == run.observed_at
            and marker.published_date == published_date
            and marker.publication_precision == "date"
            and marker.observation_kind == "publication_marker"
            and marker.publication_complete is True,
            "conflicting publication marker",
        )
        inserted += int(created)
    return inserted


def persist_source(
    contract,
    source,
    ingestion_key,
    payload=None,
    *,
    request_params=None,
    source_metadata=None,
    adapter=None,
    fetch=None,
    batch_id=None,
    isolated_review=False,
    claim=None,
    transport_budget=None,
):
    """Manual/import entry point; deterministic keys make replay a no-op."""
    require(source in contract.source_configuration, "source is outside contract")
    require(
        contract.source_configuration[source].get("eligibility_policy")
        != SOURCE_STATISTICS_POLICY,
        "source statistics require the shared evidence projector",
    )
    from core.benchmark_attribution import enforce_source_collection

    enforce_source_collection(
        contract,
        source,
        dataset=(source_metadata or {}).get("dataset_id"),
        isolated_review=isolated_review,
    )
    require(re.fullmatch(r"[0-9a-f]{64}", ingestion_key or ""), "invalid ingestion key")
    with collection_lock(contract, source):
        now = timezone.now()
        if claim is not None:
            from core.collection_state import fenced_run

            require(fetch is None, "claimed writer accepts fetched data only")
            with fenced_run(claim) as (job, run):
                require(
                    job.purpose == "metric"
                    and job.contract_id == contract.pk
                    and job.source_id == source,
                    "claimed metric identity mismatch",
                )
                require(
                    run.ingestion_key == ingestion_key,
                    "claimed ingestion identity mismatch",
                )
        existing = (
            CollectionRun.objects.filter(ingestion_key=ingestion_key).first()
            if claim is None
            else None
        )
        if existing:
            require(
                existing.job.contract_id == contract.pk
                and existing.job.source_id == source
                and existing.job.purpose == "metric",
                "ingestion key collision",
            )
            if existing.status != "running":
                require(
                    payload is None
                    or existing.payload_sha256 in (None, digest(payload)),
                    "replay payload changed",
                )
                return existing
            if existing.lease_expires_at > now:
                raise ValueError("run lease is active")
            existing.status = "aborted"
            existing.completed_at = now
            existing.error_code = "expired_lease"
            existing.save(update_fields=["status", "completed_at", "error_code"])
            return existing
        if claim is None:
            from core.collection_state import (
                claim_direct_run,
                fenced_run,
                register_direct_job,
            )

            limits = {
                "seconds": 600,
                "payload_bytes": 32 * 1024 * 1024,
                "requests": None,
                "request_budget_owner": "caller",
            }
            if transport_budget is not None:
                limits.update(
                    requests=transport_budget.remaining,
                    bytes=transport_budget.max_bytes,
                )
            job = register_direct_job(
                contract_id=contract.pk,
                source_id=source,
                purpose="metric",
                scope={},
                driver="persist_source",
                limits=limits,
            )
            run = CollectionRun(
                job=job,
                ingestion_key=ingestion_key,
                lease_expires_at=now + timedelta(minutes=10),
                source_url=DataSource.objects.get(pk=source).website_url,
                **({"batch_id": batch_id} if batch_id is not None else {}),
                selected_count=contract.mappings.filter(
                    purpose="metric", source_id=source
                ).count(),
            )
            claim = claim_direct_run(
                run,
                driver="persist_source",
                seconds=600,
                limits=limits,
            )
        else:
            run.selected_count = contract.mappings.filter(
                purpose="metric", source_id=source
            ).count()
            run.source_url = DataSource.objects.get(pk=source).website_url
            if batch_id is not None:
                run.batch_id = batch_id

        def save_result():
            if source_details:
                from core.collection_capture import archive_document

                run.source_metadata_archive = archive_document(
                    json.dumps(
                        source_details, sort_keys=True, separators=(",", ":"),
                        allow_nan=False,
                    ).encode(),
                    encoding="selected-json-canonical-v1",
                    capture_kind="source_metadata",
                )
            if transport_budget is not None:
                run.physical_bytes_received = transport_budget.total_bytes_read
            if claim.direct_driver == "persist_source":
                run.save()
                save_metric_request_coordinates(run, request_coordinates)
                return run
            from core.collection_state import finish_run

            status, error = run.status, run.error_code
            run.status, run.completed_at = "running", None
            run.save()
            result = finish_run(
                claim,
                status=status,
                request_count=run.request_count,
                selected_count=run.selected_count,
                success_count=run.success_count,
                error_code=error,
            )
            save_metric_request_coordinates(run, request_coordinates)
            return result

        request_coordinates = {}
        source_details = {}
        try:
            if fetch is not None:
                require(payload is None, "supply a payload or fetch, not both")
                if transport_budget is None:
                    payload = fetch()
                else:
                    from core.collection_capture import capture_budget

                    with capture_budget(
                        claim,
                        transport_budget,
                        scope_kind="metric_fetch",
                        scope_key="source",
                        ownership={"contract_id": str(contract.pk)},
                    ):
                        payload = fetch()
            safe_payload(payload)
            safe_payload(request_params or {})
            request_coordinates = metric_request_coordinates(request_params or {})
            safe_payload(source_metadata or {})
            require(isinstance(source_metadata or {}, dict), "source metadata must be an object")
            source_details = dict(source_metadata or {})
            from core.collection_datasets import resolve_dataset

            run.source_dataset = resolve_dataset(source, source_details)
            raw_hash = digest(payload)
            require(
                len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                <= 32 * 1024 * 1024,
                "payload byte budget exceeded",
            )
            from core.collection_capture import archive_document

            serialized_payload = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            run.payload_archive = archive_document(
                serialized_payload,
                encoding="selected-json-canonical-v1",
                capture_kind="selected_payload",
            )
            run.payload_sha256 = raw_hash
            run.observed_at = now
            run.direct_ingestion = (
                source_details.get("ingestion_mode") == "direct"
                if "ingestion_mode" in source_details else None
            )
            if source == "arena" and source_details.get("publication_dates"):
                dates = source_details["publication_dates"]
                require(
                    isinstance(dates, list) and len(dates) <= 366,
                    "publication date budget",
                )
                dates = sorted({native_date(d).isoformat() for d in dates})
                require(
                    payload.get("coverage")
                    in {"publication_window", "latest_publication_only"},
                    "unverified publication context",
                )
                require(
                    all(
                        r["leaderboard_publish_date"] in dates for r in payload["rows"]
                    ),
                    "publication context excludes rows",
                )
                source_details = {
                    **source_details,
                    "publication_start": dates[0],
                    "publication_end": dates[-1],
                }
            run.request_count = payload.get("request_count", 0)
            require(
                type(run.request_count) is int and run.request_count >= 0,
                "invalid request count",
            )
            if payload.get("as_of") and source == "openrouter":
                run.source_as_of = aware_instant(payload["as_of"])
            prepared = prepare_rows(contract, source, payload, adapter=adapter)
            retained_successful = set()
            if source == "opencode":
                from core.benchmark_opencode import prepare_revisions

                prepared, checks, retained_successful = prepare_revisions(
                    contract, prepared, payload
                )
                source_details["endpoint_checks"] = checks
                revisions = [
                    aware_instant(c["updated_at"])
                    for c in checks
                    if c.get("status") == "ok"
                ]
                run.source_as_of = max(revisions) if revisions else None
        except (ValueError, KeyError, TypeError, OverflowError):
            run.status = "failed"
            run.error_code = "invalid_source_data"
            run.completed_at = timezone.now()
            with fenced_run(claim):
                return save_result()

        with (
            transaction.atomic(),
            fenced_run(claim),
        ):
            successful = retained_successful
            errors = False
            observations, _ = commit_prepared_rows(run, prepared)
            if source == "arena" and source_details.get("publication_dates"):
                record_arena_publications(run, dates)
            for observation, (_, values) in zip(observations, prepared, strict=True):
                errors |= observation.status == "error"
                if observation.mapping_id and values:
                    successful.add(observation.mapping_id)
                if source == "opencode" and observation.status == "ok":
                    check = next(
                        c
                        for c in source_details["endpoint_checks"]
                        if c["source_identifier"] == observation.source_identifier
                    )
                    check["row_references"][observation.dimensions["date"]] = (
                        observation.pk
                    )
            if source == "opencode":
                from core.benchmark_opencode import record_endpoint_checks

                record_endpoint_checks(
                    run, source_details["endpoint_checks"], contract
                )
            run.success_count = len(successful)
            run.status = (
                "success"
                if not errors and run.success_count == run.selected_count
                else "partial"
                if successful
                or (prepared and not errors)
                or (
                    source == "arena"
                    and source_details.get("publication_dates")
                    and not errors
                )
                else "failed"
            )
            run.completed_at = timezone.now()
            result = save_result()
            if claim.direct_driver:
                from core.collection_state import complete_attempt

                complete_attempt(
                    claim, run, status=run.status, request_count=run.request_count
                )
        return result
