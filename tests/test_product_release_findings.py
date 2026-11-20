"""Source-bound transport cases shared by either initial classifier implementation."""

from copy import deepcopy

import pytest


def parse(value, *, passages=None, channels=("api", "weights")):
    from core.product_release_findings import FindingLimits, parse_release_findings

    return parse_release_findings(
        value, source={"kind": "post", "id": "source-1"},
        passages=passages or {"body": "Qwen4 weights are available today. Qwen4 API arrives next month."},
        allowed_channels=channels,
        limits=FindingLimits(max_findings=4, max_assertions=8, max_text_chars=1000),
    )


def envelope():
    return {
        "schema": "pulse-release-findings-v1",
        "findings": [{
            "observed_name": "Qwen4", "version": None, "variant": None,
            "novelty": "new_release", "category": "model-llm",
            "assertions": [{
                "claim_kind": "availability", "assertion_text": "Qwen4 weights available",
                "source_excerpt": "Qwen4 weights are available today.", "source_locator": "body",
                "access_channel": "weights",
                "effective": {"precision": "day", "value": "2026-11-17", "timezone": "Asia/Tokyo"},
            }],
        }],
    }


def test_successful_empty_is_distinct_from_missing_malformed_or_old_output():
    assert parse({"schema": "pulse-release-findings-v1", "findings": []}) == ()
    for value in (None, {}, {"findings": []}, {"schema": "old", "findings": []}):
        with pytest.raises(ValueError):
            parse(value)


@pytest.mark.parametrize("kind", ["new_version", "finetune", "adapter", "quantized", "merge"])
def test_lineage_preserves_reported_names_without_assigning_canonical_identity(kind):
    value = envelope()
    excerpt = "Qwen4 weights are available today. Qwen4 is a successor to Qwen3."
    relation = {"relationship_kind": kind, "parent_observed_name": "Qwen3",
                "source_locator": "body", "source_excerpt": excerpt}
    value["findings"][0]["lineage_evidence"] = [relation]
    finding = parse(value, passages={"body": excerpt})[0]
    assert finding["lineage_evidence"] == [relation]
    assert finding["brand_id"] is None


@pytest.mark.parametrize("mutation", [
    lambda relation: relation.update(source_locator="invented"),
    lambda relation: relation.update(source_excerpt="Qwen4 is an invented successor to Qwen3."),
    lambda relation: relation.update(parent_observed_name="Invented parent"),
    lambda relation: relation.update(source_excerpt="Qwen3 was released earlier."),
    lambda relation: relation.update(relationship_kind="same_family"),
    lambda relation: relation.update(parent_product_key="invented"),
])
def test_lineage_rejects_invented_or_unbound_evidence(mutation):
    value = envelope()
    excerpt = "Qwen4 weights are available today. Qwen4 replaces Qwen3. Qwen3 was released earlier."
    relation = {"relationship_kind": "new_version", "parent_observed_name": "Qwen3",
                "source_locator": "body", "source_excerpt": excerpt}
    mutation(relation)
    value["findings"][0]["lineage_evidence"] = [relation]
    with pytest.raises(ValueError):
        parse(value, passages={"body": excerpt})


def test_lineage_empty_and_limits_are_explicit():
    value = envelope()
    value["findings"][0]["lineage_evidence"] = []
    assert parse(value)[0]["lineage_evidence"] == []
    for invalid in (None, {}, [None] * 9):
        value["findings"][0]["lineage_evidence"] = invalid
        with pytest.raises(ValueError, match="lineage_limit"):
            parse(value)


@pytest.mark.parametrize("issuer", [
    {"relation": "source_author", "source_locator": "body", "source_excerpt": "Qwen4 weights are available today.", "observed_name": None},
    {"relation": "source_author", "source_locator": "post", "source_excerpt": "Invented issuer quote", "observed_name": None},
    {"relation": "attributed_party", "source_locator": "post", "source_excerpt": "Qwen4 weights are available today.", "observed_name": "Invented Company"},
    {"relation": "attributed_party", "source_locator": "post", "source_excerpt": "Qwen4 weights are available today.", "observed_name": None},
])
def test_issuer_cannot_transfer_context_authorship_or_invent_names(issuer):
    value = envelope()
    value["findings"][0]["issuer_evidence"] = issuer
    passages = {"post": "Qwen4 weights are available today.", "body": "Qwen4 weights are available today."}
    with pytest.raises(ValueError, match="issuer_"):
        parse(value, passages=passages)


def test_channels_and_dates_remain_per_assertion_and_replay_key_is_stable():
    value = envelope()
    value["findings"][0]["assertions"].append({
        "claim_kind": "availability", "assertion_text": "Qwen4 API next month",
        "source_excerpt": "Qwen4 API arrives next month.", "source_locator": "body",
        "access_channel": "api",
        "effective": {"precision": "month", "value": "2026-12", "timezone": None},
    })
    normalized = parse(value)[0]
    assert normalized["assertions"][0]["access_channel"] == "weights"
    assert normalized["assertions"][0]["effective_date"] == "2026-11-17"
    assert normalized["assertions"][1]["effective_month"] == 12
    assert normalized["assertions"][1]["effective_date"] is None
    assert normalized["brand_id"] is None
    assert parse(deepcopy(value)) == (normalized,)
    value["findings"][0]["assertions"].reverse()
    assert parse(value)[0]["finding_key"] == normalized["finding_key"]


def test_unnamed_release_preserves_evidence_without_creating_identity():
    value = envelope()
    finding = value["findings"][0]
    finding.update(observed_name=None, category=None, novelty="unresolved")
    finding["assertions"][0].update(
        claim_kind="announcement", assertion_text="Unnamed model announced",
        source_excerpt="Our new model is out.", access_channel=None,
        effective={"precision": "unknown", "value": None, "timezone": None},
    )
    result = parse(value, passages={"body": "Our new model is out."})[0]
    assert result["observed_name"] is None
    assert result["category"] is None
    assert result["brand_id"] is None
    assert len(result["finding_key"]) == 64


@pytest.mark.parametrize("mutation", [
    lambda f: f.update(category="llm-model"),
    lambda f: f.update(product_key="invented"),
    lambda f: f.update(observed_name="Invented Product"),
    lambda f: f["assertions"][0].update(source_excerpt="invented quote"),
    lambda f: f["assertions"][0].update(source_locator="unseen_url"),
    lambda f: f["assertions"][0].update(access_channel="new_seed"),
    lambda f: f["assertions"][0].update(effective={"precision": "day", "value": "2026-02-31", "timezone": None}),
    lambda f: f["assertions"][0].update(effective={"precision": "unknown", "value": "2026-11-17", "timezone": None}),
])
def test_invalid_or_unbacked_output_is_not_silently_accepted(mutation):
    value = envelope()
    mutation(value["findings"][0])
    with pytest.raises(ValueError):
        parse(value)


def test_two_products_and_duplicate_offerings_do_not_share_an_array_position_identity():
    value = envelope()
    other = deepcopy(value["findings"][0])
    other["observed_name"] = "XYZ"
    other["assertions"][0]["source_excerpt"] = "XYZ is available."
    value["findings"].append(other)
    passages = {"body": "Qwen4 weights are available today. XYZ is available."}
    first = parse(value, passages=passages)
    value["findings"].reverse()
    assert parse(value, passages=passages)[0]["finding_key"] == first[1]["finding_key"]
    value["findings"].append(deepcopy(other))
    with pytest.raises(ValueError, match="duplicate"):
        parse(value, passages=passages)


def test_candidate_channels_require_explicit_vocabulary_and_never_imply_novelty():
    value = envelope()
    value["findings"][0]["novelty"] = "availability_update"
    value["findings"][0]["assertions"][0]["access_channel"] = "hosted_app"
    with pytest.raises(ValueError):
        parse(value)
    result = parse(value, channels=("api", "weights", "hosted_app"))[0]
    assert result["novelty"] == "availability_update"
    assert result["assertions"][0]["access_channel"] == "hosted_app"


def test_limits_fail_explicitly_without_truncating_findings():
    value = envelope()
    value["findings"] *= 5
    with pytest.raises(ValueError, match="limit"):
        parse(value)
