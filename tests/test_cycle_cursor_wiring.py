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

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone

import pytest
from django.test import override_settings

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner, _cursor_key
from x_monitor.query_plan import PlannedCall
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
from x_monitor.x_client import XClientAuthError, XClientRateLimitError

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


class CapturingApi:
    """Model the real client's exchange hooks for scheduled source evidence."""

    base_url = "https://api.twitterapi.io"
    max_retries = 2
    on_exchange_start = None
    on_exchange_finish = None

    def capture(self, items, kwargs):
        if self.on_exchange_start is None:
            return
        request = self.on_exchange_start("/twitter/tweet/advanced_search", kwargs)
        self.on_exchange_finish(request, {
            "outcome": "received", "status_code": 200,
            "body": json.dumps({"tweets": items}).encode(),
        })


class FakeApi(CapturingApi):
    """Records the window each call received; returns scripted results."""

    def __init__(self, results=None, raise_exc=None):
        self._results = results if results is not None else []
        self._raise = raise_exc
        self.calls: list[dict] = []
        self.credential_purposes: list[TwitterApiCredentialPurpose] = []

    def run_search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        if self._raise is not None:
            raise self._raise
        items = deepcopy(self._results)
        self.capture(items, kwargs)
        return items, False  # (items, truncated)


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
def wired(monkeypatch, seeded_policy_keywords):
    """Run one cycle with a stubbed plan + API and no post-fetch LLM work."""

    def _run(
        *,
        calls=None,
        results=None,
        raise_exc=None,
        settings_over=None,
        cycle_kind="scheduled",
        runner_options=None,
    ):
        calls = calls or [_planned()]
        api = FakeApi(results=results, raise_exc=raise_exc)
        monkeypatch.setattr(
            cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: list(calls)
        )
        # run() builds its client via XClient.from_env(); replace that
        # classmethod so no test ever reaches the network while retaining the
        # purpose argument as production call-chain evidence.
        def _client_from_env(_cls, purpose):
            api.credential_purposes.append(purpose)
            return api

        monkeypatch.setattr(
            cycle_mod.XClient,
            "from_env",
            classmethod(_client_from_env),
        )
        monkeypatch.setattr(
            CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
        )
        with override_settings(**(settings_over or {})):
            runner = CycleRunner(cycle_kind=cycle_kind, **(runner_options or {}))
            stats = runner.run()
        return api, stats

    return _run


def test_delayed_live_cycle_keeps_original_window_and_runtime_deadline(wired, monkeypatch):
    import time

    from x_monitor.config import HarvestConfig

    observed = []
    original_start = HarvestConfig.start_deadline

    def start_deadline(self, **kwargs):
        result = original_start(self, **kwargs)
        observed.append(result)
        return result

    monkeypatch.setattr(HarvestConfig, "start_deadline", start_deadline)
    scheduled_at = datetime.now(UTC) - timedelta(minutes=3)
    acquired_at = scheduled_at + timedelta(seconds=75)
    started_monotonic = time.monotonic() - 75
    tweet = {**_tweet("99912345"), "text": "MiniMax release is great"}
    api, stats = wired(
        results=[tweet],
        runner_options={"_clock": lambda: acquired_at, "_collection_window_end": scheduled_at,
                        "_cycle_started_monotonic": started_monotonic},
    )
    assert stats["totals"]["n_inserted"] == 1
    assert len(api.calls) == 1
    assert api.calls[0]["until_time"] == int(scheduled_at.timestamp())
    assert api.calls[0]["since_time"] < api.calls[0]["until_time"]
    from core.models import CallState

    assert CallState.objects.get().last_completed_at == scheduled_at.replace(microsecond=0)
    assert observed[-1].started_at == started_monotonic
    assert observed[-1].remaining() < observed[-1].deadline_at - observed[-1].started_at - 74
    # Start includes the wait; real completion/receipt clocks remain current.
    assert stats["started_at"] == scheduled_at.isoformat(timespec="seconds")
    assert stats["finished_at"] == acquired_at.isoformat(timespec="seconds")


def test_delayed_live_rare_search_keeps_original_scheduled_slot(wired, monkeypatch):
    captured = []
    scheduled_at = datetime.now(UTC) - timedelta(minutes=3)

    def rare(self, call, api, *, now):
        captured.append(now)
        return {"status": "no_results", "provider_called": False}

    monkeypatch.setattr(CycleRunner, "_run_rare_type_search", rare)
    wired(calls=[_planned("RARE_EXTRA")],
          runner_options={"_collection_window_end": scheduled_at})
    assert captured == [scheduled_at]


# --- the core regression: scheduled calls are time-bounded ---------------


def test_scheduled_cycle_requests_only_scheduled_credential(wired):
    api, _ = wired(results=[])
    assert api.credential_purposes == [TwitterApiCredentialPurpose.SCHEDULED]


def test_backfill_cycle_requests_only_on_demand_credential(wired):
    api, _ = wired(results=[], cycle_kind="backfill")
    assert api.credential_purposes == [TwitterApiCredentialPurpose.ON_DEMAND]


def test_manual_cycle_requests_only_on_demand_credential(wired):
    api, _ = wired(results=[], cycle_kind="manual")
    assert api.credential_purposes == [TwitterApiCredentialPurpose.ON_DEMAND]


def test_backfill_cycle_skips_unrelated_metrics_refresh(wired, monkeypatch):
    refresh_calls = []
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh",
        lambda *args, **kwargs: refresh_calls.append((args, kwargs)),
    )

    _, stats = wired(results=[], cycle_kind="backfill")

    assert refresh_calls == []
    assert "metrics_refresh" not in stats


@pytest.mark.parametrize("cycle_kind", ["scheduled", "backfill"])
def test_cycle_persists_normalized_initial_zero_engagement(wired, cycle_kind):
    from core.models import Post
    from x_monitor.x_client import _normalize_tweet

    # The provider adapter supplies zeros even when initial counters are absent.
    # Previously the shared writer discarded these zeros as false values.
    tweet = _normalize_tweet(
        {
            "id": "1234567890",
            "text": "MiniMax release is great",
            "lang": "en",
            "createdAt": "Sat Jul 25 12:00:00 +0000 2026",
            "author": {"id": "zero-author", "userName": "zero_author"},
        }
    )
    api, stats = wired(results=[tweet], cycle_kind=cycle_kind)

    assert len(api.calls) == 1
    assert stats["totals"]["n_inserted"] == 1
    post = Post.objects.get(tweet_id="1234567890")
    assert (post.like_count, post.retweet_count, post.reply_count, post.quote_count) == (
        0, 0, 0, 0
    )
    assert post.metrics_refreshed_at is None
    assert post.view_count is None
    assert post.bookmark_count is None


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
    wired(calls=[call], raise_exc=XClientRateLimitError("429"))
    assert not CallState.objects.filter(**_cursor_key(call)).exists(), (
        "cursor advanced despite a failed fetch -- that window is now lost"
    )


def test_auth_error_does_not_advance_cursor(wired):
    from core.models import CallState

    call = _planned()
    _, stats = wired(calls=[call], raise_exc=XClientAuthError("401"))
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
            raise XClientRateLimitError("429 on the first call")
        return original(query, **kwargs)

    api.run_search = flaky
    monkeypatch_target = cycle_mod.XClient
    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: list(calls))
        mp.setattr(
            monkeypatch_target, "from_env", classmethod(lambda cls, _purpose: api)
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

    class TruncatingApi(CapturingApi):
        def __init__(self):
            self.calls = []

        def run_search(self, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            n = min(int(kwargs.get("max_results") or 50), 5)
            until = int(kwargs.get("until_time") or 0)
            base = until - 3600 if until else 1_753_430_400
            items = [
                {
                    **_tweet(f"id-{until}-{i}"),
                    "text": "DeepSeek does things",
                    "created_at": "Sat Jul 25 12:00:00 +0000 2026",
                    "created_at_epoch": base - i,
                }
                for i in range(n)
            ]
            self.capture(items, kwargs)
            return items, True

    api = TruncatingApi()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: [call])
    monkeypatch.setattr(
        cycle_mod.XClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
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

    class TruncatingApi(CapturingApi):
        def __init__(self):
            self.calls = []

        def run_search(self, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            # First pass: truncated with attributable items.
            # Later walks: empty+not-truncated would flip to ok; keep
            # truncated so the call stays status=truncated after budget.
            until = int(kwargs.get("until_time") or 1_753_434_000)
            n = 5
            items = [
                {
                    **_tweet(f"keep-{until}-{i}"),
                    "text": "DeepSeek just shipped a new model",
                    "created_at": "Sat Jul 25 12:00:00 +0000 2026",
                    "created_at_epoch": until - 10 - i,
                }
                for i in range(n)
            ]
            self.capture(items, kwargs)
            return items, True

    api = TruncatingApi()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: [call])
    monkeypatch.setattr(
        cycle_mod.XClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
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

    class CaptureApi(CapturingApi):
        def run_search(self, query, **kwargs):
            seen["max_results"] = kwargs.get("max_results")
            seen["max_pages"] = kwargs.get("max_pages")
            self.capture([], kwargs)
            return [], False

    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: [call])
    monkeypatch.setattr(
        cycle_mod.XClient,
        "from_env",
        classmethod(lambda cls, _purpose: CaptureApi()),
    )
    monkeypatch.setattr(
        CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
    )
    with override_settings(
        X_MONITOR_CYCLE_LIMIT_PER_CALL=50,
        X_MONITOR_CYCLE_MAX_PAGES_PER_CALL=5,
    ):
        CycleRunner(cycle_kind="scheduled").run()
    assert seen["max_results"] == 50, seen
    assert seen["max_pages"] == 5, seen


def test_truncated_empty_result_transfers_full_interval(wired, monkeypatch):
    """A truncated empty result preserves the full interval in the ledger.

    The non-truncation empty case advances (KTD5); the truncated empty case
    must NOT, for the same reason: 51st-and-older tweets exist but were not
    in this call's response.
    """
    from core.models import CallState, HarvestBacklogWindow

    call = _planned()

    class TruncatedEmpty(CapturingApi):
        def __init__(self):
            self.calls = []

        def run_search(self, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            self.capture([], kwargs)
            return [], True  # 0 items, truncated=True

    api = TruncatedEmpty()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: [call])
    monkeypatch.setattr(
        cycle_mod.XClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
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

    class CappedButExhausted(CapturingApi):
        def run_search(self, query, **kwargs):
            items = [
                {**_tweet(f"x-{i}"), "text": "DeepSeek does things",
                 "created_at": "Sat Jul 25 12:00:00 +0000 2026"}
                for i in range(50)
            ]
            self.capture(items, kwargs)
            return items, False  # 50 items, truncated=False (window exhausted)

    api = CappedButExhausted()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: [call])
    monkeypatch.setattr(
        cycle_mod.XClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
    )
    monkeypatch.setattr(
        CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {}, raising=False
    )
    CycleRunner(cycle_kind="scheduled").run()

    assert CallState.objects.filter(**_cursor_key(call)).exists(), (
        "the cap was hit but the window was exhausted -- advance is safe"
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_scheduled_provider_entities_reach_post_and_consumers(
    monkeypatch, seeded_policy_keywords, provider_tweet_entities, legacy,
):
    from core.models import Post
    from core.product_verification import source_repo_evidence
    from x_monitor.attribution import attribute_to_brands

    entities = provider_tweet_entities
    if legacy:
        entities["hashtags"][0]["tag"] = entities["hashtags"][0].pop("text")
        entities["user_mentions"][0]["id"] = entities["user_mentions"][0].pop("id_str")
        entities["user_mentions"][0]["username"] = entities["user_mentions"][0].pop("screen_name")
    body = {"tweets": [{"id": "99112233", "text": "@Alibaba_Qwen #Qwen https://t.co/example",
                        "createdAt": datetime.now(UTC).isoformat(), "entities": entities,
                        "author": {"id": "1002", "userName": "entity_test_author"}}],
            "has_next_page": False, "next_cursor": ""}
    monkeypatch.setenv("TWITTERAPI_IO_SCHEDULED_API_KEY", "test-scheduled-key")
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda *a, **kw: [_planned("B1", "qwen")])
    import json
    from types import SimpleNamespace
    response = SimpleNamespace(status_code=200, content=json.dumps(body).encode(),
                               text=json.dumps(body), json=lambda: body)
    requests = []
    def get(url, **kwargs):
        requests.append(url)
        return response
    monkeypatch.setattr("x_monitor.x_client.requests.get", get)
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda *a, **kw: {})
    stats = CycleRunner(cycle_kind="scheduled").run()
    assert stats["totals"]["n_inserted"] == 1
    assert requests.count("https://api.twitterapi.io/twitter/tweet/advanced_search") == 1
    assert set(requests) <= {"https://api.twitterapi.io/twitter/tweet/advanced_search",
                             "https://api.twitterapi.io/twitter/list/members"}
    post = Post.objects.get(pk="99112233")
    assert post.entities == entities
    assert source_repo_evidence(post, "Qwen/Qwen3-4B")["exact_hf_repo_link"]
    mentions = attribute_to_brands(
        {"tweet_id": post.pk, "created_at": post.created_at.isoformat(), "entities": post.entities},
        brands_accounts={"1001": "qwen"}, brand_hashtags={"qwen": "qwen"},
        compiled_keyword_index=(None, {}), search_query=[], brand_search_terms={},
    )
    assert {(m.brand_id, m.source) for m in mentions} == {("qwen", "user_mention"), ("qwen", "hashtag")}


@pytest.mark.parametrize("incomplete", [None, {}, "null", "[]", "bad json",
    {"urls": None}, {"urls": []}, {"urls": "broken"}, {"urls": [None, "broken", {}]},
    {"hashtags": [{"text": "newtag"}]},
    {"urls": [{"url": "https://t.co/example", "expanded_url": None}]},
])
def test_post_update_keeps_existing_entity_evidence(provider_tweet_entities, incomplete):
    from core.models import Post
    from monitor.cycle import _upsert_post
    post = Post.objects.create(tweet_id="entity-update", entities=provider_tweet_entities)
    _upsert_post({"id": post.pk, "entities": incomplete})
    post.refresh_from_db()
    assert provider_tweet_entities["urls"][0] in post.entities["urls"]
    assert provider_tweet_entities["hashtags"][0] in post.entities["hashtags"]
    assert provider_tweet_entities["user_mentions"][0] in post.entities["user_mentions"]


def test_post_update_adds_expansion_without_losing_positions():
    from core.models import Post
    from monitor.cycle import _upsert_post
    post = Post.objects.create(tweet_id="entity-expansion", entities={"urls": [
        {"url": "https://t.co/example", "indices": [0, 20]}]})
    incoming = {"urls": [{"url": "https://t.co/example", "expanded_url": "https://huggingface.co/Qwen/Qwen3-4B"}]}
    _upsert_post({"id": post.pk, "entities": incoming})
    _upsert_post({"id": post.pk, "entities": incoming})
    post.refresh_from_db()
    assert post.entities == {"urls": [{**incoming["urls"][0], "indices": [0, 20]}]}


@pytest.mark.django_db(transaction=True)
def test_concurrent_post_entity_updates_keep_both_observations(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections

    from core.models import Post
    from monitor import cycle

    Post.objects.create(tweet_id="entity-concurrent", entities={"urls": [{"url": "https://t.co/first"}]})
    merging, release, second_started, second_finished = Event(), Event(), Event(), Event()
    real_merge = cycle.merge_entities
    def merge(existing, incoming):
        result = real_merge(existing, incoming)
        if existing and "hashtags" in incoming:
            merging.set()
            assert release.wait(5), "test did not release first writer"
        return result
    monkeypatch.setattr(cycle, "merge_entities", merge)
    def write(entities, second=False):
        try:
            if second:
                second_started.set()
            cycle._upsert_post({"id": "entity-concurrent", "entities": entities})
            if second:
                second_finished.set()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write, {"hashtags": [{"text": "Qwen"}]})
        try:
            assert merging.wait(5)
            second = pool.submit(write, {"user_mentions": [{"id_str": "1001", "screen_name": "Qwen"}]}, True)
            assert second_started.wait(5)
            assert not second_finished.wait(0.2), "Post row lock ended before entity merge"
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    entities = Post.objects.get(pk="entity-concurrent").entities
    assert entities == {"urls": [{"url": "https://t.co/first"}],
                        "hashtags": [{"text": "Qwen"}],
                        "user_mentions": [{"id_str": "1001", "screen_name": "Qwen"}]}


def test_entity_update_preserves_repeated_url_positions_and_source_aliases():
    from monitor.cycle import _upsert_post
    first = {"url": "https://t.co/example", "indices": [0, 20]}
    second = {"url": "https://t.co/example", "indices": [25, 45]}
    post, created = _upsert_post({"id": "repeated-entities", "entities": {"urls": [first, second],
        "user_mentions": [{"id_str": "1001", "id": 1001, "screen_name": "Qwen"}]}})
    assert created
    assert post.entities["urls"] == [first, second]
    assert post.entities["user_mentions"][0] == {"id_str": "1001", "id": 1001, "screen_name": "Qwen"}
    _upsert_post({"id": post.pk, "entities": {"urls": [{**second, "expanded_url": "https://example.com"}]}})
    post.refresh_from_db()
    assert post.entities["urls"] == [first, {**second, "expanded_url": "https://example.com"}]
