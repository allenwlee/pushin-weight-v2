from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from monitor.editorial.config import EditorialConfig
from monitor.editorial.contracts import Event
from monitor.editorial.selection import should_replace, validate_decisions


def event(now, **kwargs):
    data = {
        "key": "release-1",
        "summary": "A release",
        "post_ids": ["1"],
        "brand_keys": ["deepseek"],
        "occurred_at": now,
        "chatter": True,
        "pulse": True,
        "importance": 50,
        "reason": "Important release",
    }
    data.update(kwargs)
    return Event(**data)


def test_aged_incumbent_can_lose_but_no_worthy_event_retains_it():
    now = timezone.now()
    hero = SimpleNamespace(importance=90, occurred_at=now - timedelta(hours=6))
    cfg = EditorialConfig()
    assert should_replace(event(now, importance=60), hero, now, cfg)
    assert not should_replace(event(now, importance=60, chatter=False), hero, now, cfg)
    hero.occurred_at = now
    assert not should_replace(event(now, importance=60), hero, now, cfg)


def test_no_chart_support_never_excludes_news_and_unknown_sources_are_rejected():
    now = timezone.now()
    packet = {
        "cutoff": now.isoformat(),
        "posts": [{"id": "1", "brand_keys": ["deepseek"], "images": []}],
        "people": [],
        "stories": [],
    }
    result = validate_decisions(
        {"events": [event(now).model_dump(mode="json")]}, packet
    )
    assert result.events[0].pulse
    assert result.events[0].chart_support == "unavailable"
    with pytest.raises(ValueError, match="unknown source"):
        validate_decisions(
            {"events": [event(now, post_ids=["invented"]).model_dump(mode="json")]},
            packet,
        )


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_packet_cutoff_excludes_late_fetches_and_preserves_original_media():
    from core.models import Post
    from monitor.editorial.evidence import build_packet

    now = timezone.now()
    post = Post.objects.create(
        tweet_id="1",
        text="Original 日本語",
        created_at=now - timedelta(hours=1),
        extended_entities={
            "media": [
                {
                    "type": "photo",
                    "media_url_https": "https://pbs.twimg.com/media/a.jpg",
                }
            ]
        },
    )
    Post.objects.filter(pk=post.pk).update(fetched_at=now - timedelta(minutes=1))
    Post.objects.create(
        tweet_id="late", text="Future fetch", created_at=now - timedelta(hours=1)
    )
    packet = build_packet(now, EditorialConfig())
    assert [p["id"] for p in packet["posts"]] == ["1"]
    assert packet["posts"][0]["original_text"] == "Original 日本語"
    assert packet["posts"][0]["images"] == ["https://pbs.twimg.com/media/a.jpg"]


def test_owner_fixture_preserves_explicit_and_defaulted_judgments():
    import json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).parent / "fixtures/editorial_owner_review.json").read_text()
    )
    assert len(data["cases"]) == 54
    assert sum(c["chatter"] for c in data["cases"]) == 18
    assert sum(c["pulse"] for c in data["cases"]) == 21
    assert sum(c["chatter"] and c["pulse"] for c in data["cases"]) == 12
    assert "remainder are not headline worthy" in data["default_rule"]
