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
    bb = parsed["by_brand"]
    assert len(bb) == 2
    assert bb["anthropic"]["post_type"] == "hands_on_usage"
    assert bb["anthropic"]["discourse_role"] == "dunk_yingyang"
    assert bb["anthropic"]["china_nationalism"] == "none"
    assert bb["deepseek"]["sentiment"] == "positive"
    assert bb["deepseek"]["discourse_role"] == "genuine_hype"


def test_parse_pragmatics_full_drops_hallucinated_brand():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "made_up_brand", "post_type": "hands_on_usage",
         "sentiment": "neutral", "discourse_role": "genuine_hype",
         "china_nationalism": "none", "us_nationalism": "none"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["by_brand"] == {}


def test_parse_pragmatics_full_coerces_unknown_post_type():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "made_up_type",
         "sentiment": "neutral", "discourse_role": "genuine_hype",
         "china_nationalism": "none", "us_nationalism": "none"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["by_brand"]["anthropic"]["post_type"] == "hands_on_usage"


def test_parse_pragmatics_full_coerces_unknown_sentiment():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "hands_on_usage",
         "sentiment": "made_up_sent", "discourse_role": "genuine_hype",
         "china_nationalism": "none", "us_nationalism": "none"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["by_brand"]["anthropic"]["sentiment"] == "neutral"


def test_parse_pragmatics_full_coerces_unknown_discourse_to_uncategorized():
    """KTD5: unknown discourse_role → `uncategorized`, not the bucket."""
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "hands_on_usage",
         "sentiment": "neutral", "discourse_role": "made_up_role",
         "china_nationalism": "none", "us_nationalism": "none"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["by_brand"]["anthropic"]["discourse_role"] == "uncategorized"


def test_parse_pragmatics_full_coerces_unknown_nationalism_to_none():
    from x_monitor.attribution import _parse_pragmatics_full_response

    response = {"classifications": [
        {"brand_id": "anthropic", "post_type": "hands_on_usage",
         "sentiment": "neutral", "discourse_role": "genuine_hype",
         "china_nationalism": "made_up_axis", "us_nationalism": "made_up_axis"},
    ]}
    parsed = _parse_pragmatics_full_response(response, {"anthropic"})
    assert parsed["by_brand"]["anthropic"]["china_nationalism"] == "none"
    assert parsed["by_brand"]["anthropic"]["us_nationalism"] == "none"


def test_parse_pragmatics_full_non_dict_response_returns_empty():
    from x_monitor.attribution import _parse_pragmatics_full_response

    empty = {"by_brand": {}, "unsanctioned_flags": []}
    for bad in (None, [], "string", 42):
        assert _parse_pragmatics_full_response(bad, {"anthropic"}) == empty


def test_parse_pragmatics_full_missing_classifications_key_returns_empty():
    from x_monitor.attribution import _parse_pragmatics_full_response

    empty = {"by_brand": {}, "unsanctioned_flags": []}
    assert _parse_pragmatics_full_response({}, {"anthropic"}) == empty
    assert _parse_pragmatics_full_response(
        {"other_key": "x"}, {"anthropic"}
    ) == empty


# --- classify_pragmatics_full surface -----------------------------------


def test_classify_pragmatics_full_empty_inputs_returns_empty():
    from x_monitor.attribution import classify_pragmatics_full

    client = FakeClaudeClient()
    empty = {"by_brand": {}, "unsanctioned_flags": []}
    assert classify_pragmatics_full("", ["anthropic"], [], client) == empty
    assert classify_pragmatics_full("x", [], [], client) == empty
    assert client.call_count == 0  # never even called the LLM


def test_classify_pragmatics_full_no_client_returns_empty():
    from x_monitor.attribution import classify_pragmatics_full

    result = classify_pragmatics_full(
        "x", ["anthropic"], [FakeBrandRow("anthropic")], anthropic_client=None,
    )
    assert result == {"by_brand": {}, "unsanctioned_flags": []}


def test_classify_pragmatics_full_happy_path():
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("anthropic"), FakeBrandRow("deepseek")]
    client = FakeClaudeClient()
    def factory(*_):
        # Array shape (post_types[] / discourse_roles[]) — the schema
        # the merged prompt at build_pragmatics_full_prompt asks for.
        # U2b (2026-07-06): classifier routes through the array parser,
        # so the fixture must use the array shape.
        return {"classifications": [
            {"brand_id": "anthropic",
             "post_types": ["hands_on_usage"],
             "sentiment": "negative",
             "discourse_roles": ["dunk_yingyang"],
             "china_nationalism": "none",
             "us_nationalism": "constructive_critical"},
            {"brand_id": "deepseek",
             "post_types": ["performance_comparisons"],
             "sentiment": "positive",
             "discourse_roles": ["genuine_hype"],
             "china_nationalism": "pro",
             "us_nationalism": "mild_pro"},
        ]}
    client._factory = factory

    out = classify_pragmatics_full(
        "Claude could never make this", ["anthropic", "deepseek"],
        registry, anthropic_client=client,
    )
    assert client.call_count == 1
    bb = out["by_brand"]
    assert len(bb) == 2
    assert bb["anthropic"]["post_type"] == "hands_on_usage"
    assert bb["anthropic"]["discourse_role"] == "dunk_yingyang"
    assert bb["anthropic"]["china_nationalism"] == "none"
    assert bb["anthropic"]["us_nationalism"] == "constructive_critical"
    assert bb["deepseek"]["sentiment"] == "positive"
    assert bb["deepseek"]["china_nationalism"] == "pro"
    assert out["unsanctioned_flags"] == []


def test_classify_pragmatics_full_llm_exception_returns_empty():
    """A raising factory yields the empty envelope (caller treats as
    fail-soft)."""
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("anthropic")]
    client = FakeClaudeClient()
    def boom(*_):
        raise RuntimeError("LLM down")
    client._factory = boom

    out = classify_pragmatics_full(
        "x", ["anthropic"], registry, anthropic_client=client,
    )
    assert out == {"by_brand": {}, "unsanctioned_flags": []}


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
    assert "made_up" not in out["by_brand"]
    assert "anthropic" in out["by_brand"]


def test_classify_pragmatics_full_parse_failure_returns_empty():
    """Empty classifications list → empty envelope (logged as warn)."""
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("anthropic")]
    client = FakeClaudeClient()
    def factory(*_):
        return {"classifications": []}
    client._factory = factory

    out = classify_pragmatics_full(
        "x", ["anthropic"], registry, anthropic_client=client,
    )
    assert out == {"by_brand": {}, "unsanctioned_flags": []}


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
    bb = parsed["by_brand"]
    assert bb["anthropic"]["post_type"] == "performance_comparisons"
    assert bb["anthropic"]["sentiment"] == "positive"
    assert bb["anthropic"]["discourse_role"] == "genuine_hype"
    assert bb["anthropic"]["china_nationalism"] == "anti"
    assert bb["anthropic"]["us_nationalism"] == "mixed"


# --- U2b-fix (2026-07-06): classify_pragmatics_full routes through the
# array-aware parser, NOT the scalar one. Locked in with the tests below
# so a future refactor that re-introduces the scalar routing breaks these.
#
# Bug: prior to the fix, classify_pragmatics_full called the scalar
# parser (`_parse_pragmatics_full_response`), which read `post_type` /
# `discourse_role` (singular). The prompt at
# `build_pragmatics_full_prompt` explicitly requests `post_types: [str]`
# and `discourse_roles: [str]` arrays, so the LLM's array output never
# matched the parser's singular keys, and every classification fell
# through to `post_type="hands_on_usage"` / `discourse_role="uncategorized"`.
# 2026-07-06 smoketest on /tmp/v20_fixture.jsonl confirmed 20/20 degenerate.


def _by_brand(out: dict[str, Any], bid: str) -> dict[str, str]:
    """Helper: extract by_brand[bid] from classify_pragmatics_full's U2a
    return shape (`{"by_brand": {...}, "unsanctioned_flags": [...]}`).
    """
    return out["by_brand"][bid]


def test_classify_pragmatics_full_array_shape_first_element_used():
    """U2b-fix: when the LLM emits arrays (the schema the prompt asks
    for), the first array element survives into by_brand[bid].post_type
    and by_brand[bid].discourse_role.

    Regression: prior routing parsed `post_type` (singular) instead of
    `post_types` (array), so this exact response shape degraded to
    `post_type=hands_on_usage` / `discourse_role=uncategorized`."""
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("moonshot_kimi")]
    client = FakeClaudeClient()

    def factory(*_):
        # Note: array shape (post_types[] / discourse_roles[]) matches
        # the prompt exactly. This is what the live LLM emits.
        return {"classifications": [
            {"brand_id": "moonshot_kimi",
             "post_types": ["event_announcement", "performance_comparisons"],
             "sentiment": "neutral",
             "discourse_roles": ["dunk_yingyang"],
             "china_nationalism": "none",
             "us_nationalism": "none"},
        ]}
    client._factory = factory

    out = classify_pragmatics_full(
        "Kimi K2.7 Code is generally available in GitHub Copilot",
        ["moonshot_kimi"], registry, anthropic_client=client,
    )
    bb = _by_brand(out, "moonshot_kimi")
    assert bb["post_type"] == "event_announcement", (
        "post_type must reflect the array's first element, NOT the "
        "scalar fallback 'hands_on_usage'. This is the regression test "
        "for the U2b parser-routing fix."
    )
    assert bb["discourse_role"] == "dunk_yingyang", (
        "discourse_role must reflect the array's first element, NOT "
        "the scalar fallback 'uncategorized'."
    )
    assert bb["sentiment"] == "neutral"
    assert bb["china_nationalism"] == "none"
    assert bb["us_nationalism"] == "none"
    # unsanctioned_flags is part of the U2a envelope.
    assert out["unsanctioned_flags"] == []


def test_classify_pragmatics_full_array_shape_distinct_buckets_propagate():
    """U2b-fix: distinct post_type / discourse_role values that the
    LLM emits via array shape reach the caller intact — the routing
    fix isn't a no-op for the common case.

    Locked-in to prevent re-introducing the scalar parser routing
    on a refactor that touches `_parse_pragmatics_full_response_arrays`."""
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("llama")]
    client = FakeClaudeClient()

    def factory(*_):
        return {"classifications": [
            {"brand_id": "llama",
             "post_types": ["buzz_releases"],
             "sentiment": "positive",
             "discourse_roles": ["genuine_hype"],
             "china_nationalism": "none",
             "us_nationalism": "none"},
        ]}
    client._factory = factory

    out = classify_pragmatics_full(
        "Open-source Llama 4 just dropped",
        ["llama"], registry, anthropic_client=client,
    )
    bb = _by_brand(out, "llama")
    assert bb["post_type"] == "buzz_releases"
    assert bb["discourse_role"] == "genuine_hype"


def test_classify_pragmatics_full_array_shape_multi_element_picks_first():
    """U2b-fix: when the LLM emits multiple post_types for one brand
    (e.g., ['event_announcement', 'performance_comparisons'] for a
    launch post that also benchmarks), the reshape into the legacy
    scalar by_brand shape takes the first element. This preserves
    the most-specific bucket (rule 4 of the prompt: 'most posts have
    exactly 1 post_type')."""
    from x_monitor.attribution import classify_pragmatics_full

    registry = [FakeBrandRow("deepseek")]
    client = FakeClaudeClient()

    def factory(*_):
        return {"classifications": [
            {"brand_id": "deepseek",
             "post_types": ["event_announcement", "buzz_releases"],
             "sentiment": "positive",
             "discourse_roles": [],
             "china_nationalism": "none",
             "us_nationalism": "none"},
        ]}
    client._factory = factory

    out = classify_pragmatics_full(
        "DeepSeek-V4 just dropped, MIT-licensed open weights.",
        ["deepseek"], registry, anthropic_client=client,
    )
    bb = _by_brand(out, "deepseek")
    assert bb["post_type"] == "event_announcement", (
        "multi-element post_types[] must collapse to first element "
        "(event_announcement in this case), not the default fallback."
    )
