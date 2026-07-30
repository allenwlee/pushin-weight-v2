"""U6 production wire-in tests — build_binary_relevancy_llm_call.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U6 (runtime wire-in).

The factory wraps the project's Anthropic-Claude client and returns a
`llm_call(system, user) -> str` closure that matches the dependency
shape expected by CycleRunner._relevancy_llm_call.
"""

from __future__ import annotations

from x_monitor.relevancy import build_binary_relevancy_llm_call


class FakeAnthropicClient:
    """Mimics the messages_create(**kwargs) -> dict interface used by
    translator + classifier (see x_monitor.translator.AnthropicClaudeClient)."""

    def __init__(self, response_text: str = "KEEP"):
        self.response_text = response_text
        self.calls: list[dict] = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "content": [{"type": "text", "text": self.response_text}],
        }


def test_returns_none_when_client_is_none():
    """No client → no llm_call. The cycle then runs with the gate as a
    no-op (CycleRunner.__init__ default)."""
    assert build_binary_relevancy_llm_call(client=None) is None


def test_llm_call_invokes_client_with_system_and_user():
    """The closure sends a `system` block + a single user message."""
    fake = FakeAnthropicClient(response_text="KEEP\nlooks like AI")
    llm_call = build_binary_relevancy_llm_call(client=fake)

    response = llm_call("SYS_PROMPT", "USER_PROMPT")

    assert response == "KEEP\nlooks like AI"
    assert len(fake.calls) == 1
    kwargs = fake.calls[0]
    assert kwargs["system"] == "SYS_PROMPT"
    assert kwargs["messages"] == [
        {"role": "user", "content": "USER_PROMPT"}
    ]
    assert kwargs["max_tokens"] <= 128  # gate output is small


def test_llm_call_returns_empty_string_on_empty_content():
    """Defensive: when the client returns no content blocks, the closure
    yields \"\" — the parser then sees parse_failed=True → KEEP."""
    class EmptyClient:
        def messages_create(self, **kwargs):
            return {"content": []}

    llm_call = build_binary_relevancy_llm_call(client=EmptyClient())
    assert llm_call("sys", "user") == ""


def test_llm_call_uses_default_model_when_unspecified():
    """Default model is set so callers don't have to pick one."""
    fake = FakeAnthropicClient()
    llm_call = build_binary_relevancy_llm_call(client=fake)

    llm_call("sys", "user")

    assert "model" in fake.calls[0]
    assert isinstance(fake.calls[0]["model"], str)
    assert fake.calls[0]["model"]  # non-empty


def test_llm_call_respects_custom_model():
    fake = FakeAnthropicClient()
    llm_call = build_binary_relevancy_llm_call(
        client=fake, model="claude-sonnet-4-6"
    )
    llm_call("sys", "user")
    assert fake.calls[0]["model"] == "claude-sonnet-4-6"


def test_llm_call_passes_max_tokens():
    """max_tokens is small (gate output is one KEEP/DROP + optional reason)."""
    fake = FakeAnthropicClient()
    llm_call = build_binary_relevancy_llm_call(client=fake, max_tokens=64)
    llm_call("sys", "user")
    assert fake.calls[0]["max_tokens"] == 64