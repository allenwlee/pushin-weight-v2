"""Real command paths prove scheduler authority and fenced numeric admission."""

import importlib
import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from types import SimpleNamespace

import httpx
import pytest
from django.core.management import call_command
from django.db import connection

from core.benchmark_metric_identity import configure_collection
from core.collection_budgets import invocation_budget
from core.collection_jobs import register_job, set_job_state
from core.collection_scheduling import dispatch_due, due_job, take_metric_authority
from core.collection_state import claim_job, finish_run
from core.models import CollectionRun, DataSource, MetricValue
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
NOW = datetime(2026, 10, 13, 11, tzinfo=UTC)


def scheduled(settings):
    settings.BENCHMARK_COLLECTION_ENABLED = True
    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["scheduling_enabled"] = True
    contract = configure_collection(spec)
    source = DataSource.objects.get(pk="hf")
    source.enabled = True
    source.save()
    job = register_job(
        job_key="daily",
        source=source,
        purpose="metric",
        operation="collect_metrics",
        contract=contract,
        mode="recurring",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "daily_utc", "hour": 10, "driver": "shared"},
            "budgets": {"requests": 5, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    return set_job_state(job.pk, "ready", now=NOW)


def test_registration_preserves_legacy_then_takeover_blocks_both_paths(
    settings, monkeypatch
):
    job = scheduled(settings)
    assert due_job(job, now=NOW)["reason"] == "legacy_scheduler_owns_dispatch"
    take_metric_authority(job.pk)
    job.refresh_from_db()
    assert due_job(job, now=NOW)["due"]
    set_job_state(job.pk, "paused")
    monkeypatch.setattr(
        httpx, "Client", lambda **_: (_ for _ in ()).throw(AssertionError("dry client"))
    )
    out = StringIO()
    call_command("collect_benchmark_due", contract=str(job.contract_id), stdout=out)
    assert json.loads(out.getvalue())[0]["authority"] == "shared"
    assert not json.loads(out.getvalue())[0]["due"]
    assert CollectionRun.objects.count() == 0


def test_utc_slot_and_failure_cooldown_are_separate_from_success(settings):
    job = scheduled(settings)
    take_metric_authority(job.pk)
    job.refresh_from_db()
    assert not due_job(job, now=NOW.replace(hour=9))["due"]
    claim = claim_job(job.pk, now=NOW, typed=True)
    run = finish_run(
        claim, status="failed", retry_at=NOW + timedelta(minutes=15), now=NOW,
        typed=True, physical_accounting_complete=True, request_count=0,
    )
    job.refresh_from_db()
    assert job.last_success_id is None and job.last_attempt_id == run.pk
    assert due_job(job, now=NOW + timedelta(minutes=14))["reason"] == "cooldown"
    assert due_job(job, now=NOW + timedelta(minutes=16))["slot"].endswith(
        "10:00:00+00:00"
    )


def test_metric_due_command_writes_values_to_claimed_run_once(settings, monkeypatch):
    job = scheduled(settings)
    take_metric_authority(job.pk)
    seen = []

    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(
            200, json={"id": "lab/Model", "downloads": 0, "downloadsAllTime": 100}
        )

    factory = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **_: factory(transport=httpx.MockTransport(respond))
    )
    monkeypatch.setattr("core.collection_scheduling.timezone.now", lambda: NOW)
    call_command("collect_jobs_due", job=str(job.pk), execute=True, stdout=StringIO())
    job.refresh_from_db()
    assert job.last_success_id == job.last_attempt_id
    run = job.last_success
    assert run.purpose == "metric" and run.status == "success" and run.job_id == job.pk
    assert run.observations.count() == 1 and MetricValue.objects.count() == 2
    assert run.request_count == 1
    assert run.scheduled_slot_at == NOW.replace(hour=10)
    assert len(seen) == 1
    request = run.attempts.get().requests.get()
    assert request.archive_id and request.http_status == 200
    assert run.physical_bytes_received == request.response_bytes
    assert run.observations.get().inputs.get().input_request_id == request.pk
    # The legacy command sees shared ownership and cannot fetch the same slot again.
    call_command(
        "collect_benchmark_due",
        contract=str(job.contract_id),
        apply=True,
        stdout=StringIO(),
    )
    assert len(seen) == 1 and CollectionRun.objects.count() == 1


def test_historical_run_bytes_survive_without_an_attempt(settings):
    scheduled(settings)
    # Exercise the historical migration against a temporary copy of its old
    # table shape, without restoring the retired column on the real table.
    with connection.cursor() as cursor:
        cursor.execute("CREATE TEMP TABLE collection_runs (source_metadata jsonb, physical_bytes_received bigint) ON COMMIT DROP")
        cursor.execute("INSERT INTO collection_runs VALUES ('{\"physical_bytes_received\": 42}', NULL)")
    migration = importlib.import_module("core.migrations.0175_rg6_run_physical_bytes")
    migration.copy_historical_bytes(None, SimpleNamespace(connection=connection))
    with connection.cursor() as cursor:
        cursor.execute("SELECT physical_bytes_received FROM collection_runs")
        assert cursor.fetchone() == (42,)


def test_dispatch_invocation_budget_stops_before_second_job(settings):
    job = scheduled(settings)
    take_metric_authority(job.pk)
    job.refresh_from_db()
    # Definition registration now includes the existing GitHub provider identity.
    source = DataSource.objects.get(pk="github")
    source.enabled = True
    source.save(update_fields=["enabled"])
    other = register_job(
        job_key="catalog",
        source=source,
        purpose="catalog",
        operation="github_catalog",
        mode="recurring",
        definition={
            "version": 1,
            "scope": {"publishers": []},
            "schedule": {"kind": "interval", "seconds": 86400, "driver": "shared"},
            "budgets": {"requests": 5, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    set_job_state(other.pk, "ready", now=NOW)
    calls = []
    budget = invocation_budget(
        httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
                "id": "lab/model", "downloads": 1, "downloadsAllTime": 1, "likes": 0,
            }))
        ),
        requests=1,
        max_bytes=10000,
    )

    def execute(obj, decision, child):
        calls.append(obj.pk)
        child.hf_counts("lab/model")
        claim = claim_job(obj.pk, now=NOW, typed=True)
        return finish_run(claim, status="success", request_count=1, now=NOW,
                          typed=True, physical_accounting_complete=False)

    rows = dispatch_due(budget=budget, now=NOW, execute=True, executor=execute)
    assert calls == [job.pk] and budget.remaining == 0
    assert job.runs.get().status == "success"
    assert rows[-1]["reason"] == "invocation_budget_exhausted"


def test_external_x_cron_is_never_due_even_when_ready():
    source, _ = DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"}
    )
    source.enabled = False
    source.save()
    job = register_job(
        job_key="x-external",
        source=source,
        purpose="content",
        operation="x_cycle",
        mode="recurring",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {
                "kind": "interval",
                "seconds": 900,
                "driver": "external_render_cron",
            },
            "budgets": {"requests": 5, "seconds": 60, "bytes": 100000, "items": 100},
        },
    )
    job = set_job_state(job.pk, "ready", now=NOW)
    assert due_job(job, now=NOW)["reason"] == "external_or_manual_driver"
    with pytest.raises(ValueError, match="caller authorization"):
        claim_job(job.pk, now=NOW)
    # Existing scheduled/on-demand authority is explicit and independent of metric flags.
    claim = claim_job(job.pk, manual_authorized=True, now=NOW, typed=True)
    finish_run(claim, status="success", now=NOW, typed=True, physical_accounting_complete=True, request_count=0)


def test_late_metric_response_cannot_write_after_job_is_paused(settings, monkeypatch):
    job = scheduled(settings)
    factory = httpx.Client

    def response(request):
        set_job_state(job.pk, "paused")
        return httpx.Response(
            200, json={"id": "lab/Model", "downloads": 1, "downloadsAllTime": 100}
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **_: factory(transport=httpx.MockTransport(response))
    )
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command(
            "collect_benchmark_metrics",
            contract=str(job.contract_id),
            source="hf",
            start_date="2026-10-13",
            end_date="2026-10-13",
            job=str(job.pk),
            apply=True,
            stdout=StringIO(),
        )
    assert MetricValue.objects.count() == 0
    job.refresh_from_db()
    assert job.active_run_id is None and job.last_attempt.status == "aborted"


def test_failed_readiness_rolls_back_scheduling_takeover(settings):
    from django.core.management.base import CommandError

    job = scheduled(settings)
    job.source.enabled = False
    job.source.save()
    with pytest.raises(CommandError):
        call_command(
            "collection_job_state",
            job=str(job.pk),
            state="ready",
            take_metric_authority=True,
            apply=True,
            stdout=StringIO(),
        )
    job.source.refresh_from_db()
    assert "collection_job_authorities" not in job.source.metadata


def test_existing_legacy_source_lock_prevents_paid_shared_fetch(settings, monkeypatch):
    import psycopg
    from django.core.management.base import CommandError
    from django.db import connection

    from core.measurement_taxonomy import digest

    job = scheduled(settings)
    factory = httpx.Client

    def unexpected(request):
        raise AssertionError("provider called while legacy source is active")

    monkeypatch.setattr(
        httpx, "Client", lambda **_: factory(transport=httpx.MockTransport(unexpected))
    )
    config = connection.settings_dict
    with (
        psycopg.connect(
            dbname=config["NAME"],
            host=config["HOST"],
            port=config["PORT"],
            user=config["USER"],
            password=config["PASSWORD"],
        ) as db,
        db.cursor() as cursor,
    ):
        key = int(digest(["benchmark-metrics-v1", str(job.contract_id), "hf"])[:15], 16)
        cursor.execute("SELECT pg_advisory_lock(%s)", [key])
        with pytest.raises(CommandError, match="already running"):
            call_command(
                "collect_benchmark_metrics",
                contract=str(job.contract_id),
                source="hf",
                start_date="2026-10-13",
                end_date="2026-10-13",
                job=str(job.pk),
                apply=True,
                stdout=StringIO(),
            )
    job.refresh_from_db()
    assert job.last_attempt.status == "failed" and job.last_attempt.request_count == 0


# --- Multi-contract hourly entry (GDPx daily job beside the existing contract) ---

DUE = "monitor.management.commands.collect_benchmark_due"
GDPX_EXPECTED = 367 + 26


def existing_contract(settings):
    """The deployed contract's legacy-scheduled sources: HF daily, Arena interval."""
    settings.BENCHMARK_COLLECTION_ENABLED = True
    _, spec = setup_spec()
    spec["source_configuration"]["hf"]["scheduling_enabled"] = True
    spec["source_configuration"]["arena"] = {
        "metrics": ["rating"],
        "poll_seconds": 86400,
        "scheduling_enabled": True,
    }
    contract = configure_collection(spec)
    DataSource.objects.filter(pk__in=["hf", "arena"]).update(enabled=True)
    hf = DataSource.objects.get(pk="hf")
    hf.metadata["daily_collection_hour_utc"] = 10
    hf.save(update_fields=["metadata"])
    return contract


def gdpx_contract(base, *, hour=10, key="gdpx-daily"):
    """A gdpx-only contract whose daily_utc job owns metric dispatch."""
    import copy

    from core.benchmark_attribution import GDPX_USE_POLICY
    from core.models import MetricCollectionContract
    from tests.test_benchmark_gdpx_definitions import GDPX_METRICS

    base = MetricCollectionContract.objects.get(pk=base.pk)
    source = DataSource.objects.get(pk="gdpx")
    source.enabled = True
    source.metadata["use_policy"] = copy.deepcopy(GDPX_USE_POLICY)
    source.save(update_fields=["enabled", "metadata"])
    contract = configure_collection(
        {
            "taxonomy_version": str(base.taxonomy_version_id),
            "reviewed_by": "fixture",
            "mappings": [],
            "source_configuration": {
                "gdpx": {"metrics": sorted(GDPX_METRICS), "scheduling_enabled": True}
            },
            "methodology": {"aggregation": "fixed_cohort"},
        }
    )
    job = register_job(
        job_key=key,
        source=source,
        purpose="metric",
        operation="collect_metrics",
        contract=contract,
        mode="recurring",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "daily_utc", "hour": hour, "driver": "shared"},
            "budgets": {
                "requests": 40,
                "seconds": 120,
                "bytes": 8 * 1024 * 1024,
                "items": 1000,
            },
        },
    )
    set_job_state(job.pk, "ready", now=NOW.replace(hour=0))
    return contract, take_metric_authority(job.pk)


def role_spy(monkeypatch):
    """Count the deployed role wake-up while preserving its real behavior."""
    from monitor.management.commands import collect_benchmark_due as due

    calls, real = [], due.dispatch_collection_roles

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(f"{DUE}.dispatch_collection_roles", spy)
    return calls


def legacy_spy(monkeypatch, *, fail=None):
    """Record legacy metric collections; shared-job commands still run for real."""
    from monitor.management.commands import collect_benchmark_due as due

    calls, real = [], due.call_command

    def spy(name, *args, **kwargs):
        if name != "collect_benchmark_metrics":
            return real(name, *args, **kwargs)
        calls.append({k: v for k, v in kwargs.items() if k != "stdout"})
        if fail and kwargs["source"] == fail:
            from django.core.management.base import CommandError

            raise CommandError("Collection failed: fetch_failed")
        return None

    monkeypatch.setattr(f"{DUE}.call_command", spy)
    return calls


def gdpx_site(monkeypatch, state):
    """Serve the recorded GDPx site; any other provider call fails the test."""
    from tests.test_benchmark_gdpx import site

    def respond(request):
        if request.url.host != "gdpx.semianalysis.com":
            raise AssertionError(f"unexpected provider call {request.url}")
        return site(state.get("overrides"), state.setdefault("calls", []))(request)

    factory = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **_: factory(transport=httpx.MockTransport(respond))
    )


def freeze(monkeypatch, when):
    clock = [when]
    monkeypatch.setattr("core.collection_scheduling.timezone.now", lambda: clock[0])
    return clock


def legacy_batch(contract, source, bucket):
    import uuid

    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"pw-benchmark:{contract.pk}:{source}:{bucket}")
    )


def gdpx_observations(contract):
    from core.models import CollectionObservation

    rows = CollectionObservation.objects.filter(run__job__contract=contract)
    return (
        rows.filter(observation_kind__isnull=True).count(),
        rows.filter(observation_kind="publication_marker").count(),
    )


def test_single_contract_legacy_invocation_regression_net(settings, monkeypatch):
    """Pinned on the pre-change command: rows, calls, batches, roles, exit."""
    contract = existing_contract(settings)
    freeze(monkeypatch, NOW)
    roles = role_spy(monkeypatch)
    calls = legacy_spy(monkeypatch)
    out = StringIO()
    assert (
        call_command(
            "collect_benchmark_due", contract=str(contract.pk), apply=True, stdout=out
        )
        is None
    )
    order = list(contract.source_configuration)
    assert sorted(order) == ["arena", "hf"]
    rows = {
        "hf": {"source": "hf", "enabled": True, "due": True, "applied": True,
               "daily_collection_hour_utc": 10},
        "arena": {"source": "arena", "enabled": True, "due": True, "applied": True,
                  "daily_collection_hour_utc": None},
    }
    assert json.loads(out.getvalue()) == [rows[source] for source in order]
    common = {
        "contract": str(contract.pk),
        "start_date": "2026-10-13",
        "end_date": "2026-10-13",
        "max_requests": 20,
        "max_seconds": 120,
        "max_bytes": 8388608,
        "apply": True,
    }
    expected = {
        "hf": {**common, "source": "hf", "batch_id": legacy_batch(
            contract, "hf", "daily:2026-10-13T10:00:00+00:00")},
        "arena": {**common, "source": "arena", "batch_id": legacy_batch(
            contract, "arena", int(NOW.timestamp()) // 86400)},
    }
    assert calls == [expected[source] for source in order]
    assert roles == [{"execute": True, "now": NOW}]
    # Before the UTC slot nothing is due; inspection without --apply never runs.
    freeze(monkeypatch, NOW.replace(hour=9))
    out = StringIO()
    call_command("collect_benchmark_due", contract=str(contract.pk), stdout=out)
    by_source = {row["source"]: row for row in json.loads(out.getvalue())}
    assert by_source["hf"]["due"] is False and by_source["arena"]["due"] is True
    assert not any(row["applied"] for row in by_source.values())
    assert len(calls) == 2 and roles[-1] == {"execute": False, "now": NOW.replace(hour=9)}


def test_single_contract_shared_gdpx_job_regression_net(settings, monkeypatch):
    """A GDPx daily_utc job uses the existing slot logic with no GDPx code."""
    contract, job = gdpx_contract(existing_contract(settings))
    roles = role_spy(monkeypatch)
    for hour, due, reason in ((9, False, "before_slot"), (11, True, "due")):
        freeze(monkeypatch, NOW.replace(hour=hour))
        out = StringIO()
        call_command("collect_benchmark_due", contract=str(contract.pk), stdout=out)
        assert json.loads(out.getvalue()) == [
            {
                "job_id": str(job.pk),
                "source": "gdpx",
                "operation": "collect_metrics",
                "due": due,
                "reason": reason,
                "slot": "2026-10-13T10:00:00+00:00",
                "following_slot": "2026-10-14T10:00:00+00:00",
                "next_retry_at": None,
                "applied": False,
                "authority": "shared",
            }
        ]
    assert roles == [
        {"execute": False, "now": NOW.replace(hour=9)},
        {"execute": False, "now": NOW.replace(hour=11)},
    ]
    assert CollectionRun.objects.count() == 0


@pytest.mark.parametrize("failure", ["unknown", "collection", "disabled"])
def test_single_contract_failure_regression_net(failure, settings, monkeypatch):
    """One failing contract raises its own error, writes nothing, wakes no roles."""
    from django.core.management.base import CommandError

    contract = existing_contract(settings)
    freeze(monkeypatch, NOW)
    roles = role_spy(monkeypatch)
    calls = legacy_spy(monkeypatch, fail="hf")
    target = str(contract.pk)
    message = "Collection failed: fetch_failed"
    if failure == "unknown":
        import uuid

        target, message = str(uuid.uuid4()), "Unknown collection contract"
    elif failure == "disabled":
        settings.BENCHMARK_COLLECTION_ENABLED = False
        message = "Benchmark collection is disabled in this environment"
    out = StringIO()
    with pytest.raises(CommandError) as caught:
        call_command("collect_benchmark_due", contract=target, apply=True, stdout=out)
    assert str(caught.value) == message
    assert out.getvalue() == "" and roles == []
    assert [c["source"] for c in calls] == (["hf"] if failure == "collection" else [])


def due_command(*contracts, apply=True, out=None):
    args = [arg for contract in contracts for arg in ("--contract", str(contract))]
    call_command(
        "collect_benchmark_due",
        *args,
        *(["--apply"] if apply else []),
        stdout=out or StringIO(),
        stderr=StringIO(),
    )


def job_batches(monkeypatch):
    """Record the batch ids the shared dispatcher gives metric collections."""
    import core.collection_scheduling as scheduling

    batches, real = [], scheduling.call_command

    def spy(name, *args, **kwargs):
        if name == "collect_benchmark_metrics":
            batches.append((kwargs["slot"], kwargs["batch_id"]))
        return real(name, *args, **kwargs)

    monkeypatch.setattr("core.collection_scheduling.call_command", spy)
    return batches


def test_two_contracts_both_run_and_roles_dispatch_once(settings, monkeypatch):
    import uuid

    existing = existing_contract(settings)
    contract, job = gdpx_contract(existing)
    clock = freeze(monkeypatch, NOW)
    roles, calls = role_spy(monkeypatch), legacy_spy(monkeypatch)
    batches, state = job_batches(monkeypatch), {}
    gdpx_site(monkeypatch, state)
    out = StringIO()
    due_command(existing.pk, contract.pk, out=out)
    rows = json.loads(out.getvalue())
    assert {r["source"] for r in rows if r.get("authority") != "shared"} == {"hf", "arena"}
    (shared,) = [r for r in rows if r.get("authority") == "shared"]
    assert shared["job_id"] == str(job.pk) and shared["applied"]
    assert shared["status"] == "success"
    assert roles == [{"execute": True, "now": NOW}]
    assert {c["source"] for c in calls} == {"hf", "arena"}
    slot = "2026-10-13T10:00:00+00:00"
    assert batches == [
        (slot, str(uuid.uuid5(uuid.NAMESPACE_URL, f"pw-job:{job.pk}:{slot}")))
    ]
    assert gdpx_observations(contract) == (GDPX_EXPECTED, 1)
    # A later tick in the same slot reuses every batch id and fetches nothing.
    first = {c["source"]: c["batch_id"] for c in calls}
    requests = len(state["calls"])
    clock[0] = NOW + timedelta(minutes=30)
    due_command(existing.pk, contract.pk)
    assert {c["source"]: c["batch_id"] for c in calls[2:]} == first
    assert len(batches) == 1 and len(state["calls"]) == requests
    assert len(roles) == 2


@pytest.mark.parametrize("failure", ["raises", "unknown"])
def test_failed_gdpx_contract_does_not_stop_existing_contract(
    failure, settings, monkeypatch
):
    import uuid

    from django.core.management.base import CommandError

    existing = existing_contract(settings)
    contract, _ = gdpx_contract(existing)
    freeze(monkeypatch, NOW)
    roles, calls = role_spy(monkeypatch), legacy_spy(monkeypatch)
    target = str(contract.pk)
    if failure == "raises":
        def boom(job, decision, budget):
            raise RuntimeError("gdpx exploded")

        monkeypatch.setattr("core.collection_scheduling.execute_due_job", boom)
    else:
        target = str(uuid.uuid4())
    out, err = StringIO(), StringIO()
    with pytest.raises(CommandError, match="1 of 2 collection contracts failed") as caught:
        call_command(
            "collect_benchmark_due", "--contract", target, "--contract",
            str(existing.pk), "--apply", stdout=out, stderr=err,
        )
    assert target in str(caught.value)
    # The GDPx contract came first; the existing contract still collected.
    assert {c["source"] for c in calls} == {"hf", "arena"}
    assert {r["source"] for r in json.loads(out.getvalue())} >= {"hf", "arena"}
    assert roles == [{"execute": True, "now": NOW}]
    assert target in err.getvalue()


def test_gdpx_failure_cools_down_then_retries_next_hourly_tick(settings, monkeypatch):
    from core.models import CollectionJob

    contract, job = gdpx_contract(existing_contract(settings))
    ten = NOW.replace(hour=10)
    clock = freeze(monkeypatch, ten)
    batches = job_batches(monkeypatch)
    state = {"overrides": {"/": httpx.Response(404)}}
    gdpx_site(monkeypatch, state)
    due_command(contract.pk)
    job = CollectionJob.objects.get(pk=job.pk)
    assert job.last_attempt.status == "failed"
    assert job.last_attempt.error_code == "fetch_failed"
    assert job.last_success_id is None
    assert job.next_retry_at == ten + timedelta(minutes=15)
    assert gdpx_observations(contract) == (0, 0)
    # Inside the cooldown nothing is fetched.
    clock[0] = ten + timedelta(minutes=10)
    requests = len(state["calls"])
    out = StringIO()
    due_command(contract.pk, out=out)
    assert json.loads(out.getvalue())[0]["reason"] == "cooldown"
    assert len(state["calls"]) == requests
    # The 11:00 hourly tick retries the same UTC slot and succeeds.
    state["overrides"] = None
    clock[0] = ten + timedelta(hours=1)
    due_command(contract.pk)
    job = CollectionJob.objects.get(pk=job.pk)
    assert job.last_success_id == job.last_attempt_id
    assert job.last_success.status == "success"
    assert job.last_success.scheduled_slot_at == ten
    assert job.next_retry_at is None
    assert job.next_due_at == ten + timedelta(days=1)
    assert gdpx_observations(contract) == (GDPX_EXPECTED, 1)
    assert [slot for slot, _ in batches] == [ten.isoformat()] * 2
    assert batches[0][1] == batches[1][1]
    # Later ticks wait for the following day's 10:00 UTC slot.
    for later, reason in (
        (ten + timedelta(hours=2), "before_slot"),
        (ten + timedelta(hours=23), "before_slot"),
        (ten + timedelta(days=1), "due"),
    ):
        clock[0] = later
        out = StringIO()
        due_command(contract.pk, apply=False, out=out)
        assert json.loads(out.getvalue())[0]["reason"] == reason


class Killed(BaseException):
    """The worker process died after fetching, before storing."""


def test_interrupted_gdpx_run_retries_in_same_slot_without_duplicates(
    settings, monkeypatch
):
    from core.models import CollectionJob

    contract, job = gdpx_contract(existing_contract(settings))
    ten = NOW.replace(hour=10)
    clock = freeze(monkeypatch, ten)
    state = {}
    gdpx_site(monkeypatch, state)
    real = importlib.import_module(
        "monitor.management.commands.collect_benchmark_metrics"
    ).persist_source

    def die(*args, **kwargs):
        raise Killed

    monkeypatch.setattr(
        "monitor.management.commands.collect_benchmark_metrics.persist_source", die
    )
    with pytest.raises(Killed):
        due_command(contract.pk)
    job = CollectionJob.objects.get(pk=job.pk)
    interrupted = job.active_run
    assert interrupted.status == "running" and job.last_success_id is None
    assert gdpx_observations(contract) == (0, 0)
    monkeypatch.setattr(
        "monitor.management.commands.collect_benchmark_metrics.persist_source", real
    )
    # While the lease is live, a tick does not start a competing run.
    clock[0] = ten + timedelta(minutes=2)
    out = StringIO()
    due_command(contract.pk, out=out)
    assert json.loads(out.getvalue())[0]["reason"] == "active_lease"
    # After the lease expires, the 11:00 tick retries the same slot once.
    clock[0] = ten + timedelta(hours=1)
    due_command(contract.pk)
    job = CollectionJob.objects.get(pk=job.pk)
    interrupted.refresh_from_db()
    assert (interrupted.status, interrupted.error_code) == ("aborted", "expired_lease")
    assert job.last_success.scheduled_slot_at == ten
    assert job.last_success_id != interrupted.pk
    assert gdpx_observations(contract) == (GDPX_EXPECTED, 1)
    requests = len(state["calls"])
    clock[0] = ten + timedelta(hours=2)
    due_command(contract.pk)
    assert len(state["calls"]) == requests
    assert gdpx_observations(contract) == (GDPX_EXPECTED, 1)
    assert CollectionRun.objects.filter(job=job, status="success").count() == 1
