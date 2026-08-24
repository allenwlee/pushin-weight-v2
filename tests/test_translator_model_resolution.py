"""Regression pin: translator model-name inference must honor X_MONITOR_TRANSLATOR_BASE_URL.

Plan: docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md
Added 2026-08-05 (post-mortem: translator was sending MiniMax-M3.0 to
api.deepseek.com because _resolve_translator_model read the env-group's
stale ANTHROPIC_BASE_URL instead of the per-role override).

If this test fails, the model-name resolution has reverted to reading
ANTHROPIC_BASE_URL even when X_MONITOR_TRANSLATOR_BASE_URL routes the
translator to DeepSeek. Symptom on prod: DeepSeek returns 400 with
"The supported API model names are deepseek-v4-pro or deepseek-v4-flash,
but you passed MiniMax-M3.0."
"""

from __future__ import annotations

import pytest

from x_monitor.attribution import _resolve_translator_model


def test_x_monitor_translator_base_url_drives_deepseek_model_name(monkeypatch):
    """When X_MONITOR_TRANSLATOR_BASE_URL points at deepseek.com,
    the translator model name must be 'deepseek-v4-flash' (NOT 'MiniMax-M3.0')."""
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv(
        "X_MONITOR_TRANSLATOR_BASE_URL", "https://api.deepseek.com/anthropic"
    )
    assert _resolve_translator_model() == "deepseek-v4-flash", (
        "Model-name inference must honor X_MONITOR_TRANSLATOR_BASE_URL "
        "(parallel to _resolve_thinking_default). Got the legacy MiniMax-M3.0 "
        "because the env-group's ANTHROPIC_BASE_URL=api.minimax.io leaked through."
    )


def test_anthropic_base_url_still_drives_minimax_when_no_override(monkeypatch):
    """When no X_MONITOR_TRANSLATOR_BASE_URL is set, fall back to ANTHROPIC_BASE_URL."""
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    assert _resolve_translator_model() == "MiniMax-M3.0"


def test_anthropic_base_url_drives_deepseek_when_no_override(monkeypatch):
    """When no X_MONITOR_TRANSLATOR_BASE_URL is set, ANTHROPIC_BASE_URL
    routing to deepseek.com yields 'deepseek-v4-flash'."""
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    assert _resolve_translator_model() == "deepseek-v4-flash"


def test_anthropic_model_env_var_overrides_inference(monkeypatch):
    """ANTHROPIC_MODEL (operator shell override) still wins."""
    monkeypatch.setenv("ANTHROPIC_MODEL", "custom-translator-model")
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_BASE_URL", "https://api.deepseek.com/anthropic")
    assert _resolve_translator_model() == "custom-translator-model"


def test_no_base_url_falls_back_to_claude_haiku(monkeypatch):
    """No base URL configured -> claude-haiku-4-5 (direct Anthropic default)."""
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    assert _resolve_translator_model() == "claude-haiku-4-5"
