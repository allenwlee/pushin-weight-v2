"""U4 tests for x_monitor.attribution.classify_pragmatics_full.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 4 of 8).

Verifies:
- The merged prompt lists all 5 prongs (post_type, sentiment,
  discourse_role, china_nationalism, us_nationalism) and their
  full controlled vocabularies.
- classify_pragmatics_full returns {} for empty inputs.
- classify_pragmatics_full returns {} when no client is provided.
- A happy-path LLM response yields 5 prongs per attributed brand.
- Hallucinated brand_ids (not in registry) are dropped.
- Unknown post_type / sentiment coerce to the v1.5 defaults
  ('hands_on_usage' / 'neutral') — same as classify_post.
- Unknown discourse_role coerces to 'uncategorized' (KTD5).
- Unknown nationalism values coerce to 'none'.
- A parse failure (missing 'classifications' key) returns {}.
- A length-mismatch / non-dict response returns {}.
- The function survives a real LLM exception (returns {}, logs warn).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest


# --- Test fixtures ------------------------------------------------------


@dataclass(frozen=True)
class FakeBrandRow:
    brand_id: str
    display_name: str = ""


class FakeClaudeClient:
    """Minimal canned-response client (mirrors other test patterns)."""

    def __init__(self, response_factory=None):
        self._factory = response_factory or self._default_factory
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def _default_factory(self, *_):
        return {"classifications": []}

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        return self._factory(*self.calls[-1].get("_test_args", (None, None)))


# --- Prompt builder -----------------------------------------------------


def test_pragmatics_full_prompt_lists_all_five_prongs():
    """The prompt names every controlled vocabulary set."""
    from x_monitor.attribution import build_pragmatics_full_prompt

    prompt = build_pragmatics_full_prompt(
        "Claude could never",
        ["anthropic", "deepseek"],
    )
    # post_type vocabulary
    for token in ("buzz_releases", "hands_on_usage",
                  "performance_comparisons", "feedback_questions"):
        assert token in prompt
    # sentiment vocabulary (each appears at least once in the legend)
    for token in ("positive", "negative", "neutral", "mixed"):
        assert token in prompt
    # discourse_role vocabulary (all 9)
    for token in ("genuine_hype", "sarcasm", "dunk_yingyang",
                  "self_deprecation", "cope", "fud",
                  "distillation_accusation", "ai_slop_critique",
                  "absurdist_meme"):
        assert token in prompt, f"missing discourse_role {token}"
    # nationalism vocabulary (each appears at least once; the
    # "both axes" copy means most tokens appear multiple times).
    for token in ("none", "mild_pro", "pro", "constructive_critical",
                  "anti", "mixed"):
        assert token in prompt
    # 5-prong row shape
    for token in ("china_nationalism", "us_nationalism",
                  "discourse_role", "post_type", "sentiment"):
        assert token in prompt


def test_pragmatics_full_prompt_embeds_text_and_brands():
    from x_monitor.attribution import build_pragmatics_full_prompt

    prompt = build_pragmatics_full_prompt(
        "Claude could never",
        ["anthropic", "deepseek"],
    )
    assert "Claude could never" in prompt
    assert "anthropic" in prompt
    assert "deepseek" in prompt


# --- Parser -------------------------------------------------------------


def test_parse_pragmatics_full_response_happy_path():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "hands_on_usage",
         "sentiment": "negative", "discourse_role": "dunk_yingyang",
         "china_nationalism": "none", "us_nationalism": "constructive_critical"},
        {"brand_id": "deepseek", "post_type": "performance_comparisons",
         "sentiment": "positive", "discourse_role": "genuine_hype",
         "china_nationalism": "pro", "us_nationalism": "mild_pro"},
    ]}
    parsed = _parse_pragmatics_full_response(
        response, {"anthropic", "deepseek"},
    )
    assert len(parsed) == 2
    assert parsed["anthropic"]["post_type"] == "hands_on_usage"
    assert parsed["anthropic"]["discourse_role"] == "dunk_yingyang"
    assert parsed["anthropic"]["china_nationalism"] == "none"
    assert parsed["deepseek"]["sentiment"] == "positive"
    assert parsed["deepseek"]["discourse_role"] == "genuine_hype"


def test_parse_pragmatics_full_drops_hallucinated_brand():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "made_up_brand", "post_type": "hands_on_usage",
         "sentiment": "neutral", "discourse_role": "genuine_hype",
         "china_nationalism": "none", "us_nationalism": "none"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed == {}


def test_parse_pragmatics_full_coerces_unknown_post_type():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "made_up_type",
         "sentiment": "neutral", "discourse_role": "genuine_hype",
         "china_nationalism": "none", "us_nationalism": "none"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["anthropic"]["post_type"] == "hands_on_usage"


def test_parse_pragmatics_full_coerces_unknown_sentiment():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "hands_on_usage",
         "sentiment": "made_up_sent", "discourse_role": "genuine_hype",
         "china_nationalism": "none", "us_nationalism": "none"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["anthropic"]["sentiment"] == "neutral"


def test_parse_pragmatics_full_coerces_unknown_discourse_to_uncategorized():
    """KTD5: unknown discourse_role → `uncategorized`, not the bucket."""
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "hands_on_usage",
         "sentiment": "neutral", "discourse_role": "made_up_role",
         "china_nationalism": "none", "us_nationalism": "none"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["anthropic"]["discourse_role"] == "uncategorized"


def test_parse_pragmatics_full_coerces_unknown_nationalism_to_none():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "hands_on_usage",
         "sentiment": "neutral", "discourse_role": "genuine_hype",
         "china_nationalism": "made_up_axis", "us_nationalism": "made_up_axis"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["anthropic"]["china_nationalism"] == "none"
    assert parsed["anthropic"]["us_nationalism"] == "none"


def test_parse_pragmatics_full_non_dict_response_returns_empty():
    from x_monitor.attribution import _parse_pragmatics_full_response

    for bad in (None, [], "string", 42):
        assert _parse_pragmatics_full_response(bad, {"anthropic"}) == {}


def test_parse_pragmatics_full_missing_classifications_key_returns_empty():
    from x_monitor.attribution import _parse_pragmatics_full_response

    assert _parse_pragmatics_full_response({}, {"anthropic"}) == {}
    assert _parse_pragmatics_full_response(
        {"other_key": "x"}, {"anthropic"}
    ) == {}


# --- classify_pragmatics_full surface -----------------------------------


def test_classify_pragmatics_full_empty_inputs_returns_empty():
    from x_monitor.attribution import classify_pragmatics_full

    client = FakeClaudeClient()
    assert classify_pragmatics_full("", ["anthropic"], [], client) == {}
    assert classify_pragmatics_full("x", [], [], client) == {}
    assert client.call_count == 0  # never even called the LLM


def test_classify_pragmatics_full_no_client_returns_empty():
    from x_monitor.attribution import classify_pragmatics_full

    result = classify_pragmatics_full(
        "x", ["anthropic"], [FakeBrandRow("anthropic")], anthropic_client=None,
    )
    assert result == {}


def test_classify_pragmatics_full_happy_path():
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("anthropic"), FakeBrandRow("deepseek")]
    client = FakeClaudeClient()
    def factory(*_):
        return {"classifications": [
            {"brand_id": "anthropic", "post_type": "hands_on_usage",
             "sentiment": "negative", "discourse_role": "dunk_yingyang",
             "china_nationalism": "none",
             "us_nationalism": "constructive_critical"},
            {"brand_id": "deepseek", "post_type": "performance_comparisons",
             "sentiment": "positive", "discourse_role": "genuine_hype",
             "china_nationalism": "pro", "us_nationalism": "mild_pro"},
        ]}
    client._factory = factory

    out = classify_pragmatics_full(
        "Claude could never make this", ["anthropic", "deepseek"],
        registry, anthropic_client=client,
    )
    assert client.call_count == 1
    assert len(out) == 2
    assert out["anthropic"]["post_type"] == "hands_on_usage"
    assert out["anthropic"]["discourse_role"] == "dunk_yingyang"
    assert out["anthropic"]["china_nationalism"] == "none"
    assert out["anthropic"]["us_nationalism"] == "constructive_critical"
    assert out["deepseek"]["sentiment"] == "positive"
    assert out["deepseek"]["china_nationalism"] == "pro"


def test_classify_pragmatics_full_llm_exception_returns_empty():
    """A raising factory yields {} (caller treats as fail-soft)."""
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("anthropic")]
    client = FakeClaudeClient()
    def boom(*_):
        raise RuntimeError("LLM down")
    client._factory = boom

    out = classify_pragmatics_full(
        "x", ["anthropic"], registry, anthropic_client=client,
    )
    assert out == {}


def test_classify_pragmatics_full_dropped_hallucinated_brands():
    """A response that adds brands not in the registry drops them."""
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("anthropic")]
    client = FakeClaudeClient()
    def factory(*_):
        return {"classifications": [
            {"brand_id": "made_up", "post_type": "hands_on_usage",
             "sentiment": "neutral", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
            {"brand_id": "anthropic", "post_type": "hands_on_usage",
             "sentiment": "neutral", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
        ]}
    client._factory = factory

    out = classify_pragmatics_full(
        "x", ["anthropic"], registry, anthropic_client=client,
    )
    assert "made_up" not in out
    assert "anthropic" in out


def test_classify_pragmatics_full_parse_failure_returns_empty():
    """Empty classifications list → empty dict (logged as warn)."""
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("anthropic")]
    client = FakeClaudeClient()
    def factory(*_):
        return {"classifications": []}
    client._factory = factory

    out = classify_pragmatics_full(
        "x", ["anthropic"], registry, anthropic_client=client,
    )
    assert out == {}


def test_classify_pragmatics_full_nationalism_orthogonal_to_post_type():
    """Nationalism is orthogonal to the other 3 prongs — any combination
    is legal (tested via the parser surface since the surface area is
    the merge step)."""
    from x_monitor.attribution import _parse_pragmatics_full_response

    # Extreme combinations: anti + positive + genuine_hype + perf_compare
    # — proves the four axes are stored independently.
    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "performance_comparisons",
         "sentiment": "positive", "discourse_role": "genuine_hype",
         "china_nationalism": "anti", "us_nationalism": "mixed"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["anthropic"]["post_type"] == "performance_comparisons"
    assert parsed["anthropic"]["sentiment"] == "positive"
    assert parsed["anthropic"]["discourse_role"] == "genuine_hype"
    assert parsed["anthropic"]["china_nationalism"] == "anti"
    assert parsed["anthropic"]["us_nationalism"] == "mixed"