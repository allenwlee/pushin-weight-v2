"""Regression pin: env var X_MONITOR_TRANSLATOR_BASE_URL must override yaml null.

Plan: docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md
Added 2026-08-05 (post-mortem: translator was hitting api.minimax.io/anthropic
because the merge in load_config treated yaml's `translator_base_url: null`
as "set" and overwrote the env-var value).

If this test fails, the translator's base-URL resolution has reverted to
silently preferring yaml null over an operator's env-var override. The
symptom on prod is `text_zh_cn` NULL on every post for 6+ hours, with
the cron traceback pointing at `api.minimax.io/anthropic` socket timeouts.
"""

from __future__ import annotations

import pytest

from x_monitor.config import load_config


REPO_ROOT = "/Users/fuchitalee/development/pushin-weight-v2"
CONFIG_PATH = f"{REPO_ROOT}/config.yaml"


def test_env_overrides_yaml_null_translator_base_url(tmp_path, monkeypatch):
    """A yaml `translator_base_url: null` MUST NOT clobber the env override.

    Bug: yaml wins over env at the dict-spread level, but yaml null is
    not actually "set" — it's the explicit instruction to use the default
    fallback (ANTHROPIC_BASE_URL). Without filtering, the env var
    X_MONITOR_TRANSLATOR_BASE_URL is silently overridden by yaml null.
    """
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("""\
enabled_models: [minimax]
daily_ceiling: 333
x_monitor_list_id: "123"
llm:
  translator_model: minimax/MiniMax-M3.0[1m]
  translator_base_url: null
""")
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_BASE_URL", "https://api.deepseek.com/anthropic")
    cfg = load_config(cfg_path)
    assert cfg.llm.translator_base_url == "https://api.deepseek.com/anthropic", (
        f"env override failed: translator_base_url={cfg.llm.translator_base_url}; "
        "yaml `null` clobbered the env var. Fix in load_config."
    )


def test_yaml_explicit_string_wins_over_env(tmp_path, monkeypatch):
    """When yaml has a non-null string, it wins over the env override."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("""\
enabled_models: [minimax]
daily_ceiling: 333
x_monitor_list_id: "123"
llm:
  translator_model: minimax/MiniMax-M3.0[1m]
  translator_base_url: https://api.deepseek.com/anthropic
""")
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_BASE_URL", "https://api.minimax.io/anthropic")
    cfg = load_config(cfg_path)
    assert cfg.llm.translator_base_url == "https://api.deepseek.com/anthropic", (
        "yaml non-null string should win over env (operators can pin in yaml)"
    )


def test_no_env_no_yaml_returns_none(tmp_path, monkeypatch):
    """With no env and no yaml value, translator_base_url is None (fallback path)."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("""\
enabled_models: [minimax]
daily_ceiling: 333
x_monitor_list_id: "123"
llm:
  translator_model: minimax/MiniMax-M3.0[1m]
""")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    cfg = load_config(cfg_path)
    assert cfg.llm.translator_base_url is None


def test_env_unset_yaml_null_returns_none(tmp_path, monkeypatch):
    """With env unset and yaml null, translator_base_url is None (fallback)."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("""\
enabled_models: [minimax]
daily_ceiling: 333
x_monitor_list_id: "123"
llm:
  translator_model: minimax/MiniMax-M3.0[1m]
  translator_base_url: null
""")
    monkeypatch.delenv("X_MONITOR_TRANSLATOR_BASE_URL", raising=False)
    cfg = load_config(cfg_path)
    assert cfg.llm.translator_base_url is None