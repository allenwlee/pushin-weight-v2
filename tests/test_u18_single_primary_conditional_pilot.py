import pytest

from scripts import u18_single_primary_conditional_pilot as pilot


def packet(text="Qwen meetup", tweet_id="opaque"):
    return {"tweet_id": tweet_id, "text": text, "context": [], "brand_ids": ["qwen"], "affiliations": [], "source_language": "en"}


def response(tweet_id="opaque", types=None):
    return {"results": [{"tweet_id": tweet_id, "classifications": [{"brand_id": "qwen", "outcome": "classified", "post_types": types or ["events"], "product_labels": [], "sentiment": "neutral", "china_nationalism": "none", "us_nationalism": "none"}], "unsanctioned_flags": []}]}


def test_primary_parser_preserves_all_axes_and_batch_identity():
    source = packet()
    parsed = pilot.parse_primary(response(), [source])
    row = pilot.primary_result([source], parsed, 0)["merged"][0]
    assert row["target_brand"] == "qwen"
    assert row["post_types"] == ["events"]
    assert row["sentiment"] == "neutral"
    assert row["china_nationalism"] == "none"


@pytest.mark.parametrize("mutate", [
    lambda r: r.__setitem__("extra", True),
    lambda r: r.__setitem__("tweet_id", "foreign"),
    lambda r: r.__setitem__("classifications", []),
])
def test_primary_parser_fails_closed_for_malformed_rows(mutate):
    answer = response(); mutate(answer["results"][0])
    with pytest.raises(ValueError):
        pilot.parse_primary(answer, [packet()])


def test_conditional_schedule_uses_primary_and_visible_source_not_owner_reference():
    source = packet("Register for the Qwen meetup")
    parsed = pilot.parse_primary(response(types=["opinions_reactions"]), [source])
    primary = {"batches": [pilot.primary_result([source], parsed, 0)]}
    schedule, routing = pilot.conditional_schedule([source], primary)
    assert routing[0]["selected"] is True
    assert schedule[0]["rows"][0]["previous_post_types"] == ["opinions_reactions"]


def test_conditional_merge_cannot_overwrite_primary_axes():
    source = packet()
    parsed = pilot.parse_primary(response(types=["opinions_reactions"]), [source])
    base = {"batches": [pilot.primary_result([source], parsed, 0)]}
    key = base["batches"][0]["merged"][0]["row_key"]
    merged = pilot.rare.merge_additions(base, {key: {"events": {"applies": True, "evidence": "Qwen meetup"}}})
    before, after = base["batches"][0]["merged"][0], merged["batches"][0]["merged"][0]
    assert after["post_types"] == ["events", "opinions_reactions"]
    assert all(after[field] == before[field] for field in ("outcome", "product_labels", "sentiment", "china_nationalism", "us_nationalism"))
