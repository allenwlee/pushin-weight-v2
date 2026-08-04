"""Regression net for the trailing-prose-tolerant LLM-response parser.

BEFORE: AnthropicClaudeClient.messages_create in both x_monitor/attribution.py
and x_monitor/translator.py called json.loads() on the LLM's textual
response. When the model returned valid JSON followed by trailing prose,
json.loads raised JSONDecodeError and the batch was either dropped
(classifier) or the wrapper raised and retry was exhausted (translator).
Net effect: lang_detected was never persisted for those posts.

Observed in prod on 2026-08-04 04:33-04:39 (Render cron
crn-d9gv94o4n6ts739tqaug): 42% of an 1h cohort had lang_detected IS NULL
in the pushinweight_shadow DB.

AFTER: parse_llm_response uses json.JSONDecoder().raw_decode() to consume
the first valid JSON value in the string and silently drop trailing
prose. lang_detected coverage recovers.

Each test below fails on the pre-fix code and passes on the post-fix
code. Assertion messages include a BEFORE comment so the next maintainer
sees the diff if the regression is intentionally relaxed.
"""
from __future__ import annotations

import types

from x_monitor._json_parser import parse_llm_response


# --- 1. Trailing prose after valid JSON -------------------------------

def test_parse_llm_response_tolerates_trailing_prose_after_valid_json():
    raw = '{"verdict": "yes", "reason": "test"}\n\nAlso, here is some extra explanation.'
    result = parse_llm_response(raw)
    assert result == {"verdict": "yes", "reason": "test"}, (
        "BEFORE: json.loads raised JSONDecodeError on trailing prose; "
        "this test pins the raw_decode tolerance."
    )


# --- 2. Trailing prose after fenced JSON ------------------------------

def test_parse_llm_response_tolerates_trailing_prose_after_json_in_code_fence():
    raw = (
        '```json\n'
        '{"results": [{"tweet_id": "1", "text_en": "hello"}]}\n'
        '```\n\n'
        "And here is my analysis: ..."
    )
    result = parse_llm_response(raw)
    assert result == {"results": [{"tweet_id": "1", "text_en": "hello"}]}, (
        "BEFORE: json.loads raised on the closing fence + trailing prose; "
        "this test pins the fence-strip + raw_decode combination."
    )


# --- 3. Prose-only falls back to classifier-shaped uncertain ----------

def test_parse_llm_response_returns_uncertain_fallback_for_prose_only():
    raw = "I am unable to comply with that request."
    result = parse_llm_response(raw)
    assert result == {"verdict": "uncertain", "reason": "llm_non_json_response"}, (
        "BEFORE: json.loads raised JSONDecodeError; the helper's default "
        "fallback matches the classifier's existing except-branch return."
    )


# --- 4. Empty string falls back safely --------------------------------

def test_parse_llm_response_returns_uncertain_fallback_for_empty_string():
    result = parse_llm_response("")
    assert result == {"verdict": "uncertain", "reason": "llm_non_json_response"}, (
        "BEFORE: json.loads('') raised JSONDecodeError; this test pins "
        "the empty-string fallback contract."
    )


# --- 5. Translator wrapper round-trips with trailing prose -----------

def test_translator_messages_create_tolerates_trailing_prose(monkeypatch):
    """Wrap-level pin: the translator SDK wrapper returns the parsed dict
    when the LLM response is JSON followed by trailing prose.

    Pre-fix: json.loads raises JSONDecodeError on the prose suffix and the
    wrapper propagates. Post-fix: parse_llm_response returns the dict.
    """
    from x_monitor import translator

    class _FakeBlock:
        def __init__(self, text: str) -> None:
            self.type = "text"
            self.text = text

    class _FakeMsg:
        def __init__(self, text: str) -> None:
            self.content = [_FakeBlock(text)]

    class _FakeMessages:
        def create(self, *, model, max_tokens, messages):
            return _FakeMsg(
                '{"results": [{"tweet_id": "1", "text_en": "hello", "literal_zh": null}]}\n\nThis is my analysis.'
            )

    class _FakeAnthropic:
        def __init__(self, *a, **kw) -> None:
            self.messages = _FakeMessages()

    # The translator imports `import anthropic` lazily inside __init__
    # (see x_monitor/translator.py:910). We trigger the import by
    # constructing the wrapper, then patch anthropic.Anthropic so the
    # next __init__ uses our fake. Cleanest path: monkeypatch the
    # anthropic module itself before constructing.
    import anthropic as _anthropic
    monkeypatch.setattr(_anthropic, "Anthropic", _FakeAnthropic)

    client = translator.AnthropicClaudeClient(api_key="dummy", base_url="http://localhost")
    result = client.messages_create(
        model="claude-opus-4-1",
        max_tokens=4096,
        messages=[{"role": "user", "content": "translate"}],
    )
    assert result == {
        "results": [{"tweet_id": "1", "text_en": "hello", "literal_zh": None}]
    }, (
        "BEFORE: json.loads raised on the trailing prose and the wrapper "
        "propagated; this test pins the SDK-path wrapper's tolerance."
    )


# --- 6. Non-dict JSON falls back to uncertain ------------------------

def test_parse_llm_response_returns_uncertain_fallback_for_non_dict_json():
    """If the model returns a bare array (e.g. [1, 2, 3]), the helper
    must fall back rather than returning the array — both wrappers expect
    a dict-shaped contract.
    """
    raw = "[1, 2, 3]\n\nExtra prose."
    result = parse_llm_response(raw)
    assert result == {"verdict": "uncertain", "reason": "llm_non_json_response"}, (
        "BEFORE: json.loads returned [1, 2, 3] (an array, not a dict), and "
        "the classifier wrapper would have iterated it as text; this test "
        "pins the non-dict fallback contract."
    )


# --- 7. Translator wrapper falls back to {"results": []} on prose ----

def test_translator_messages_create_returns_empty_results_fallback_on_prose(monkeypatch):
    """Wrap-level pin for the translator fallback shape.

    Pre-fix: json.loads raised on prose-only and the wrapper propagated.
    Post-fix: parse_llm_response returns {"results": []}, which
    translate_batch._parse_response treats as a parse failure (None)
    and marks the batch as translation_failed=True.
    """
    from x_monitor import translator

    class _FakeBlock:
        def __init__(self, text: str) -> None:
            self.type = "text"
            self.text = text

    class _FakeMsg:
        def __init__(self, text: str) -> None:
            self.content = [_FakeBlock(text)]

    class _FakeMessages:
        def create(self, *, model, max_tokens, messages):
            return _FakeMsg("I cannot help with that request.")

    class _FakeAnthropic:
        def __init__(self, *a, **kw) -> None:
            self.messages = _FakeMessages()

    import anthropic as _anthropic
    monkeypatch.setattr(_anthropic, "Anthropic", _FakeAnthropic)

    client = translator.AnthropicClaudeClient(api_key="dummy", base_url="http://localhost")
    result = client.messages_create(
        model="claude-opus-4-1",
        max_tokens=4096,
        messages=[{"role": "user", "content": "translate"}],
    )
    assert result == {"results": []}, (
        "BEFORE: json.loads raised JSONDecodeError on prose-only; this "
        "test pins the translator's soft-fail to {'results': []}."
    )
