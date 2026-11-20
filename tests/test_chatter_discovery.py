"""Discovery is fresh evidence; a selector must account for every candidate and pool."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone


def candidate():
    ref = str(uuid4())
    return {"candidate_ref": ref, "post_ids": ["123"], "eligible": True}


def selection(row):
    from monitor.editorial.chatter_discovery import POOLS

    return {
        "candidate_tags": [
            {
                "candidate_ref": row["candidate_ref"],
                "dominant_source_language": "en",
                "editorial_group": "rest",
                "pool_ref": "en-rest",
                "language_evidence_ref": "language:" + row["candidate_ref"],
                "language_reason": "The supplied source text is English.",
                "group_policy_ref": "giants:test",
                "primary_subjects": ["A small lab"],
                "group_evidence_post_ids": ["123"],
                "group_reason": "The primary subject is outside the giant set.",
                "classification_notes": [],
            }
        ],
        "group_decisions": [
            {
                "scope_ref": pool,
                "ranked_candidates": (
                    [
                        {
                            "candidate_ref": row["candidate_ref"],
                            "rank": 1,
                            "outcome": "selected",
                            "reason": "A supported development merits a lead.",
                            "measurement_refs": [],
                            "history_refs": [],
                            "asset_refs": [],
                        }
                    ]
                    if pool == "en-rest"
                    else []
                ),
                "lead_action": "publish" if pool == "en-rest" else "none",
                "lead_ref": row["candidate_ref"] if pool == "en-rest" else None,
                "incumbent_ref": None,
                "reason": "A supported story leads."
                if pool == "en-rest"
                else "No eligible source story.",
                "gaps": [],
            }
            for pool in POOLS
        ],
        "coverage_notes": [],
        "history_requests": [],
    }


def test_selector_accounts_for_six_pools_without_borrowing_a_lead():
    from monitor.editorial.chatter_discovery import validate_selection

    row = candidate()
    result = selection(row)
    assert validate_selection(result, [row], {}, "giants:test") == result
    result["group_decisions"][0].update(
        lead_action="publish", lead_ref=row["candidate_ref"]
    )
    with pytest.raises(ValueError, match="pool"):
        validate_selection(result, [row], {}, "giants:test")


def test_selector_must_explain_every_passed_over_candidate_and_classify_all():
    from monitor.editorial.chatter_discovery import validate_selection

    row = candidate()
    result = selection(row)
    result["candidate_tags"] = []
    with pytest.raises(ValueError, match="classif"):
        validate_selection(result, [row], {}, "giants:test")
    result = selection(row)
    result["group_decisions"][1]["ranked_candidates"][0]["reason"] = ""
    with pytest.raises(ValueError, match="reason"):
        validate_selection(result, [row], {}, "giants:test")


def test_unknown_search_execution_cannot_become_a_successful_empty_cycle():
    from monitor.editorial.chatter_discovery import validate_semantic

    raw = {
        "stories": [],
        "keyword_query": "",
        "search_notes": [],
        "history_requests": [],
    }
    with pytest.raises(ValueError, match="execution"):
        validate_semantic({"data": raw, "usage": {}, "search_activity": []}, set())
    result = validate_semantic(
        {"data": raw, "usage": {"x_search_calls": 1}, "search_activity": []}, set()
    )
    assert result["stories"] == [] and result["tool_detail_visibility"] == "unavailable"


def test_one_bad_semantic_story_does_not_remove_a_valid_sibling():
    from monitor.editorial.chatter_discovery import validate_semantic

    row = {
        "story_ref": "S1",
        "subject": "A small lab's announcement",
        "angle": "The source reports a release.",
        "reader_appeal": "A useful unexpected development.",
        "keyword_query": '"small lab"',
        "prior_development_id": None,
        "primary_posts": [
            {
                "url": "https://x.com/lab/status/123",
                "author_handle": "lab",
                "text": "Unverified search notes.",
                "created_at": None,
            }
        ],
        "discussion_posts": [],
        "gaps": [],
    }
    raw = {
        "stories": [{**row, "story_ref": "bad", "extra": "not allowed"}, row],
        "keyword_query": '"small lab"',
        "search_notes": [],
        "history_requests": [],
    }
    result = validate_semantic({"data": raw, "usage": {"x_search_calls": 1}}, set())
    assert len(result["stories"]) == 1 and result["stories"][0]["post_ids"] == ["123"]
    assert len(result["rejections"]) == 1
    raw["stories"] = [
        row,
        {**row, "story_ref": "S2", "subject": "A separate lawsuit in the same roundup"},
    ]
    result = validate_semantic({"data": raw, "usage": {"x_search_calls": 1}}, set())
    assert len(result["stories"]) == 2
    assert result["stories"][0]["post_ids"] == result["stories"][1]["post_ids"]
    raw["stories"] = [row, {**row, "story_ref": "second-identity"}]
    with pytest.raises(ValueError, match="ambiguous_semantic_identity"):
        validate_semantic({"data": raw, "usage": {"x_search_calls": 1}}, set())
    from uuid import uuid4

    prior = str(uuid4())
    raw["stories"] = [
        {**row, "prior_development_id": prior},
        {
            **row,
            "story_ref": "S2",
            "subject": "A separate development",
            "prior_development_id": prior,
        },
    ]
    with pytest.raises(ValueError, match="ambiguous_semantic_identity"):
        validate_semantic({"data": raw, "usage": {"x_search_calls": 1}}, {prior})


def test_attention_uses_comparable_measurement_times_and_keeps_missing_values_unknown():
    from monitor.editorial.chatter_discovery import attention

    now = timezone.now()
    old = {
        "id": "123",
        "author_id": "1",
        "counters": {
            "observed_at": (now - timedelta(minutes=30)).isoformat(),
            "likes": 10,
            "replies": 0,
            "reposts": 2,
            "quotes": 1,
        },
    }
    new = {
        "id": "123",
        "author_id": "1",
        "counters": {
            "observed_at": now.isoformat(),
            "likes": 30,
            "replies": 2,
            "reposts": 4,
            "quotes": 1,
        },
    }
    result = attention([new, new], {"123": old})
    assert result["observed_post_count"] == 1 and result["distinct_known_authors"] == 1
    assert result["posts"][0]["per_15_minutes"]["likes"] == 10
    result = attention(
        [{**new, "counters": {**new["counters"], "observed_at": None}}], {"123": old}
    )
    assert result["posts"][0]["per_15_minutes"] is None


def test_code_keep_requires_fresh_comparable_measurements_and_same_persistence():
    from copy import deepcopy

    from monitor.editorial.chatter_discovery import attention, keep_fingerprint

    at = timezone.now()
    source = {
        "id": "123",
        "author_id": "42",
        "source_language": "en",
        "created_at": at.isoformat(),
        "observed_at": at.isoformat(),
        "verification_basis": "provider_receipt",
        "counters": {
            "observed_at": at.isoformat(),
            "likes": 10,
            "replies": 2,
            "reposts": 3,
            "quotes": 1,
        },
    }
    previous = deepcopy(source)
    previous["counters"]["observed_at"] = (at - timedelta(minutes=15)).isoformat()
    candidate = {
        "candidate_ref": "A",
        "eligible": True,
        "evidence": [source],
        "subject_label": "A launch",
        "discovery_note": "A supported announcement",
        "required_release_refs": [],
        "persistence": {
            "continuity_known": True,
            "consecutive_lower_bound": 8,
            "fresh_periods": 8,
            "unknown_periods": 0,
        },
    }
    payload = {
        "candidates": [candidate],
        "coverage": {"lookup_omitted": 0, "board_may_be_capped": False},
        "measurements": [
            {"candidate_ref": "A", **attention([source], {"123": previous})}
        ],
        "giant_group_policy": {},
        "required_release_refs": [],
        "asset_manifest": [],
        "prior_visual_observations": [],
    }
    fingerprint = keep_fingerprint(payload)
    assert fingerprint is not None
    later = deepcopy(payload)
    later["candidates"][0]["evidence"][0]["observed_at"] = (
        at + timedelta(minutes=15)
    ).isoformat()
    assert keep_fingerprint(later) == fingerprint
    later["candidates"][0]["persistence"]["consecutive_lower_bound"] = 7
    assert keep_fingerprint(later) != fingerprint
    later["measurements"][0]["posts"][0]["delta"] = None
    assert keep_fingerprint(later) is None
