"""Tests for plan 2026-08-01-002 U2: factory builders take cfg + typed warnings.

Pins:
- build_translator_client_from_env(cfg) and build_anthropic_client_from_env(cfg)
  accept a Config (or None for backward compat).
- Missing credential emits a typed `logger.warning` — NOT silent None.
  This is the regression net for the silent-failure mode that hid the
  original lang_detected bug (commit 05c3d92 + pre-existing _build_client_for_base_url).
- _resolve_signal_model(cfg) / _resolve_translator_model(cfg) take cfg and
  honor `cfg.llm.*` model names.
"""
import os
from pathlib import Path


def _django_setup():
    """Set Django env so x_monitor.config / reattribute imports work."""
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_API_KEY", "dummy_for_factory_test")
    import django
    if not django.apps.apps.ready:
        django.setup()


def test_factory_builders_accept_optional_cfg():
    """Both factories must accept cfg=None (backward compat) AND cfg=Config(...)."""
    _django_setup()
    from x_monitor.config import Config, LlmConfig
    from x_monitor.reattribute import build_translator_client_from_env, build_anthropic_client_from_env
    cfg = Config.model_validate({"enabled_models": ["minimax"], "daily_ceiling": 1})
    # cfg=None path (v1 callers) — must not raise
    build_translator_client_from_env(cfg=None)
    build_anthropic_client_from_env(cfg=None)
    # cfg=Config path (v2 callers) — must not raise
    build_translator_client_from_env(cfg=cfg)
    build_anthropic_client_from_env(cfg=cfg)


def test_factory_warns_on_missing_credential(monkeypatch, caplog):
    """When MINIMAX_API_TOKEN is missing AND base URL routes through minimax proxy,
    the factory must log a typed warning (NOT silent None).

    This is the regression net that would have caught the silent-failure
    mode which hid the lang_detected bug (every cycle silently returned
    None clients with no log line).
    """
    _django_setup()
    from x_monitor.config import Config
    from x_monitor.reattribute import build_translator_client_from_env
    # Set base URL to minimax proxy, but unset the credential
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.delenv("MINIMAX_API_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = Config.model_validate({"enabled_models": ["minimax"], "daily_ceiling": 1})
    with caplog.at_level("WARNING"):
        result = build_translator_client_from_env(cfg=cfg)
    assert result is None, (
        "build_translator_client_from_env must return None when credential is missing"
    )
    # The warning MUST be logged — silent None was the original bug.
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any(
        "MINIMAX_API_TOKEN" in r.getMessage() or "minimax proxy" in r.getMessage()
        for r in warning_records
    ), (
        f"build_translator_client_from_env must emit a typed warning when MINIMAX_API_TOKEN "
        f"is missing; got warnings: {[r.getMessage() for r in warning_records]}"
    )


def test_resolve_signal_model_honors_cfg(monkeypatch):
    """_resolve_signal_model(cfg) returns cfg.llm.signal_model when provided."""
    _django_setup()
    from x_monitor.config import Config
    from x_monitor.attribution import _resolve_signal_model
    # Unset env so the resolver must fall through to cfg
    monkeypatch.delenv("X_MONITOR_CLASSIFIER_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    cfg = Config.model_validate({"enabled_models": ["minimax"], "daily_ceiling": 1})
    # Override signal_model via cfg
    cfg.llm.signal_model = "custom-signal-from-cfg"
    assert _resolve_signal_model(cfg) == "custom-signal-from-cfg"


def test_resolve_translator_model_honors_cfg(monkeypatch):
    """_resolve_translator_model(cfg) returns cfg.llm.translator_model when provided."""
    _django_setup()
    from x_monitor.config import Config
    from x_monitor.attribution import _resolve_translator_model
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    cfg = Config.model_validate({"enabled_models": ["minimax"], "daily_ceiling": 1})
    cfg.llm.translator_model = "custom-translator-from-cfg"
    assert _resolve_translator_model(cfg) == "custom-translator-from-cfg"


def test_resolve_signal_model_falls_back_to_env(monkeypatch):
    """When cfg is None, _resolve_signal_model uses env vars (backward compat)."""
    _django_setup()
    from x_monitor.attribution import _resolve_signal_model
    monkeypatch.setenv("X_MONITOR_CLASSIFIER_MODEL", "from-env-classifier")
    assert _resolve_signal_model(None) == "from-env-classifier"


def test_resolve_translator_model_falls_back_to_env(monkeypatch):
    """When cfg is None, _resolve_translator_model uses env vars (backward compat)."""
    _django_setup()
    from x_monitor.attribution import _resolve_translator_model
    monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-translator")
    assert _resolve_translator_model(None) == "from-env-translator"


def test_resolve_translator_model_cfg_wins_over_env(monkeypatch):
    """When both cfg and env are set, cfg wins (operator's yaml is canonical)."""
    _django_setup()
    from x_monitor.config import Config
    from x_monitor.attribution import _resolve_translator_model
    monkeypatch.setenv("ANTHROPIC_MODEL", "from-env")
    cfg = Config.model_validate({"enabled_models": ["minimax"], "daily_ceiling": 1})
    cfg.llm.translator_model = "from-cfg"
    assert _resolve_translator_model(cfg) == "from-cfg"