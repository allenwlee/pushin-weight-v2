"""Failure preserves the last good evaluation clock; successful keeps clear delay."""

from datetime import timedelta

import pytest
from django.utils import timezone

from tests.test_original_content_consideration import consideration

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_activation_clock_without_any_dispatched_run():
    from monitor.editorial.chatter_status import delay_status

    now = timezone.now()
    activated = now - timedelta(minutes=45)
    assert delay_status(now, activated_at=activated)["delayed"]
    assert not delay_status(now - timedelta(seconds=1), activated_at=activated)[
        "delayed"
    ]


def test_runtime_activation_time_is_aware_and_rejects_a_naive_value(monkeypatch):
    from monitor.editorial.config import load_editorial_config

    monkeypatch.setenv("CHATTER_ACTIVATED_AT", "2026-11-04T01:00:00+00:00")
    assert (
        load_editorial_config().chatter.activated_at.isoformat()
        == "2026-11-04T01:00:00+00:00"
    )
    monkeypatch.setenv("CHATTER_ACTIVATED_AT", "2026-11-04T01:00:00")
    with pytest.raises(ValueError, match="timezone"):
        load_editorial_config()


def test_45_minute_boundary_uses_successful_evaluation_including_keep():
    from monitor.editorial.chatter_status import delay_status

    row = consideration()
    row.run.scope_key = "chatter:v1"
    now = timezone.now()
    row.run.outcome = {
        "healthy_at": (now - timedelta(minutes=45)).isoformat(),
        "phase": "held",
        "failed_stage": "writer",
    }
    row.run.save(update_fields=["outcome", "scope_key"])
    assert delay_status(now)["delayed"]
    row.run.outcome = {
        "healthy_at": (now - timedelta(minutes=44, seconds=59)).isoformat(),
        "phase": "complete",
        "selected": 0,
    }
    row.run.save(update_fields=["outcome"])
    assert not delay_status(now)["delayed"]


def test_first_reader_observation_uses_original_cycle_clock_and_records_a_miss(
    monkeypatch,
):
    from monitor.editorial.chatter_chain import _record_ready
    from tests.test_chatter_pool_readers import published

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    text = published("rest", "884301")
    run = text.narrative.run
    ready = run.cycle_started_at + timedelta(seconds=301)
    monkeypatch.setattr("django.utils.timezone.now", lambda: ready)
    _record_ready(run, text)
    run.refresh_from_db()
    assert run.outcome["first_reader_seconds"] == 301
    assert run.outcome["first_text_target_missed"]
    assert run.outcome["first_text_at"] == text.created_at.isoformat()
