"""Tests for x_monitor.reattribute.build_anthropic_client_from_env.

The factory resolves three env-var routing branches (Plan 2026-07-15-002):
  1. Direct Anthropic API (ANTHROPIC_API_KEY, no proxy)
  2. MiniMax M3 proxy (ANTHROPIC_BASE_URL contains "minimax.io", MINIMAX_API_TOKEN)
  3. DeepSeek V4 Pro (ANTHROPIC_BASE_URL contains "deepseek.com", DEEPSEEK_API_KEY)

All three return an AnthropicClaudeClient constructed with the right
api_key + base_url. The factory returns None (not raise) when the
required credential is missing — the reattribute falls back to
non-LLM mode.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip all LLM env vars before each test, then restore the test's
    own setting via the `monkeypatch` argument on each test."""
    for var in (
        "ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "MINIMAX_API_TOKEN",
        "DEEPSEEK_API_KEY", "DEEPSEEK_API_TOKEN", "ANTHROPIC_BASE_URL",
        "X_MONITOR_CLASSIFIER_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def client_construction(monkeypatch):
    """Capture the factory boundary without constructing an HTTP client."""
    from x_monitor import reattribute

    calls: list[dict[str, str | None]] = []
    client = object()

    def construct(**kwargs):
        calls.append(kwargs)
        return client

    monkeypatch.setattr(reattribute, "AnthropicClaudeClient", construct)
    return client, calls


@pytest.fixture
def warning_messages(monkeypatch):
    """Capture operator warnings independently of global logging state."""
    from x_monitor import reattribute

    messages: list[str] = []
    monkeypatch.setattr(
        reattribute.logger,
        "warning",
        lambda message, *args: messages.append(message % args),
    )
    return messages


def _assert_route(result, construction, *, api_key, base_url):
    client, calls = construction
    assert result is client
    assert calls == [{"api_key": api_key, "base_url": base_url}]


def test_direct_anthropic_uses_anthropic_api_key(monkeypatch, client_construction):
    """No proxy -> ANTHROPIC_API_KEY (or ANTHROPIC_KEY alias) -> direct."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123")
    client = build_anthropic_client_from_env()
    _assert_route(
        client,
        client_construction,
        api_key="sk-ant-test-123",
        base_url=None,
    )


def test_direct_anthropic_anthropic_key_alias(monkeypatch, client_construction):
    """ANTHROPIC_KEY is the legacy alias and is honored."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv("ANTHROPIC_KEY", "sk-ant-alias-456")
    client = build_anthropic_client_from_env()
    _assert_route(
        client,
        client_construction,
        api_key="sk-ant-alias-456",
        base_url=None,
    )


def test_direct_anthropic_missing_key_returns_none(monkeypatch, client_construction):
    """No credential -> None (not raise) so the reattribute falls back
    to non-LLM mode."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    client = build_anthropic_client_from_env()
    assert client is None
    assert client_construction[1] == []


def test_minimax_proxy_uses_minimax_api_token(monkeypatch, client_construction):
    """ANTHROPIC_BASE_URL contains 'minimax.io' -> MINIMAX_API_TOKEN."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    base_url = "https://api.minimax.io/anthropic"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base_url)
    monkeypatch.setenv("MINIMAX_API_TOKEN", "sk-cp-minimax-789")
    client = build_anthropic_client_from_env()
    _assert_route(
        client,
        client_construction,
        api_key="sk-cp-minimax-789",
        base_url=base_url,
    )


def test_minimax_proxy_missing_token_returns_none_with_warning(
    monkeypatch, client_construction, warning_messages
):
    """MiniMax proxy + missing MINIMAX_API_TOKEN -> None + WARNING log.

    The warning surfaces in the operator's run log so the credential
    rotation issue is visible without a separate smoke check.
    """
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    client = build_anthropic_client_from_env()
    assert client is None
    assert client_construction[1] == []
    assert any("MINIMAX_API_TOKEN" in message for message in warning_messages)


def test_deepseek_proxy_uses_deepseek_api_key(monkeypatch, client_construction):
    """ANTHROPIC_BASE_URL contains 'deepseek.com' -> DEEPSEEK_API_KEY
    (the new branch from Plan 2026-07-15-002)."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    base_url = "https://api.deepseek.com/anthropic"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base_url)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-abc")
    client = build_anthropic_client_from_env()
    _assert_route(
        client,
        client_construction,
        api_key="sk-deepseek-abc",
        base_url=base_url,
    )


def test_deepseek_proxy_deepseek_api_token_alias(monkeypatch, client_construction):
    """DEEPSEEK_API_TOKEN is the alternate name; both are accepted."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    base_url = "https://api.deepseek.com/anthropic"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base_url)
    monkeypatch.setenv("DEEPSEEK_API_TOKEN", "sk-deepseek-token-xyz")
    client = build_anthropic_client_from_env()
    _assert_route(
        client,
        client_construction,
        api_key="sk-deepseek-token-xyz",
        base_url=base_url,
    )


def test_deepseek_proxy_missing_key_returns_none_with_warning(
    monkeypatch, client_construction, warning_messages
):
    """DeepSeek proxy + missing DEEPSEEK_API_KEY -> None + WARNING log."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv(
        "ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"
    )
    client = build_anthropic_client_from_env()
    assert client is None
    assert client_construction[1] == []
    assert any("DEEPSEEK_API_KEY" in message for message in warning_messages)


def test_minimax_route_uses_minimax_token_when_both_tokens_are_present(
    monkeypatch, client_construction
):
    """A MiniMax route selects its credential when both keys are present."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    # Substring 'minimax.io' appears in many test URLs; pin the
    # actual ordering. The current implementation checks minimax
    # first, so this is the regression net.
    base_url = "https://api.minimax.io/anthropic"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base_url)
    monkeypatch.setenv("MINIMAX_API_TOKEN", "sk-cp-minimax")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    client = build_anthropic_client_from_env()
    _assert_route(
        client,
        client_construction,
        api_key="sk-cp-minimax",
        base_url=base_url,
    )


def test_classifier_override_routes_to_deepseek_while_process_stays_minimax(
    monkeypatch, client_construction
):
    """X_MONITOR_CLASSIFIER_BASE_URL overrides ANTHROPIC_BASE_URL when set.

    Plan 2026-07-15-003: lets M3 stay as the process-wide default
    (ANTHROPIC_BASE_URL=minimax.io) while the classifier routes to DS V4
    via the override. The factory picks up the override and constructs
    a client with the deepseek api_key + deepseek base_url.
    """
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv("MINIMAX_API_TOKEN", "sk-cp-minimax")
    base_url = "https://api.deepseek.com/anthropic"
    monkeypatch.setenv("X_MONITOR_CLASSIFIER_BASE_URL", base_url)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-override")
    client = build_anthropic_client_from_env()
    _assert_route(
        client,
        client_construction,
        api_key="sk-deepseek-override",
        base_url=base_url,
    )


def test_classifier_override_unset_falls_back_to_anthropic_base_url(
    monkeypatch, client_construction
):
    """X_MONITOR_CLASSIFIER_BASE_URL unset -> falls back to ANTHROPIC_BASE_URL.

    Regression net for the precedence rule. Without the fallback, the
    factory would only route via the override, breaking operators who
    haven't set it.
    """
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.delenv("X_MONITOR_CLASSIFIER_BASE_URL", raising=False)
    base_url = "https://api.minimax.io/anthropic"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base_url)
    monkeypatch.setenv("MINIMAX_API_TOKEN", "sk-cp-minimax-fb")
    client = build_anthropic_client_from_env()
    _assert_route(
        client,
        client_construction,
        api_key="sk-cp-minimax-fb",
        base_url=base_url,
    )
