import json

import pytest
from django.utils import timezone

from monitor.editorial.config import EditorialConfig, Route
from monitor.editorial.contracts import Event
from monitor.editorial.voices import load_voice
from monitor.editorial.writing import validate_copy, writer_request


def test_writer_reads_original_evidence_and_profile_without_few_shot_examples():
    now = timezone.now()
    e = Event(
        key="outfit",
        summary="A price correction",
        post_ids=["1"],
        occurred_at=now,
        chatter=True,
        pulse=False,
        importance=70,
        reason="Human interest",
    )
    packet = {"posts": [{"id": "1", "original_text": "原文", "images": []}]}
    req = writer_request(e, packet, load_voice("chatter-en-v1"), EditorialConfig())
    assert "New York Post" in req["system"]
    assert "原文" in req["user"]
    assert "THE PRICE IS WANG" not in req["system"]
    assert "visual_brief" not in json.loads(req["user"])["output_schema"]["required"]
    with pytest.raises(ValueError):
        validate_copy(
            {
                "headline": "A",
                "byline": "B",
                "article": "C",
                "locale": "en",
                "post_ids": ["unknown"],
            },
            e,
            "en",
        )


def test_essential_image_is_passed_to_vision_route_and_text_route_holds():
    from monitor.editorial.providers import request_payload

    e = Event(
        key="outfit",
        summary="A price correction",
        post_ids=["1"],
        occurred_at=timezone.now(),
        chatter=True,
        pulse=False,
        importance=70,
        reason="Human interest",
        visual_essential=True,
        source_image_url="https://pbs.twimg.com/media/a.jpg",
    )
    req = writer_request(
        e,
        {"posts": [{"id": "1", "images": [e.source_image_url]}]},
        load_voice("chatter-en-v1"),
        EditorialConfig(),
    )
    route = Route(
        model="explicit",
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        key_env="OPENROUTER_API_KEY",
        input_usd_per_million=1,
        output_usd_per_million=1,
    )
    with pytest.raises(ValueError, match="vision"):
        request_payload(route, req)
    payload = request_payload(route.model_copy(update={"vision": True}), req)
    assert (
        payload["messages"][1]["content"][1]["image_url"]["url"] == e.source_image_url
    )
    assert payload["provider"] == {
        "allow_fallbacks": False,
        "require_parameters": True,
        "max_price": {"prompt": 1, "completion": 1},
    }
