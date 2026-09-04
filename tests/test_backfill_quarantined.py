from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_quarantined_dry_run_needs_no_historical_window_and_writes_nothing():
    from core.models import HarvestBacklogWindow

    stdout = StringIO()
    call_command("backfill", quarantined=True, dry_run=True, stdout=stdout)
    assert "Quarantined harvest intervals: 0" in stdout.getvalue()
    assert HarvestBacklogWindow.objects.count() == 0


def test_historical_backfill_still_requires_since():
    with pytest.raises(CommandError, match="--since is required"):
        call_command("backfill")


def test_dots_only_backfill_dry_run_selects_only_b1(monkeypatch):
    from monitor import cycle as cycle_mod

    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(
            lambda cls, purpose: (_ for _ in ()).throw(
                AssertionError("dry-run must not construct provider")
            )
        ),
    )
    stdout = StringIO()

    call_command(
        "backfill",
        "--since",
        "2026-08-13",
        "--until",
        "2026-08-15",
        "--brands",
        "dots",
        "--call-ids",
        "B1",
        "--dry-run",
        stdout=stdout,
    )

    assert "Would execute calls: ['B1']" in stdout.getvalue()


def test_brand_scoped_backfill_rejects_unrelated_call_before_provider(
    monkeypatch,
):
    from monitor import cycle as cycle_mod

    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(
            lambda cls, purpose: (_ for _ in ()).throw(
                AssertionError("invalid scope must not construct provider")
            )
        ),
    )
    with pytest.raises(CommandError, match="not applicable to brands dots"):
        call_command(
            "backfill",
            "--since",
            "2026-08-13",
            "--until",
            "2026-08-15",
            "--brands",
            "dots",
            "--call-ids",
            "C1",
        )


def test_backfill_incomplete_call_remains_pending(monkeypatch, tmp_path):
    import monitor.management.commands.backfill as backfill_module
    from monitor import cycle as cycle_mod

    monkeypatch.setattr(backfill_module, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(
        cycle_mod,
        "plan_calls_for_cycle",
        lambda cfg=None: [SimpleNamespace(call_id="B1")],
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_anthropic_client_from_env",
        lambda cfg: None,
    )

    class TruncatedRunner:
        def __init__(self, **kwargs):
            assert kwargs["cycle_kind"] == "backfill"
            assert kwargs["_backfill_call_ids"] == ["B1"]

        def run(self):
            return {
                "run_id": "dots-truncated",
                "status": "completed",
                "totals": {"n_inserted": 2, "n_calls_run": 1},
                "calls": [{"call_id": "B1", "status": "truncated"}],
                "errors": [],
            }

    monkeypatch.setattr(cycle_mod, "CycleRunner", TruncatedRunner)
    stderr = StringIO()
    call_command(
        "backfill",
        "--since",
        "2026-08-13",
        "--until",
        "2026-08-15",
        "--brands",
        "dots",
        "--call-ids",
        "B1",
        "--pause",
        "0",
        stdout=StringIO(),
        stderr=stderr,
    )

    state_files = list(tmp_path.glob("*.json"))
    assert len(state_files) == 1
    state = json.loads(state_files[0].read_text())
    assert state["calls_completed_ids"] == []
    assert state["calls_remaining"] == ["B1"]
    assert state["finished"] is False
    assert state["total_inserted"] == 2
    assert state["runs"][0]["call_status"] == "truncated"
    assert "remains pending" in stderr.getvalue()


def test_backfill_restores_runtime_settings_after_scope_failure(monkeypatch):
    setting_names = (
        "X_MONITOR_CYCLE_SINCE_TIME",
        "X_MONITOR_CYCLE_UNTIL_TIME",
        "X_MONITOR_CYCLE_LIMIT_PER_CALL",
        "X_MONITOR_CYCLE_MAX_PAGES_PER_CALL",
    )
    sentinels = {name: object() for name in setting_names}
    prior_brand_filter = "prior-brand-filter"

    with override_settings(
        **sentinels,
        X_MONITOR_CYCLE_BRAND_FILTER=prior_brand_filter,
    ):
        with pytest.raises(CommandError, match="must be enabled models"):
            call_command(
                "backfill",
                "--since",
                "2026-08-13",
                "--until",
                "2026-08-15",
                "--brands",
                "not-enabled",
                "--call-ids",
                "B1",
                "--dry-run",
            )

        for name, value in sentinels.items():
            assert getattr(settings, name) is value
        assert settings.X_MONITOR_CYCLE_BRAND_FILTER == prior_brand_filter


@override_settings(X_MONITOR_CYCLE_BRAND_FILTER="stale-brand-filter")
def test_unscoped_backfill_ignores_stale_runtime_brand_filter(
    monkeypatch,
    tmp_path,
):
    import monitor.management.commands.backfill as backfill_module
    from monitor import cycle as cycle_mod

    observed_filters = []
    monkeypatch.setattr(backfill_module, "_STATE_DIR", tmp_path)

    def fake_plan(cfg=None):
        observed_filters.append(
            getattr(settings, "X_MONITOR_CYCLE_BRAND_FILTER", None)
        )
        return [SimpleNamespace(call_id="B1")]

    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", fake_plan)

    call_command(
        "backfill",
        "--since",
        "2026-08-13",
        "--until",
        "2026-08-15",
        "--dry-run",
        stdout=StringIO(),
    )

    assert observed_filters == [None]
    assert settings.X_MONITOR_CYCLE_BRAND_FILTER == "stale-brand-filter"
