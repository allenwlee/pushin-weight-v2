"""The headline status command is observable and side-effect free."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from core.models import TrendNarrativeVersion

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_empty_status_is_redacted_and_does_not_call_provider_or_queue(monkeypatch):
    monkeypatch.setenv("X_MONITOR_HEADLINE_API_KEY", "must-not-appear")
    monkeypatch.setattr(
        "monitor.trend_narrative_generation.generate_trend_narrative",
        lambda *_args, **_kwargs: pytest.fail("status called provider"),
    )
    monkeypatch.setattr(
        "monitor.tasks.refresh_trend_narratives.apply_async",
        lambda *_args, **_kwargs: pytest.fail("status enqueued work"),
    )
    stdout = StringIO()

    call_command("headline_status", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert [row["window_days"] for row in payload["windows"]] == [1, 7, 30, 365]
    assert all(row["state"] == "disabled" for row in payload["windows"])
    assert "must-not-appear" not in stdout.getvalue()
    assert TrendNarrativeVersion.objects.count() == 0
