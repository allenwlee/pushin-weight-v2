"""Fresh paired trial responses, not historical Jev answers or general accuracy evidence."""
import json
from pathlib import Path

import pytest

from x_monitor.compressed_classifier import build_jev, finish
from x_monitor.compressed_classifier_prompts import QUESTIONS

FIXTURE = json.loads((Path(__file__).parent / "fixtures/u5_meta_wording.json").read_text())


@pytest.mark.parametrize("record", FIXTURE["records"] + FIXTURE["controls"], ids=lambda record: record["id"])
def test_meta_cases_use_the_evaluated_wording(record):
    prepared = build_jev(record["case"], {"entities": []})
    assert prepared["request"] == record["request"]
    result = finish(record["case"], prepared, record["response"])
    assert result["publication_result"]["valid"], result["contract_errors"]
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == record["expected_outcome"]


def test_other_brand_identity_questions_remain_unchanged():
    case = FIXTURE["records"][0]["case"].copy()
    case["target_brands"] = ["qwen"]
    case["state"] = {**case["state"], "target_brand": "qwen", "tracked_brands": [
        {"brand_id": "qwen", "display_name": "Qwen", "aliases": ["Qwen"], "products": [], "accounts": []}
    ]}
    prepared = build_jev(case, {"entities": []})
    for key in ("identity_namesake_only", "identity_keyword_only", "identity_word_only"):
        question = prepared["request"]["questions"][key]["instructions"]
        assert question == QUESTIONS[key].format(b="Qwen and its offerings [post-matched catalog names: none; database key: qwen]")


def test_multibrand_packet_changes_only_meta_identity_wording():
    case = FIXTURE["records"][0]["case"].copy()
    case["target_brands"] = ["llama", "qwen"]
    case["state"] = {**case["state"], "tracked_brands": [
        *case["state"]["tracked_brands"],
        {"brand_id": "qwen", "display_name": "Qwen", "aliases": ["Qwen"], "products": [], "accounts": []},
    ]}
    prepared = build_jev(case, {"entities": []})
    mapping = prepared["metadata"]["question_map"]
    for key in ("identity_namesake_only", "identity_keyword_only", "identity_word_only"):
        meta = prepared["request"]["questions"][mapping["llama"][key]]["instructions"]
        qwen = prepared["request"]["questions"][mapping["qwen"][key]]["instructions"]
        assert "Muse" in meta
        assert qwen == QUESTIONS[key].format(b="Qwen and its offerings [post-matched catalog names: none; database key: qwen]")


def test_new_brand_prompt_revision_preserves_old_release_readers():
    from core.classification_contract import COMPRESSED_CLASSIFIER_REVISIONS, COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS

    old = ("compressed8-pulse-content-v2", "compressed8-pulse-brand-v2", "compressed8-pulse-merge-v2")
    u4 = ("compressed8-pulse-content-v2", "compressed8-pulse-brand-v2", "compressed8-pulse-merge-v3")
    assert old in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS
    assert u4 in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS
    assert COMPRESSED_CLASSIFIER_REVISIONS[1] != old[1]
    assert COMPRESSED_CLASSIFIER_REVISIONS[2] not in {old[2], u4[2]}


@pytest.mark.parametrize("version", ["compressed8-pulse-merge-v2", "compressed8-pulse-merge-v3", "compressed8-pulse-merge-v4"])
def test_older_feed_only_judgments_remain_visible(version):
    from monitor.views import _feed_axes_complete_post_ids

    row = {"post_id": "post", "brand_id": "llama", "selected_final_judgment__changes_json": {},
           "selected_final_judgment__prompt_version": version,
           "selected_final_judgment__validation_state": "validated"}
    assert _feed_axes_complete_post_ids(["post"], brand_pairs=[("post", "llama")], state_rows=[row]) == {"post"}


@pytest.mark.parametrize(("text", "positive", "expected"), [
    ("Meta announced its new AI research.", {"relevant", "type:releases_updates"}, "classified"),
    ("The meta analysis covers these studies.", {"identity_word_only"}, "context_missing"),
])
def test_meta_company_and_generic_meta_word_controls(text, positive, expected):
    from tests.test_compressed_classifier import answers

    case = FIXTURE["records"][0]["case"].copy()
    case["state"] = {**case["state"], "source_text": text}
    prepared = build_jev(case, {"entities": []})
    result = finish(case, prepared, answers(prepared["request"], positive_keys=positive))
    assert result["publication_result"]["by_brand"]["llama"]["outcome"] == expected
