"""U2 tests: cursor wiring in CycleRunner's per-call fetch path.

Plan: docs/plans/2026-07-27-002-fix-v2-harvest-cursor-regression-plan.md
Unit U2 (R1, R2, R3, R6).

These tests drive a full CycleRunner.run() with a faked API client and assert
on the window handed to run_search plus the resulting cursor state.  The
central pair of behaviors:

  * every scheduled call is TIME-BOUNDED (the bug: v2 passed since_time=None,
    so each cycle re-skimmed the newest ~100 posts per query), and
  * the cursor advances ONLY when the call actually succeeded, so a transient
    failure causes a re-sweep instead of a permanently skipped window.

A genuinely-empty window and a failed fetch both used to look like `[]` to
the caller; distinguishing them is required here, because an empty window is
a successful sweep (KTD5) while a failure must not advance.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from django.test import override_settings

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner, _cursor_key
from x_monitor.apify import TwitterApiAuthError, TwitterApiRateLimitError
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _planned(call_id: str = "B1", brand_id: str = "minimax") -> PlannedCall:
    return PlannedCall(
        call_id=call_id,
        call_kind="brand_wide",
        brand_id=brand_id,
        bucket=None,
        query_string="(alpha OR beta) min_faves:0",
        query_length=27,
    )


class FakeApi:
    """Records the window each call received; returns scripted results."""

    def __init__(self, results=None, raise_exc=None):
        self._results = results if results is not None else []
        self._raise = raise_exc
        self.calls: list[dict] = []

    def run_search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        if self._raise is not None:
            raise self._raise
        return list(self._results), False  # (items, truncated)


def _tweet(tid: str = "1", handle: str | None = None):
    return {
        "id": tid,
        "author_id": f"a{tid}",
        "author_handle": handle or f"user_{tid}",
        "text": "alpha release is great",
        "lang": "en",
        "created_at": "Sat Jul 25 12:00:00 +0000 2026",
    }


@pytest.fixture
def wired(monkeypatch):
    """Run one cycle with a stubbed plan + API and no post-fetch LLM work."""

    def _run(*, calls=None, results=None, raise_exc=None, settings_over=None):
        calls = calls or [_planned()]
        api = FakeApi(results=results, raise_exc=raise_exc)
        monkeypatch.setattr(
            cycle_mod, "plan_calls_for_cycle", lambda cfg=None: list(calls)
        )
        # run() builds its client via TwitterApiClient.from_env(); replace that
        # classmethod so no test ever reaches the network.
        monkeypatch.setattr(
            cycle_mod.TwitterApiClient,
            "from_env",
            classmethod(lambda cls: api),
        )
        monkeypatch.setattr(
            CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
        )
        with override_settings(**(settings_over or {})):
            runner = CycleRunner(cycle_kind="scheduled")
            stats = runner.run()
        return api, stats

    return _run


# --- the core regression: scheduled calls are time-bounded ---------------


def test_scheduled_call_passes_both_time_bounds(wired):
    """THE BUG. v2 passed since_time=None/until_time=None in production."""
    api, _ = wired(results=[_tweet()])
    assert api.calls, "no API call was made"
    for c in api.calls:
        assert c.get("since_time") is not None, (
            "since_time is None -- the cycle is unbounded again and will "
            "re-skim the newest posts instead of sweeping the window"
        )
        assert c.get("until_time") is not None, "until_time is None"


def test_window_is_ordered_and_recent(wired):
    api, _ = wired(results=[_tweet()])
    c = api.calls[0]
    assert c["since_time"] < c["until_time"]
    now = int(datetime.now(timezone.utc).timestamp())
    assert c["until_time"] <= now + 5, "until_time is in the future"
    assert c["until_time"] > now - 300, "until_time is implausibly old"


def test_cursor_advances_to_the_queried_upper_bound(wired):
    """KTD4: the value stored must equal the until_time actually queried, so
    consecutive windows chain exactly."""
    from core.models import CallState

    call = _planned()
    api, _ = wired(calls=[call], results=[_tweet()])
    row = CallState.objects.filter(**_cursor_key(call)).first()
    assert row is not None, "cursor row was not created"
    assert int(row.last_completed_at.timestamp()) == api.calls[0]["until_time"]


# --- advance only on success (R2) ----------------------------------------


def test_empty_window_still_advances_cursor(wired):
    """KTD5: zero results is a successful sweep, not a failure. If this did
    not advance, a quiet brand would re-sweep the same window forever."""
    from core.models import CallState

    call = _planned()
    wired(calls=[call], results=[])
    assert CallState.objects.filter(**_cursor_key(call)).exists(), (
        "an empty-but-successful window must advance the cursor"
    )


def test_rate_limit_error_does_not_advance_cursor(wired):
    """R2: the window must be retried, not skipped."""
    from core.models import CallState

    call = _planned()
    wired(calls=[call], raise_exc=TwitterApiRateLimitError("429"))
    assert not CallState.objects.filter(**_cursor_key(call)).exists(), (
        "cursor advanced despite a failed fetch -- that window is now lost"
    )


def test_auth_error_does_not_advance_cursor(wired):
    from core.models import CallState

    call = _planned()
    _, stats = wired(calls=[call], raise_exc=TwitterApiAuthError("401"))
    assert not CallState.objects.filter(**_cursor_key(call)).exists()
    assert stats["errors"], "auth failure should be recorded in cycle errors"


def test_one_failing_call_does_not_block_the_others(wired):
    """A per-call failure is contained; the remaining calls still run.

    The failure must be REAL for this to mean anything: an earlier version of
    this test passed `results=[...]` with no exception, so all three calls
    succeeded and it could not tell "iteration survives an exception" from
    "no exception ever happened".
    """
    from core.models import CallState

    calls = [_planned("B1"), _planned("B2", "doubao"), _planned("C1", "mimo")]
    api = FakeApi(results=[_tweet()])
    # First call raises, the remaining two succeed.
    original = api.run_search
    state = {"n": 0}

    def flaky(query, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            api.calls.append({"query": query, **kwargs})
            raise TwitterApiRateLimitError("429 on the first call")
        return original(query, **kwargs)

    api.run_search = flaky
    monkeypatch_target = cycle_mod.TwitterApiClient
    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None: list(calls))
        mp.setattr(
            monkeypatch_target, "from_env", classmethod(lambda cls: api)
        )
        mp.setattr(
            CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
        )
        CycleRunner(cycle_kind="scheduled").run()

    assert len(api.calls) == 3, (
        f"only {len(api.calls)} of 3 calls ran; a failure on the first call "
        "aborted the rest of the cycle"
    )
    # The failed call holds its cursor; the two that succeeded advance theirs.
    assert not CallState.objects.filter(call_id="B1").exists()
    assert CallState.objects.filter(call_id="B2").exists()
    assert CallState.objects.filter(call_id="C1").exists()


# --- cursor drives the next window --------------------------------------


def test_second_cycle_resumes_from_the_first_cursor(wired):
    """Windows must chain: cycle 2 starts at cycle 1's end (minus overlap),
    never back at the lookback floor."""
    call = _planned()
    api1, _ = wired(calls=[call], results=[_tweet("1")])
    api2, _ = wired(calls=[call], results=[_tweet("2")])

    first_upper = api1.calls[0]["until_time"]
    second_since = api2.calls[0]["since_time"]
    assert second_since <= first_upper, "gap between consecutive windows"
    assert second_since > first_upper - 3600, (
        "cycle 2 fell back to the lookback floor instead of resuming from "
        "the cursor -- the cursor is not being read"
    )


# --- backfill override still wins (R6) ----------------------------------


def test_operator_supplied_window_overrides_the_cursor(wired):
    """R6: the backfill command sets these explicitly; they must win."""
    since = int((datetime.now(timezone.utc) - timedelta(days=3)).timestamp())
    until = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
    api, _ = wired(
        results=[_tweet()],
        settings_over={
            "X_MONITOR_CYCLE_SINCE_TIME": since,
            "X_MONITOR_CYCLE_UNTIL_TIME": until,
        },
    )
    assert api.calls[0]["since_time"] == since
    assert api.calls[0]["until_time"] == until


def test_operator_window_does_not_advance_the_cursor(wired):
    """A historical backfill must not move the live harvest's cursor
    forward -- that would skip everything between."""
    from core.models import CallState

    call = _planned()
    since = int((datetime.now(timezone.utc) - timedelta(days=3)).timestamp())
    until = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
    wired(
        calls=[call],
        results=[_tweet()],
        settings_over={
            "X_MONITOR_CYCLE_SINCE_TIME": since,
            "X_MONITOR_CYCLE_UNTIL_TIME": until,
        },
    )
    assert not CallState.objects.filter(**_cursor_key(call)).exists()


# --- resilience (R3) ----------------------------------------------------


def test_cursor_write_failure_does_not_fail_the_cycle(wired, monkeypatch):
    """R3: posts are already stored; a cursor blip costs a re-fetch, not a
    cycle."""
    monkeypatch.setattr(
        cycle_mod, "_advance_cursor", lambda *a, **k: False
    )
    _, stats = wired(results=[_tweet()])
    assert stats["status"] in {"completed", "degraded"}


def test_each_call_gets_its_own_cursor_row(wired):
    """R5: six calls, six rows; advancing one must not move another."""
    from core.models import CallState

    calls = [_planned("B1"), _planned("B2", "doubao"), _planned("C1", "mimo")]
    wired(calls=calls, results=[_tweet()])
    assert CallState.objects.count() == 3


def test_persist_failure_does_not_advance_the_cursor(wired, monkeypatch):
    """A post that failed to PERSIST must leave the window re-sweepable.

    _persist_items catches per-item exceptions, rolls that item's transaction
    back, and returns counts with no failure signal. So a tweet whose
    Account/Post/attribution write raises is silently lost AND the cursor
    advances past its window -- the next cycle starts at cursor minus the
    1-minute overlap, so anything older than that boundary is never fetched
    again. Overlap and tweet_id dedup cannot recover it: overlap only covers
    the last minute, and dedup only suppresses duplicates of writes that
    already succeeded.

    Reported by a peer review session against 26d9071.
    """
    from core.models import Brand, CallState, Post

    Brand.objects.get_or_create(nickname="deepseek")
    call = _planned()

    def boom(raw, account=None):
        raise RuntimeError("simulated persist failure")

    monkeypatch.setattr(cycle_mod, "_upsert_post", boom)

    tweet = _tweet("persist-fail")
    tweet["text"] = "DeepSeek just shipped a new model"
    _, stats = wired(calls=[call], results=[tweet])

    assert not Post.objects.filter(tweet_id="persist-fail").exists(), (
        "fixture bug: the post was supposed to fail persistence"
    )
    assert any("persist" in e for e in stats["errors"]), (
        f"persist failure was not recorded in cycle errors: {stats['errors']}"
    )
    assert not CallState.objects.filter(**_cursor_key(call)).exists(), (
        "cursor advanced past a window whose post failed to persist -- that "
        "tweet is now unreachable forever"
    )


def test_partial_persist_failure_still_holds_the_cursor(wired, monkeypatch):
    """One failure among several items is enough to hold the window.

    The successful items are already stored and dedup will discard them on the
    re-sweep, so holding is cheap; advancing would strand the failed one.
    """
    from core.models import Brand, CallState, Post

    Brand.objects.get_or_create(nickname="deepseek")
    call = _planned()
    real_upsert = cycle_mod._upsert_post

    def flaky(raw, account=None):
        if str(raw.get("id")) == "bad":
            raise RuntimeError("simulated persist failure")
        return real_upsert(raw, account=account)

    monkeypatch.setattr(cycle_mod, "_upsert_post", flaky)

    good = _tweet("good")
    good["text"] = "DeepSeek just shipped a new model"
    bad = _tweet("bad")
    bad["text"] = "DeepSeek also shipped something else"
    wired(calls=[call], results=[good, bad])

    assert Post.objects.filter(tweet_id="good").exists(), "good item should persist"
    assert not Post.objects.filter(tweet_id="bad").exists()
    assert not CallState.objects.filter(**_cursor_key(call)).exists(), (
        "a partial persist failure must still hold the cursor"
    )


def test_clean_persist_still_advances_the_cursor(wired):
    """Guard against over-correcting: a fully successful call must advance."""
    from core.models import Brand, CallState

    Brand.objects.get_or_create(nickname="deepseek")
    call = _planned()
    tweet = _tweet("clean")
    tweet["text"] = "DeepSeek just shipped a new model"
    _, stats = wired(calls=[call], results=[tweet])
    assert CallState.objects.filter(**_cursor_key(call)).exists(), (
        "a clean call must still advance -- otherwise the harvest never "
        "moves forward at all"
    )


def test_repeat_sighting_reports_update_not_insert(wired):
    """R22: the production cycle must preserve Django's created boolean.

    A repeated tweet is useful work because mutable engagement and author
    fields are refreshed, but it is not a new database insert.  Counting it
    as inserted makes the operator summary overstate freshness and hides the
    exact fetch-to-insert gap this pipeline is meant to explain.
    """
    from core.models import Brand, Post

    Brand.objects.get_or_create(nickname="deepseek")
    call = _planned()
    tweet = _tweet("repeat")
    tweet["text"] = "DeepSeek just shipped a new model"

    _, first = wired(calls=[call], results=[tweet])
    _, second = wired(calls=[call], results=[tweet])

    assert Post.objects.filter(tweet_id="repeat").count() == 1
    assert first["totals"]["n_inserted"] == 1
    assert first["totals"]["n_updated"] == 0
    assert second["totals"]["n_inserted"] == 0
    assert second["totals"]["n_updated"] == 1


def test_truncated_window_transfers_residual_then_advances_cursor(wired, monkeypatch):
    """A capped live window moves its unsearched tail to durable ownership.

    TwitterAPI.io answers advanced_search with up to max_results per call. If
    the window contains more tweets than the cap, truncated=True. Advancing
    would strand the unreturned older posts forever. Items that *were*
    returned must still be eligible for persist (see sibling test); this
    test pins the hold-cursor half of the contract.
    """
    from core.models import Brand, CallState, HarvestBacklogWindow

    Brand.objects.get_or_create(nickname="deepseek")
    call = _planned()

    class TruncatingApi:
        def __init__(self):
            self.calls = []

        def run_search(self, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            n = min(int(kwargs.get("max_results") or 50), 5)
            until = int(kwargs.get("until_time") or 0)
            base = until - 3600 if until else 1_753_430_400
            return [
                {
                    **_tweet(f"id-{until}-{i}"),
                    "text": "DeepSeek does things",
                    "created_at": "Sat Jul 25 12:00:00 +0000 2026",
                    "created_at_epoch": base - i,
                }
                for i in range(n)
            ], True

    api = TruncatingApi()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [call])
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env", classmethod(lambda cls: api)
    )
    monkeypatch.setattr(
        CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
    )
    stats = CycleRunner(cycle_kind="scheduled").run()

    entry = [c for c in stats["calls"] if c["call_id"] == "B1"][-1]
    assert entry["status"] == "truncated_replay_queued", (
        f"expected queued residual, got {entry['status']!r}"
    )
    assert entry.get("cursor_advanced") is True
    assert CallState.objects.filter(**_cursor_key(call)).exists()
    assert HarvestBacklogWindow.objects.filter(**_cursor_key(call)).count() == 1
    assert api.calls, "the live tip was never requested"


def test_truncated_window_still_persists_attributable_items(wired, monkeypatch):
    """Truncation must not discard the page: persist items, hold cursor.

    C1 deadlock root cause: every cycle re-fetched the tip, threw away the
    results on outcome=truncated, and never advanced -- zero progress forever.
    """
    from core.models import Brand, CallState, Post

    Brand.objects.get_or_create(nickname="deepseek")
    call = _planned()

    class TruncatingApi:
        def __init__(self):
            self.calls = []

        def run_search(self, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            # First pass: truncated with attributable items.
            # Later walks: empty+not-truncated would flip to ok; keep
            # truncated so the call stays status=truncated after budget.
            until = int(kwargs.get("until_time") or 1_753_434_000)
            n = 5
            return [
                {
                    **_tweet(f"keep-{until}-{i}"),
                    "text": "DeepSeek just shipped a new model",
                    "created_at": "Sat Jul 25 12:00:00 +0000 2026",
                    "created_at_epoch": until - 10 - i,
                }
                for i in range(n)
            ], True

    api = TruncatingApi()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [call])
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env", classmethod(lambda cls: api)
    )
    monkeypatch.setattr(
        CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
    )
    stats = CycleRunner(cycle_kind="scheduled").run()

    entry = [c for c in stats["calls"] if c["call_id"] == "B1"][-1]
    assert entry["status"] == "truncated_replay_queued"
    assert entry["n_inserted"] >= 1, (
        f"truncated path must persist attributable items; n_inserted="
        f"{entry.get('n_inserted')}"
    )
    assert Post.objects.filter(tweet_id__startswith="keep-").exists(), (
        "no posts persisted on truncated outcome"
    )
    assert CallState.objects.filter(**_cursor_key(call)).exists()


def test_c1_uses_shared_config_ceiling(wired, monkeypatch):
    """C1 must not silently override the shared search-budget contract."""
    call = _planned(call_id="C1", brand_id="mimo")
    seen = {}

    class CaptureApi:
        def run_search(self, query, **kwargs):
            seen["max_results"] = kwargs.get("max_results")
            seen["max_pages"] = kwargs.get("max_pages")
            return [], False

    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [call])
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env", classmethod(lambda cls: CaptureApi())
    )
    monkeypatch.setattr(
        CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
    )
    with override_settings(
        X_MONITOR_CYCLE_LIMIT_PER_CALL=50,
        X_MONITOR_CYCLE_MAX_PAGES_PER_CALL=5,
    ):
        CycleRunner(cycle_kind="scheduled").run()
    assert seen["max_results"] == 20, seen
    assert seen["max_pages"] == 1, seen


def test_truncated_empty_result_transfers_full_interval(wired, monkeypatch):
    """A truncated empty result preserves the full interval in the ledger.

    The non-truncation empty case advances (KTD5); the truncated empty case
    must NOT, for the same reason: 51st-and-older tweets exist but were not
    in this call's response.
    """
    from core.models import CallState, HarvestBacklogWindow

    call = _planned()

    class TruncatedEmpty:
        def __init__(self):
            self.calls = []

        def run_search(self, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            return [], True  # 0 items, truncated=True

    api = TruncatedEmpty()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [call])
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env", classmethod(lambda cls: api)
    )
    monkeypatch.setattr(
        CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
    )
    stats = CycleRunner(cycle_kind="scheduled").run()

    entry = [c for c in stats["calls"] if c["call_id"] == "B1"][-1]
    assert entry["status"] == "truncated_replay_queued", (
        f"expected queued residual, got {entry['status']!r}"
    )
    assert entry["cursor_advanced"] is True
    assert CallState.objects.filter(**_cursor_key(call)).exists()
    assert HarvestBacklogWindow.objects.filter(**_cursor_key(call)).count() == 1


def test_non_truncated_full_cap_advances_cursor(wired, monkeypatch):
    """Returns the cap's worth of items but has_next_page is False.

    The cap was hit but the window is exhausted -- safe to advance.
    """
    from core.models import Brand, CallState

    Brand.objects.get_or_create(nickname="deepseek")
    call = _planned()

    class CappedButExhausted:
        def run_search(self, query, **kwargs):
            return [
                {**_tweet(f"x-{i}"), "text": "DeepSeek does things",
                 "created_at": "Sat Jul 25 12:00:00 +0000 2026"}
                for i in range(50)
            ], False  # 50 items, truncated=False (window exhausted)

    api = CappedButExhausted()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [call])
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env", classmethod(lambda cls: api)
    )
    monkeypatch.setattr(
        CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
    )
    CycleRunner(cycle_kind="scheduled").run()

    assert CallState.objects.filter(**_cursor_key(call)).exists(), (
        "the cap was hit but the window was exhausted -- advance is safe"
    )
