from datetime import UTC, datetime, timedelta

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


@pytest.mark.parametrize(
    ("now", "previous", "due"),
    [
        ("2026-10-09T09:59:59+00:00", "2026-10-08T09:00:00+00:00", False),
        ("2026-10-09T10:00:00+00:00", "2026-10-08T11:00:00+00:00", True),
        ("2026-10-09T11:00:00+00:00", "2026-10-08T11:00:00+00:00", True),
        ("2026-10-09T11:00:00+00:00", "2026-10-09T10:01:00+00:00", False),
        ("2026-10-10T09:00:00+00:00", "2026-10-09T10:01:00+00:00", False),
        ("2026-10-09T09:00:00+00:00", None, False),
        ("2026-10-09T11:00:00+00:00", None, True),
        ("2026-10-09T19:00:00+09:00", "2026-10-08T10:01:00+00:00", True),
    ],
)
def test_daily_hf_schedule_dispatches_at_utc_slot_once(now, previous, due, settings):
    import json
    from io import StringIO
    from unittest.mock import patch

    from django.core.management import call_command

    from core.models import DataSource, MetricCollectionRun

    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["scheduling_enabled"] = True
    contract = configure_collection(spec)
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.metadata["daily_collection_hour_utc"] = 10
    source.save(update_fields=["enabled", "metadata"])
    if previous:
        run = persist_source(
            contract, "hf", digest("previous"), {"status": "failed", "rows": []}
        )
        MetricCollectionRun.objects.filter(pk=run.pk).update(
            started_at=datetime.fromisoformat(previous)
        )
    settings.BENCHMARK_COLLECTION_ENABLED = True
    output = StringIO()
    with (
        patch(
            "monitor.management.commands.collect_benchmark_due.timezone.now",
            return_value=datetime.fromisoformat(now),
        ),
        patch("monitor.management.commands.collect_benchmark_due.call_command") as collect,
    ):
        call_command(
            "collect_benchmark_due",
            contract=str(contract.pk),
            apply=True,
            stdout=output,
        )
    assert collect.call_count == int(due)
    result = json.loads(output.getvalue())[-1]
    assert result["daily_collection_hour_utc"] == 10
    assert result["due"] is due
    if due:
        assert collect.call_args.kwargs["source"] == "hf"
        assert collect.call_args.kwargs["end_date"] == "2026-10-09"


def test_daily_slot_batch_is_stable_and_health_exposes_schedule():
    from io import StringIO
    from unittest.mock import patch

    from django.core.management import call_command

    from core.benchmark_metric_operations import collection_health
    from core.models import DataSource

    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["scheduling_enabled"] = True
    contract = configure_collection(spec)
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.metadata["daily_collection_hour_utc"] = 10
    source.save(update_fields=["enabled", "metadata"])
    batches = []
    for hour in (10, 11):
        with (
            patch(
                "monitor.management.commands.collect_benchmark_due.timezone.now",
                return_value=datetime(2026, 10, 9, hour, tzinfo=UTC),
            ),
            patch("monitor.management.commands.collect_benchmark_due.call_command") as collect,
            patch("monitor.management.commands.collect_benchmark_due.settings.BENCHMARK_COLLECTION_ENABLED", True),
        ):
            call_command(
                "collect_benchmark_due", contract=str(contract.pk), apply=True,
                stdout=StringIO(),
            )
        batches.append(collect.call_args.kwargs["batch_id"])
    assert batches[0] == batches[1]
    assert collection_health(contract)["hf"]["daily_collection_hour_utc"] == 10


@pytest.mark.parametrize("hour", [-1, 24, "10", True])
def test_daily_schedule_rejects_invalid_registry_hours(hour):
    from core.benchmark_metric_operations import collection_health
    from core.models import DataSource

    _, spec = setup_spec()
    contract = configure_collection(spec)
    source = DataSource.objects.get(pk="hf")
    source.metadata["daily_collection_hour_utc"] = hour
    source.save(update_fields=["metadata"])
    with pytest.raises(ValueError, match="daily_collection_hour_utc"):
        collection_health(contract)


def test_daily_hf_real_command_persists_once_without_provider_calls(settings):
    from io import StringIO
    from unittest.mock import patch

    import httpx
    from django.core.management import call_command

    from core.models import DataSource, MetricCollectionRun, MetricValue

    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["scheduling_enabled"] = True
    contract = configure_collection(spec)
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.metadata["daily_collection_hour_utc"] = 10
    source.save(update_fields=["enabled", "metadata"])
    settings.BENCHMARK_COLLECTION_ENABLED = True
    requests = []

    def respond(request):
        requests.append(request.url.path)
        return httpx.Response(
            200, json={"id": "lab/Model", "downloads": 10, "downloadsAllTime": 50}
        )

    for hour in (9, 10, 11):
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with (
            patch(
                "monitor.management.commands.collect_benchmark_due.timezone.now",
                return_value=datetime(2026, 10, 9, hour, tzinfo=UTC),
            ),
            patch(
                "monitor.management.commands.collect_benchmark_metrics.httpx.Client",
                return_value=client,
            ),
        ):
            call_command(
                "collect_benchmark_due", contract=str(contract.pk), apply=True,
                stdout=StringIO(),
            )
            if hour == 10:
                # The model's default holds the original clock callable.
                MetricCollectionRun.objects.update(started_at=timezone.now())
        client.close()
    assert requests == ["/api/models/lab/Model"]
    assert MetricCollectionRun.objects.get().status == "success"
    assert MetricCollectionRun.objects.get().started_at.hour == 10
    assert MetricValue.objects.count() == 2


def test_hf_daily_override_preserves_other_provider_intervals(settings):
    from io import StringIO
    from unittest.mock import patch

    from django.core.management import call_command

    from core.models import DataSource, MetricCollectionRun

    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["scheduling_enabled"] = True
    for source, metric, interval in (
        ("openrouter", "total_tokens", 86400),
        ("arena", "rating", 86400),
        ("opencode", "tokens", 3600),
    ):
        spec["source_configuration"][source] = {
            "metrics": [metric], "poll_seconds": interval, "scheduling_enabled": True,
        }
    contract = configure_collection(spec)
    DataSource.objects.filter(pk__in=spec["source_configuration"]).update(enabled=True)
    hf = DataSource.objects.get(pk="hf")
    hf.metadata["daily_collection_hour_utc"] = 10
    hf.save(update_fields=["metadata"])
    for source, previous in (
        ("hf", "2026-10-08T11:00:00+00:00"),
        ("openrouter", "2026-10-08T10:00:00+00:00"),
        ("arena", "2026-10-09T09:00:00+00:00"),
        ("opencode", "2026-10-09T09:00:00+00:00"),
    ):
        run = persist_source(
            contract, source, digest(source), {"status": "failed", "rows": []}
        )
        MetricCollectionRun.objects.filter(pk=run.pk).update(
            started_at=datetime.fromisoformat(previous)
        )
    settings.BENCHMARK_COLLECTION_ENABLED = True
    with (
        patch(
            "monitor.management.commands.collect_benchmark_due.timezone.now",
            return_value=datetime(2026, 10, 9, 10, tzinfo=UTC),
        ),
        patch("monitor.management.commands.collect_benchmark_due.call_command") as collect,
    ):
        call_command(
            "collect_benchmark_due", contract=str(contract.pk), apply=True,
            stdout=StringIO(),
        )
    calls = {call.kwargs["source"]: call.kwargs for call in collect.call_args_list}
    assert set(calls) == {"hf", "openrouter", "opencode"}
    assert calls["openrouter"]["start_date"] == "2026-10-02"
    assert calls["openrouter"]["end_date"] == "2026-10-08"
    assert calls["opencode"]["end_date"] == "2026-10-09"
