import json

from scripts import u18_fresh45_v4_0731_best_compare as subject


def test_batches_preserve_all_45_cases_in_production_sized_groups():
    packet_batches = subject.batches(subject.sol.packets())

    assert [len(batch) for batch in packet_batches] == [20, 20, 5]
    assert [packet["case_id"] for batch in packet_batches for packet in batch] == [
        packet["case_id"] for packet in subject.sol.packets()
    ]


def test_requests_use_model_specific_fixed_slots_and_deepinfra():
    batch = subject.sol.packets()[:2]
    body = subject.route.request(batch, "content")

    assert body["provider"]["only"] == ["DeepInfra"]
    assert body["provider"]["allow_fallbacks"] is False
    assert body["reasoning"] == {"enabled": False, "exclude": True}
    assert body["temperature"] == 1.0
    assert body["top_p"] == 1.0
    assert "response_format" not in body
    assert "D01" in body["messages"][0]["content"]


def test_comparison_excludes_owner_blanks_and_scores_explicit_values():
    owner = {
        "cases": {
            "C1": {
                "review_targets": ["minimax"],
                "per_brand": {
                    "minimax": {
                        "outcome": "classified", "sentiment": "", "post_types": ["events"],
                        "product_labels": [], "audience_topics": ["none"], "geopolitical_modes": ["none"],
                        "china_national_stance": "none", "us_national_stance": "none",
                    }
                },
                "post_level": {"untracked_brand_promotions": ["none"]},
            }
        }
    }
    result = {
        "roles": {
            "content": [{"case_id": "C1", "by_brand": [{"brand_id": "minimax", "outcome": "classified", "post_types": ["events"], "audience_topics": ["none"]}], "untracked_brand_promotions": ["none"]}],
            "brand": [{"case_id": "C1", "by_brand": [{"brand_id": "minimax", "product_labels": ["none"], "sentiment": "positive", "geopolitical_modes": ["none"], "china_national_stance": "none", "us_national_stance": "none"}]}],
        }
    }
    original_merge = subject.sol.merge_sol
    subject.sol.merge_sol = lambda _: original_merge(result)
    try:
        artifact = subject.comparison_artifact(owner, result, "test-result-sha")
    finally:
        subject.sol.merge_sol = original_merge

    assert artifact["counts"] == {"reviewed": 7, "matches": 7, "differences": 0, "unreviewed": 2}
