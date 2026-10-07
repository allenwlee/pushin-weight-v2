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


def test_editor_and_writer_use_existing_rules_short_sources_and_owned_passages():
    from monitor.editorial.grounding import restore_sources, source_spans
    from monitor.editorial.writing import editor_request
    from monitor.headline_grounding import SOURCE_READING_RULES

    now = timezone.now()
    source = {
        "id": "2106383170857791527",
        "original_text": "FlashX is available on a platform.",
        "stored_quote": "Quoted speaker's claim",
        "images": [],
        "brand_keys": ["glm"],
    }
    packet = {
        "posts": [source],
        "context": [],
        "stories": [],
        "people": [],
        "cutoff": now.isoformat(),
    }
    req = editor_request(packet, EditorialConfig())
    body = json.loads(req["user"])
    assert SOURCE_READING_RULES in req["system"]
    assert "Neither is a valid choice" not in req["system"]
    assert body["evidence"]["posts"][0]["id"] == "S001"
    assert "stored_quote" in {
        row["source_field"] for row in body["evidence"]["posts"][0]["source_spans"]
    }
    assert "post_ids" not in body["output_schema"]["$defs"]["Event"]["properties"]
    restored = restore_sources(
        {"events": [{"post_ids": ["S001"], "source_check": [{"post_id": "S001"}]}]},
        req["source_ids"],
    )
    assert restored["events"][0]["post_ids"] == [source["id"]]
    assert restored["events"][0]["source_check"][0]["post_id"] == source["id"]
    e = Event(
        key="availability",
        summary="Availability",
        post_ids=[source["id"]],
        occurred_at=now,
        chatter=False,
        pulse=True,
        importance=20,
        reason="Availability",
    )
    writer = writer_request(e, packet, load_voice("pulse-en-v1"), EditorialConfig())
    assert SOURCE_READING_RULES in writer["system"]
    assert json.loads(writer["user"])["event"]["post_ids"] == ["S001"]
    claim = {
        "post_id": source["id"],
        "span_ids": [source_spans(source)[0]["span_id"]],
        "actor": "A platform",
        "action": "offers",
        "target": "FlashX",
        "status": "source_report",
    }
    copy = {
        "headline": "FlashX availability",
        "byline": "A platform offers FlashX",
        "article": "Source reports availability",
        "locale": "en",
        "post_ids": [source["id"]],
        "source_check": [claim],
    }
    assert validate_copy(copy, e, "en", packet=packet).source_check
    copy["source_check"][0]["span_ids"] = ["s:invented"]
    with pytest.raises(ValueError, match="unowned passage"):
        validate_copy(copy, e, "en", packet=packet)
