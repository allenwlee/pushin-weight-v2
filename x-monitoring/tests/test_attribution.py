# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.attribution: consolidator + per-brand classifier.

Covers Decision 13 (raw_token format), R7 (compute_post_brands),
R8 (classify_post brand_id validation + hallucination drop), and
the 16 plan-mandated scenarios (multi-brand equal split, dedup,
case-insensitive, unknown handles, NULL entities, etc.).
"""

from __future__ import annotations

from typing import Any

import pytest

from x_monitor.attribution import (
    AnthropicClaudeClient,
    BrandRow,
    MentionRow,
    attribute_to_brands,
    build_signal_prompt,
    classify_post,
    compile_keyword_index,
    compute_post_brands,
    extract_body_keywords,
    extract_hashtag_mentions,
    extract_search_term_match,
    extract_user_mentions,
    validate_raw_token,
)


# --- Shared fixtures: 11-brand registry + 4 detection tables ------------

BRAND_REGISTRY: list[BrandRow] = [
    BrandRow("minimax", "MiniMax", "#a855f7", False),
    BrandRow("qwen", "Qwen", "#22c55e", False),
    BrandRow("deepseek", "DeepSeek", "#0ea5e9", False),
    BrandRow("glm", "GLM", "#facc15", False),
    BrandRow("mimo", "MiMo", "#ef4444", False),
    BrandRow("moonshot_kimi", "Kimi", "#ec4899", False),
    BrandRow("inclusionai", "InclusionAI", "#3b82f6", False),
    BrandRow("mistral", "Mistral", "#facc15", False),
    BrandRow("stepfun", "StepFun", "#22c55e", False),
    BrandRow("ernie", "Ernie", "#0ea5e9", False),
    BrandRow("hunyuan", "Hunyuan", "#ec4899", False),
    BrandRow("_unattributed", "Unattributed", "#6b7280", True),
]

# Detection tables used by the 4 extractors.
BRAND_ACCOUNTS: dict[str, str] = {
    "1001": "minimax",     # @MiniMaxAI (numeric id)
    "1002": "qwen",        # @Alibaba_Qwen
    "1003": "deepseek",    # @deepseek_ai
    "1004": "moonshot_kimi",  # @Kimi_Moonshot
}

BRAND_HASHTAGS: dict[str, str] = {
    "kimi":     "moonshot_kimi",
    "minimax":  "minimax",
    "qwen":     "qwen",
    "deepseek": "deepseek",
}

BRAND_KEYWORDS_RAW: list[tuple[str, str, bool]] = [
    ("minimax",       "MiniMax", False),
    ("minimax",       "Hailuo", False),
    ("minimax",       "海螺",     False),
    ("qwen",          "Qwen",    False),
    ("deepseek",      "DeepSeek", False),
    ("deepseek",      r"DS[ -]?V\d+", True),  # regex: matches DS-V3, DS V3
    ("glm",           "GLM",     False),
    ("glm",           "智谱",     False),
    ("mimo",   "MiMo",    False),
    ("moonshot_kimi", "Kimi",    False),
    ("inclusionai",   "Ling",    False),
]

BRAND_SEARCH_TERMS: dict[str, str] = {
    "minimax": "minimax",
    "qwen": "qwen",
    "deepseek": "deepseek",
}


def _keyword_index():
    return compile_keyword_index(BRAND_KEYWORDS_RAW)


def _post(**overrides) -> dict[str, Any]:
    """Default post factory with sensible defaults."""
    base: dict[str, Any] = {
        "tweet_id": "1234567890",
        "id": "1234567890",
        "created_at": "2026-06-19T12:34:56Z",
        "text": "",
        "author_handle": "",
        "entities": {},
    }
    base.update(overrides)
    return base


# --- raw_token format (Decision 13) --------------------------------------


class TestRawTokenFormat:
    """Validate raw_token matches Decision 13 per-source format."""

    def test_user_mention_format_examples(self):
        # 3+ examples each per the plan.
        validate_raw_token("user_mention", "@MiniMaxAI")  # OK
        validate_raw_token("user_mention", "@kimi_devs")  # OK
        validate_raw_token("user_mention", "@MiniMax_AI")  # OK
        validate_raw_token("user_mention", "@ab")  # OK short
        with pytest.raises(ValueError):
            validate_raw_token("user_mention", "MiniMaxAI")  # no @
        with pytest.raises(ValueError):
            validate_raw_token("user_mention", "@")  # empty handle
        with pytest.raises(ValueError):
            validate_raw_token("user_mention", "@thisisaverylonghandle")  # >15
        with pytest.raises(ValueError):
            validate_raw_token("user_mention", "")

    def test_hashtag_format_examples(self):
        validate_raw_token("hashtag", "#kimi")
        validate_raw_token("hashtag", "#MiniMax")
        validate_raw_token("hashtag", "#qwen3")
        with pytest.raises(ValueError):
            validate_raw_token("hashtag", "kimi")  # no #
        with pytest.raises(ValueError):
            validate_raw_token("hashtag", "#")  # empty tag
        with pytest.raises(ValueError):
            validate_raw_token("hashtag", "")

    def test_body_keyword_format_examples(self):
        validate_raw_token("body_keyword", "MiniMax")  # bare
        validate_raw_token("body_keyword", "海螺")  # CJK
        validate_raw_token("body_keyword", "DS-V3")  # regex match
        validate_raw_token("body_keyword", "M3.0")  # punctuation OK
        with pytest.raises(ValueError):
            validate_raw_token("body_keyword", "@MiniMax")  # @ forbidden
        with pytest.raises(ValueError):
            validate_raw_token("body_keyword", "#kimi")  # # forbidden
        with pytest.raises(ValueError):
            validate_raw_token("body_keyword", "  MiniMax  ")  # whitespace
        with pytest.raises(ValueError):
            validate_raw_token("body_keyword", "")

    def test_search_term_format_examples(self):
        validate_raw_token("search_term", "minimax")
        validate_raw_token("search_term", "MiniMax")
        validate_raw_token("search_term", "海螺")
        # R6: search_term ALLOWS empty raw_token (sentinel row for
        # "no search keyword matched" provenance). The other 3
        # sources still reject empty.
        validate_raw_token("search_term", "")

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError):
            validate_raw_token("unknown_source", "anything")  # type: ignore

    def test_mentionrow_constructor_enforces_format(self):
        # Construction calls validate_raw_token via __post_init__.
        with pytest.raises(ValueError):
            MentionRow(
                post_id="1",
                brand_id="minimax",
                source="user_mention",
                raw_token="no_at_prefix",
                mentioned_at="2026-06-19T00:00:00Z",
            )


# --- Happy path: each source independently -------------------------------


class TestSingleBrandHappyPaths:
    """One brand via each of the 4 sources."""

    def test_single_brand_via_author_handle(self):
        # post.entities has user_mention for @MiniMaxAI (id 1001)
        post = _post(
            entities={
                "user_mentions": [
                    {"id": "1001", "username": "MiniMaxAI"},
                ],
            },
        )
        rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
        assert len(rows) == 1
        assert rows[0].brand_id == "minimax"
        assert rows[0].source == "user_mention"
        assert rows[0].raw_token == "@MiniMaxAI"

    def test_single_brand_via_hashtag(self):
        post = _post(
            entities={
                "hashtags": [{"tag": "kimi"}],
            },
        )
        rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
        assert len(rows) == 1
        assert rows[0].brand_id == "moonshot_kimi"
        assert rows[0].source == "hashtag"
        assert rows[0].raw_token == "#kimi"

    def test_single_brand_via_body_keyword(self):
        post = _post(text="I love Qwen 3")
        rows = extract_body_keywords(post, _keyword_index())
        assert len(rows) == 1
        assert rows[0].brand_id == "qwen"
        assert rows[0].source == "body_keyword"
        assert rows[0].raw_token == "Qwen"  # matched substring

    def test_single_brand_via_search_term(self):
        post = _post()
        rows = extract_search_term_match(
            post,
            search_query=["minimax"],
            brand_search_terms=BRAND_SEARCH_TERMS,
        )
        # No body_keyword match, but search_term matches.
        assert len(rows) == 1
        assert rows[0].brand_id == "minimax"
        assert rows[0].source == "search_term"
        assert rows[0].raw_token == "minimax"


# --- compute_post_brands (R7) -------------------------------------------


class TestComputePostBrands:
    """Consolidator: union, fractional 1/N weights, _unattributed fallback."""

    def test_single_brand_full_weight(self):
        post = _post()
        mentions = [
            MentionRow("1", "minimax", "user_mention", "@MiniMaxAI", "2026-06-19T00:00:00Z"),
            MentionRow("1", "minimax", "body_keyword", "MiniMax", "2026-06-19T00:00:00Z"),
        ]
        result = compute_post_brands(post, mentions)
        assert result == [("minimax", 1.0)]

    def test_multi_brand_equal_split(self):
        post = _post(text="Qwen 3 vs DeepSeek V3")
        mentions = extract_body_keywords(post, _keyword_index())
        result = compute_post_brands(post, mentions)
        # Should have at least qwen + deepseek.
        brand_ids = [b for b, _ in result]
        assert "qwen" in brand_ids
        assert "deepseek" in brand_ids
        # Weights sum to 1.0.
        assert sum(w for _, w in result) == pytest.approx(1.0)
        # Equal split among the detected brands.
        n = len(result)
        for _, w in result:
            assert w == pytest.approx(1.0 / n)

    def test_no_brand_found_returns_unattributed(self):
        post = _post(
            text="This is a random tweet about nothing in particular.",
            entities={},
        )
        mentions: list[MentionRow] = []
        mentions.extend(extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"]))
        mentions.extend(extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"]))
        mentions.extend(extract_body_keywords(post, _keyword_index()))
        # No search_term match yet either, but the extractor always
        # emits at least one row.
        mentions.extend(extract_search_term_match(post, [], BRAND_SEARCH_TERMS))
        result = compute_post_brands(post, mentions)
        # The search_term row with brand_id=None gets filtered; the
        # remaining union is empty -> _unattributed.
        assert result == [("_unattributed", 1.0)]

    def test_dedup_three_sources_to_one_brand(self):
        post = _post(
            text="minimax M3 is great",
            entities={
                "user_mentions": [{"id": "1001", "username": "MiniMaxAI"}],
                "hashtags": [{"tag": "minimax"}],
            },
        )
        mentions: list[MentionRow] = []
        mentions.extend(extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"]))
        mentions.extend(extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"]))
        mentions.extend(extract_body_keywords(post, _keyword_index()))
        # 3 rows, all minimax.
        assert len(mentions) == 3
        assert all(m.brand_id == "minimax" for m in mentions)
        result = compute_post_brands(post, mentions)
        assert result == [("minimax", 1.0)]

    def test_dedup_filters_null_brand_ids(self):
        # An unknown @mention preserves brand_id=None; it should
        # NOT participate in the union.
        post = _post(
            entities={
                "user_mentions": [
                    {"id": "1001", "username": "MiniMaxAI"},  # known
                    {"id": "9999", "username": "random_user"},  # unknown
                ],
            },
        )
        mentions = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
        # 2 rows: one with brand_id=minimax, one with brand_id=None.
        assert len(mentions) == 2
        result = compute_post_brands(post, mentions)
        # Only minimax survives the union.
        assert result == [("minimax", 1.0)]


# --- Case-insensitive matching ------------------------------------------


class TestCaseInsensitive:
    """Hashtag + body_keyword are case-insensitive per R4 / R5."""

    def test_uppercase_hashtag_resolves(self):
        post = _post(entities={"hashtags": [{"tag": "MINIMAX"}]})
        rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
        assert len(rows) == 1
        assert rows[0].brand_id == "minimax"
        assert rows[0].raw_token == "#minimax"  # lowercased

    def test_uppercase_body_keyword_matches(self):
        post = _post(text="I love MINIMAX")
        rows = extract_body_keywords(post, _keyword_index())
        assert len(rows) == 1
        assert rows[0].brand_id == "minimax"
        assert rows[0].raw_token == "MINIMAX"  # matched substring preserved


# --- Unknown hashtag / user_mention -------------------------------------


class TestUnknownHandling:
    """Unknown hashtags silently dropped; unknown user_mentions get None."""

    def test_unknown_hashtag_silently_dropped(self):
        post = _post(entities={"hashtags": [{"tag": "worldcup-2026"}]})
        rows = extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"])
        assert rows == []

    def test_unknown_user_mention_brand_id_null(self):
        post = _post(
            entities={
                "user_mentions": [{"id": "9999", "username": "random_user"}],
            },
        )
        rows = extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"])
        assert len(rows) == 1
        assert rows[0].brand_id is None
        assert rows[0].raw_token == "@random_user"


# --- Regex body_keyword (capture groups) ---------------------------------


class TestRegexBodyKeyword:
    """R5 + Decision: regex patterns return matched substrings."""

    def test_regex_matches_pattern(self):
        post = _post(text="Try DS-V3 and DS V2 for inference")
        rows = extract_body_keywords(post, _keyword_index())
        # Both DS-V3 and DS V2 match the deepseek regex r"DS[ -]?V\d+".
        ds_matches = [r for r in rows if r.brand_id == "deepseek"]
        assert len(ds_matches) == 2
        matched = sorted([r.raw_token for r in ds_matches])
        assert matched == ["DS V2", "DS-V3"]


# --- NULL entities handling ---------------------------------------------


class TestNullEntities:
    """entities can be None, the string 'null', or non-dict JSON."""

    def test_entities_none(self):
        post = _post(text="minimax is great", entities=None)
        mentions: list[MentionRow] = []
        mentions.extend(extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"]))
        mentions.extend(extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"]))
        mentions.extend(extract_body_keywords(post, _keyword_index()))
        # body_keyword still matches (text is unaffected).
        assert len(mentions) == 1
        assert mentions[0].brand_id == "minimax"
        assert mentions[0].source == "body_keyword"

    def test_entities_string_null(self):
        post = _post(text="minimax is great", entities="null")
        mentions: list[MentionRow] = []
        mentions.extend(extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"]))
        mentions.extend(extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"]))
        mentions.extend(extract_body_keywords(post, _keyword_index()))
        # Should not raise; body_keyword still matches.
        assert len(mentions) == 1
        assert mentions[0].brand_id == "minimax"

    def test_entities_string_empty(self):
        post = _post(text="minimax is great", entities="")
        mentions: list[MentionRow] = []
        mentions.extend(extract_user_mentions(post, BRAND_ACCOUNTS, post["entities"]))
        mentions.extend(extract_hashtag_mentions(post, BRAND_HASHTAGS, post["entities"]))
        mentions.extend(extract_body_keywords(post, _keyword_index()))
        assert len(mentions) == 1


# --- classify_post (R8, U9) --------------------------------------------


class FakeClaudeClient:
    """Minimal in-memory Claude client for tests."""

    def __init__(self, response: dict[str, Any] | Exception):
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class TestClassifyPost:
    """R8 + U9: per-brand (post_type, sentiment) classification.

    U9 replaces the legacy 6-bucket `signal` taxonomy with the
    (post_type, sentiment) decomposition. The LLM still validates
    brand_ids against the registry (R8 hallucination drop).
    """

    def test_validates_brand_ids_against_registry(self):
        # LLM returns real brands -> preserved.
        client = FakeClaudeClient({
            "classifications": [
                {"brand_id": "minimax", "post_type": "buzz_releases", "sentiment": "positive"},
                {"brand_id": "qwen", "post_type": "buzz_releases", "sentiment": "negative"},
            ]
        })
        out = classify_post(
            "minimax is great, qwen is bad",
            brand_ids=["minimax", "qwen"],
            brand_registry=BRAND_REGISTRY,
            anthropic_client=client,
        )
        assert out == {
            "minimax": ("buzz_releases", "positive"),
            "qwen": ("buzz_releases", "negative"),
        }

    def test_drops_hallucinated_brand_ids(self):
        # LLM invents "m3_pro" -> dropped (R8).
        client = FakeClaudeClient({
            "classifications": [
                {"brand_id": "minimax", "post_type": "buzz_releases", "sentiment": "positive"},
                {"brand_id": "m3_pro", "post_type": "buzz_releases", "sentiment": "positive"},  # hallucinated
                {"brand_id": "fakebrand", "post_type": "buzz_releases", "sentiment": "positive"},  # hallucinated
            ]
        })
        out = classify_post(
            "minimax M3 is amazing",
            brand_ids=["minimax"],
            brand_registry=BRAND_REGISTRY,
            anthropic_client=client,
        )
        assert out == {"minimax": ("buzz_releases", "positive")}

    def test_coerces_unknown_post_type_to_hands_on_usage(self):
        # Unknown post_type / sentiment -> fallback per 022 default.
        client = FakeClaudeClient({
            "classifications": [
                {"brand_id": "minimax", "post_type": "BOGUS_VALUE", "sentiment": "BOGUS_VALUE"},
            ]
        })
        out = classify_post(
            "minimax",
            brand_ids=["minimax"],
            brand_registry=BRAND_REGISTRY,
            anthropic_client=client,
        )
        assert out == {"minimax": ("hands_on_usage", "neutral")}

    def test_returns_empty_when_no_client(self):
        # Offline / dry-run path.
        out = classify_post(
            "minimax",
            brand_ids=["minimax"],
            brand_registry=BRAND_REGISTRY,
            anthropic_client=None,
        )
        assert out == {}

    def test_returns_empty_when_no_brand_ids(self):
        client = FakeClaudeClient({"classifications": []})
        out = classify_post(
            "nothing",
            brand_ids=[],
            brand_registry=BRAND_REGISTRY,
            anthropic_client=client,
        )
        assert out == {}
        # LLM should not be called.
        assert client.calls == []

    def test_returns_empty_on_llm_failure(self):
        client = FakeClaudeClient(RuntimeError("upstream down"))
        out = classify_post(
            "minimax",
            brand_ids=["minimax"],
            brand_registry=BRAND_REGISTRY,
            anthropic_client=client,
        )
        assert out == {}

    def test_returns_empty_on_malformed_response(self):
        client = FakeClaudeClient({"unexpected_key": []})  # no "classifications"
        out = classify_post(
            "minimax",
            brand_ids=["minimax"],
            brand_registry=BRAND_REGISTRY,
            anthropic_client=client,
        )
        assert out == {}

    def test_build_signal_prompt_contains_brand_ids(self):
        prompt = build_signal_prompt("minimax is great", ["minimax", "qwen"])
        assert "minimax" in prompt
        assert "qwen" in prompt
        assert "minimax is great" in prompt
        # U9: the prompt now asks for (post_type, sentiment), not the
        # legacy 6-bucket signal taxonomy.
        assert "post_type" in prompt
        assert "sentiment" in prompt


# --- attribute_to_brands end-to-end (R2) --------------------------------


class TestAttributeToBrands:
    """The top-level driver; verifies mention-row emission + confidence.

    v1.8 (R2) rewrite: `attribute_to_brands` returns the consolidated
    `list[MentionRow]` (deduped by `(brand_id, source)`). Per-brand
    confidence is derived via `BRAND_SOURCE_PRIORITY[m.source]`
    (the highest source priority contributing to a brand gives the
    per-brand confidence).
    """

    @staticmethod
    def _per_brand_confidence(
        mentions: list[MentionRow],
    ) -> dict[str, float]:
        """Aggregate max source-priority per brand_id."""
        from x_monitor.attribution import BRAND_SOURCE_PRIORITY
        out: dict[str, float] = {}
        for m in mentions:
            if not m.brand_id:
                continue
            prev = out.get(m.brand_id, 0.0)
            conf = BRAND_SOURCE_PRIORITY[m.source]
            if conf > prev:
                out[m.brand_id] = conf
        return out

    def test_user_mention_plus_hashtag_yields_confidence_1(self):
        post = _post(
            text="",
            entities={
                "user_mentions": [{"id": "1001", "username": "MiniMaxAI"}],
                "hashtags": [{"tag": "minimax"}],
            },
        )
        mentions = attribute_to_brands(
            post,
            BRAND_ACCOUNTS,
            BRAND_HASHTAGS,
            _keyword_index(),
            search_query=[],
            brand_search_terms=BRAND_SEARCH_TERMS,
        )
        # Two high-confidence sources -> confidence = max(1.0, 0.9) = 1.0.
        assert self._per_brand_confidence(mentions) == {"minimax": 1.0}

    def test_body_keyword_plus_search_term_yields_confidence_07(self):
        post = _post(text="Qwen 3 is great")
        mentions = attribute_to_brands(
            post,
            BRAND_ACCOUNTS,
            BRAND_HASHTAGS,
            _keyword_index(),
            search_query=["qwen"],
            brand_search_terms=BRAND_SEARCH_TERMS,
        )
        # body_keyword=0.7, search_term=0.6 -> max=0.7.
        assert self._per_brand_confidence(mentions) == {"qwen": 0.7}

    def test_mixed_sources_take_max_confidence(self):
        # body_keyword (0.7) + search_term (0.6) + user_mention (1.0)
        # -> confidence = 1.0 for the brand.
        post = _post(
            text="Qwen 3 is amazing",
            entities={
                "user_mentions": [{"id": "1002", "username": "Alibaba_Qwen"}],
            },
        )
        mentions = attribute_to_brands(
            post,
            BRAND_ACCOUNTS,
            BRAND_HASHTAGS,
            _keyword_index(),
            search_query=["qwen"],
            brand_search_terms=BRAND_SEARCH_TERMS,
        )
        assert self._per_brand_confidence(mentions) == {"qwen": 1.0}

    def test_no_brand_returns_unattributed_zero_confidence(self):
        post = _post(text="completely unrelated")
        mentions = attribute_to_brands(
            post,
            BRAND_ACCOUNTS,
            BRAND_HASHTAGS,
            _keyword_index(),
            search_query=[],
            brand_search_terms=BRAND_SEARCH_TERMS,
        )
        # No brand detected -> empty per-brand confidence map.
        assert self._per_brand_confidence(mentions) == {}


def test_resolve_signal_model_resolution_ladder(monkeypatch):
    """_resolve_signal_model env-var resolution order (P1 #2 regression
    guard for the M2.7 -> M3.0 default).

      1. ANTHROPIC_MODEL env wins always.
      2. else, MiniMax-M3.0 if ANTHROPIC_BASE_URL routes through minimax.io.
      3. else, deepseek-v4-pro if ANTHROPIC_BASE_URL routes through deepseek.com.
      4. else, claude-haiku-4-5 (direct api.anthropic.com).
    """
    from x_monitor.attribution import _resolve_signal_model

    # (env unset, no proxy) -> claude-haiku-4-5
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    assert _resolve_signal_model() == "claude-haiku-4-5"

    # (env unset, minimax proxy) -> MiniMax-M3.0 (the fix's default)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    assert _resolve_signal_model() == "MiniMax-M3.0"

    # (env=M2.7, proxy) -> M2.7 (env wins; operator can still opt into the
    # slower thinking-block model if they want)
    monkeypatch.setenv("ANTHROPIC_MODEL", "MiniMax-M2.7")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    assert _resolve_signal_model() == "MiniMax-M2.7"

    # (env=haiku, no proxy) -> haiku
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    assert _resolve_signal_model() == "claude-haiku-4-5"

    # (env unset, deepseek proxy) -> deepseek-v4-pro (Plan 2026-07-15-002)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    assert _resolve_signal_model() == "deepseek-v4-pro"

    # (env=override, deepseek) -> override wins
    monkeypatch.setenv("ANTHROPIC_MODEL", "custom-deepseek-model")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    assert _resolve_signal_model() == "custom-deepseek-model"

    # (env unset, deepseek wins over direct-haiku) -> deepseek-v4-pro
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    assert _resolve_signal_model() == "deepseek-v4-pro"


def test_resolve_thinking_default(monkeypatch):
    """_resolve_thinking_default returns {"type": "disabled"} only for
    the deepseek path. The MiniMax M3 and direct-Anthropic paths return
    None so the parameter is omitted from the SDK call and behavior is
    unchanged from the pre-swap state.

    Without thinking=disabled, the DeepSeek V4 Pro reasoning model
    would consume the entire output budget on internal deliberation
    (verified during the 2026-07-15 live probe — 4096-token budget
    was 100% consumed by thinking, no JSON emitted).
    """
    from x_monitor.attribution import _resolve_thinking_default

    # Unset base_url -> None (default, no thinking param)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    assert _resolve_thinking_default() is None

    # MiniMax proxy -> None (M3 path unchanged)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    assert _resolve_thinking_default() is None

    # DeepSeek path -> {"type": "disabled"} (required for reasoning model)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    assert _resolve_thinking_default() == {"type": "disabled"}

    # Direct Anthropic -> None
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    assert _resolve_thinking_default() is None


def test_max_tokens_for_batch():
    """_max_tokens_for_batch returns min(8192, max(4096, 200*batch_size)).

    Grounded in two probe runs at data/runs/dsv4-probe-20260715T071331Z.json:
    batch_size=20 used 99 tokens/tweet; batch_size=40 with max_tokens=8192
    used 108 tokens/tweet. The 200-token coefficient gives 100% headroom.
    """
    from x_monitor.attribution import _max_tokens_for_batch

    # Floor: small batches get the 4096 minimum
    assert _max_tokens_for_batch(1) == 4096
    assert _max_tokens_for_batch(10) == 4096
    # 200*20 = 4000, clamped up to 4096
    assert _max_tokens_for_batch(20) == 4096

    # Linear: 21 tweets -> 200*21 = 4200
    assert _max_tokens_for_batch(21) == 4200
    # 40 tweets -> 200*40 = 8000
    assert _max_tokens_for_batch(40) == 8000

    # Cap: 80 tweets -> 200*80 = 16000, capped to 8192
    assert _max_tokens_for_batch(80) == 8192
    # Even very large batches cap at 8192 (safety margin)
    assert _max_tokens_for_batch(200) == 8192


def test_validate_deepseek_response_shape_valid():
    """_validate_deepseek_response_shape accepts a valid wire format.

    The wire format is the production response shape (the one
    _classify_one_batch_to_by_brand consumes): {"results": [{"tweet_id":
    str, "classifications": list, "unsanctioned_flags": [str]}]} with
    one entry per input tweet.
    """
    from x_monitor.attribution import _validate_deepseek_response_shape

    # Valid: results is a list of dicts with tweet_id + classifications
    valid = {
        "results": [
            {"tweet_id": "t1", "classifications": [], "unsanctioned_flags": []},
            {"tweet_id": "t2", "classifications": [], "unsanctioned_flags": []},
        ]
    }
    # Should not raise
    _validate_deepseek_response_shape(valid, 2)


def test_validate_deepseek_response_shape_missing_unsanctioned_flags(caplog):
    """_validate_deepseek_response_shape does NOT raise on missing
    unsanctioned_flags; logs at WARNING. The existing parser
    defaults to [] via _parse_unsanctioned_flags (line 1467 returns []
    for non-list input).
    """
    import logging
    from x_monitor.attribution import _validate_deepseek_response_shape

    missing_flags = {
        "results": [
            {"tweet_id": "t1", "classifications": []},  # no unsanctioned_flags
        ]
    }
    with caplog.at_level(logging.WARNING):
        _validate_deepseek_response_shape(missing_flags, 1)
    assert any("unsanctioned_flags" in r.message for r in caplog.records)


def test_validate_deepseek_response_shape_raises_on_drift():
    """_validate_deepseek_response_shape raises ValueError on shape drift.

    Seven failure modes (each raises ValueError with a descriptive
    message), per plan U3 test scenario list.
    """
    import pytest
    from x_monitor.attribution import _validate_deepseek_response_shape

    # (a) count mismatch
    with pytest.raises(ValueError, match="shape drift"):
        _validate_deepseek_response_shape(
            {"results": [{"tweet_id": "t1", "classifications": []}]}, 2
        )

    # (b) missing 'results' key
    with pytest.raises(ValueError, match="missing 'results'"):
        _validate_deepseek_response_shape({"foo": "bar"}, 0)

    # (c) results is not a list
    with pytest.raises(ValueError, match="'results' is"):
        _validate_deepseek_response_shape({"results": "not a list"}, 1)

    # (d) results is None
    with pytest.raises(ValueError, match="is NoneType, expected list"):
        _validate_deepseek_response_shape({"results": None}, 0)

    # (e) entry is not a dict
    with pytest.raises(ValueError, match="results\\[0\\] is"):
        _validate_deepseek_response_shape(
            {"results": [None]}, 1
        )

    # (f) entry missing tweet_id
    with pytest.raises(ValueError, match="tweet_id is"):
        _validate_deepseek_response_shape(
            {"results": [{"classifications": []}]}, 1
        )

    # (g) entry missing classifications
    with pytest.raises(ValueError, match="classifications is"):
        _validate_deepseek_response_shape(
            {"results": [{"tweet_id": "t1"}]}, 1
        )

    # bonus: response is not a dict
    with pytest.raises(ValueError, match="is NoneType, expected dict"):
        _validate_deepseek_response_shape(None, 0)

    with pytest.raises(ValueError, match="is str, expected dict"):
        _validate_deepseek_response_shape("not a dict", 0)


def test_call_signal_with_retry_threads_thinking_through():
    """_call_signal_with_retry forwards `thinking` to messages_create as
    a top-level kwarg when set. When None, the kwarg is absent (M3
    and direct-Anthropic paths unchanged).

    The Anthropic SDK's thinking parameter shape for the disabled case
    is {"type": "disabled"} (per the ThinkingConfigDisabledParam
    TypedDict in anthropic-sdk-python 0.104.0).
    """
    from x_monitor.attribution import _call_signal_with_retry

    captured = {}

    class FakeClient:
        def messages_create(self, **kwargs):
            captured.update(kwargs)
            return {"results": []}

    client = FakeClient()
    prompt = "test prompt"

    # thinking=None: kwarg absent (M3 path default, also direct)
    captured.clear()
    _call_signal_with_retry(client, prompt, max_tokens=4096, thinking=None)
    assert "thinking" not in captured
    # The model is whatever _SIGNAL_MODEL resolved to at import time
    # (cached). The test doesn't pin the model — only the thinking
    # threading behavior.
    assert captured["max_tokens"] == 4096

    # thinking={"type": "disabled"}: kwarg present
    captured.clear()
    _call_signal_with_retry(
        client, prompt, max_tokens=4096, thinking={"type": "disabled"}
    )
    assert captured["thinking"] == {"type": "disabled"}


def test_classify_batch_pragmatics_full_resolves_thinking_default(monkeypatch):
    """classify_batch_pragmatics_full resolves the `thinking` default
    from env when not explicitly passed. The deepseek path gets
    {"type": "disabled"}; the M3/direct paths get None.
    """
    from x_monitor.attribution import classify_batch_pragmatics_full

    captured = {}

    class FakeClient:
        def messages_create(self, **kwargs):
            captured.update(kwargs)
            # Return valid wire format with one entry per input tweet
            tweets = kwargs["messages"][0]["content"][0]["text"]
            # Crude: count tweet_ids in the user prompt
            import re
            n = len(re.findall(r'"tweet_id":', tweets))
            return {
                "results": [
                    {"tweet_id": f"t{i}", "classifications": [], "unsanctioned_flags": []}
                    for i in range(n)
                ]
            }

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    captured.clear()
    tweets = [{"tweet_id": f"t{i}", "text": f"tweet {i}", "brand_ids": ["minimax"]} for i in range(3)]
    classify_batch_pragmatics_full(
        tweets=tweets,
        brand_registry=[],
        anthropic_client=FakeClient(),
        max_tokens=4096,
    )
    assert captured.get("thinking") == {"type": "disabled"}, (
        f"deepseek path should auto-thread thinking=disabled; got {captured.get('thinking')}"
    )

    # M3 path: thinking=None, parameter omitted
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    captured.clear()
    classify_batch_pragmatics_full(
        tweets=tweets,
        brand_registry=[],
        anthropic_client=FakeClient(),
        max_tokens=4096,
    )
    assert "thinking" not in captured, (
        f"M3 path should not thread thinking; got {captured.get('thinking')}"
    )


def test_classify_batch_pragmatics_full_shape_drift_emits_empty(monkeypatch):
    """When the LLM returns a malformed response (drift), the new
    _validate_deepseek_response_shape safety net catches the drift,
    the per-batch path emits empty for the whole batch, and
    on_batch_error is invoked with the ValueError. This is the same
    fail-soft contract that pre-swap used for the count-mismatch case.
    """
    from x_monitor.attribution import classify_batch_pragmatics_full

    class FakeClient:
        def messages_create(self, **kwargs):
            # Return a response missing 'results' — the new shape
            # validator will raise ValueError
            return {"unexpected_key": "drift"}

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    captured_exc = []
    tweets = [{"tweet_id": "t1", "text": "x", "brand_ids": ["minimax"]}]
    results = classify_batch_pragmatics_full(
        tweets=tweets,
        brand_registry=[],
        anthropic_client=FakeClient(),
        on_batch_error=lambda batch, exc: captured_exc.append(exc),
        max_tokens=4096,
    )
    # Whole batch emits empty
    assert results == [{"by_brand": {}, "unsanctioned_flags": []}]
    # on_batch_error was called with the shape-drift ValueError
    assert len(captured_exc) == 1
    assert isinstance(captured_exc[0], ValueError)
    assert "shape drift" in str(captured_exc[0])


def test_classify_batch_pragmatics_full_uses_max_tokens_helper_at_call_site(
    monkeypatch,
):
    """The production call site at x_monitor/run.py:648 (now in the
    import surface) passes max_tokens=_max_tokens_for_batch(N) where N
    is the input batch size. Pin the integration so a future change
    doesn't accidentally re-introduce the hardcoded 4096.
    """
    from x_monitor.attribution import (
        _max_tokens_for_batch,
        classify_batch_pragmatics_full,
    )

    captured = {}

    class FakeClient:
        def messages_create(self, **kwargs):
            captured["max_tokens"] = kwargs.get("max_tokens")
            n = 3
            return {
                "results": [
                    {"tweet_id": f"t{i}", "classifications": [], "unsanctioned_flags": []}
                    for i in range(n)
                ]
            }

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    tweets = [{"tweet_id": f"t{i}", "text": f"x{i}", "brand_ids": ["minimax"]} for i in range(3)]
    classify_batch_pragmatics_full(
        tweets=tweets,
        brand_registry=[],
        anthropic_client=FakeClient(),
        max_tokens=_max_tokens_for_batch(len(tweets)),
    )
    # For 3 tweets, the helper returns 4096 (floor)
    assert captured["max_tokens"] == 4096, (
        f"call site should use helper value; got {captured['max_tokens']}"
    )
