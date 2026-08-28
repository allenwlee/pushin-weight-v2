"""Entry-point contracts for the per-brand headline worker."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.conf import settings

from monitor.tasks import refresh_trend_narratives

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _envelope() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_cycle_id": "cycle-per-brand",
        "completed_at": NOW.isoformat(),
        "outcome": "completed",
        "dry_run": False,
    }


def test_production_refresh_routes_only_to_durable_per_brand_reconciler(monkeypatch):
    observed = []
    monkeypatch.setattr(
        "monitor.trend_narrative_tasks.reconcile_per_brand_trend_narratives",
        lambda envelope, **_kwargs: (
            observed.append(envelope)
            or {"status": "reconciled", "transport_started": 0}
        ),
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_queue.coalesce_envelope", lambda envelope: envelope
    )

    result = refresh_trend_narratives.run(_envelope())

    assert result["status"] == "reconciled"
    assert observed == [_envelope()]


def test_task_is_queue_isolated_and_has_no_automatic_retry():
    assert refresh_trend_narratives.name == "monitor.tasks.refresh_trend_narratives"
    assert refresh_trend_narratives.max_retries == 0
    assert refresh_trend_narratives.ignore_result is True
    assert refresh_trend_narratives.acks_late is True
    assert refresh_trend_narratives.reject_on_worker_lost is True
    assert refresh_trend_narratives.time_limit < 15 * 60
    assert settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"] > (
        refresh_trend_narratives.time_limit
    )
