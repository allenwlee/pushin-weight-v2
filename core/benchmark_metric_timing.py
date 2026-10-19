"""Reported measurement timing; source event cutoffs remain separate evidence."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.measurement_taxonomy import require
from core.models import Product

POLICY = "reported-time-v1"
HF_CREATION_FLOOR = datetime(2022, 3, 2, 23, 29, 4, tzinfo=UTC)


TIME_FIELDS = (
    "as_of_at",
    "as_of_date",
    "window_start_at",
    "window_end_at",
    "period_label_date",
)


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
            reported = point.get("_reported_time", {})
            require(
                start is None
                or end is None
                or (status == "date_only" and reported.get("policy") == POLICY),
                "complete interval requires exact precision or reported date basis",
            )
        if status == "date_only":
            require(label is not None, "date-only flow needs native date")
            if start is not None and end is not None:
                reported = point.get("_reported_time", {})
                day_start, day_end = calendar_window(label.isoformat(), "UTC")
                if definition.source_id == "hf":
                    require(
                        reported.get("normalization")
                        == "UTC_report_day_exclusive_next_midnight"
                        and end == day_end,
                        "reported HF boundary basis mismatch",
                    )
                elif definition.source_id == "opencode":
                    require(
                        reported.get("basis") == "published_partial_update"
                        and reported.get("partial") is True
                        and start == day_start
                        and end < day_end,
                        "reported partial boundary basis mismatch",
                    )
                else:
                    raise ValueError("unsupported reported date interval")
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


def catalog_origins(identifiers):
    """Creation belongs to the HF repository, never to local first-seen time."""
    return {
        product.repo_id.casefold(): product.created_at
        for product in Product.objects.filter(
            repo_id__in=identifiers, publisher_account__data_source_id="hf"
        ).only("repo_id", "created_at")
    }


def native_origin(raw):
    return (
        raw.get("createdAt")
        or raw.get("created_at")
        or raw.get("raw", {}).get("createdAt")
        or raw.get("raw", {}).get("created_at")
    )


def verified_origin(native, catalog):
    try:
        native = aware_instant(native) if native else None
        catalog = aware_instant(catalog) if catalog else None
    except (ValueError, TypeError):
        return None, "invalid_repository_creation"
    if native and catalog and native != catalog:
        return None, "conflicting_repository_creation"
    origin = native or catalog
    if origin is None:
        return None, "missing_repository_creation"
    if origin <= HF_CREATION_FLOOR:
        return None, "creation_tracking_floor_or_earlier"
    return (
        origin,
        "native_repository_creation" if native else "catalog_repository_creation",
    )


def reported_times(
    definition, point, observation, *, native_created=None, catalog_created=None
):
    """Resolve only omitted timing. Return a new point and per-metric explanation."""
    source = definition.source_id
    metadata = observation.get("source_metadata", {})
    if source == "opencode":
        if (
            metadata.get("period_status") != "partial"
            or point.get("window_end_at") is not None
        ):
            return point, None
        start = aware_instant(point["window_start_at"])
        end = aware_instant(metadata["updated_at"])
        nominal = start + timedelta(days=1)
        if not start < end < nominal:
            return point, {
                "policy": POLICY,
                "unknowns": {"end": "partial_update_not_inside_day"},
            }
        basis = {
            "policy": POLICY,
            "basis": "published_partial_update",
            "precision": "instant",
            "partial": True,
            "unknowns": {},
        }
        return {
            **point,
            "window_end_at": end,
            "temporal_status": "date_only",
            "_reported_time": basis,
        }, basis
    if source not in {"hf", "github"}:
        return point, None
    if (
        definition.measurement_kind == "state"
        and point.get("temporal_status", "unknown") != "unknown"
    ):
        return point, None
    if (
        definition.measurement_kind == "flow"
        and point.get("window_start_at") is not None
        and point.get("window_end_at") is not None
    ):
        return point, None
    unknowns = {"provider_refresh_lag": "not_reported"}
    if definition.source_timezone == "unknown":
        unknowns["provider_timezone"] = "not_reported"
    snapshot = (
        metadata.get("numeric_snapshot_identity")
        or metadata.get("snapshot_identity")
        or {}
    )
    snapshot_day = snapshot.get("date") or snapshot.get("period")
    try:
        snapshot_day = native_date(snapshot_day).isoformat() if snapshot_day else None
    except (ValueError, TypeError):
        snapshot_day = None
    day = (
        observation.get("published_date")
        or metadata.get("archive_snapshot_date")
        or snapshot_day
    )
    published = observation.get("published_at")
    basis_name = (
        "publication_date"
        if observation.get("published_date")
        else "archive_snapshot_date"
        if metadata.get("archive_snapshot_date")
        else "published_snapshot_date"
    )
    if published:
        end = aware_instant(published)
        day = None
        basis_name = "publication_instant"
    elif day:
        day = native_date(day.isoformat() if hasattr(day, "isoformat") else day)
        _, end = calendar_window(day.isoformat(), "UTC")
    else:
        captured = metadata.get("original_retrieved_at") or observation.get(
            "observed_at"
        )
        if not captured:
            return point, {
                "policy": POLICY,
                "unknowns": {"end": "missing_publication_archive_and_capture"},
            }
        end = aware_instant(captured)
        basis_name = "original_capture_proxy"
    precision = "date" if day else "instant"
    basis = {
        "policy": POLICY,
        "basis": basis_name,
        "precision": precision,
        "unknowns": unknowns,
    }
    resolved = {**point}
    if definition.measurement_kind == "state":
        resolved.update(
            as_of_date=day.isoformat() if day else None,
            as_of_at=None if day else end,
            temporal_status="date_only" if day else "exact",
        )
    else:
        label = day or end.date()
        start = None
        if (
            definition.window_mode == "rolling"
            and source == "hf"
            and definition.window_unit == "day"
            and definition.window_amount == 30
        ):
            start = end - timedelta(days=30)
            basis["start_basis"] = "reported_30_day_interval"
            unknowns["provider_window_alignment"] = "not_reported"
        elif definition.window_mode == "since_origin" and source == "hf":
            start, origin_basis = verified_origin(native_created, catalog_created)
            if start and start >= end:
                start, origin_basis = (
                    None,
                    "repository_creation_not_before_reported_end",
                )
            if start:
                basis["start_basis"] = origin_basis
            else:
                unknowns["start"] = origin_basis
        else:
            unknowns["start"] = "unsupported_reported_interval"
        if day:
            basis["normalization"] = "UTC_report_day_exclusive_next_midnight"
            basis["native_report_date"] = day.isoformat()
            basis["archive_timezone"] = metadata.get(
                "archive_snapshot_timezone", "unknown"
            )
        resolved.update(
            window_start_at=start,
            window_end_at=end,
            period_label_date=label.isoformat(),
            temporal_status="date_only" if day else "exact" if start else "unknown",
        )
    resolved["_reported_time"] = basis
    return resolved, basis
