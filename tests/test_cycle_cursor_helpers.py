"""U1 tests: incremental harvest cursor helpers.

Plan: docs/plans/2026-07-27-002-fix-v2-harvest-cursor-regression-plan.md
Unit U1 (R1, R4, R5).

Covers the three behaviors the cursor helpers must get right:
  * the clamped `since_time` floor (cold start / fresh / stale cursor),
  * timezone-aware round-tripping through CallState (TIMESTAMPTZ),
  * the identity tuple that keeps the six per-cycle calls on separate rows.

The clamp math is pure datetime arithmetic, so it is tested against a fake
cursor row without touching the database -- deliberate, because every
django_db test in this repo errors on a SQLite DATABASE_URL (the core models
declare a Postgres ICU collation).  The DB-backed tests below carry a skip
guard for the same reason.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from monitor import cycle as cycle_mod
from monitor.cycle import (
    _CURSOR_OVERLAP,
    _MAX_LOOKBACK,
    _NULL_BUCKET_SENTINEL,
    _advance_cursor,
    _cursor_key,
    _read_cursor_since,
)
from x_monitor.query_plan import PlannedCall



NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


def _call(call_id: str = "B1", *, brand_id: str = "minimax", bucket=None):
    return PlannedCall(
        call_id=call_id,
        call_kind="brand_wide",
        brand_id=brand_id,
        bucket=bucket,
        query_string="(foo OR bar) min_faves:0",
        query_length=24,
    )


class _FakeRow:
    def __init__(self, last_completed_at):
        self.last_completed_at = last_completed_at


class _FakeManager:
    """Stands in for CallState.objects for the pure-math clamp tests."""

    def __init__(self, row=None, raise_on_read=False):
        self._row = row
        self._raise = raise_on_read
        self.filter_kwargs = None

    def filter(self, **kwargs):
        self.filter_kwargs = kwargs
        if self._raise:
            raise RuntimeError("simulated DB read failure")
        return self

    def first(self):
        return self._row


@pytest.fixture
def fake_cursor(monkeypatch):
    """Swap CallState.objects for a fake so clamp math needs no database."""

    def _install(row=None, raise_on_read=False):
        mgr = _FakeManager(row=row, raise_on_read=raise_on_read)
        monkeypatch.setattr(cycle_mod.CallState, "objects", mgr, raising=False)
        return mgr

    return _install


# --- the clamped since_time floor ----------------------------------------


def test_cold_start_uses_clamped_lookback(fake_cursor):
    """No cursor row -> start at the bounded floor, never at epoch zero."""
    fake_cursor(row=None)
    assert _read_cursor_since(_call(), now=NOW) == NOW - _MAX_LOOKBACK


def test_row_with_null_timestamp_is_treated_as_cold_start(fake_cursor):
    """A row can exist with last_completed_at NULL (nullable column)."""
    fake_cursor(row=_FakeRow(None))
    assert _read_cursor_since(_call(), now=NOW) == NOW - _MAX_LOOKBACK


def test_fresh_cursor_uses_overlap_not_the_floor(fake_cursor):
    """A recent cursor must win over the floor, minus the boundary overlap.

    This is the steady-state path: if the floor won here, every cycle would
    re-sweep the whole lookback window and the cursor would be pointless.
    """
    cursor = NOW - timedelta(minutes=15)
    fake_cursor(row=_FakeRow(cursor))
    assert _read_cursor_since(_call(), now=NOW) == cursor - _CURSOR_OVERLAP


def test_stale_cursor_is_clamped_to_lookback(fake_cursor):
    """R4: prod's cursor sat frozen ~5 days; an unclamped sweep would
    silently truncate against the per-call page cap."""
    fake_cursor(row=_FakeRow(NOW - timedelta(days=5)))
    assert _read_cursor_since(_call(), now=NOW) == NOW - _MAX_LOOKBACK


def test_cursor_exactly_at_the_boundary_does_not_move_window_backward(
    fake_cursor,
):
    """Guards the off-by-one: at the boundary the clamp must win, so the
    returned floor is never older than now - _MAX_LOOKBACK."""
    fake_cursor(row=_FakeRow(NOW - _MAX_LOOKBACK))
    since = _read_cursor_since(_call(), now=NOW)
    assert since == NOW - _MAX_LOOKBACK
    assert since >= NOW - _MAX_LOOKBACK


def test_returned_since_is_always_timezone_aware(fake_cursor):
    fake_cursor(row=_FakeRow(NOW - timedelta(minutes=5)))
    assert _read_cursor_since(_call(), now=NOW).tzinfo is not None


def test_read_failure_degrades_to_clamped_floor(fake_cursor):
    """A DB blip must not skip the cycle; a bounded re-fetch is safe."""
    fake_cursor(raise_on_read=True)
    assert _read_cursor_since(_call(), now=NOW) == NOW - _MAX_LOOKBACK


def test_overlap_is_smaller_than_lookback():
    """Sanity pin: an overlap >= lookback would make the clamp unreachable."""
    assert _CURSOR_OVERLAP < _MAX_LOOKBACK


# --- identity tuple (R5 / KTD8) ------------------------------------------


def test_cursor_key_normalizes_none_bucket():
    """Every v2 PlannedCall has bucket=None, but the column defaults to "".
    Both must address the same row."""
    assert _cursor_key(_call(bucket=None))["bucket"] == _NULL_BUCKET_SENTINEL
    assert _cursor_key(_call(bucket=""))["bucket"] == _NULL_BUCKET_SENTINEL


def test_cursor_key_uses_call_id_as_query_id():
    assert _cursor_key(_call("C2"))["query_id"] == "C2"


def test_cursor_key_shape_for_list_call():
    """Call A's brand_id is the planner's "*" placeholder, not a brand."""
    call_a = PlannedCall(
        call_id="A",
        call_kind="account",
        brand_id="*",
        bucket=None,
        query_string="(list:123) min_faves:0",
        query_length=22,
    )
    assert _cursor_key(call_a) == {
        "brand_id": "*",
        "call_id": "A",
        "call_kind": "account",
        "bucket": "",
        "query_id": "A",
    }


def test_calls_differing_only_by_call_id_get_distinct_keys():
    """B1/B2/B3 share a brand placeholder shape; call_id must disambiguate."""
    k1 = _cursor_key(_call("B1", brand_id="minimax"))
    k2 = _cursor_key(_call("B2", brand_id="minimax"))
    assert k1 != k2
    assert k1["call_id"] != k2["call_id"]


# --- write path ----------------------------------------------------------


def test_advance_cursor_rejects_naive_datetime():
    """CallState.last_completed_at is TIMESTAMPTZ under USE_TZ=True; a naive
    value would either raise deep in the ORM or be silently misinterpreted."""
    with pytest.raises(ValueError, match="aware datetime"):
        _advance_cursor(_call(), upper_bound=datetime(2026, 7, 27, 12, 0, 0))


def test_advance_cursor_swallows_db_error(monkeypatch):
    """R3: a failed cursor write must not abort the cycle."""

    class _Boom:
        def update_or_create(self, **kwargs):
            raise RuntimeError("simulated write failure")

    monkeypatch.setattr(cycle_mod.CallState, "objects", _Boom(), raising=False)
    assert _advance_cursor(_call(), upper_bound=NOW, now=NOW) is False


def test_advance_cursor_reports_success(monkeypatch):
    calls = {}

    class _Ok:
        def update_or_create(self, **kwargs):
            calls.update(kwargs)
            return (object(), True)

    monkeypatch.setattr(cycle_mod.CallState, "objects", _Ok(), raising=False)
    assert _advance_cursor(_call("C1"), upper_bound=NOW, now=NOW) is True
    assert calls["call_id"] == "C1"
    assert calls["defaults"]["last_completed_at"] == NOW


# --- DB-backed round trip ------------------------------------------------


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_write_then_read_round_trips_through_the_database():
    """The strongest form: a real row, read back through the real query."""
    call = _call("B3")
    upper = datetime.now(timezone.utc)
    assert _advance_cursor(call, upper_bound=upper) is True

    since = _read_cursor_since(call, now=upper)
    assert since == upper - _CURSOR_OVERLAP


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_stored_timestamp_is_timezone_aware():
    """Single assertion that catches every naive-datetime regression."""
    from core.models import CallState

    call = _call("C1")
    _advance_cursor(call, upper_bound=datetime.now(timezone.utc))
    row = CallState.objects.filter(**_cursor_key(call)).first()
    assert row is not None
    assert row.last_completed_at.tzinfo is not None


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_advance_updates_in_place_without_duplicating_rows():
    from core.models import CallState

    call = _call("B2")
    first = datetime.now(timezone.utc) - timedelta(minutes=30)
    second = datetime.now(timezone.utc)
    _advance_cursor(call, upper_bound=first)
    _advance_cursor(call, upper_bound=second)

    rows = CallState.objects.filter(**_cursor_key(call))
    assert rows.count() == 1
    assert rows.first().last_completed_at == second


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_none_and_empty_bucket_address_the_same_row():
    """KTD8: None must normalize to "" so the two never split into two rows."""
    from core.models import CallState

    upper = datetime.now(timezone.utc)
    _advance_cursor(_call("C2", bucket=None), upper_bound=upper)
    _advance_cursor(_call("C2", bucket=""), upper_bound=upper)
    assert CallState.objects.filter(call_id="C2").count() == 1


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_distinct_calls_keep_independent_cursors():
    """R5: advancing one call must not move another's window."""
    from core.models import CallState

    early = datetime.now(timezone.utc) - timedelta(hours=1)
    late = datetime.now(timezone.utc)
    _advance_cursor(_call("B1"), upper_bound=early)
    _advance_cursor(_call("B2"), upper_bound=late)

    assert CallState.objects.filter(call_id="B1").first().last_completed_at == early
    assert CallState.objects.filter(call_id="B2").first().last_completed_at == late


# --- defensive paths found in code review --------------------------------


def test_naive_cursor_value_does_not_abort_the_cycle(fake_cursor):
    """A naive last_completed_at must not raise.

    `max(naive - delta, aware)` raises TypeError, and the per-call loop in
    run() has no try/except -- so an unguarded naive value would kill the
    WHOLE cycle (all six calls), not degrade one. Reachable if USE_TZ is
    flipped, a raw SQL insert lands, or a v1 ISO-string value survives a
    migration.
    """
    naive = datetime(2026, 7, 27, 11, 55, 0)  # no tzinfo
    fake_cursor(row=_FakeRow(naive))
    since = _read_cursor_since(_call(), now=NOW)
    assert since.tzinfo is not None
    # Treated as UTC, so it wins over the floor rather than being discarded.
    assert since == naive.replace(tzinfo=timezone.utc) - _CURSOR_OVERLAP


def test_operator_since_time_of_zero_is_honored(monkeypatch):
    """Epoch 0 is a legitimate full-history backfill bound.

    A falsy check would silently swap it for the 2h cursor floor, shrinking
    an operator's requested window without saying so.
    """
    from monitor.cycle import CycleRunner

    monkeypatch.setattr(
        cycle_mod.settings, "X_MONITOR_CYCLE_SINCE_TIME", 0, raising=False
    )
    monkeypatch.setattr(
        cycle_mod.settings, "X_MONITOR_CYCLE_UNTIL_TIME", None, raising=False
    )
    since, until, cursor_owned = CycleRunner(cycle_kind="manual")._resolve_window(
        _call(), now=NOW
    )
    assert since == 0, "epoch 0 was discarded instead of used as the floor"
    assert cursor_owned is False, "an operator window must not own the cursor"
    assert until == int(NOW.timestamp())


def test_future_cursor_value_does_not_invert_the_window(fake_cursor):
    """A prior > now must NOT produce since > until.

    Reachable on NTP rollback, a v1 legacy row whose TZ was mis-parsed, or
    any manual psql insert. An inverted window returns [] from TwitterAPI.io
    with no error, and the empty-sweep advance rewinds the cursor to now --
    permanently losing every post in the (now, prior) span.
    """
    future = NOW + timedelta(minutes=10)
    fake_cursor(row=_FakeRow(future))
    since = _read_cursor_since(_call(), now=NOW)
    # Since must be in the past relative to now. NOT future, NOT in the
    # future-leaning portion of overlap.
    assert since <= NOW, (
        f"_read_cursor_since returned {since.isoformat()}, which is AFTER "
        f"now ({NOW.isoformat()}). The window would invert (since > until) "
        "and the next cycle's empty-sweep advance would rewind the cursor."
    )
    # Specifically: clamped to (now - overlap), so the next sweep is bounded
    # to a single re-fetch that dedup absorbs, rather than the 2h floor
    # (which would silently drop the (now, prior) span).
    assert since == NOW - _CURSOR_OVERLAP


def test_cursor_advance_rejects_future_upper_bound():
    """Belt-and-suspenders: an in-tree writer must not be able to persist a
    future timestamp at all, even if some external path produces one."""
    import datetime as _dt

    future = NOW + _dt.timedelta(minutes=5)
    with pytest.raises(ValueError, match="future"):
        _advance_cursor(_call(), upper_bound=future, now=NOW)


# --- defensive paths from a second peer review ---------------------------


def test_x_query_specs_must_have_distinct_call_id_placeholders():
    """Two specs sharing call_id AND first brand would address one cursor
    row. Advance from one overwrites the other, collapsing the second
    call's next window to a 1-minute overlap. Validation lives in
    load_config; this asserts it fires.
    """
    from pathlib import Path
    from x_monitor.config import load_config
    import yaml as _yaml

    bad = {
        "search": {"max_results": 50, "max_pages": 5, "max_per_page": 20},
        "x_monitor_list_id": 1,
        "x_query_specs": [
            {
                "call_id": "DUP",
                "brands": {"deepseek": ["deepseek"]},
                "co_occurrence": ["api"],
                "min_faves": 0,
            },
            {
                "call_id": "DUP",
                "brands": {"deepseek": ["deepseek-r1"]},
                "co_occurrence": ["api"],
                "min_faves": 0,
            },
        ],
        "enabled_models": ["deepseek"],
    }
    path = Path("/tmp/_bad_dup_call_id.yaml")
    path.write_text(_yaml.safe_dump(bad))
    try:
        with pytest.raises(ValueError, match="duplicate call_id"):
            load_config(path)
    finally:
        path.unlink(missing_ok=True)
