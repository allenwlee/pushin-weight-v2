"""U4-batch tests for x_monitor.attribution.classify_batch_pragmatics_full.

Plan: docs/plans/2026-07-13-001-feat-live-a-z-populate-db-plan.md (timeout
follow-up). Mirrors `tests/test_classify_pragmatics_full.py` but for the
batch API: one LLM call per 20-post batch, result list index-aligned
with input.

Verifies:
- `build_batch_pragmatics_full_prompt` reuses `_PRAGMATICS_FULL_SYSTEM_PROMPT`
  as the prefix (Anthropic prompt-cache-friendly).
- Empty inputs return [] without calling LLM.
- None client returns per-tweet empty shape in an index-aligned list.
- A happy-path LLM response yields 5 prongs per attributed brand PER post.
- Hallucinated brand_ids (not in registry) are dropped.
- Response count mismatch (LLM returned 19 for a 20-post batch) yields
  empty shape for the entire batch (don't half-commit).
- The function survives a real LLM exception (per-tweet empty shapes,
  on_batch_error callback fires).
- Tweet_id round-trips even when LLM reorders; lookup is by tweet_id.
- Posts with no `brand_ids` get empty shape (per-post skip path).
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
    """Minimal canned-response client (mirrors the per-post test pattern)."""

    def __init__(self, response_factory=None):
        self._factory = response_factory or self._default_factory
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def _default_factory(self, *_):
        return {"results": []}

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        return self._factory()


# --- Prompt builder -----------------------------------------------------


def test_build_batch_prompt_prefix_is_shared_constant():
    """The batch prompt MUST reuse the per-post prefix so Anthropic's
    prompt-cache stays warm across the cycle."""
    from x_monitor.attribution import (
        _PRAGMATICS_FULL_SYSTEM_PROMPT,
        build_batch_pragmatics_full_prompt,
    )

    tweets = [
        {"tweet_id": "t1", "text": "Kimi is fast", "brand_ids": ["kimi"]},
        {"tweet_id": "t2", "text": "GLM crashed", "brand_ids": ["glm"]},
    ]
    prompt = build_batch_pragmatics_full_prompt(tweets)
    assert prompt.startswith(_PRAGMATICS_FULL_SYSTEM_PROMPT), (
        "batch prompt must reuse the shared system prompt prefix; "
        "Anthropic's prompt-cache key is the prefix bytes, so any "
        "divergence breaks caching cycle-over-cycle"
    )
    # Tweet payload is at the tail.
    assert '"t1"' in prompt
    assert '"t2"' in prompt
    assert "Kimi is fast" in prompt
    assert "GLM crashed" in prompt


def test_build_batch_prompt_handles_missing_keys():
    """A tweet dict missing `text` or `brand_ids` should not raise."""
    from x_monitor.attribution import build_batch_pragmatics_full_prompt

    tweets = [
        {"tweet_id": "t1"},  # missing text + brand_ids
        {"tweet_id": "t2", "text": "ok"},
    ]
    prompt = build_batch_pragmatics_full_prompt(tweets)
    assert '"tweet_id": "t1"' in prompt or '"tweet_id":"t1"' in prompt
    assert '"text": ""' in prompt or '"text":""' in prompt


# --- classify_batch_pragmatics_full (public) ----------------------------


def test_classify_batch_returns_empty_for_empty_input():
    from x_monitor.attribution import classify_batch_pragmatics_full

    client = FakeClaudeClient()
    out = classify_batch_pragmatics_full([], [], client)
    assert out == []
    assert client.call_count == 0


def test_classify_batch_short_circuits_when_no_client():
    """`anthropic_client=None` → per-tweet empty shape, index-aligned,
    zero LLM calls."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    tweets = [
        {"tweet_id": "t1", "text": "Kimi is fast", "brand_ids": ["kimi"]},
        {"tweet_id": "t2", "text": "GLM crashed", "brand_ids": ["glm"]},
    ]
    out = classify_batch_pragmatics_full(tweets, [], anthropic_client=None)
    assert len(out) == 2
    for entry in out:
        assert entry == {"by_brand": {}, "unsanctioned_flags": []}


def test_classify_batch_happy_path_per_post_by_brand():
    """LLM returns N result rows; each maps to its tweet_id; per-post
    by_brand dict has all 5 prongs."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    client = FakeClaudeClient(
        response_factory=lambda: {
            "results": [
                {
                    "tweet_id": "t1",
                    "classifications": [{
                        "brand_id": "kimi",
                        "post_types": ["hands_on_usage"],
                        "sentiment": "positive",
                        "discourse_roles": ["genuine_hype"],
                        "china_nationalism": "none",
                        "us_nationalism": "none",
                    }],
                    "unsanctioned_flags": [],
                },
                {
                    "tweet_id": "t2",
                    "classifications": [{
                        "brand_id": "glm",
                        "post_types": ["buzz_releases"],
                        "sentiment": "negative",
                        "discourse_roles": ["fud"],
                        "china_nationalism": "none",
                        "us_nationalism": "none",
                    }],
                    "unsanctioned_flags": ["crypto"],
                },
            ]
        }
    )
    tweets = [
        {"tweet_id": "t1", "text": "Kimi is fast", "brand_ids": ["kimi"]},
        {"tweet_id": "t2", "text": "GLM crashed", "brand_ids": ["glm"]},
    ]
    out = classify_batch_pragmatics_full(tweets, [], client)
    assert len(out) == 2
    assert out[0]["by_brand"] == {
        "kimi": {
            "post_type": "hands_on_usage",
            "sentiment": "positive",
            "discourse_role": "genuine_hype",
            "china_nationalism": "none",
            "us_nationalism": "none",
        }
    }
    assert out[1]["by_brand"]["glm"]["sentiment"] == "negative"
    assert out[1]["by_brand"]["glm"]["discourse_role"] == "fud"
    assert out[1]["unsanctioned_flags"] == ["crypto"]


def test_classify_batch_drops_hallucinated_brand_ids():
    """brand_ids not in the registry are silently dropped."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    client = FakeClaudeClient(
        response_factory=lambda: {
            "results": [{
                "tweet_id": "t1",
                "classifications": [
                    {"brand_id": "kimi",
                     "post_types": ["hands_on_usage"],
                     "sentiment": "positive",
                     "discourse_roles": ["genuine_hype"],
                     "china_nationalism": "none",
                     "us_nationalism": "none"},
                    {"brand_id": "hallucinated_brand",
                     "post_types": ["hands_on_usage"],
                     "sentiment": "positive",
                     "discourse_roles": ["genuine_hype"],
                     "china_nationalism": "none",
                     "us_nationalism": "none"},
                ],
                "unsanctioned_flags": [],
            }]
        }
    )
    brand_registry = [FakeBrandRow(brand_id="kimi")]
    tweets = [
        {"tweet_id": "t1", "text": "Kimi is fast and BrandX too",
         "brand_ids": ["kimi", "hallucinated_brand"]},
    ]
    out = classify_batch_pragmatics_full(tweets, brand_registry, client)
    assert "kimi" in out[0]["by_brand"]
    assert "hallucinated_brand" not in out[0]["by_brand"], (
        "LLM-added brands not in the registry must be dropped"
    )


def test_classify_batch_count_mismatch_emits_empty_for_batch():
    """When the LLM returns 19 results for a 20-post batch, the whole
    batch should fall through to empty (don't half-commit)."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    client = FakeClaudeClient(
        response_factory=lambda: {
            "results": [{
                "tweet_id": "t1",
                "classifications": [],
                "unsanctioned_flags": [],
            }]
        }
    )
    tweets = [
        {"tweet_id": "t1", "text": "x", "brand_ids": ["kimi"]},
        {"tweet_id": "t2", "text": "y", "brand_ids": ["kimi"]},
    ]
    out = classify_batch_pragmatics_full(tweets, [], client)
    assert len(out) == 2
    assert all(
        e == {"by_brand": {}, "unsanctioned_flags": []}
        for e in out
    )


def test_classify_batch_tweet_id_round_trip_robust_to_reorder():
    """LLM may emit results in a different order than the input.
    We round-trip by `tweet_id`, NOT by positional index."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    client = FakeClaudeClient(
        response_factory=lambda: {
            "results": [
                # t2 first, t1 second
                {
                    "tweet_id": "t2",
                    "classifications": [{
                        "brand_id": "glm",
                        "post_types": ["buzz_releases"],
                        "sentiment": "negative",
                        "discourse_roles": ["fud"],
                        "china_nationalism": "none",
                        "us_nationalism": "none",
                    }],
                    "unsanctioned_flags": [],
                },
                {
                    "tweet_id": "t1",
                    "classifications": [{
                        "brand_id": "kimi",
                        "post_types": ["hands_on_usage"],
                        "sentiment": "positive",
                        "discourse_roles": ["genuine_hype"],
                        "china_nationalism": "none",
                        "us_nationalism": "none",
                    }],
                    "unsanctioned_flags": [],
                },
            ]
        }
    )
    tweets = [
        {"tweet_id": "t1", "text": "Kimi", "brand_ids": ["kimi"]},
        {"tweet_id": "t2", "text": "GLM", "brand_ids": ["glm"]},
    ]
    out = classify_batch_pragmatics_full(tweets, [], client)
    assert out[0]["by_brand"].get("kimi"), (
        "t1 should resolve to kimi's positive classification even though "
        "the LLM emitted t2 first"
    )
    assert out[1]["by_brand"].get("glm")


def test_classify_batch_unknown_enum_values_coerce_to_defaults():
    """post_type / sentiment / discourse_role / nationalism values
    that aren't in the enum fall back to the v1.5 defaults."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    client = FakeClaudeClient(
        response_factory=lambda: {
            "results": [{
                "tweet_id": "t1",
                "classifications": [{
                    "brand_id": "kimi",
                    "post_types": ["bogus_value"],
                    "sentiment": "garbage_sentiment",
                    "discourse_roles": ["garbage_role"],
                    "china_nationalism": "made_up_axis",
                    "us_nationalism": "also_made_up",
                }],
                "unsanctioned_flags": ["totally_bogus_flag"],
            }]
        }
    )
    tweets = [
        {"tweet_id": "t1", "text": "x", "brand_ids": ["kimi"]},
    ]
    out = classify_batch_pragmatics_full(tweets, [], client)
    prong = out[0]["by_brand"]["kimi"]
    assert prong["post_type"] == "hands_on_usage"
    assert prong["sentiment"] == "neutral"
    assert prong["discourse_role"] == "uncategorized"
    assert prong["china_nationalism"] == "none"
    assert prong["us_nationalism"] == "none"
    # Unsanctioned flags are filtered against the allow-list, not coerced.
    assert out[0]["unsanctioned_flags"] == []


def test_classify_batch_one_batch_invocation_per_20_posts():
    """20 posts → 1 LLM call (batching), not 20 (per-post serial)."""
    from x_monitor.attribution import (
        _CLASSIFY_BATCH_SIZE,
        classify_batch_pragmatics_full,
    )

    posts = [
        {"tweet_id": f"t{i}", "text": f"text {i}",
         "brand_ids": ["kimi"]}
        for i in range(_CLASSIFY_BATCH_SIZE)
    ]

    client = FakeClaudeClient(
        response_factory=lambda: {
            "results": [
                {
                    "tweet_id": f"t{i}",
                    "classifications": [{
                        "brand_id": "kimi",
                        "post_types": ["hands_on_usage"],
                        "sentiment": "neutral",
                        "discourse_roles": ["uncategorized"],
                        "china_nationalism": "none",
                        "us_nationalism": "none",
                    }],
                    "unsanctioned_flags": [],
                }
                for i in range(_CLASSIFY_BATCH_SIZE)
            ]
        }
    )
    out = classify_batch_pragmatics_full(posts, [], client)
    assert client.call_count == 1, (
        f"expected 1 LLM call for 20 posts; got {client.call_count} — "
        f"the batch isn't actually batching"
    )
    assert len(out) == _CLASSIFY_BATCH_SIZE
    for entry in out:
        assert "kimi" in entry["by_brand"]


def test_classify_batch_llm_exception_yields_empty_shape():
    """When the LLM call raises after retries, every post in that batch
    gets the empty shape, AND on_batch_error fires exactly once."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    class BoomClient:
        def __init__(self):
            self.calls = 0

        def messages_create(self, **kwargs):
            self.calls += 1
            raise RuntimeError("kaboom")

    on_err_calls: list[tuple[list, Exception]] = []

    def on_err(batch, exc):
        on_err_calls.append((batch, exc))

    tweets = [
        {"tweet_id": "t1", "text": "x", "brand_ids": ["kimi"]},
        {"tweet_id": "t2", "text": "y", "brand_ids": ["kimi"]},
    ]
    out = classify_batch_pragmatics_full(
        tweets, [], BoomClient(), on_batch_error=on_err,
    )
    assert len(out) == 2
    for entry in out:
        assert entry == {"by_brand": {}, "unsanctioned_flags": []}
    assert len(on_err_calls) == 1


def test_batch_failure_fallback_keeps_explicit_model_and_thinking(monkeypatch):
    """Every per-post fallback keeps the batch's explicit DeepSeek route."""
    from x_monitor import attribution

    monkeypatch.setattr(attribution, "_BACKOFF_BASE_SECONDS", 0)

    class BatchFailsClient:
        def __init__(self):
            self.calls: list[dict[str, Any]] = []

        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            prompt = kwargs["messages"][0]["content"]
            if "Tweets (JSON array of" in prompt:
                raise RuntimeError("force batch fallback")
            return {
                "results": [{
                    "tweet_id": "_single_",
                    "classifications": [],
                    "unsanctioned_flags": [],
                }]
            }

    client = BatchFailsClient()
    tweets = [
        {"tweet_id": "fallback-1", "text": "DeepSeek one", "brand_ids": ["deepseek"]},
        {"tweet_id": "fallback-2", "text": "DeepSeek two", "brand_ids": ["deepseek"]},
    ]

    attribution.classify_batch_pragmatics_full(
        tweets,
        [FakeBrandRow(brand_id="deepseek")],
        client,
        model="deepseek-v4-flash",
        thinking={"type": "disabled"},
    )

    fallback_calls = [
        call for call in client.calls
        if "Apply the rules and worked examples to this single tweet" in
        call["messages"][0]["content"]
    ]
    assert len(fallback_calls) == 2
    assert {call["model"] for call in fallback_calls} == {"deepseek-v4-flash"}
    assert {call["thinking"]["type"] for call in fallback_calls} == {"disabled"}


def test_classify_batch_no_brand_ids_post_yields_empty_shape():
    """A tweet with empty brand_ids still occupies a slot in the
    returned list — the empty shape is surfaced, NOT skipped."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    client = FakeClaudeClient(
        response_factory=lambda: {
            "results": [{
                "tweet_id": "t2",
                "classifications": [{
                    "brand_id": "kimi",
                    "post_types": ["hands_on_usage"],
                    "sentiment": "positive",
                    "discourse_roles": ["genuine_hype"],
                    "china_nationalism": "none",
                    "us_nationalism": "none",
                }],
                "unsanctioned_flags": [],
            }]
        }
    )
    tweets = [
        {"tweet_id": "t1", "text": "no brand here", "brand_ids": []},
        {"tweet_id": "t2", "text": "Kimi is fast", "brand_ids": ["kimi"]},
    ]
    out = classify_batch_pragmatics_full(tweets, [], client)
    assert len(out) == 2
    assert out[0] == {"by_brand": {}, "unsanctioned_flags": []}, (
        "the no-brand post should emit an empty-shape entry even though "
        "the LLM batch only included the second tweet"
    )
    assert "kimi" in out[1]["by_brand"]
    # The skipped post should NOT have been forwarded to the LLM —
    # i.e. the LLM was called with exactly 1 tweet.
    last_call = client.calls[0]
    prompt_content = last_call["messages"][0]["content"]
    assert '"tweet_id": "t2"' in prompt_content
    assert '"tweet_id": "t1"' not in prompt_content
