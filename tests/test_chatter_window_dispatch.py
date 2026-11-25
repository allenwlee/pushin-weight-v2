"""The rolling workers consume archived X receipts and never repeat paid decisions."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from core.models import CollectionRequest, OriginalContentCall, OriginalContentRun
from monitor.editorial.chatter_trends import (
    CAPTURE_SCOPE,
    DECISION_SCOPE,
    checkpoint,
    read_ranked_batch,
    reserve_due_slot,
)
from monitor.editorial.chatter_window_runs import decide_window
from monitor.editorial.config import ChatterTrial
from monitor.editorial.dispatch import dispatch_chatter_due_slot
from tests.test_chatter_trends import (
    discover,
    official_response,
    rank_wire,
    trends_config,
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

BOUNDARY = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)


@pytest.fixture
def rolling(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture")
    cfg = trends_config()
    return cfg.model_copy(
        update={
            "chatter": cfg.chatter.model_copy(
                update={"discovery_lane": "personalized-trends-v2"}
            )
        }
    )


def ranking(n):
    code, body = rank_wire(n)
    wire = json.loads(body)
    text = wire["choices"][0]["message"]
    rows = json.loads(text["content"])["ranked_stories"]
    for row in rows:
        row.update(qualifies=True, prior_episode_id=None, material_change=None)
    text["content"] = json.dumps({"ranked_stories": rows})
    return code, json.dumps(wire).encode()


def slot(cfg, at, scope):
    return reserve_due_slot(
        at.isoformat(), at, cfg=cfg, purpose="scheduled", scope=scope
    )[0]


def test_fifty_dollar_trial():
    assert (
        ChatterTrial(scope="chatter-window", limit_usd=50, carry_usd=21).limit_usd == 50
    )
    with pytest.raises(ValueError):
        ChatterTrial(scope="chatter-window", limit_usd=51, carry_usd=0)


def test_quarter_capture_and_half_hour_owner(rolling):
    with patch("django.utils.timezone.now", return_value=BOUNDARY):
        task = Mock()
        first = dispatch_chatter_due_slot(
            "a", BOUNDARY, cfg=rolling, task=task, purpose="scheduled"
        )
        again = dispatch_chatter_due_slot(
            "b", BOUNDARY, cfg=rolling, task=task, purpose="scheduled"
        )
        assert (first["run_id"], first["decision_run_id"]) == (
            again["run_id"],
            again["decision_run_id"],
        )
    with patch(
        "django.utils.timezone.now", return_value=BOUNDARY + timedelta(minutes=15)
    ):
        second = dispatch_chatter_due_slot(
            "c",
            BOUNDARY + timedelta(minutes=15),
            cfg=rolling,
            task=task,
            purpose="scheduled",
        )
    assert second["decision_run_id"] is None and second["run_id"] != first["run_id"]
    assert OriginalContentRun.objects.filter(scope_key=CAPTURE_SCOPE).count() == 2


def test_completed_capture_wakes_coincident_decision_through_worker_dispatch(rolling, django_capture_on_commit_callbacks):
    from monitor.editorial.chatter_chain import run_chatter
    from monitor.editorial.chatter_trends import envelope_for

    with patch("django.utils.timezone.now", return_value=BOUNDARY + timedelta(minutes=1)):
        capture = slot(rolling, BOUNDARY, CAPTURE_SCOPE)
        decision = slot(rolling, BOUNDARY, DECISION_SCOPE)
        captured, official, unused = discover(capture, rolling, official_response(1))
        assert captured["status"] == "captured" and official.call_count == 1 and not unused.called
        with patch("monitor.tasks.chatter_stage") as task, django_capture_on_commit_callbacks(execute=True):
            result = run_chatter(envelope_for(capture), cfg=rolling)
        assert result["status"] == "captured"
        task.apply_async.assert_called_once_with(args=["discover", envelope_for(decision)],
            queue="trend-narratives", expires=900, countdown=0, priority=0)


def test_freeze_and_drain_without_paid_replay(rolling):
    now = BOUNDARY + timedelta(minutes=1)
    with patch("django.utils.timezone.now", return_value=now):
        capture, decision = (
            slot(rolling, BOUNDARY, CAPTURE_SCOPE),
            slot(rolling, BOUNDARY, DECISION_SCOPE),
        )
        assert decide_window(decision.pk)["status"] == "waiting_capture"
        captured, physical, unused = discover(capture, rolling, official_response(3))
        assert (
            captured["status"] == "captured"
            and physical.call_count == 1
            and not unused.called
        )
        transport = Mock(return_value=ranking(3))
        assert decide_window(decision.pk, transport=transport)["status"] == "ranked"
        assert decide_window(decision.pk, transport=transport)["status"] == "ranked"
        batch = read_ranked_batch(decision.pk)
        assert [r["rank"] for r in batch["leads"]] == [
            1,
            2,
        ] and transport.call_count == 1
        decision.refresh_from_db()
        assert (
            checkpoint(decision).freeze_at == now
            and len(checkpoint(decision).missing_slots) == 3
        )
    with patch(
        "django.utils.timezone.now", return_value=BOUNDARY + timedelta(minutes=36)
    ):
        next_run = slot(rolling, BOUNDARY + timedelta(minutes=30), DECISION_SCOPE)
        forbidden = Mock(side_effect=AssertionError("unexpected paid call"))
        assert decide_window(next_run.pk, transport=forbidden)["status"] == "ranked"
        second = read_ranked_batch(next_run.pk)
        assert [r["title"] for r in second["leads"]] == ["Story 3"]
        assert second["leads"][0]["rank_call_id"] == batch["rank_call_id"]
        from core.models import Post
        from monitor.editorial.chatter_gathering import gather_trends

        Post.objects.create(
            tweet_id="739331",
            text="Original headline 3 confirmed by the lab.",
            author_handle="reporter",
            lang="en",
            created_at=BOUNDARY,
        )
        assert (
            gather_trends(next_run.pk, cfg=rolling, x_client=forbidden)["status"]
            == "discovered"
        )
        appearance = next_run.brand_narratives.get(appearance_kind="personalized_trend")
        assert appearance.discovery_call_id == batch["rank_call_id"]
        assert appearance.selection["episode_id"] == second["leads"][0]["episode_id"]
        assert not forbidden.called
    assert (
        CollectionRequest.objects.count() == 1
        and OriginalContentCall.objects.count() == 1
    )


@pytest.mark.parametrize(
    "status,code",
    [(401, "official_authentication_failed"), (429, "official_rate_limited")],
)
def test_rejected_capture_freezes_as_missing_and_is_not_a_healthy_evaluation(
    rolling, status, code
):
    from monitor.editorial.chatter_gathering import gather_trends

    now = BOUNDARY + timedelta(minutes=1)
    with patch("django.utils.timezone.now", return_value=now):
        capture, decision = (
            slot(rolling, BOUNDARY, CAPTURE_SCOPE),
            slot(rolling, BOUNDARY, DECISION_SCOPE),
        )
        outcome, _, _ = discover(capture, rolling, official_response(0, status=status))
        assert outcome["error_code"] == code
        forbidden = Mock(side_effect=AssertionError("unexpected rank"))
        assert decide_window(decision.pk, transport=forbidden)["status"] == "empty"
        assert gather_trends(decision.pk, cfg=rolling)["status"] == "empty"
        decision.refresh_from_db()
        state = checkpoint(decision)
        assert state.freeze_at == now and len(state.missing_slots) == 4
        assert not decision.outcome.get("healthy_at") and not forbidden.called


def test_late_observation_does_not_reopen_a_frozen_window(rolling):
    with patch(
        "django.utils.timezone.now", return_value=BOUNDARY + timedelta(minutes=6)
    ):
        capture, decision = (
            slot(rolling, BOUNDARY, CAPTURE_SCOPE),
            slot(rolling, BOUNDARY, DECISION_SCOPE),
        )
        forbidden = Mock(side_effect=AssertionError("unexpected rank"))
        assert decide_window(decision.pk, transport=forbidden)["status"] == "empty"
        assert (
            discover(capture, rolling, official_response(2))[0]["status"] == "captured"
        )
        assert read_ranked_batch(decision.pk)["headlines"] == []
        assert not forbidden.called


def test_unknown_ranking_is_held_without_automatic_duplicate(rolling):
    with patch(
        "django.utils.timezone.now", return_value=BOUNDARY + timedelta(minutes=1)
    ):
        capture, decision = (
            slot(rolling, BOUNDARY, CAPTURE_SCOPE),
            slot(rolling, BOUNDARY, DECISION_SCOPE),
        )
        assert (
            discover(capture, rolling, official_response(2))[0]["status"] == "captured"
        )
        transport = Mock(side_effect=TimeoutError("fixture lost reply"))
        assert decide_window(decision.pk, transport=transport)["status"] == "held"
        assert decide_window(decision.pk, transport=transport)["status"] == "held"
        assert transport.call_count == 1


@pytest.mark.parametrize("expires", [False, True])
def test_presend_contention_retries_frozen_decision_only_before_next_boundary(
    rolling, django_capture_on_commit_callbacks, expires
):
    from tests.test_graphics_accounting import make_run, reserve

    now = BOUNDARY + timedelta(minutes=1)
    ranker = Mock(return_value=ranking(2))
    with patch("django.utils.timezone.now", return_value=now):
        capture = slot(rolling, BOUNDARY, CAPTURE_SCOPE)
        decision = slot(rolling, BOUNDARY, DECISION_SCOPE)
        assert (
            discover(capture, rolling, official_response(2))[0]["status"] == "captured"
        )
        blocker, _ = reserve(make_run())
        with (
            patch("monitor.tasks.chatter_stage") as task,
            django_capture_on_commit_callbacks(execute=True),
        ):
            waiting = decide_window(decision.pk, transport=ranker)
            assert waiting["status"] == "waiting_capacity"
            assert decide_window(decision.pk, transport=ranker) == waiting
        task.apply_async.assert_called_once()
        assert task.apply_async.call_args.kwargs["countdown"] == 60
        assert not ranker.called and not decision.provider_calls.exists()
        decision.refresh_from_db()
        frozen = checkpoint(decision)
    later = BOUNDARY + timedelta(minutes=30) if expires else now + timedelta(minutes=1)
    with patch("django.utils.timezone.now", return_value=later):
        blocker.delete()
        result = decide_window(decision.pk, transport=ranker)
        if expires:
            assert result["error_code"] == "ranking_capacity_expired"
            assert not ranker.called and not decision.provider_calls.exists()
        else:
            assert result["status"] == "ranked" and ranker.call_count == 1
        decision.refresh_from_db()
        assert checkpoint(decision).manifest == frozen.manifest
        assert checkpoint(decision).freeze_at == frozen.freeze_at


def test_financial_hold_before_send_never_schedules_capacity_retry(
    rolling, django_capture_on_commit_callbacks
):
    from monitor.editorial.persistence import BudgetHeld

    with patch(
        "django.utils.timezone.now", return_value=BOUNDARY + timedelta(minutes=1)
    ):
        capture, decision = (
            slot(rolling, BOUNDARY, CAPTURE_SCOPE),
            slot(rolling, BOUNDARY, DECISION_SCOPE),
        )
        assert (
            discover(capture, rolling, official_response(2))[0]["status"] == "captured"
        )
        with (
            patch(
                "monitor.editorial.chatter_accounting.admit",
                side_effect=BudgetHeld("budget exhausted"),
            ),
            patch("monitor.tasks.chatter_stage") as task,
            django_capture_on_commit_callbacks(execute=True),
        ):
            assert decide_window(decision.pk, transport=Mock())["status"] == "held"
            assert decide_window(decision.pk, transport=Mock())["status"] == "held"
        assert not task.apply_async.called and not decision.provider_calls.exists()


@pytest.mark.parametrize("standing", [False, True])
def test_recovery_only_notifies_matching_trial_or_standing_scope(rolling, standing):
    from monitor.editorial.dispatch import recover_chatter_starts

    other_trial = rolling.chatter.trial.model_copy(
        update={"scope": "chatter-other-watch"}
    )
    other = rolling.model_copy(
        update={"chatter": rolling.chatter.model_copy(update={"trial": other_trial})}
    )
    regular = rolling.model_copy(
        update={"chatter": rolling.chatter.model_copy(update={"trial": None})}
    )
    with patch("django.utils.timezone.now", return_value=BOUNDARY):
        same = slot(rolling, BOUNDARY, DECISION_SCOPE)
        slot(other, BOUNDARY - timedelta(minutes=30), DECISION_SCOPE)
        no_trial = slot(regular, BOUNDARY - timedelta(minutes=60), DECISION_SCOPE)
        with patch(
            "monitor.editorial.dispatch._enqueue_chatter_start", return_value=True
        ) as enqueue:
            assert recover_chatter_starts(
                cfg=regular if standing else rolling, task=Mock()
            ) == {"enqueued": 1}
        assert enqueue.call_count == 1 and enqueue.call_args.args[0].pk == (
            no_trial.pk if standing else same.pk
        )


def test_abandoned_foreign_trial_does_not_stall_a_new_decision(rolling):
    other = rolling.model_copy(
        update={"chatter": rolling.chatter.model_copy(update={"trial": None})}
    )
    with patch(
        "django.utils.timezone.now", return_value=BOUNDARY + timedelta(minutes=6)
    ):
        previous = slot(other, BOUNDARY - timedelta(minutes=30), DECISION_SCOPE)
        current = slot(rolling, BOUNDARY, DECISION_SCOPE)
        assert decide_window(current.pk, transport=Mock())["status"] == "empty"
        previous.refresh_from_db()
        assert checkpoint(previous).phase == "queued"


def test_unpublished_failed_or_finished_admissions_can_reopen(monkeypatch):
    from types import SimpleNamespace
    from monitor.editorial.chatter_window_runs import _reopen_unpublished_episodes

    cutoff = BOUNDARY + timedelta(hours=1)
    previous = SimpleNamespace(interval=BOUNDARY, outcome={"window_result": {"history": {
        "admitted": [{"episode_id": value} for value in ("failed", "failed2", "passed", "published", "active", "unknown", "evidence-only")]
    }}})
    def owner(identity, phase, execution, lease):
        return SimpleNamespace(pk=identity, outcome={"phase": phase, "window_result": {
            "admissions": [{"episode_id": identity}]}}, execution_state=execution, lease_until=lease)
    owners = [owner("failed", "held", "running", cutoff + timedelta(minutes=1)),
              owner("passed", "complete", "completed", cutoff),
              owner("published", "complete", "completed", cutoff),
              owner("active", "discovered", "running", cutoff + timedelta(minutes=1))]
    published_query = Mock()
    published_query.values_list.return_value = ["published"]
    monkeypatch.setattr("monitor.editorial.chatter_window_runs.OriginalContent.objects.filter", Mock(return_value=published_query))
    owners[0].outcome["window_result"]["admissions"].append({"episode_id": "failed2"})
    owners[1].outcome["window_result"]["admissions"].append({"episode_id": "evidence-only"})
    owners[1].outcome["covered_episode_ids"] = ["evidence-only"]
    unresolved = Mock(return_value=False)
    monkeypatch.setattr("monitor.editorial.chatter_window_runs._admission_has_unresolved_work", unresolved)
    run_query = Mock()
    run_query.order_by.return_value.only.return_value = owners
    monkeypatch.setattr("monitor.editorial.chatter_window_runs.OriginalContentRun.objects.filter", Mock(return_value=run_query))
    assert _reopen_unpublished_episodes(previous, cutoff) == ["failed", "failed2", "passed"]
    assert unresolved.call_count == 2
    assert _reopen_unpublished_episodes(None, cutoff) == []


def test_reopened_admission_is_not_reintroduced_by_selected_snapshot():
    from types import SimpleNamespace
    from monitor.editorial.chatter_window_runs import _admitted_after_reopening

    selected = [SimpleNamespace(episode_id="failed", title="Failed", selected_at=BOUNDARY, wordings=[]),
                SimpleNamespace(episode_id="live", title="Live", selected_at=BOUNDARY, wordings=[])]
    history = {"admitted": [{"episode_id": "failed"}, {"episode_id": "live"}]}
    current = _admitted_after_reopening(history, selected, ["failed"])
    legacy = _admitted_after_reopening(history, selected, None)
    assert [row["episode_id"] for row in current] == ["live"]
    assert {row["episode_id"] for row in legacy} == {"failed", "live"}


def test_uncertain_provider_or_running_graphics_blocks_readmission(monkeypatch):
    from types import SimpleNamespace
    from monitor.editorial.chatter_window_runs import _admission_has_unresolved_work

    calls = Mock()
    graphics = Mock()
    monkeypatch.setattr("monitor.editorial.chatter_sources.source_resume_is_safe", lambda _: True)
    monkeypatch.setattr("monitor.editorial.chatter_window_runs.OriginalContentCall.objects.filter", calls)
    monkeypatch.setattr("monitor.editorial.chatter_window_runs.OriginalContentRun.objects.filter", graphics)
    run = SimpleNamespace(pk=123)
    calls.return_value.exists.return_value = True
    assert _admission_has_unresolved_work(run)
    graphics.assert_not_called()
    calls.return_value.exists.return_value = False
    graphics.return_value.exists.return_value = True
    assert _admission_has_unresolved_work(run)
    graphics.return_value.exists.return_value = False
    assert not _admission_has_unresolved_work(run)
