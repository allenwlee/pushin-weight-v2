"""GDPx command wiring: the claimed, captured request path and typed failures."""

import copy
import json
from io import StringIO
from unittest.mock import patch

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tests.test_benchmark_gdpx import (
    DATA_PATH,
    DECOY_PATH,
    HOMEPAGE,
    STUB,
    chunk_with,
    dataset,
    site,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

RESULTS, OVERALL = 367, 26
EXPECTED = RESULTS + OVERALL
POLL_REQUESTS = 13
COMMAND = "monitor.management.commands.collect_benchmark_metrics.httpx.Client"


def contract():
    """A gdpx-only contract frozen with the recorded owner use policy."""
    from core.benchmark_attribution import GDPX_USE_POLICY
    from core.benchmark_metric_identity import configure_collection
    from core.models import DataSource
    from tests.test_benchmark_gdpx_definitions import gdpx_spec

    spec = gdpx_spec()
    source = DataSource.objects.get(pk="gdpx")
    source.metadata["use_policy"] = copy.deepcopy(GDPX_USE_POLICY)
    source.save(update_fields=["metadata"])
    return configure_collection(spec)


def gdpx_job(target):
    from core.collection_jobs import register_job, set_job_state
    from core.models import DataSource

    source = DataSource.objects.get(pk="gdpx")
    source.enabled = True
    source.save(update_fields=["enabled"])
    job = register_job(
        job_key="gdpx-daily",
        source=source,
        purpose="metric",
        operation="collect_metrics",
        contract=target,
        mode="recurring",
        definition={
            "version": 1,
            "scope": {},
            "schedule": {"kind": "daily_utc", "hour": 6, "driver": "shared"},
            "budgets": {
                "requests": 40,
                "seconds": 120,
                "bytes": 8 * 1024 * 1024,
                "items": 1000,
            },
        },
    )
    return set_job_state(job.pk, "ready")


def collect(target, overrides=None, *, calls=None, **options):
    calls = [] if calls is None else calls
    client = httpx.Client(transport=httpx.MockTransport(site(overrides, calls)))
    output = StringIO()
    with patch(COMMAND, return_value=client):
        call_command(
            "collect_benchmark_metrics",
            contract=str(target.pk),
            source="gdpx",
            start_date="2026-11-27",
            end_date="2026-11-27",
            apply=True,
            stdout=output,
            **options,
        )
    return json.loads(output.getvalue())


def requests_of(run):
    from core.models import CollectionRequest

    return list(CollectionRequest.objects.filter(attempt__run=run).order_by("ordinal"))


def status(job_id):
    output = StringIO()
    call_command("collection_status", job=str(job_id), source="gdpx", stdout=output)
    return json.loads(output.getvalue())


def ambiguous():
    other = dataset()
    other["results"][0]["score"] = 1.0
    return {DECOY_PATH: chunk_with(other)}


def shape_changed():
    data = dataset()
    data["results"][0]["score"] = 100.5
    return {DATA_PATH: chunk_with(data)}


def mismatched():
    return {
        "/": HOMEPAGE.replace(
            '<span class="block text-sm font-semibold">19.3<!-- -->%</span>',
            '<span class="block text-sm font-semibold">19.5<!-- -->%</span>',
        )
    }


FAILURES = {
    "fetch_failed": lambda: {"/": httpx.Response(404)},
    "fetch_challenged": lambda: {"/": httpx.Response(403, text="Just a moment...")},
    "dataset_not_found": lambda: {DATA_PATH: STUB},
    "dataset_ambiguous": ambiguous,
    "shape_changed": shape_changed,
    "headline_mismatch": mismatched,
}


@pytest.mark.parametrize("claimed", [False, True], ids=["direct", "job"])
def test_command_stores_first_poll_and_archives_every_request(claimed):
    from core.collection_capture import read_document
    from core.models import CollectionObservation, CollectionRun, MetricValue

    target = contract()
    options = {"job": str(gdpx_job(target).pk)} if claimed else {}
    calls = []
    output = collect(target, calls=calls, **options)
    run = CollectionRun.objects.get(pk=output["run_id"])
    assert (run.status, run.error_code) == ("success", None)
    assert (run.selected_count, run.success_count) == (EXPECTED, EXPECTED)
    assert output["request_count"] == run.request_count == len(calls) == POLL_REQUESTS
    stored = CollectionObservation.objects.filter(run=run, observation_kind__isnull=True)
    assert stored.count() == EXPECTED
    assert stored.filter(category_key="overall").count() == OVERALL
    assert MetricValue.objects.filter(observation__run=run).exists()
    (marker,) = CollectionObservation.objects.filter(observation_kind="publication_marker")
    assert marker.run_id == run.pk and marker.provider_revision == "v1.0"
    # Every HTTP call is a captured CollectionRequest with an archived body.
    captured = requests_of(run)
    assert [str(r.url) for r in calls] == [r.endpoint_url for r in captured]
    assert all(r.http_status == 200 and r.archive_id for r in captured)
    assert {r.headers["user-agent"] for r in calls} == {"PushinWeight-public-metadata"}
    # Reader request references are persisted as the captured request ids.
    archived = read_document(run.payload_archive)
    assert [r["request_id"] for r in archived["requests"]] == [str(r.pk) for r in captured]
    assert archived["anomalies"] == []


def test_repoll_reads_previous_probe_from_latest_publication_marker():
    from core.collection_capture import read_document
    from core.models import CollectionRun

    target = contract()
    first = collect(target)
    relabeled = {"/": HOMEPAGE.replace(">v1.0</span>", ">v2.0</span>")}
    second = collect(target, relabeled)
    run = CollectionRun.objects.get(pk=second["run_id"])
    assert run.pk != first["run_id"]
    assert run.status == "success"
    assert (run.selected_count, run.success_count) == (EXPECTED, EXPECTED)
    assert read_document(run.payload_archive)["anomalies"] == ["version_label_changed"]
    assert read_document(run.source_metadata_archive)["anomalies"] == [
        "version_label_changed"
    ]


@pytest.mark.parametrize("claimed", [False, True], ids=["direct", "job"])
@pytest.mark.parametrize("code", sorted(FAILURES))
def test_each_reader_failure_code_is_persisted_and_shown_by_status(code, claimed):
    from core.models import CollectionAttempt, CollectionRun, MetricValue

    target = contract()
    options = {"job": str(gdpx_job(target).pk)} if claimed else {}
    calls = []
    with pytest.raises(CommandError, match=f"Collection failed: {code}"):
        collect(target, FAILURES[code](), calls=calls, **options)
    run = CollectionRun.objects.get(job__source_id="gdpx")
    assert (run.status, run.error_code) == ("failed", code)
    # A claimed attempt carried the store's generic code; direct attempts had none.
    assert CollectionAttempt.objects.get(run=run).stop_reason == (code if claimed else None)
    assert run.request_count == len(calls) > 0
    assert len(requests_of(run)) == len(calls)
    assert not MetricValue.objects.exists()
    if claimed:
        # Direct one-off runs are not a job's last attempt; scheduled jobs are.
        report = status(run.job_id)
        assert report["source"] == "gdpx"
        assert report["last_attempt"]["run_id"] == str(run.pk)
        assert report["last_attempt"]["error_code"] == code
        assert report["last_success"] is None


def test_collection_status_reads_gdpx_values_with_their_coordinates():
    target = contract()
    collect(target)
    output = StringIO()
    call_command(
        "collection_status",
        contract=str(target.pk),
        source="gdpx",
        identifier="claude-fable-5-2",
        stdout=output,
    )
    report = json.loads(output.getvalue())
    assert report["source"] == "gdpx" and not report["truncated"]
    fleet = {
        row["metric"]: row
        for row in report["values"]
        if row["dimensions"].get("category") == "fleet"
    }
    assert fleet["score"]["value"] == 9.29
    assert fleet["score"]["dimensions"] == {
        "category": "fleet",
        "config": "Claude Code|max",
        "domain": fleet["score"]["dimensions"]["domain"],
        "date": "2026-11-25",
    }
    assert fleet["score"]["native_only"] is True
    assert any(row["dimensions"]["category"] == "overall" for row in report["values"])


def test_unknown_source_is_rejected_and_never_falls_back_to_arena(monkeypatch):
    from core.models import CollectionRun, MetricCollectionContract

    target = contract()
    with pytest.raises(CommandError, match="invalid choice"):
        call_command(
            "collect_benchmark_metrics", contract=str(target.pk), source="bogus",
            start_date="2026-11-27", end_date="2026-11-27", apply=True,
            stdout=StringIO(),
        )
    # A contract source with no reader once silently ran the Arena reader.
    configuration = dict(target.source_configuration)
    configuration["github"] = {"adapter_key": "unreviewed", "metrics": []}
    MetricCollectionContract.objects.filter(pk=target.pk).update(
        source_configuration=configuration
    )
    arena = []
    monkeypatch.setattr(
        "scripts.benchmark_download_collector.sources.arena",
        lambda *args, **kwargs: arena.append(args) or {"status": "ok", "rows": []},
    )
    with (
        patch(COMMAND, side_effect=AssertionError("no transport for unknown source")),
        pytest.raises(CommandError, match="unsupported metric source"),
    ):
        call_command(
            "collect_benchmark_metrics", contract=str(target.pk), source="github",
            start_date="2026-11-27", end_date="2026-11-27", apply=True,
            stdout=StringIO(),
        )
    assert arena == []
    assert not CollectionRun.objects.exists()
