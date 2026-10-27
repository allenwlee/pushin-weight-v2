from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import EnrichmentBudgetWindow
from monitor.enrichment_budget import config_fingerprint
from monitor.management.commands import enrichment_budget
from x_monitor.config import Config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.fixture
def cfg(monkeypatch):
    config = Config(enabled_models=["deepseek"], daily_ceiling=100)
    monkeypatch.setattr(enrichment_budget, "load_config", lambda path: config)
    return config


@pytest.mark.parametrize("scope,requests", [("pilot", 1200), ("scheduled", 1201)])
@pytest.mark.parametrize("apply", [False, True])
def test_budget_command_preview_and_apply_use_typed_kind(cfg, scope, requests, apply):
    before = EnrichmentBudgetWindow.objects.count()
    output = StringIO()
    arguments = ["--scope", scope, "--hours", "2", "--requests", str(requests), "--usd-limit", "0.250000"]
    if apply:
        arguments.append("--apply")
    with CaptureQueriesContext(connection) as queries:
        call_command("enrichment_budget", *arguments, stdout=output)
    receipt = json.loads(output.getvalue())
    assert receipt["applied"] is apply
    assert receipt["scope"] == scope
    assert receipt["requests"] == requests
    assert Decimal(receipt["usd_limit"]) == Decimal("0.25")
    assert receipt["config_fingerprint"] == config_fingerprint(cfg)
    assert EnrichmentBudgetWindow.objects.count() == before + int(apply)
    if apply:
        window = EnrichmentBudgetWindow.objects.get(pk=receipt["window_id"])
        assert window.enrichment_window_kind == scope
        assert window.ends_at - window.starts_at == timedelta(hours=2)
        assert window.request_limit == requests
        assert window.usd_limit == Decimal("0.25")
        assert window.config_fingerprint == receipt["config_fingerprint"]
        assert window.reserved_requests == window.reserved_usd == 0
    else:
        assert not EnrichmentBudgetWindow.objects.filter(pk=receipt["window_id"]).exists()
        assert not any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries)


@pytest.mark.parametrize("arguments", [
    ["--scope", "pilot", "--hours", "1", "--requests", "1201", "--usd-limit", "1"],
    ["--scope", "scheduled", "--hours", "0", "--requests", "1", "--usd-limit", "1"],
    ["--scope", "scheduled", "--hours", "1", "--requests", "1", "--usd-limit", "0"],
])
def test_invalid_budget_command_does_not_create_allowance(cfg, arguments):
    before = EnrichmentBudgetWindow.objects.count()
    with pytest.raises(CommandError):
        call_command("enrichment_budget", *arguments, "--apply", stdout=StringIO())
    assert EnrichmentBudgetWindow.objects.count() == before
