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
    _resolve_translator_model(None) returns "deepseek-v4-flash"
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
        def __init__(self, translator_model: str | None):
            self.translator_model = translator_model

    def __init__(self, translator_model: str | None = "deepseek-v4-flash"):
        self.llm = self._Llm(translator_model)


def test_cfg_first_resolves_to_canonical_model_when_env_disagrees(monkeypatch):
    """Regression: a cfg-pinned Flash model wins over ambient MiniMax."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    cfg = _CfgStub("deepseek-v4-flash")
    assert _resolve_translator_model(cfg) == "deepseek-v4-flash"


def test_explicit_pro_config_rollback_still_wins(monkeypatch):
    """An explicit config change can roll the translator back to V4 Pro."""
    monkeypatch.setenv("ANTHROPIC_MODEL", "ambient-model")
    assert _resolve_translator_model(_CfgStub("deepseek-v4-pro")) == "deepseek-v4-pro"


def test_cfg_threaded_batch_call_sends_flash_and_disables_thinking(monkeypatch):
    """The real translator batch call sends cfg Flash despite ambient mismatch."""
    monkeypatch.setenv("ANTHROPIC_MODEL", "ambient-model")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv(
        "X_MONITOR_TRANSLATOR_BASE_URL",
        "https://api.deepseek.com/anthropic",
    )

    class FakeClient:
        def __init__(self):
            self.calls = []

        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "results": [{
                    "tweet_id": "translator-flash",
                    "lang_detected": "en",
                    "text_en": "DeepSeek release",
                    "text_zh_cn": "深度求索发布",
                    "literal_zh": "深度求索发布",
                    "cn_equivalent": "深度求索发布",
                    "annotation": "",
                    "noop_en": True,
                    "noop_zh": False,
                }]
            }

    client = FakeClient()
    translate_batch_pragmatics(
        [{"tweet_id": "translator-flash", "text": "DeepSeek release"}],
        ["en", "zh_cn"],
        client,
        few_shot_examples=[],
        cfg=_CfgStub("deepseek-v4-flash"),
    )

    assert client.calls[0]["model"] == "deepseek-v4-flash"
    assert client.calls[0]["thinking"] == {"type": "disabled"}


def test_cfg_falls_back_to_env_when_translator_model_unset(monkeypatch):
    """If cfg is provided but cfg.llm.translator_model is None/empty,
    infer from the env. This is the secondary fallback."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    cfg = _CfgStub(None)
    assert _resolve_translator_model(cfg) == "deepseek-v4-flash"


def test_no_cfg_env_only_still_works(monkeypatch):
    """Preexisting env-only path. Must NOT regress: cf=None + base_url with
    'deepseek.com' returns deepseek-v4-flash."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert _resolve_translator_model(None) == "deepseek-v4-flash"
