import json

from scripts import u18_fresh40_v4_0731_adapted as adapted
from scripts import u18_fresh40_v4_0731_three_role as subject


def decoded(payload):
    return {
        "model": subject.baseline.MODEL,
        "provider": subject.baseline.PROVIDER,
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
        "openrouter_metadata": {"endpoints": {"available": [{"provider": "DeepInfra", "selected": True}]}},
    }


def test_requests_split_axes_and_keep_same_route():
    batch = subject.sol.packets()[:2]
    bodies = {role: subject.request(batch, role) for role in ("types", "topics", "brand")}
    assert all("response_format" not in body for body in bodies.values())
    assert all(body["provider"]["only"] == ["DeepInfra"] for body in bodies.values())
    assert '"outcome"' in bodies["types"]["messages"][0]["content"]
    assert '"audience_topics"' in bodies["topics"]["messages"][0]["content"]
    assert '"product_labels"' in bodies["brand"]["messages"][0]["content"]


def test_type_and_topic_rows_merge_into_existing_content_shape():
    batch = subject.sol.packets()[:2]
    decisions, posts = adapted.slot_map(batch)
    types_payload = {"decisions": {slot: {"outcome": "classified", "post_types": ["opinions_reactions"]} for slot in decisions}}
    topics_payload = {
        "decisions": {slot: {"audience_topics": []} for slot in decisions},
        "post_promotions": {slot: [] for slot in posts},
    }
    type_rows, _, _ = subject.parse(decoded(types_payload), batch, "types")
    topic_rows, _, changes = subject.parse(decoded(topics_payload), batch, "topics")

    rows = subject.merge_content(type_rows, topic_rows)

    assert len(rows) == 2
    assert rows[0]["by_brand"][0]["post_types"] == ["opinions_reactions"]
    assert rows[0]["by_brand"][0]["audience_topics"] == ["none"]
    assert rows[0]["untracked_brand_promotions"] == ["none"]
    assert len(changes) == len(decisions) + len(posts)


def test_fixed_slots_are_still_required_in_each_narrow_role():
    batch = subject.sol.packets()[:2]
    decisions, _ = adapted.slot_map(batch)
    values = {slot: {"outcome": "classified", "post_types": ["other"]} for slot in decisions}
    values.pop(next(iter(values)))

    try:
        subject.parse(decoded({"decisions": values}), batch, "types")
    except ValueError as exc:
        assert "fixed decision slots missing or extra" in str(exc)
    else:
        raise AssertionError("missing decision slot was accepted")
