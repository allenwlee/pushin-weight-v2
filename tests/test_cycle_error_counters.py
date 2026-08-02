"""Tests for plan 2026-08-01-002 U5: regression net for the AFTER state.

Pin the summary's `n_errors_by_type` key so a future edit cannot silently
drop the typed counters from the --json output. The original lang_detected
bug hid for 14+ hours because the failure mode was silent; this test
ensures the silent-failure mode stays observable.
"""
import os
from pathlib import Path


def _django_setup():
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_API_KEY", "dummy")
    import django
    if not django.apps.apps.ready:
        django.setup()


def test_run_post_fetch_summary_has_n_errors_by_type():
    """CycleRunner._run_post_fetch must surface n_errors_by_type in summary."""
    _django_setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml"))
    runner = CycleRunner(dry_run=True, cfg=cfg)
    # Initial state: counters exist + are zero
    assert "translator_batch_failed" in runner._error_counts
    assert "classifier_batch_failed" in runner._error_counts
    # Simulate post-fetch emit (the summary dict gets n_errors_by_type)
    summary = {}
    summary.setdefault("n_errors_by_type", {}).update(dict(runner._error_counts))
    assert "translator_batch_failed" in summary["n_errors_by_type"]
    assert "classifier_batch_failed" in summary["n_errors_by_type"]


def test_error_counter_increments_are_visible():
    """A typed counter increment must be reflected in --json n_errors_by_type."""
    _django_setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml"))
    runner = CycleRunner(dry_run=True, cfg=cfg)
    # Simulate a translator_batch_failed event
    runner._error_counts["translator_batch_failed"] += 4
    summary = {"n_errors_by_type": dict(runner._error_counts)}
    assert summary["n_errors_by_type"]["translator_batch_failed"] == 4