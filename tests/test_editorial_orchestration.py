from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from core.models import EditorialAssessment, EditorialEdition
from monitor.editorial.service import run_editorial
from tests.editorial_support import active_config

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_editor_publishes_two_angles_and_reuses_unchanged_evidence(monkeypatch):
    from core.models import Post

    post = Post.objects.create(
        tweet_id="100",
        text="A company releases a major model.",
        created_at=timezone.now() - timedelta(minutes=2),
    )
    calls = []

    def call(assessment, stage, route, request, cfg):
        calls.append(stage)
        if stage.startswith("editor"):
            data = {
                "events": [
                    {
                        "key": "release-1",
                        "summary": "A company releases a major model.",
                        "post_ids": ["100"],
                        "occurred_at": post.created_at.isoformat(),
                        "chatter": True,
                        "pulse": True,
                        "importance": 90,
                        "reason": "Major release",
                    }
                ]
            }
        else:
            track = "chatter" if "chatter" in stage else "pulse"
            data = {
                "headline": "MODEL BEHAVIOR"
                if track == "chatter"
                else "Company releases new model",
                "byline": "A release for developers.",
                "article": "The company announced a new model.",
                "locale": "en",
                "post_ids": ["100"],
            }
        return {"data": data, "model": "test", "usage": {}}

    cfg = active_config(pictures={})
    now = timezone.now()
    envelope = {
        "schema_version": 1,
        "completed_at": now.isoformat(),
        "source_cycle_id": "1",
        "outcome": "completed",
        "dry_run": False,
    }
    result = run_editorial(envelope, cfg=cfg, call=call)
    assert result["published"] == 2, result
    assert EditorialEdition.objects.count() == 2
    assert len(calls) == 3
    assert run_editorial(envelope, cfg=cfg, call=call)["status"] == "already_claimed"
    # Re-evaluate the same source packet in the next claimed interval without time travel.
    EditorialAssessment.objects.update(
        interval=now - timedelta(minutes=20), cutoff=now - timedelta(minutes=20)
    )
    result = run_editorial(envelope, cfg=cfg, call=call)
    assert result["status"] == "unchanged"
    assert len(calls) == 3


def test_production_harvest_dispatch_reaches_g2_when_legacy_headlines_are_off(
    monkeypatch,
):
    from monitor.editorial import dispatch
    from monitor.trend_narrative_dispatch import dispatch_harvest_completion

    task = Mock()
    monkeypatch.setattr(
        dispatch, "load_editorial_config", lambda: active_config(pictures={})
    )
    monkeypatch.setattr(dispatch, "editorial_task", lambda: task)
    monkeypatch.setattr(
        "monitor.trend_narrative_dispatch.load_config",
        lambda _: type(
            "Config",
            (),
            {"headline_narrative": type("Legacy", (), {"enqueue_active": False})()},
        )(),
    )
    stats = {
        "run_id": "cycle",
        "finished_at": timezone.now().isoformat(),
        "status": "completed",
    }
    assert dispatch_harvest_completion(stats, dry_run=False).status == "disabled"
    assert task.apply_async.call_count == 1
    assert task.apply_async.call_args.kwargs["queue"] == "trend-narratives"
    dispatch_harvest_completion(stats, dry_run=True)
    assert task.apply_async.call_count == 1


def test_stale_publication_cannot_replace_a_newer_hero():
    from core.models import EditorialHero
    from monitor.editorial.contracts import Copy
    from monitor.editorial.persistence import claim_assessment
    from monitor.editorial.service import publish_edition
    from monitor.editorial.voices import load_voice
    from tests.test_editorial_selection import event
    from tests.test_editorial_views import edition

    current = edition("CURRENT HERO")
    EditorialHero.objects.create(key="chatter:en", edition=current)
    old = claim_assessment(timezone.now() - timedelta(minutes=30), "late-worker")
    result = publish_edition(
        old,
        event(old.cutoff, importance=100),
        {"cutoff": old.cutoff.isoformat(), "posts": []},
        "chatter",
        load_voice("chatter-en-v1"),
        Copy(
            headline="STALE",
            byline="Stale",
            article="Stale",
            locale="en",
            post_ids=["1"],
        ),
        "test",
        active_config(pictures={}),
    )
    assert result is None
    assert EditorialHero.objects.get(key="chatter:en").edition_id == current.pk
