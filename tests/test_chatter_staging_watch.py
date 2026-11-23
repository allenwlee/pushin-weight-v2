from datetime import UTC, datetime, timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from monitor.editorial import chatter_staging_watch as watch

START = datetime(2026, 11, 20, 9, tzinfo=UTC)
END = START + timedelta(hours=1)
ARGS = (START.isoformat(), END.isoformat(), "chatter-test-watch", "50", "0.20")


def test_watch_requires_actual_staging_service_and_expires_without_dispatch(
    monkeypatch,
):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv("RENDER_SERVICE_NAME", "pushinweight-staging-harvest")
    with pytest.raises(CommandError, match="staging harvest service"):
        watch.scheduled_watch_tick(*ARGS, now=START)
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    assert watch.scheduled_watch_tick(*ARGS, now=END) == {"status": "outside_watch"}


def test_watch_uses_scheduled_entrypoint_and_shared_trial(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_NAME", "pushinweight-staging-harvest")
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    seen = []
    monkeypatch.setattr(
        watch, "_inspect_database", lambda db, policy: seen.append("db")
    )

    def dispatch(source, started, *, kind, dry_run, cfg):
        seen.append(kind)
        assert source.startswith("pushinweight-staging-harvest:") and started == START
        assert kind == "scheduled" and not dry_run
        assert cfg.chatter.discovery_lane == "personalized-trends-v2"
        assert cfg.chatter.trial.scope == ARGS[2] and cfg.chatter.trial.limit_usd == 50
        assert cfg.chatter.trial.publication_limit == 1
        assert cfg.chatter.selector == cfg.chatter.ranking
        assert (
            cfg.routes["chatter"].vision
            and cfg.routes["chatter"].key_env == "OPENROUTER_API_KEY"
        )
        return {"status": "enqueued"}

    monkeypatch.setattr(watch, "dispatch_chatter_cycle", dispatch)
    assert watch.scheduled_watch_tick(*ARGS, now=START)["status"] == "enqueued"
    assert seen == ["db", "scheduled"]


def test_manual_watch_command_is_rejected_before_dispatch():
    with pytest.raises(CommandError, match="requires its own scheduled tick"):
        call_command("run_cycle", "--staging-chatter-watch", *ARGS)


def test_bounded_watch_uses_on_demand_credential_purpose(monkeypatch):
    from pathlib import Path

    from django.conf import settings

    from monitor.editorial import dispatch

    cfg = watch.watch_profile(
        watch.load_editorial_config(
            Path(settings.BASE_DIR) / "config/editorial-chatter-staging.yaml"
        ),
        *ARGS[2:],
    )
    observed = {}

    def reserve(*args, **kwargs):
        observed.update(kwargs)
        return {"status": "enqueued"}

    monkeypatch.setattr(dispatch, "dispatch_chatter_due_slot", reserve)
    dispatch.dispatch_chatter_cycle(
        "tick", START, kind="scheduled", dry_run=False, cfg=cfg
    )
    assert observed["purpose"] == "on-demand"


def test_production_profile_routes_chatter_through_personalized_trends():
    from pathlib import Path

    from django.conf import settings

    cfg = watch.load_editorial_config(
        Path(settings.BASE_DIR) / "config/editorial-english-launch.yaml"
    )
    assert cfg.chatter.enabled
    assert cfg.chatter.discovery_lane == "personalized-trends-v2"
    assert cfg.chatter.trial is None
    assert cfg.chatter.selector == cfg.chatter.ranking
    assert cfg.chatter.ranking.model == "openai/gpt-6-sol"
    assert cfg.routes["chatter"].model == "openai/gpt-6-sol"
    assert cfg.routes["chatter"].vision
    assert all(route.key_env == "OPENROUTER_API_KEY" for route in cfg.locale_routes.values())
