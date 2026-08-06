"""Regression net for the translator cfg pass-through fix.

Before the fix: x_monitor/translator.py:_call_with_retry called
_resolve_translator_model() with no args. _resolve_translator_model
fell back to env inference, which returned "MiniMax-M3.0" when
ANTHROPIC_BASE_URL pointed at api.minimax.io even though the cron
overrode X_MONITOR_TRANSLATOR_BASE_URL to api.deepseek.com. This
caused the 2026-08-06 08:47 UTC translator_batch_failed (DeepSeek
400: "supported API model names are deepseek-v4-pro or
deepseek-v4-flash, but you passed minimax/MiniMax-M3.0").

After the fix:
  - _call_with_retry takes cfg=None kwarg.
  - The 3 translate_batch_* signatures (translate_batch,
    translate_batch_pragmatics, translate_registry_rows) take cfg=None.
  - They thread cfg through to _call_with_retry which passes it to
    _resolve_translator_model(cfg).

These tests pin:
  - All 3 translate_batch_* signatures accept cfg.
  - _call_with_retry signature accepts cfg.
  - When cfg is provided AND cfg.llm.translator_model is set,
    _resolve_translator_model(cfg) returns that model name
    REGARDLESS of the active ANTHROPIC_BASE_URL env (the regression).
  - When cfg is None and ANTHROPIC_BASE_URL contains "deepseek.com",
    _resolve_translator_model(None) returns "deepseek-v4-pro"
    (preexisting behavior — must NOT regress).
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

from x_monitor.attribution import _resolve_translator_model
from x_monitor.translator import (
    _call_with_retry,
    translate_batch,
    translate_batch_pragmatics,
    translate_registry_rows,
)


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch):
    """Save and restore the ANTHROPIC_BASE_URL env around each test."""
    saved = os.environ.get("ANTHROPIC_BASE_URL")
    yield
    if saved is None:
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", saved)


# ---------------------------------------------------------------------------
# Signature-level pinning: every entry point must accept `cfg` so callers
# CAN thread the canonical config through.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fn",
    [translate_batch, translate_batch_pragmatics, translate_registry_rows, _call_with_retry],
    ids=["translate_batch", "translate_batch_pragmatics", "translate_registry_rows", "_call_with_retry"],
)
def test_signature_accepts_cfg_kwarg(fn):
    """All 3 translate_batch_* + _call_with_retry must accept cfg=None kwarg."""
    sig = inspect.signature(fn)
    assert "cfg" in sig.parameters, (
        f"{fn.__name__} must accept a `cfg` kwarg; signature = {sig}"
    )
    # Default value must be None so v1 callers (no cfg) keep working.
    assert sig.parameters["cfg"].default is None, (
        f"{fn.__name__}.cfg default must be None for backward compat; "
        f"got {sig.parameters['cfg'].default!r}"
    )


# ---------------------------------------------------------------------------
# The actual regression: when cfg is provided with translator_model set,
# the resolver must return that value even if the env points at MiniMax.
# ---------------------------------------------------------------------------

class _CfgStub:
    """Minimal Config stand-in. _resolve_translator_model reads only cfg.llm.translator_model."""
    class _Llm:
        translator_model: str | None = "deepseek-v4-pro"
    llm = _Llm()


def test_cfg_first_resolves_to_canonical_model_when_env_disagrees(monkeypatch):
    """Regression: ANTHROPIC_BASE_URL=api.minimax.io + cfg.translator_model=deepseek-v4-pro
    must return deepseek-v4-pro, not MiniMax-M3.0. This is the bug that caused
    the 2026-08-06 08:47 UTC translator_batch_failed."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    cfg = _CfgStub()
    cfg.llm.translator_model = "deepseek-v4-pro"
    assert _resolve_translator_model(cfg) == "deepseek-v4-pro"


def test_cfg_falls_back_to_env_when_translator_model_unset(monkeypatch):
    """If cfg is provided but cfg.llm.translator_model is None/empty,
    infer from the env. This is the secondary fallback."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    cfg = _CfgStub()
    cfg.llm.translator_model = None  # not set
    assert _resolve_translator_model(cfg) == "deepseek-v4-pro"


def test_no_cfg_env_only_still_works(monkeypatch):
    """Preexisting env-only path. Must NOT regress: cf=None + base_url with
    'deepseek.com' returns deepseek-v4-pro."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert _resolve_translator_model(None) == "deepseek-v4-pro"
