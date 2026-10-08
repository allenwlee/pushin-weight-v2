from datetime import timedelta

import pytest
from django.utils import timezone

from core.benchmark_metric_identity import configure_collection
from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import digest
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_health_separates_last_attempt_success_and_effective_time():
    from core.benchmark_metric_operations import collection_health

    _, spec = setup_spec()
    contract = configure_collection(spec)
    payload = {
        "status": "ok",
        "rows": [
            {
                "repo_id": "lab/Model",
                "status": "ok",
                "raw": {"downloads": 10, "downloadsAllTime": 50},
            }
        ],
    }
    successful = persist_source(contract, "hf", digest("ok"), payload)
    failed = persist_source(
        contract, "hf", digest("bad"), {"status": "failed", "rows": []}
    )
    result = collection_health(contract, now=timezone.now() + timedelta(days=3))["hf"]
    assert result["last_attempt"]["run_id"] == str(failed.pk)
    assert result["last_success"]["run_id"] == str(successful.pk)
    assert result["retrieval_freshness"] == "stale"
    assert result["latest_effective_date"] is None
    assert result["effective_freshness"] == "unknown"
    assert result["scheduling_enabled"] is False


def test_operation_settings_reject_unbounded_budget():
    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["max_requests"] = 10001
    with pytest.raises(ValueError, match="max_requests"):
        configure_collection(spec)


def test_due_collection_requires_activation_and_only_dispatches_due_sources(settings):
    from io import StringIO
    from unittest.mock import patch

    from django.core.management import call_command
    from django.core.management.base import CommandError

    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["scheduling_enabled"] = True
    contract = configure_collection(spec)
    with pytest.raises(CommandError, match="disabled"):
        call_command(
            "collect_benchmark_due",
            contract=str(contract.pk),
            apply=True,
            stdout=StringIO(),
        )
    settings.BENCHMARK_COLLECTION_ENABLED = True
    from core.models import DataSource

    DataSource.objects.filter(pk="hf").update(enabled=True)
    with patch(
        "monitor.management.commands.collect_benchmark_due.call_command"
    ) as collect:
        call_command(
            "collect_benchmark_due",
            contract=str(contract.pk),
            apply=True,
            stdout=StringIO(),
        )
    assert collect.call_count == 1
    assert collect.call_args.args[0] == "collect_benchmark_metrics"
    assert collect.call_args.kwargs["source"] == "hf"


def test_openrouter_configuration_requires_a_completed_utc_day():
    _, spec = setup_spec()
    spec["source_configuration"]["openrouter"] = {
        "metrics": ["total_tokens"],
        "completed_day_lag": 0,
    }
    with pytest.raises(ValueError, match="OpenRouter.*completed_day_lag"):
        configure_collection(spec)


def test_hf_configuration_allows_zero_completed_day_lag():
    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["completed_day_lag"] = 0
    contract = configure_collection(spec)
    assert contract.source_configuration["hf"]["completed_day_lag"] == 0
