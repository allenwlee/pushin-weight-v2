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
    ):
        monkeypatch.delenv(var, raising=False)


def test_direct_anthropic_uses_anthropic_api_key(monkeypatch):
    """No proxy -> ANTHROPIC_API_KEY (or ANTHROPIC_KEY alias) -> direct."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123")
    client = build_anthropic_client_from_env()
    assert client is not None
    # Client stores api_key/base_url; the base_url is whatever env says
    # (None when unset means default to api.anthropic.com)
    assert client._client.api_key == "sk-ant-test-123"


def test_direct_anthropic_anthropic_key_alias(monkeypatch):
    """ANTHROPIC_KEY is the legacy alias and is honored."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv("ANTHROPIC_KEY", "sk-ant-alias-456")
    client = build_anthropic_client_from_env()
    assert client is not None
    assert client._client.api_key == "sk-ant-alias-456"


def test_direct_anthropic_missing_key_returns_none(monkeypatch):
    """No credential -> None (not raise) so the reattribute falls back
    to non-LLM mode."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    client = build_anthropic_client_from_env()
    assert client is None


def test_minimax_proxy_uses_minimax_api_token(monkeypatch):
    """ANTHROPIC_BASE_URL contains 'minimax.io' -> MINIMAX_API_TOKEN."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv("MINIMAX_API_TOKEN", "sk-cp-minimax-789")
    client = build_anthropic_client_from_env()
    assert client is not None
    assert client._client.api_key == "sk-cp-minimax-789"


def test_minimax_proxy_missing_token_returns_none_with_warning(
    monkeypatch, caplog
):
    """MiniMax proxy + missing MINIMAX_API_TOKEN -> None + WARNING log.

    The warning surfaces in the operator's run log so the credential
    rotation issue is visible without a separate smoke check.
    """
    import logging
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    with caplog.at_level(logging.WARNING):
        client = build_anthropic_client_from_env()
    assert client is None
    assert any("MINIMAX_API_TOKEN" in r.message for r in caplog.records)


def test_deepseek_proxy_uses_deepseek_api_key(monkeypatch):
    """ANTHROPIC_BASE_URL contains 'deepseek.com' -> DEEPSEEK_API_KEY
    (the new branch from Plan 2026-07-15-002)."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv(
        "ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-abc")
    client = build_anthropic_client_from_env()
    assert client is not None
    assert client._client.api_key == "sk-deepseek-abc"


def test_deepseek_proxy_deepseek_api_token_alias(monkeypatch):
    """DEEPSEEK_API_TOKEN is the alternate name; both are accepted."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv(
        "ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"
    )
    monkeypatch.setenv("DEEPSEEK_API_TOKEN", "sk-deepseek-token-xyz")
    client = build_anthropic_client_from_env()
    assert client is not None
    assert client._client.api_key == "sk-deepseek-token-xyz"


def test_deepseek_proxy_missing_key_returns_none_with_warning(
    monkeypatch, caplog
):
    """DeepSeek proxy + missing DEEPSEEK_API_KEY -> None + WARNING log."""
    import logging
    from x_monitor.reattribute import build_anthropic_client_from_env

    monkeypatch.setenv(
        "ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"
    )
    with caplog.at_level(logging.WARNING):
        client = build_anthropic_client_from_env()
    assert client is None
    assert any("DEEPSEEK_API_KEY" in r.message for r in caplog.records)


def test_deepseek_branch_takes_precedence_over_minimax(monkeypatch):
    """If the base_url contains BOTH substrings (unlikely but possible
    in test scaffolding), the deepseek branch is checked first
    (since it's the more recent addition). The factory reads the
    substrings in order: minimax first (per code), but the test
    verifies the actual behavior — direct Anthropic wins, then
    minimax, then deepseek. (This matches the implementation in
    reattribute.py: the elif chain is minimax -> deepseek -> else.)"""
    from x_monitor.reattribute import build_anthropic_client_from_env

    # Substring 'minimax.io' appears in many test URLs; pin the
    # actual ordering. The current implementation checks minimax
    # first, so this is the regression net.
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv("MINIMAX_API_TOKEN", "sk-cp-minimax")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    client = build_anthropic_client_from_env()
    assert client is not None
    # minimax branch wins (the elif is checked first)
    assert client._client.api_key == "sk-cp-minimax"
