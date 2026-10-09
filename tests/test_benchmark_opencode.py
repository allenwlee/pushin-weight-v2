"""OpenCode exact identities, UTC windows and immutable hourly revisions."""

from copy import deepcopy
from datetime import UTC, datetime

import httpx
import pytest

from tests.test_benchmark_download_sources import budget


def endpoint(tokens=9007199254740993123, updated="2026-10-07T12:44:18Z"):
    return {
        "page": "model",
        "updatedAt": updated,
        "model": {"id": "deepseek/deepseek-v4.1-flash"},
        "usage": {
            "daily": [
                {
                    "date": "2026-10-06",
                    "tokens": tokens,
                    "uniqueUsers": 57,
                    "sessions": 113,
                },
                {"date": "2026-10-07", "tokens": 100, "uniqueUsers": 2, "sessions": 3},
            ]
        },
    }


SELECTED = [
    {
        "external_identifier": "deepseek/deepseek-v4.1-flash",
        "endpoint_path": "/data/deepseek/deepseek-v4-1-flash.json",
    }
]


def read(data, *, now=None):
    from scripts.benchmark_download_collector.sources import opencode

    requests = []

    def handler(request):
        requests.append(request)
        assert (
            request.url == "https://opencode.ai/data/deepseek/deepseek-v4-1-flash.json"
        )
        assert (
            "authorization" not in request.headers and "cookie" not in request.headers
        )
        return httpx.Response(200, json=data)

    result = opencode(
        budget(handler), SELECTED, now=now or datetime(2026, 10, 7, 13, tzinfo=UTC)
    )
    assert len(requests) == 1
    return result


def test_reader_retains_all_dates_partial_day_and_exact_large_integer():
    result = read(endpoint())
    assert result["status"] == "ok"
    assert result["rows"][0]["tokens"] == 9007199254740993123
    assert result["rows"][0]["_source_metadata"]["period_status"] == "completed"
    assert result["rows"][1]["_source_metadata"]["period_status"] == "partial"
    assert result["endpoint_checks"][0]["updated_at"] == "2026-10-07T12:44:18+00:00"


@pytest.mark.parametrize(
    "change", ["id", "duplicate", "future", "negative", "float", "bool", "timestamp"]
)
def test_invalid_endpoint_is_retained_as_failed_subject_without_numeric_rows(change):
    data = deepcopy(endpoint())
    if change == "id":
        data["model"]["id"] = "other/model"
    elif change == "duplicate":
        data["usage"]["daily"].append(data["usage"]["daily"][0])
    elif change == "future":
        data["usage"]["daily"][0]["date"] = "2026-10-08"
    elif change == "timestamp":
        data["updatedAt"] = "2026-10-07"
    else:
        data["usage"]["daily"][0]["tokens"] = {
            "negative": -1,
            "float": 1.5,
            "bool": True,
        }[change]
    result = read(data)
    assert result["status"] == "partial"
    assert all(row.get("status") == "error" for row in result["rows"])


def test_optional_counts_can_be_absent_without_inventing_zero():
    data = endpoint()
    del data["usage"]["daily"][0]["uniqueUsers"]
    result = read(data)
    assert result["status"] == "ok"
    assert "uniqueUsers" not in result["rows"][0]


def configured():
    from core.benchmark_metric_identity import configure_collection
    from tests.test_benchmark_download_db_identity import setup_spec

    _, spec = setup_spec()
    spec["mappings"][0].update(
        source="opencode",
        source_subject_kind="model",
        identifier_scope="",
        external_identifier=SELECTED[0]["external_identifier"],
        identifier_metadata={"endpoint_path": SELECTED[0]["endpoint_path"]},
        evidence_url="https://opencode.ai/data/deepseek/deepseek-v4-1-flash.json",
    )
    spec["source_configuration"] = {
        "opencode": {"metrics": ["tokens", "unique_users", "sessions"]}
    }
    return configure_collection(spec)


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_hourly_replay_deduplicates_values_and_retains_corrected_partial_windows():
    from core.benchmark_metric_store import persist_source
    from core.models import MetricValue

    contract = configured()
    first = persist_source(contract, "opencode", "1" * 64, read(endpoint()))
    assert first.status == "success"
    assert MetricValue.objects.count() == 6
    partial = MetricValue.objects.get(
        source_metric__metric_key="tokens", period_label_date="2026-10-07"
    )
    assert partial.window_start_at == datetime(2026, 10, 7, tzinfo=UTC)
    assert partial.window_end_at is None and partial.temporal_status == "date_only"
    assert partial.window_range is None
    completed = MetricValue.objects.get(
        source_metric__metric_key="tokens", period_label_date="2026-10-06"
    )
    assert completed.window_range.lower == datetime(2026, 10, 6, tzinfo=UTC)
    assert completed.window_range.upper == partial.window_start_at
    assert completed.window_range.lower_inc and not completed.window_range.upper_inc
    second = persist_source(
        contract, "opencode", "2" * 64, read(endpoint(updated="2026-10-07T12:59:18Z"))
    )
    assert second.status == "success"
    assert MetricValue.objects.count() == 6
    assert (
        second.source_metadata["endpoint_checks"][0]["row_references"]
        == first.source_metadata["endpoint_checks"][0]["row_references"]
    )
    correction = persist_source(
        contract,
        "opencode",
        "3" * 64,
        read(endpoint(tokens=10, updated="2026-10-07T13:00:18Z")),
    )
    assert correction.status == "success" and MetricValue.objects.count() == 9
    assert (
        persist_source(
            contract,
            "opencode",
            "3" * 64,
            read(endpoint(tokens=10, updated="2026-10-07T13:00:18Z")),
        ).pk
        == correction.pk
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_endpoint_revision_orders_current_data_and_same_time_conflicts_are_flagged():
    from core.benchmark_metric_store import persist_source
    from core.benchmark_opencode import selected_rows

    contract = configured()
    for key, value, stamp in [
        ("4", 40, "12:00:00"),
        ("5", 40, "12:30:00"),
        ("6", 10, "12:15:00"),
    ]:
        persist_source(
            contract,
            "opencode",
            key * 64,
            read(endpoint(value, "2026-10-07T" + stamp + "Z")),
        )
    selected = selected_rows(
        contract,
        list(contract.mappings.values_list("pk", flat=True)),
        "2026-10-06",
        "2026-10-07",
    )
    obs = selected[(SELECTED[0]["external_identifier"], "2026-10-06")]["observation"]
    assert obs.values.get(source_metric__metric_key="tokens").integer_value == 40
    conflict = persist_source(
        contract, "opencode", "7" * 64, read(endpoint(20, "2026-10-07T12:30:00Z"))
    )
    assert (
        conflict.source_metadata["endpoint_checks"][0]["revision_anomaly"]
        == "same_update_different_body"
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_full_window_old_correction_midnight_and_failed_poll_keep_history():
    from datetime import timedelta

    from core.benchmark_metric_store import persist_source
    from core.benchmark_opencode import selected_rows
    from core.models import MetricValue

    contract = configured()
    data = endpoint(100)
    data["usage"]["daily"] = [
        {
            "date": (datetime(2026, 8, 13, tzinfo=UTC) + timedelta(days=i))
            .date()
            .isoformat(),
            "tokens": 0 if i == 0 else 100,
            "sessions": 3,
        }
        for i in range(56)
    ]
    first = persist_source(contract, "opencode", "a" * 64, read(data))
    assert first.success_count == 1 and MetricValue.objects.count() == 112
    data["updatedAt"] = "2026-10-08T00:05:00Z"
    data["usage"]["daily"][1]["tokens"] = 50
    data["usage"]["daily"].append({"date": "2026-10-08", "tokens": 1})
    second = persist_source(
        contract,
        "opencode",
        "b" * 64,
        read(data, now=datetime(2026, 10, 8, 0, 10, tzinfo=UTC)),
    )
    assert second.status == "success" and MetricValue.objects.count() == 117
    rows = selected_rows(
        contract,
        list(contract.mappings.values_list("pk", flat=True)),
        "2026-08-13",
        "2026-10-08",
    )
    assert len(rows) == 57
    assert (
        rows[(SELECTED[0]["external_identifier"], "2026-08-13")]["observation"]
        .values.get(source_metric__metric_key="tokens")
        .integer_value
        == 0
    )
    completed = rows[(SELECTED[0]["external_identifier"], "2026-10-07")][
        "observation"
    ].values.get(source_metric__metric_key="tokens")
    assert completed.window_end_at == datetime(2026, 10, 8, tzinfo=UTC)
    broken = endpoint()
    broken["model"]["id"] = "wrong/model"
    failed = persist_source(contract, "opencode", "c" * 64, read(broken))
    assert failed.status == "failed" and MetricValue.objects.count() == 117
    assert (
        len(
            selected_rows(
                contract,
                list(contract.mappings.values_list("pk", flat=True)),
                "2026-08-13",
                "2026-10-08",
            )
        )
        == 57
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_hourly_health_uses_endpoint_revision_even_when_values_unchanged():
    from datetime import timedelta

    from django.utils import timezone

    from core.benchmark_metric_operations import collection_health
    from core.benchmark_metric_store import persist_source

    contract = configured()
    persist_source(contract, "opencode", "d" * 64, read(endpoint()))
    health = collection_health(contract, now=datetime(2026, 10, 7, 15, tzinfo=UTC))[
        "opencode"
    ]
    assert health["publication_freshness"] == "stale"
    assert health["publication_time_precision"] == "instant"
    assert health["scheduling_enabled"] is False
    assert contract.source_configuration["opencode"]["poll_seconds"] == 3600
    assert (
        collection_health(contract, now=timezone.now() + timedelta(hours=3))[
            "opencode"
        ]["retrieval_freshness"]
        == "stale"
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_real_command_chain_imports_source_rows_and_remains_inert_by_default():
    from io import StringIO
    from unittest.mock import patch

    from django.core.management import call_command

    from core.models import MetricCollectionRun, MetricValue

    contract = configured()
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=endpoint()))
    )
    with patch(
        "monitor.management.commands.collect_benchmark_metrics.httpx.Client",
        return_value=client,
    ):
        call_command(
            "collect_benchmark_metrics",
            contract=str(contract.pk),
            source="opencode",
            start_date="2026-10-06",
            end_date="2026-10-07",
            apply=True,
            stdout=StringIO(),
        )
    assert MetricCollectionRun.objects.get().status == "success"
    assert MetricValue.objects.count() == 6
    output = StringIO()
    call_command("collect_benchmark_due", contract=str(contract.pk), stdout=output)
    assert '"enabled": false' in output.getvalue()


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_operational_cutoff_and_raw_snapshot_export_never_include_later_poll():
    import json
    from datetime import timedelta
    from io import StringIO
    from unittest.mock import patch

    from django.core.management import call_command
    from django.utils import timezone

    from core.benchmark_forecast_inputs import forecast_inputs
    from core.benchmark_metric_store import persist_source

    contract = configured()
    now = timezone.now()
    cutoff = now + timedelta(seconds=5)
    with patch("django.utils.timezone.now", return_value=now):
        first = persist_source(contract, "opencode", "e" * 64, read(endpoint(10)))
    with patch("django.utils.timezone.now", return_value=now + timedelta(seconds=10)):
        later = persist_source(
            contract, "opencode", "f" * 64, read(endpoint(20, "2026-10-07T12:59:00Z"))
        )
    result = forecast_inputs(contract, cutoff)
    assert {v["run_id"] for v in result["values"]} == {str(first.pk)}
    assert str(later.pk) not in str(result)
    assert any(
        v["source_metadata"]["period_status"] == "partial"
        and v["window_end_at"] is None
        for v in result["values"]
    )
    output = StringIO()
    call_command(
        "benchmark_opencode_snapshots",
        contract=str(contract.pk),
        start_date="2026-10-06",
        end_date="2026-10-07",
        cutoff=cutoff.isoformat(),
        stdout=output,
    )
    data = json.loads(output.getvalue())
    assert len(data["rows"]) == 2
    assert {r["check_run_id"] for r in data["rows"]} == {str(first.pk)}


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_history_command_keeps_endpoint_metadata_and_is_idempotent(tmp_path):
    from io import StringIO
    from unittest.mock import patch

    from django.core.management import call_command

    from core.models import MetricValue

    contract = configured()
    for _ in range(2):
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=endpoint(10))
            )
        )
        with patch(
            "monitor.management.commands.backfill_opencode_history.httpx.Client",
            return_value=client,
        ):
            call_command(
                "backfill_opencode_history",
                contract=str(contract.pk),
                output=str(tmp_path),
                apply=True,
                stdout=StringIO(),
            )
    assert MetricValue.objects.count() == 6
    assert (
        MetricValue.objects.get(
            source_metric__metric_key="tokens", period_label_date="2026-10-07"
        ).window_end_at
        is None
    )
