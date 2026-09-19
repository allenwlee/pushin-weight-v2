import json

from scripts import u18_fresh40_v4_0731_adapted as adapted
from scripts import u18_fresh40_v4_0731_secondary_reviewer as subject


def decoded(payload):
    return {
        "model": subject.baseline.MODEL,
        "provider": subject.baseline.PROVIDER,
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
        "openrouter_metadata": {"endpoints": {"available": [{"provider": "DeepInfra", "selected": True}]}},
    }


def primary_rows(batch, post_types=None):
    values = post_types or ["opinions_reactions"]
    return [
        {
            "case_id": packet["case_id"],
            "by_brand": [
                {
                    "brand_id": brand_id,
                    "outcome": "classified",
                    "post_types": list(values),
                    "audience_topics": ["none"],
                }
                for brand_id in packet["brand_ids"]
            ],
            "untracked_brand_promotions": ["none"],
        }
        for packet in batch
    ]


def test_reviewer_sees_primary_types_and_uses_same_pinned_route():
    batch = subject.sol.packets()[:2]
    body = subject.reviewer_request(batch, primary_rows(batch))

    assert body["provider"]["only"] == ["DeepInfra"]
    assert body["provider"]["allow_fallbacks"] is False
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert "response_format" not in body
    assert "primary_post_types" in body["messages"][1]["content"]
    assert "owner" not in body["messages"][1]["content"].lower()


def test_reviewer_accepts_only_new_concrete_post_types():
    batch = subject.sol.packets()[:2]
    rows = primary_rows(batch)
    decisions, _ = adapted.slot_map(batch)
    payload = {
        "decisions": {
            slot: {"additional_post_types": ["results_evaluations"]}
            for slot in decisions
        }
    }
    additions, issues = subject.parse_reviewer(decoded(payload), batch, rows)

    assert set(additions) == {
        (packet["case_id"], brand_id)
        for packet in batch
        for brand_id in packet["brand_ids"]
    }
    assert all(value == ["results_evaluations"] for value in additions.values())
    assert issues == []

    first_slot = next(iter(decisions))
    payload["decisions"][first_slot]["additional_post_types"] = ["opinions_reactions"]
    try:
        subject.parse_reviewer(decoded(payload), batch, rows)
    except ValueError as exc:
        assert "repeated primary type" in str(exc)
    else:
        raise AssertionError("a repeated primary type was accepted")


def test_reviewer_normalizes_exact_slots_at_json_root():
    batch = subject.sol.packets()[:2]
    rows = primary_rows(batch)
    decisions, _ = adapted.slot_map(batch)
    payload = {slot: {"additional_post_types": []} for slot in decisions}

    additions, issues = subject.parse_reviewer(decoded(payload), batch, rows)

    assert all(value == [] for value in additions.values())
    assert issues == [{"issue": "root_decision_slots_wrapped"}]


def test_additions_union_with_primary_and_remove_residual_other():
    batch = subject.sol.packets()[:1]
    rows = primary_rows(batch, ["other"])
    additions = {
        (packet["case_id"], brand_id): ["events", "opportunities"]
        for packet in batch
        for brand_id in packet["brand_ids"]
    }

    final_rows, ledger = subject.apply_additions(rows, additions)

    assert final_rows[0]["by_brand"][0]["post_types"] == ["events", "opportunities"]
    assert ledger[0]["before"] == ["other"]
    assert ledger[0]["added"] == ["events", "opportunities"]


def test_timing_adds_sequential_reviewer_after_parallel_primary():
    result = {
        "measurements": [
            {"batch": 1, "role": "content", "latency_ms": 10_000},
            {"batch": 1, "role": "brand", "latency_ms": 8_000},
            {"batch": 1, "role": "post_type_review", "latency_ms": 4_000},
            {"batch": 2, "role": "content", "latency_ms": 7_000},
            {"batch": 2, "role": "brand", "latency_ms": 9_000},
            {"batch": 2, "role": "post_type_review", "latency_ms": 3_000},
        ]
    }

    timing = subject.reviewer_timing(result)

    assert timing["measured_call_seconds"] == 41.0
    assert timing["estimated_primary_parallel_plus_review_seconds"] == 26.0
