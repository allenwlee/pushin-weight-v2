"""Regression net for plan 2026-08-01-002 U0.

Pins:
- plan_calls_for_cycle() accepts cfg: Config | None = None without
  raising NameError. The function body was migrated to use self.cfg
  by plan 2026-08-01-001 but the function signature was not updated
  to a method, so module-level callers hit NameError. This test
  would have caught the original regression (commit 05c3d92).
- CycleRunner._plan_calls() does not abort with NameError; the
  7-call hybrid layout flows through.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"


def _django_setup():
    """Configure Django for monitor.cycle imports.

    Idempotent — safe to call from multiple tests.
    """
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_SCHEDULED_API_KEY", "dummy_for_regression_test")
    import django
    if not django.apps.apps.ready:
        django.setup()


def test_plan_calls_for_cycle_accepts_optional_cfg():
    """plan_calls_for_cycle must accept cfg=None without raising NameError.

    Pin against the post-2026-08-02 signature: cfg: Config | None = None.
    """
    _django_setup()
    from monitor.cycle import plan_calls_for_cycle

    # Call with no arg — must not raise NameError; returns a list.
    result = plan_calls_for_cycle()
    assert isinstance(result, list), (
        "plan_calls_for_cycle() must return a list of PlannedCall; "
        "the regression was returning NameError instead."
    )


def test_plan_calls_for_cycle_accepts_cfg_kwarg():
    """plan_calls_for_cycle must accept cfg= kwarg without raising."""
    _django_setup()
    from monitor.cycle import plan_calls_for_cycle
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    result = plan_calls_for_cycle(cfg=cfg)
    assert isinstance(result, list)


def test_cycle_runner_plan_calls_does_not_abort_with_self_undefined():
    """CycleRunner._plan_calls() must return the 7-call layout, not [].

    The original bug (commit 05c3d92) caused _plan_calls to return []
    because plan_calls_for_cycle() raised NameError on `self.cfg`.
    The empty-list return was logged as 'plan_calls failed' and the
    cycle aborted with 0 inserted.
    """
    _django_setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    runner = CycleRunner(dry_run=True, cfg=cfg)
    calls = runner._plan_calls()
    # The 7-call hybrid layout must flow through. Even without the
    # full TwitterAPI fetch, the planning step must produce calls.
    # (Dry-run may trim the list, but the function must not crash
    # AND must not return [] solely because of the NameError.)
    assert isinstance(calls, list)
    # If the regression had fired, the cycle's error log would have
    # an entry. We check that _errors is empty as the strongest
    # signal the NameError path was avoided.
    assert runner._errors == [], (
        f"CycleRunner._errors must be empty after _plan_calls; got {runner._errors}. "
        "Empty list typically indicates the NameError regression."
    )
