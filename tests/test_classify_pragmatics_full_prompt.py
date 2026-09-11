"""Prompt contract for the Stage 1 classifier."""

from __future__ import annotations

import pytest

from core.classification_contract import (
    NATIONALISM_KEYS,
    POST_TYPE_KEYS,
    PRODUCT_LABEL_KEYS,
    PROMPT_VERSION,
    SENTIMENT_KEYS,
)
from x_monitor.attribution import _PRAGMATICS_FULL_SYSTEM_PROMPT


@pytest.mark.parametrize("key", POST_TYPE_KEYS)
def test_prompt_enumerates_every_post_type(key):
    assert f"- {key}:" in _PRAGMATICS_FULL_SYSTEM_PROMPT


@pytest.mark.parametrize("key", PRODUCT_LABEL_KEYS)
def test_prompt_enumerates_every_product_label(key):
    assert f"- {key}:" in _PRAGMATICS_FULL_SYSTEM_PROMPT


def test_prompt_enumerates_sentiment_and_nationalism_values():
    assert (
        "SENTIMENT (required for classified): " + ", ".join(SENTIMENT_KEYS)
    ) in _PRAGMATICS_FULL_SYSTEM_PROMPT
    assert ", ".join(NATIONALISM_KEYS) in _PRAGMATICS_FULL_SYSTEM_PROMPT
    for meaning in (
        "positive: praise",
        "negative: criticism",
        "neutral: informational",
        "mixed: materially both",
        "none means the supplied source can be assessed",
        "Use null only when missing or unusable context",
        "Nationalism requires explicit US-China",
    ):
        assert meaning in _PRAGMATICS_FULL_SYSTEM_PROMPT


def test_prompt_preserves_unsanctioned_vocabulary_definitions_and_boundaries():
    prompt = _PRAGMATICS_FULL_SYSTEM_PROMPT
    for key, evidence in (
        ("marketing_spam", "promotional CTA"),
        ("scam", "payment, credentials, or a wallet seed"),
        ("crypto", "token tickers, airdrops, wallet claims"),
        ("unauthorized", "third-party giveaway"),
    ):
        assert f"- {key}:" in prompt
        assert evidence in prompt
    assert "Advertising or CTA-heavy wrapper content" in prompt
    assert "specific evidence" in prompt


def test_prompt_contains_taxonomy_boundaries_from_settled_contract():
    prompt = _PRAGMATICS_FULL_SYSTEM_PROMPT
    for boundary in (
        "Future intent",
        "news roundup is not hands_on_usage",
        "release date",
        "not events",
        "substantive recap",
        "Attendance means presence",
        "asynchronous task before a deadline is not events",
        "action-for-benefit exchange",
        "Jobs use job_listings rather than opportunities",
        "job listing needs a concrete role and application route",
        "personnel change needs a named person",
        "effective dates may be unknown",
        "Mentioning a benchmark",
        "Rhetorical headings are not questions_requests",
        "parent companies",
    ):
        assert boundary in prompt


def test_prompt_defines_product_labels_as_independent_and_non_adjudicating():
    prompt = _PRAGMATICS_FULL_SYSTEM_PROMPT
    assert "independent multi-label array" in prompt
    assert "empty array is valid" in prompt
    assert "Product-label keys are forbidden in post_types" in prompt
    assert "ideas and requests stay combined" in prompt
    assert "never adjudicates the claim false" in prompt


def test_prompt_defines_classified_context_missing_and_other_without_defaults():
    prompt = _PRAGMATICS_FULL_SYSTEM_PROMPT
    assert "classified requires at least one post_type" in prompt
    assert "context_missing requires empty post_types and product_labels" in prompt
    assert "use null for an unknown scalar" in prompt
    assert "other: a confident residual only" in prompt
    assert "exclusive" in prompt


def test_prompt_limits_context_to_stored_provenance_and_forbids_fetches():
    prompt = _PRAGMATICS_FULL_SYSTEM_PROMPT
    assert "already stored context entries" in prompt
    assert "provenance markers" in prompt
    assert "do not fetch parents, links, media" in prompt


def test_prompt_output_has_no_discourse_or_primary_type_contract():
    prompt = _PRAGMATICS_FULL_SYSTEM_PROMPT
    assert "discourse_role" not in prompt
    assert "primary_type" not in prompt
    assert '"post_types":[str]' in prompt
    assert '"product_labels":[str]' in prompt


def test_prompt_version_tracks_the_system_user_boundary():
    assert PROMPT_VERSION == "stage1-prompt-v6"


def test_prompt_identity_is_shared_by_batch_and_single_builders():
    import json

    from x_monitor.attribution import (
        build_batch_pragmatics_full_prompt,
        build_pragmatics_full_prompt,
    )

    single = build_pragmatics_full_prompt("text", ["deepseek"])
    batch = build_batch_pragmatics_full_prompt(
        [{"tweet_id": "one", "text": "text", "brand_ids": ["deepseek"]}]
    )

    assert _PRAGMATICS_FULL_SYSTEM_PROMPT not in single
    assert _PRAGMATICS_FULL_SYSTEM_PROMPT not in batch
    assert json.loads(single) == [
        {
            "tweet_id": "_single_",
            "text": "text",
            "brand_ids": ["deepseek"],
            "context": [],
        }
    ]
    assert json.loads(batch) == [
        {
            "tweet_id": "one",
            "text": "text",
            "brand_ids": ["deepseek"],
            "context": [],
        }
    ]
