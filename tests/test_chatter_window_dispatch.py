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
