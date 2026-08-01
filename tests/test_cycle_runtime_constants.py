"""Regression net for plan 2026-08-01-001.

Pins:
- Config.cycle default values match the prior hardcoded values
  (BEFORE: _CURSOR_OVERLAP=60s, _MAX_LOOKBACK=2h, _C1_MAX_RESULTS=150,
  _C1_MAX_PAGES=8, _MAX_TRUNCATION_WALKS=5)
- CycleRunner reads cfg.cycle (not module-scope constants)
- KNOWN_MODELS is removed from project/settings.py
- _load_enabled_models / _load_x_monitor_list_id / _load_x_query_specs are gone
- 7-call hybrid shape preserved
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"


# ---------------------------------------------------------------------------
# Config.cycle default pin
# ---------------------------------------------------------------------------

EXPECTED_CYCLE_DEFAULTS = {
    "cursor_overlap_seconds": 60,        # was _CURSOR_OVERLAP = timedelta(minutes=1)
    "max_lookback_hours": 2,             # was _MAX_LOOKBACK = timedelta(hours=2)
    "c1_max_results": 150,              # was _C1_MAX_RESULTS = 150
    "c1_max_pages": 8,                   # was _C1_MAX_PAGES = 8
    "max_truncation_walks": 5,           # was _MAX_TRUNCATION_WALKS = 5
}


def test_cycle_config_defaults_match_prior_hardcoded_values():
    """The pydantic schema defaults for CycleConfig MUST match the
    prior hardcoded values in monitor/cycle.py. Omitting the cycle:
    block in config.yaml must preserve the existing behavior.
    """
    from x_monitor.config import CycleConfig
    cfg = CycleConfig()
    for field, expected in EXPECTED_CYCLE_DEFAULTS.items():
        actual = getattr(cfg, field)
        assert actual == expected, (
            f"CycleConfig.{field} default must be {expected} (BEFORE: prior hardcoded constant). "
            f"Got {actual}. If you intentionally changed the default, update this pin."
        )


def test_cycle_config_yaml_block_overrides_defaults():
    """When config.yaml has a cycle: block, those values flow through."""
    from x_monitor.config import load_config
    cfg = load_config(CONFIG_PATH)
    for field, expected in EXPECTED_CYCLE_DEFAULTS.items():
        actual = getattr(cfg.cycle, field)
        assert actual == expected, (
            f"config.yaml::cycle.{field} must be {expected} to preserve behavior. "
            f"Got {actual}."
        )


# ---------------------------------------------------------------------------
# Runtime resolution pin
# ---------------------------------------------------------------------------

def test_cycle_runner_uses_config_cycle_not_module_constants():
    """CycleRunner must read from self.cfg.cycle.* not from
    module-scope constants (which have been removed). Verifies
    CycleRunner instantiates with the loaded config and exposes
    the cycle fields on self.cfg.
    """
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_API_KEY", "dummy_for_smoketest")
    import django
    django.setup()
    from monitor.cycle import CycleRunner

    runner = CycleRunner(dry_run=True)
    # cycle fields must be present and equal to schema defaults
    assert runner.cfg.cycle.cursor_overlap_seconds == 60
    assert runner.cfg.cycle.max_lookback_hours == 2
    assert runner.cfg.cycle.c1_max_results == 150
    assert runner.cfg.cycle.c1_max_pages == 8
    assert runner.cfg.cycle.max_truncation_walks == 5


def test_cycle_runner_propagates_weird_config_values():
    """When config.yaml has an unusual cycle: value, the runner
    sees it. Proves the runner reads from cfg.cycle, not from
    hardcoded constants."""
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_API_KEY", "dummy_for_smoketest")
    import django
    django.setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import Config, load_config, CycleConfig

    cfg = load_config(CONFIG_PATH)
    # Force an unusual value
    cfg.cycle.c1_max_results = 999

    runner = CycleRunner(dry_run=True, cfg=cfg)
    assert runner.cfg.cycle.c1_max_results == 999, (
        "CycleRunner must read c1_max_results from cfg, not a hardcoded constant"
    )


# ---------------------------------------------------------------------------
# Deletion pins
# ---------------------------------------------------------------------------

def test_known_models_removed_from_settings():
    """KNOWN_MODELS must NOT be in project/settings.py anymore."""
    import importlib
    import sys
    # Force fresh import
    if "project.settings" in sys.modules:
        del sys.modules["project.settings"]
    import project.settings as proj_settings
    assert not hasattr(proj_settings, "KNOWN_MODELS"), (
        "KNOWN_MODELS frozenset must be removed from project/settings.py; "
        "Config.enabled_models is the single source of truth."
    )


def test_cycle_module_constants_removed():
    """The 5 module-scope constants must NOT be in monitor/cycle.py."""
    import re
    cyc_text = (REPO_ROOT / "monitor" / "cycle.py").read_text()
    for forbidden in (
        "_CURSOR_OVERLAP = ",
        "_MAX_LOOKBACK = ",
        "_C1_MAX_RESULTS = ",
        "_C1_MAX_PAGES = ",
        "_MAX_TRUNCATION_WALKS = ",
    ):
        assert forbidden not in cyc_text, (
            f"Module-scope constant '{forbidden.strip()}' still present in monitor/cycle.py; "
            f"all 5 must be removed in favor of self.cfg.cycle.*"
        )


def test_cycle_load_helpers_removed():
    """The 3 _load_* helpers must NOT be in monitor/cycle.py."""
    cyc_text = (REPO_ROOT / "monitor" / "cycle.py").read_text()
    for removed_helper in (
        "def _load_enabled_models(",
        "def _load_x_monitor_list_id(",
        "def _load_x_query_specs(",
    ):
        assert removed_helper not in cyc_text, (
            f"Helper '{removed_helper}' must be removed from monitor/cycle.py; "
            f"replaced by _resolve_enabled_models / _resolve_x_monitor_list_id / _resolve_x_query_specs."
        )


# ---------------------------------------------------------------------------
# 7-call hybrid shape pin (already covered by tests/test_mistral_call_placement.py
# but pinned here too for completeness)
# ---------------------------------------------------------------------------

EXPECTED_CALL_IDS_AFTER_U3 = {"A", "B1", "B2", "B3", "C1", "C2", "C3"}


def test_seven_call_shape_preserved_post_refactor():
    """Plan 2026-08-01-001 is a refactor of the loading mechanism,
    not the call structure. The 7-call hybrid shape must survive.
    """
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_API_KEY", "dummy_for_smoketest")
    import django
    django.setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    runner = CycleRunner(dry_run=True, cfg=cfg)
    # x_query_specs has 6 entries (C1/C2/C3 + B1/B2/B3); A is implicit
    # in plan_calls_for_cycle. The full 7-call layout is the union of
    # the 6 specs + Call A.
    actual_spec_ids = {s.call_id for s in cfg.x_query_specs}
    assert actual_spec_ids == (EXPECTED_CALL_IDS_AFTER_U3 - {"A"}), (
        f"x_query_specs call_ids must be {sorted(EXPECTED_CALL_IDS_AFTER_U3 - {'A'})} (A is implicit), "
        f"got {sorted(actual_spec_ids)}"
    )
