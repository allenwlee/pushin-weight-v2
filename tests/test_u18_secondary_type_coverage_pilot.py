import pytest
from scripts import u18_secondary_type_coverage_pilot as pilot


def row(key="row", brand="qwen"):
    return {"row_key": key, "target_brand": brand, "text": "I tested Qwen at the meetup", "context": [], "affiliations": [], "source_language": "en", "previous_post_types": []}


def answer(key="row", brand="qwen", positive="hands_on_usage"):
    decisions = {t: {"applies": t == positive, "evidence": "I tested Qwen" if t == positive else None} for t in pilot.TYPES}
    return {"rows": [{"row_key": key, "target_brand": brand, "decisions": decisions}]}


def test_validate_requires_all_eight_independent_decisions_with_visible_evidence():
    parsed = pilot.validate(answer(), [row()])
    assert parsed["row"]["hands_on_usage"]["applies"] is True


@pytest.mark.parametrize("mutate", [
    lambda a: a["rows"][0]["decisions"].pop("events"),
    lambda a: a["rows"][0]["decisions"]["hands_on_usage"].__setitem__("evidence", "invented"),
    lambda a: a["rows"][0].__setitem__("target_brand", "foreign"),
])
def test_validate_fails_closed_on_missing_or_unverifiable_decisions(mutate):
    payload = answer(); mutate(payload)
    with pytest.raises(ValueError):
        pilot.validate(payload, [row()])


def test_merge_can_only_add_types_and_preserves_primary_axes():
    primary = {"batches": [{"merged": [{"row_key": "row", "target_brand": "qwen", "outcome": "classified", "post_types": ["opinions_reactions"], "sentiment": "neutral", "product_labels": [], "china_nationalism": "none", "us_nationalism": "none"}]}]}
    decisions = {"row": {"hands_on_usage": {"applies": True, "evidence": "x"}}}
    updated = pilot.merge(primary, decisions)["batches"][0]["merged"][0]
    assert updated["post_types"] == ["hands_on_usage", "opinions_reactions"]
    assert updated["sentiment"] == "neutral"
    assert updated["outcome"] == "classified"
