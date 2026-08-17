from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from x_monitor.config import load_config
from x_monitor.query_plan import PlannedCall

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 10, hour, minute, tzinfo=UTC)


def _call(
    query: str = "(list:123) min_faves:0",
    *,
    call_id: str = "A",
    call_kind: str = "account",
    brand_id: str = "*",
) -> PlannedCall:
    return PlannedCall(
        call_id=call_id,
        call_kind=call_kind,
        brand_id=brand_id,
        bucket=None,
        query_string=query,
        query_length=len(query),
    )


def test_parse_utc_accepts_minute_second_z_and_offset_forms():
    from monitor.backfill import parse_utc

    assert parse_utc("2026-08-10T10:30") == datetime(2026, 8, 10, 10, 30, tzinfo=UTC)
    assert parse_utc("2026-08-10T10:30:45Z") == datetime(
        2026, 8, 10, 10, 30, 45, tzinfo=UTC
    )
    assert parse_utc("2026-08-10T19:30:45+09:00") == datetime(
        2026, 8, 10, 10, 30, 45, tzinfo=UTC
    )
    assert parse_utc("2026-08-10") == datetime(2026, 8, 10, tzinfo=UTC)


@pytest.mark.parametrize("value", ["", "not-a-time", "2026-08-10T25:00"])
def test_parse_utc_rejects_invalid_values(value):
    from monitor.backfill import parse_utc

    with pytest.raises(ValueError, match="UTC timestamp"):
        parse_utc(value)


def test_validate_range_rejects_reversed_equal_and_future_ranges():
    from monitor.backfill import validate_range

    now = _dt(12)
    for since, until in [(_dt(2), _dt(2)), (_dt(3), _dt(2)), (_dt(2), _dt(13))]:
        with pytest.raises(ValueError):
            validate_range(since, until, now=now)

    assert validate_range(_dt(2), _dt(3), now=now) == (_dt(2), _dt(3))


def test_gap_selector_merges_only_zero_runs_at_or_above_threshold():
    from monitor.backfill import CoverageInterval, detect_zero_coverage_gaps

    # Every 15-minute bucket has a post except the one-hour 01:00-02:00 run
    # and a short 02:45-03:15 run. Only the long run is recoverable by default.
    occupied = [
        _dt(0, 1),
        _dt(0, 16),
        _dt(0, 31),
        _dt(0, 46),
        _dt(2, 1),
        _dt(2, 16),
        _dt(2, 31),
        _dt(3, 16),
        _dt(3, 31),
        _dt(3, 46),
    ]

    assert detect_zero_coverage_gaps(
        occupied,
        since=_dt(0),
        until=_dt(4),
        bucket_minutes=15,
        min_gap_minutes=60,
    ) == [CoverageInterval(_dt(1), _dt(2))]


def test_gap_selector_handles_leading_trailing_and_partial_range_buckets():
    from monitor.backfill import CoverageInterval, detect_zero_coverage_gaps

    occupied = [_dt(1, 16), _dt(1, 31), _dt(1, 46), _dt(2, 1), _dt(2, 16)]

    assert detect_zero_coverage_gaps(
        occupied,
        since=_dt(0, 7),
        until=_dt(3, 52),
        bucket_minutes=15,
        min_gap_minutes=60,
    ) == [
        CoverageInterval(_dt(0, 15), _dt(1, 15)),
        CoverageInterval(_dt(2, 30), _dt(3, 45)),
    ]


def test_post_anywhere_inside_bucket_prevents_that_bucket_being_selected():
    from monitor.backfill import CoverageInterval, detect_zero_coverage_gaps

    assert detect_zero_coverage_gaps(
        [_dt(1, 14)],
        since=_dt(0),
        until=_dt(2),
        bucket_minutes=15,
        min_gap_minutes=15,
    ) == [
        CoverageInterval(_dt(0), _dt(1)),
        CoverageInterval(_dt(1, 15), _dt(2)),
    ]


def test_current_shared_planner_accepts_explicit_brand_filter_and_keeps_seven_calls():
    from monitor.cycle import plan_calls_for_cycle

    calls = plan_calls_for_cycle(load_config(CONFIG_PATH), brand_filter=["deepseek"])

    assert [call.call_id for call in calls] == ["A", "B1", "C1", "C2", "C3", "B2", "B3"]
    assert "DeepSeek" in next(
        call.query_string for call in calls if call.call_id == "B1"
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_build_plan_supports_explicit_and_detected_selection_without_writes():
    from core.models import BackfillJob
    from monitor.backfill import CoverageInterval, build_plan

    cfg = load_config(CONFIG_PATH)
    explicit = build_plan(
        cfg,
        since=_dt(0),
        until=_dt(4),
        detect_gaps=False,
        brand_filter=["deepseek"],
    )
    detected = build_plan(
        cfg,
        since=_dt(0),
        until=_dt(4),
        detect_gaps=True,
        min_gap_minutes=15,
        timestamps=[_dt(0, 1), _dt(2, 1), _dt(3, 1)],
        brand_filter=["deepseek"],
    )

    assert explicit.selection_mode == BackfillJob.SelectionMode.EXPLICIT
    assert explicit.intervals == (CoverageInterval(_dt(0), _dt(4)),)
    assert explicit.work_rows == 7
    assert detected.selection_mode == BackfillJob.SelectionMode.DETECTED_GAPS
    assert detected.intervals == (
        CoverageInterval(_dt(0, 15), _dt(2)),
        CoverageInterval(_dt(2, 15), _dt(3)),
        CoverageInterval(_dt(3, 15), _dt(4)),
    )
    assert detected.work_rows == 21
    assert BackfillJob.objects.count() == 0


def test_plan_signature_and_job_key_are_stable_but_cover_their_inputs():
    from monitor.backfill import make_job_key, make_plan_signature

    params = {"bucket_minutes": 15, "min_gap_minutes": 60}
    signature = make_plan_signature([_call()], brand_filter=["deepseek"])
    key = make_job_key(
        since=_dt(0),
        until=_dt(2),
        selection_mode="detected_gaps",
        selection_params=params,
        brand_filter=["deepseek"],
    )

    assert signature == make_plan_signature([_call()], brand_filter=["deepseek"])
    assert signature != make_plan_signature(
        [_call("different")], brand_filter=["deepseek"]
    )
    assert signature != make_plan_signature([_call()], brand_filter=[])
    assert key == make_job_key(
        since=_dt(0),
        until=_dt(2),
        selection_mode="detected_gaps",
        selection_params=params,
        brand_filter=["deepseek"],
    )
    assert key != make_job_key(
        since=_dt(0),
        until=_dt(2) + timedelta(minutes=15),
        selection_mode="detected_gaps",
        selection_params=params,
        brand_filter=["deepseek"],
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_persist_plan_is_idempotent_and_seeds_one_job_row_per_interval_and_call():
    from core.models import BackfillJob, HarvestBacklogWindow
    from monitor.backfill import BackfillPlan, CoverageInterval, persist_plan

    intervals = (CoverageInterval(_dt(0), _dt(1)), CoverageInterval(_dt(2), _dt(3)))
    calls = (
        _call(),
        _call(
            "second-query",
            call_id="B1",
            call_kind="brand_wide",
            brand_id="deepseek",
        ),
    )
    plan = BackfillPlan.create(
        since=_dt(0),
        until=_dt(4),
        selection_mode=BackfillJob.SelectionMode.DETECTED_GAPS,
        selection_params={"bucket_minutes": 15, "min_gap_minutes": 60},
        intervals=intervals,
        calls=calls,
        brand_filter=("deepseek",),
    )

    first = persist_plan(plan)
    second = persist_plan(plan)

    assert first.pk == second.pk
    assert BackfillJob.objects.count() == 1
    assert HarvestBacklogWindow.objects.filter(backfill_job=first).count() == 4
    assert set(first.windows.values_list("state", flat=True)) == {"pending"}
    assert first.selected_intervals == [
        {"since": "2026-08-10T00:00:00+00:00", "until": "2026-08-10T01:00:00+00:00"},
        {"since": "2026-08-10T02:00:00+00:00", "until": "2026-08-10T03:00:00+00:00"},
    ]
