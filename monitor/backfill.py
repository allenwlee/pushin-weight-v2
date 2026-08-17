"""Planning primitives for durable, date-bounded harvest recovery.

This module is deliberately provider-free. It turns an operator range into
current harvester call identities and durable work, but it never creates a
TwitterAPI client or mutates the live cursor ledger.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import transaction

from x_monitor.config import Config
from x_monitor.query_plan import PlannedCall


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="seconds")


def parse_utc(value: str) -> datetime:
    """Parse an ISO date/time and normalize it to aware UTC."""

    try:
        parsed = datetime.fromisoformat(value.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError(
            f"Invalid UTC timestamp {value!r}; use YYYY-MM-DD or an ISO date-time."
        ) from exc
    return _as_utc(parsed)


def validate_range(
    since: datetime,
    until: datetime,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return a normalized historical half-open range or raise."""

    since = _as_utc(since)
    until = _as_utc(until)
    now = _as_utc(now or datetime.now(UTC))
    if since >= until:
        raise ValueError("--since must be earlier than --until")
    if until > now:
        raise ValueError("--until cannot be in the future")
    return since, until


@dataclass(frozen=True, order=True)
class CoverageInterval:
    since: datetime
    until: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "since", _as_utc(self.since))
        object.__setattr__(self, "until", _as_utc(self.until))
        if self.since >= self.until:
            raise ValueError("coverage interval must be increasing")

    def as_dict(self) -> dict[str, str]:
        return {"since": _iso(self.since), "until": _iso(self.until)}

    @classmethod
    def from_dict(cls, value: dict[str, str]) -> CoverageInterval:
        return cls(parse_utc(value["since"]), parse_utc(value["until"]))


def _bucket_floor(value: datetime, bucket: timedelta) -> datetime:
    epoch = int(_as_utc(value).timestamp())
    bucket_seconds = int(bucket.total_seconds())
    return datetime.fromtimestamp(epoch - (epoch % bucket_seconds), tz=UTC)


def _bucket_ceil(value: datetime, bucket: timedelta) -> datetime:
    floor = _bucket_floor(value, bucket)
    return floor if floor == _as_utc(value) else floor + bucket


def detect_zero_coverage_gaps(
    timestamps: Iterable[datetime],
    *,
    since: datetime,
    until: datetime,
    bucket_minutes: int = 15,
    min_gap_minutes: int = 60,
) -> list[CoverageInterval]:
    """Return merged runs of fully covered buckets containing zero posts.

    This is intentionally conservative evidence: a bucket containing even one
    post is not selected, so partial outages remain an explicit-range task.
    Partial buckets at either edge of the requested range are ignored.
    """

    if bucket_minutes <= 0:
        raise ValueError("bucket_minutes must be positive")
    if min_gap_minutes <= 0:
        raise ValueError("min_gap_minutes must be positive")
    since = _as_utc(since)
    until = _as_utc(until)
    if since >= until:
        raise ValueError("since must be earlier than until")

    bucket = timedelta(minutes=bucket_minutes)
    first_start = _bucket_ceil(since, bucket)
    last_end = _bucket_floor(until, bucket)
    if first_start >= last_end:
        return []

    occupied = {
        _bucket_floor(ts, bucket)
        for ts in timestamps
        if first_start <= _as_utc(ts) < last_end
    }
    minimum = timedelta(minutes=min_gap_minutes)
    gaps: list[CoverageInterval] = []
    run_start: datetime | None = None
    cursor = first_start
    while cursor < last_end:
        if cursor not in occupied:
            run_start = run_start or cursor
        elif run_start is not None:
            if cursor - run_start >= minimum:
                gaps.append(CoverageInterval(run_start, cursor))
            run_start = None
        cursor += bucket
    if run_start is not None and last_end - run_start >= minimum:
        gaps.append(CoverageInterval(run_start, last_end))
    return gaps


def normalize_brand_filter(brands: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(sorted({brand.strip() for brand in brands or () if brand.strip()}))


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _call_identity(call: PlannedCall) -> dict[str, str]:
    return {
        "brand_id": call.brand_id,
        "call_id": call.call_id,
        "call_kind": call.call_kind,
        "bucket": call.bucket or "",
        "query_id": call.call_id,
    }


def make_plan_signature(
    calls: Sequence[PlannedCall], *, brand_filter: Iterable[str] | None
) -> str:
    planned = [
        {**_call_identity(call), "query_string": call.query_string} for call in calls
    ]
    planned.sort(
        key=lambda item: (
            item["call_id"],
            item["call_kind"],
            item["brand_id"],
            item["bucket"],
            item["query_id"],
        )
    )
    return _digest(
        {
            "brand_filter": normalize_brand_filter(brand_filter),
            "calls": planned,
        }
    )


def make_job_key(
    *,
    since: datetime,
    until: datetime,
    selection_mode: str,
    selection_params: dict,
    brand_filter: Iterable[str] | None,
) -> str:
    return _digest(
        {
            "since": _iso(since),
            "until": _iso(until),
            "selection_mode": selection_mode,
            "selection_params": selection_params,
            "brand_filter": normalize_brand_filter(brand_filter),
        }
    )


@dataclass(frozen=True)
class BackfillPlan:
    key: str
    since: datetime
    until: datetime
    selection_mode: str
    selection_params: dict
    intervals: tuple[CoverageInterval, ...]
    calls: tuple[PlannedCall, ...]
    brand_filter: tuple[str, ...]
    plan_signature: str

    @classmethod
    def create(
        cls,
        *,
        since: datetime,
        until: datetime,
        selection_mode: str,
        selection_params: dict,
        intervals: Sequence[CoverageInterval],
        calls: Sequence[PlannedCall],
        brand_filter: Iterable[str] | None,
    ) -> BackfillPlan:
        brands = normalize_brand_filter(brand_filter)
        return cls(
            key=make_job_key(
                since=since,
                until=until,
                selection_mode=selection_mode,
                selection_params=selection_params,
                brand_filter=brands,
            ),
            since=_as_utc(since),
            until=_as_utc(until),
            selection_mode=selection_mode,
            selection_params=selection_params,
            intervals=tuple(intervals),
            calls=tuple(calls),
            brand_filter=brands,
            plan_signature=make_plan_signature(calls, brand_filter=brands),
        )

    @property
    def work_rows(self) -> int:
        return len(self.intervals) * len(self.calls)


def build_plan(
    cfg: Config,
    *,
    since: datetime,
    until: datetime,
    detect_gaps: bool,
    bucket_minutes: int = 15,
    min_gap_minutes: int = 60,
    brand_filter: Iterable[str] | None = None,
    timestamps: Iterable[datetime] | None = None,
) -> BackfillPlan:
    """Build the same in-memory plan used by dry-run and execution."""

    from core.models import BackfillJob, Post
    from monitor.cycle import plan_calls_for_cycle

    since, until = validate_range(since, until)
    brands = normalize_brand_filter(brand_filter)
    calls = plan_calls_for_cycle(cfg, brand_filter=list(brands))
    if detect_gaps:
        if timestamps is None:
            timestamps = Post.objects.filter(
                created_at__gte=since,
                created_at__lt=until,
            ).values_list("created_at", flat=True)
        intervals = detect_zero_coverage_gaps(
            timestamps,
            since=since,
            until=until,
            bucket_minutes=bucket_minutes,
            min_gap_minutes=min_gap_minutes,
        )
        mode = BackfillJob.SelectionMode.DETECTED_GAPS
        params = {
            "bucket_minutes": bucket_minutes,
            "min_gap_minutes": min_gap_minutes,
        }
    else:
        intervals = [CoverageInterval(since, until)]
        mode = BackfillJob.SelectionMode.EXPLICIT
        params = {}
    return BackfillPlan.create(
        since=since,
        until=until,
        selection_mode=mode,
        selection_params=params,
        intervals=intervals,
        calls=calls,
        brand_filter=brands,
    )


def validate_job_plan(job, plan: BackfillPlan) -> None:
    """Refuse resume when stored identity no longer matches current planning."""

    expected = {
        "requested_since": plan.since,
        "requested_until": plan.until,
        "selection_mode": plan.selection_mode,
        "selection_params": plan.selection_params,
        "brand_filter": list(plan.brand_filter),
        "plan_signature": plan.plan_signature,
    }
    mismatches = [
        field for field, value in expected.items() if getattr(job, field) != value
    ]
    if mismatches:
        raise ValueError(
            "Existing backfill job no longer matches the current plan: "
            + ", ".join(mismatches)
        )


def persist_plan(plan: BackfillPlan):
    """Create or resume one durable job and idempotently seed its work rows."""

    from core.models import BackfillJob, HarvestBacklogWindow

    interval_json = [interval.as_dict() for interval in plan.intervals]
    with transaction.atomic():
        job, _created = BackfillJob.objects.get_or_create(
            key=plan.key,
            defaults={
                "requested_since": plan.since,
                "requested_until": plan.until,
                "selection_mode": plan.selection_mode,
                "selection_params": plan.selection_params,
                "selected_intervals": interval_json,
                "brand_filter": list(plan.brand_filter),
                "plan_signature": plan.plan_signature,
            },
        )
        job = BackfillJob.objects.select_for_update().get(pk=job.pk)
        validate_job_plan(job, plan)
        if job.state == BackfillJob.State.COMPLETED:
            return job

        # Stored intervals are authoritative on resume: posts inserted by an
        # earlier slice must not silently shrink a detected-gap recovery.
        for raw_interval in job.selected_intervals:
            interval = CoverageInterval.from_dict(raw_interval)
            for call in plan.calls:
                identity = _call_identity(call)
                HarvestBacklogWindow.objects.get_or_create(
                    backfill_job=job,
                    **identity,
                    remaining_since=interval.since,
                    remaining_until=interval.until,
                    defaults={
                        "original_since": interval.since,
                        "original_until": interval.until,
                        "reason_code": (
                            "backfill_detected_gap"
                            if plan.selection_mode
                            == BackfillJob.SelectionMode.DETECTED_GAPS
                            else "backfill_explicit"
                        ),
                    },
                )
        return job
