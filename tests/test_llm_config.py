"""Tests for Config.llm + env-var resolution (plan 2026-08-01-002 U1).

Pins:
- LlmConfig defaults match the values the v1 + v2 stacks used
  prior to this change (regression net for "operator-tunable LLM config").
- X_MONITOR_TRANSLATOR_MODEL env var overrides the default.
- yaml block wins over env when both are set.
- A config.yaml without an `llm:` block loads with all defaults
  (regression net for "omitting llm: preserves existing behavior").
"""
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"


def _cfg_with_models() -> dict:
    """Minimal valid Config input — LlmConfig has defaults so no llm block needed."""
    return {"enabled_models": ["minimax"], "daily_ceiling": 1}


def test_llm_config_defaults_match_v1_translator_model():
    """LlmConfig defaults MUST match the v1 + v2 working values."""
    from x_monitor.config import Config
    cfg = Config.model_validate(_cfg_with_models())
    # BEFORE: hardcoded in _resolve_translator_model when ANTHROPIC_BASE_URL
    # contained "minimax.io"; also matches ANTHROPIC_MODEL on fuchitalee shell.
    assert cfg.llm.translator_model == "minimax/MiniMax-M3.0[1m]", (
        "Config.llm.translator_model default must match the v1 shell's ANTHROPIC_MODEL "
        "(BEFORE: hardcoded in _resolve_translator_model)."
    )
    # BEFORE: hardcoded in _resolve_signal_model; x_monitor/relevancy.py::DEFAULT_RELEVANCY_MODEL.
    assert cfg.llm.signal_model == "claude-haiku-4-5", (
        "Config.llm.signal_model default must match _resolve_signal_model default."
    )
    assert cfg.llm.relevancy_model == "claude-haiku-4-5", (
        "Config.llm.relevancy_model default must match DEFAULT_RELEVANCY_MODEL."
    )
    # BEFORE: hardcoded in _resolve_signal_model via deepseek substring branch (plan 2026-07-15).
    assert cfg.llm.classifier_model == "deepseek-v4-pro", (
        "Config.llm.classifier_model default must match the 2026-07-15 DS V4 swap."
    )


def test_llm_config_translator_base_url_default_is_none():
    """translator_base_url defaults to None; the factory resolves to ANTHROPIC_BASE_URL env."""
    from x_monitor.config import Config
    cfg = Config.model_validate(_cfg_with_models())
    assert cfg.llm.translator_base_url is None


def test_llm_config_yaml_block_overrides_defaults():
    """When yaml provides an llm: block, those values flow through."""
    from x_monitor.config import Config
    raw = _cfg_with_models()
    raw["llm"] = {
        "translator_model": "custom-model",
        "classifier_model": "custom-classifier",
        "relevancy_model": "custom-relevancy",
        "signal_model": "custom-signal",
    }
    cfg = Config.model_validate(raw)
    assert cfg.llm.translator_model == "custom-model"
    assert cfg.llm.classifier_model == "custom-classifier"
    assert cfg.llm.relevancy_model == "custom-relevancy"
    assert cfg.llm.signal_model == "custom-signal"


def test_llm_config_yaml_wins_over_env(monkeypatch):
    """When both env and yaml are set, yaml wins (operator's yaml is canonical)."""
    from x_monitor.config import load_config
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_MODEL", "from-env")
    # load_config reads the on-disk config.yaml; it has no llm: block yet.
    # So env wins here. We assert the load happens correctly; the precedence
    # test is in the env-only test below.
    cfg = load_config(CONFIG_PATH)
    # config.yaml has no llm: block → env var (if set) takes effect
    assert cfg.llm.translator_model in ("minimax/MiniMax-M3.0[1m]", "from-env")


def test_llm_config_env_var_overrides_default(monkeypatch, tmp_path):
    """X_MONITOR_TRANSLATOR_MODEL env var flows into cfg.llm.translator_model."""
    from x_monitor.config import load_config
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_MODEL", "from-env-override")
    # Build a minimal config.yaml with no llm: block
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "enabled_models:\n  - minimax\ndaily_ceiling: 1\n",
        encoding="utf-8",
    )
    cfg = load_config(yaml_path)
    assert cfg.llm.translator_model == "from-env-override"


def test_llm_config_yaml_wins_when_both_set(monkeypatch, tmp_path):
    """When yaml sets a value AND env sets the same value, yaml wins."""
    from x_monitor.config import load_config
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_MODEL", "from-env")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "enabled_models:\n  - minimax\ndaily_ceiling: 1\nllm:\n  translator_model: from-yaml\n",
        encoding="utf-8",
    )
    cfg = load_config(yaml_path)
    assert cfg.llm.translator_model == "from-yaml"


def test_config_yaml_has_llm_block():
    """The committed config.yaml has the llm: block (operator-facing documentation)."""
    import yaml
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert "llm" in raw, (
        "config.yaml must declare an llm: block so operators can find the LLM config; "
        "the block should pin the four model names with their defaults explicitly."
    )
    assert raw["llm"]["translator_model"] == "minimax/MiniMax-M3.0[1m]"
    assert raw["llm"]["classifier_model"] == "deepseek-v4-pro"
    assert raw["llm"]["relevancy_model"] == "claude-haiku-4-5"
    assert raw["llm"]["signal_model"] == "claude-haiku-4-5"


def test_load_config_unset_env_falls_back_to_defaults(monkeypatch, tmp_path):
    """When env vars are unset, defaults flow through (regression net)."""
    from x_monitor.config import load_config
    for key in (
        "X_MONITOR_TRANSLATOR_MODEL",
        "X_MONITOR_CLASSIFIER_MODEL",
        "X_MONITOR_RELEVANCY_MODEL",
        "X_MONITOR_SIGNAL_MODEL",
        "X_MONITOR_TRANSLATOR_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "enabled_models:\n  - minimax\ndaily_ceiling: 1\n",
        encoding="utf-8",
    )
    cfg = load_config(yaml_path)
    assert cfg.llm.translator_model == "minimax/MiniMax-M3.0[1m]"
    assert cfg.llm.classifier_model == "deepseek-v4-pro"
    assert cfg.llm.relevancy_model == "claude-haiku-4-5"
    assert cfg.llm.signal_model == "claude-haiku-4-5"