"""Atomic numeric ingestion with explicit precision and retained retrieval evidence."""

from __future__ import annotations

import json
import math
import re
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import connection, transaction
from django.utils import timezone

from core.benchmark_metric_identity import definition_snapshot
from core.measurement_taxonomy import digest, require
from core.models import (
    DataSource,
    MetricCollectionRun,
    MetricObservation,
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
TIME_FIELDS = (
    "as_of_at",
    "as_of_date",
    "window_start_at",
    "window_end_at",
    "period_label_date",
)


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


def aware_instant(value):
    try:
        result = datetime.fromisoformat(value) if isinstance(value, str) else value
    except ValueError as exc:
        raise ValueError("invalid instant") from exc
    require(
        isinstance(result, datetime)
        and result.tzinfo is not None
        and result.utcoffset() is not None,
        "timezone offset required",
    )
    return result.astimezone(UTC)


def native_date(value):
    require(isinstance(value, str), "native date string required")
    parsed = date.fromisoformat(value)
    require(parsed.isoformat() == value, "canonical date required")
    return parsed


def calendar_window(label, zone, amount=1):
    require(
        type(amount) is int and 0 < amount <= 366,
        "calendar whole-day duration required",
    )
    tz = ZoneInfo(zone)
    first = native_date(label)
    instants = []
    for day in (first, first + timedelta(days=amount)):
        local = datetime.combine(day, time.min, tzinfo=tz)
        require(
            local.utcoffset() == local.replace(fold=1).utcoffset(),
            "ambiguous local midnight",
        )
        instant = local.astimezone(UTC)
        require(
            instant.astimezone(tz).replace(tzinfo=None) == local.replace(tzinfo=None),
            "nonexistent local midnight",
        )
        instants.append(instant)
    return tuple(instants)


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


def value_times(definition, point):
    status = point.get("temporal_status", "unknown")
    zone = point.get("source_timezone", definition.source_timezone)
    require(
        zone == definition.source_timezone, "timezone differs from pinned definition"
    )
    result = {field: point.get(field) for field in TIME_FIELDS}
    for field, value in result.items():
        if value is not None:
            result[field] = (
                aware_instant(value) if field.endswith("_at") else native_date(value)
            )
    a, d, start, end, label = [result[f] for f in TIME_FIELDS]
    require(status in {"exact", "date_only", "unknown"}, "invalid temporal status")
    if definition.measurement_kind == "state":
        require(
            start is None and end is None and label is None,
            "state cannot have flow window",
        )
        require(
            (status == "exact" and a is not None and d is None)
            or (status == "date_only" and a is None and d is not None)
            or (status == "unknown" and a is None and d is None),
            "state precision mismatch",
        )
    else:
        require(a is None and d is None, "flow cannot have state instant")
        if start is not None and end is not None:
            require(end > start, "invalid window order")
        if status == "exact":
            require(
                start is not None and end is not None,
                "exact flow needs both boundaries",
            )
        else:
            require(
                start is None or end is None,
                "complete interval requires exact precision",
            )
        if status == "date_only":
            require(label is not None, "date-only flow needs native date")
        if definition.window_mode == "calendar" and status == "exact":
            require(label is not None, "calendar label required")
            require(
                definition.window_unit == "day"
                and definition.window_duration_basis == "calendar"
                and definition.window_amount == int(definition.window_amount),
                "unverified calendar basis",
            )
            expected = calendar_window(
                label.isoformat(), zone, int(definition.window_amount)
            )
            require((start, end) == expected, "calendar bounds mismatch")
    return dict(result, temporal_status=status, source_timezone=zone)


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
        elif source == "arena":
            metadata["publication_complete"] = payload.get("coverage") in {
                "latest_publication_only",
                "publication_window",
            }
            day = row["leaderboard_publish_date"]
            require(row["category"] == "overall", "Arena category mismatch")
            config = payload.get("config")
            require(
                config in {"text", "text_style_control"}, "Arena configuration mismatch"
            )
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
                        "rating",
                        "rating_lower",
                        "rating_upper",
                        "vote_count",
                        "rank",
                        "variance",
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
        (m.source_subject_kind, m.identifier_scope, m.normalized_identifier): m
        for m in contract.mappings.filter(source_id=source)
    }
    required = {key for key, obj in definitions.items() if obj.required}
    result = []
    seen = {}
    for row in adapter(payload) if adapter else native_rows(source, payload):
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
        metadata = row.get("source_metadata", {})
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
                applicable_required = required
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
                    values.append(
                        dict(
                            source_metric=definition,
                            **numeric_value(definition, point["value"]),
                            **value_times(definition, point),
                        )
                    )
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
        result.append((observation, values))
    return result


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
):
    """Manual/import entry point; deterministic keys make replay a no-op."""
    require(source in contract.source_configuration, "source is outside contract")
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
        existing = MetricCollectionRun.objects.filter(
            ingestion_key=ingestion_key
        ).first()
        if existing:
            require(
                existing.contract_id == contract.pk and existing.source_id == source,
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
        run = MetricCollectionRun.objects.create(
            contract=contract,
            source_id=source,
            ingestion_key=ingestion_key,
            lease_expires_at=now + timedelta(minutes=10),
            source_url=DataSource.objects.get(pk=source).website_url,
            **({"batch_id": batch_id} if batch_id is not None else {}),
            selected_count=contract.mappings.filter(source_id=source).count(),
        )
        try:
            if fetch is not None:
                require(payload is None, "supply a payload or fetch, not both")
                payload = fetch()
            safe_payload(payload)
            safe_payload(request_params or {})
            safe_payload(source_metadata or {})
            raw_hash = digest(payload)
            require(
                len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                <= 32 * 1024 * 1024,
                "payload byte budget exceeded",
            )
            run.raw_payload = payload
            run.payload_sha256 = raw_hash
            run.observed_at = now
            run.request_params = request_params or {}
            run.source_metadata = source_metadata or {}
            if source == "arena" and run.source_metadata.get("publication_dates"):
                dates = run.source_metadata["publication_dates"]
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
                run.source_metadata = {
                    **run.source_metadata,
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
        except (ValueError, KeyError, TypeError, OverflowError):
            run.status = "failed"
            run.error_code = "invalid_source_data"
            run.completed_at = timezone.now()
            run.save()
            return run
        with transaction.atomic():
            successful = set()
            errors = False
            observations = MetricObservation.objects.bulk_create(
                [MetricObservation(run=run, **data) for data, _ in prepared],
                batch_size=1000,
            )
            MetricValue.objects.bulk_create(
                [
                    MetricValue(observation=observation, **value)
                    for observation, (_, values) in zip(
                        observations, prepared, strict=True
                    )
                    for value in values
                ],
                batch_size=1000,
            )
            for observation, (_, values) in zip(observations, prepared, strict=True):
                errors |= observation.status == "error"
                if observation.mapping_id and values:
                    successful.add(observation.mapping_id)
            run.success_count = len(successful)
            run.status = (
                "success"
                if not errors and run.success_count == run.selected_count
                else "partial"
                if successful
                or (prepared and not errors)
                or (
                    source == "arena"
                    and run.source_metadata.get("publication_dates")
                    and not errors
                )
                else "failed"
            )
            run.completed_at = timezone.now()
            run.save()
        return run
