"""Fixed 576-scope storage/parity workload; two serial and two parallel samples.

Only controlled localhost HTTP and the owned fixture database are used. Timings
describe this fixture, not historical keyword recall or production throughput.
"""
import hashlib
import json
import os
import re
import resource
import threading
import time
from pathlib import Path

import pytest
from django.db import connection
from django.db.models import Sum

from core.models import (
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
    Post,
    PostBrand,
)
from monitor.backfill_collection import execute_job
from tests.test_backfill_pipeline import page
from tests.test_backfill_prefetch import http_pages as http_pages_fixture
from tests.test_backfill_prefetch import job_for_scopes
from tests.test_backfill_prefetch import pipeline as pipeline_fixture
from x_monitor.apify import TwitterApiClient

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
http_pages = pytest.fixture(name="http_pages")(http_pages_fixture.__wrapped__)
pipeline = pytest.fixture(name="pipeline")(pipeline_fixture.__wrapped__)


def recorded_response(params):
    i = int(re.search(r"marker(\d+)", params["query"]).group(1))
    cursor = params.get("cursor")
    if i % 12 == 0:
        return {"tweets": [], "has_next_page": False, "next_cursor": "terminal-ignore"}
    if i % 12 == 1 and cursor is None:
        return {"tweets": [], "has_next_page": True, "next_cursor": "next-empty"}
    body = page(str(i + 1), cursor="next-full" if i % 12 == 2 and cursor is None else None)
    if i % 12 == 2 and cursor:
        body["tweets"] += page(str(10000 + i))["tweets"]
    if i % 12 == 3:
        body["tweets"] += page(str(20000 + i))["tweets"]
    return body


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@pytest.mark.parametrize("mode,repetition", [("serial", 1), ("parallel", 1), ("serial", 2), ("parallel", 2)])
def test_recorded_workload_preserves_fields_checkpoints_and_requests(http_pages, monkeypatch, mode, repetition):
    job = job_for_scopes(576, request_cap=200, maximum=1250)
    options = {"concurrency": 20, "starts_per_second": 20} if mode == "parallel" else None

    def respond(params):
        time.sleep(.2)
        return recorded_response(params)

    sql_usage = {"statements": 0, "seconds": 0.0}
    http_seconds = []
    http_guard = threading.Lock()
    original_get = TwitterApiClient._get

    def timed_get(client, *args, **kwargs):
        start = time.monotonic()
        try:
            return original_get(client, *args, **kwargs)
        finally:
            with http_guard:
                http_seconds.append(time.monotonic() - start)

    def measure_sql(execute, sql, params, many, context):
        start = time.monotonic()
        try:
            return execute(sql, params, many, context)
        finally:
            sql_usage["statements"] += 1
            sql_usage["seconds"] += time.monotonic() - start

    monkeypatch.setattr(TwitterApiClient, "_get", timed_get)
    attempt_seconds = []
    connection_samples = []
    started = time.monotonic()
    with http_pages(respond) as state, connection.execute_wrapper(measure_sql):
        for _ in range(8):
            report = execute_job(job.pk, collection_options=options)
            attempt_seconds.append(report["usage"]["elapsed_seconds"])
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()")
                connection_samples.append(cursor.fetchone()[0])
            if report["collection_drained"]:
                break
        else:
            pytest.fail("bounded fixture did not finish within eight attempts")
    elapsed = time.monotonic() - started
    expected_ids = {str(i + 1) for i in range(576) if i % 12 != 0}
    expected_ids |= {str(10000 + i) for i in range(576) if i % 12 == 2}
    expected_ids |= {str(20000 + i) for i in range(576) if i % 12 == 3}
    assert set(Post.objects.values_list("pk", flat=True)) == expected_ids
    assert len(state["requests"]) == 672
    assert len(http_seconds) == 672
    assert CollectionRun.objects.filter(job=job).aggregate(n=Sum("request_count"))["n"] == 672
    observations = set(CollectionObservation.objects.filter(run__job=job).values_list("post_id", flat=True))
    assert observations == expected_ids
    assert set(PostBrand.objects.values_list("post_id", "brand_id", "weight")) == {
        (pid, "qwen", 1.0) for pid in expected_ids
    }
    fields = ["tweet_id", "text", "lang", "created_at", "created_at_epoch", "created_at_raw",
              "native_author_id", "author_handle", "tweet_type", "is_reply", "is_retweet", "is_quote"]
    posts = list(Post.objects.order_by("tweet_id").values(*fields))
    for post in posts:
        assert post["text"] == "Qwen model release"
        assert post["lang"] == "en"
        assert post["created_at"].isoformat() == "2026-08-09T00:10:00+00:00"
        assert post["native_author_id"] == "author-" + post["tweet_id"]
        assert post["author_handle"] == "user" + post["tweet_id"]
    scopes = list(CollectionScopeRun.objects.filter(run_id=report["run_id"]).order_by("scope_key"))
    assert len(scopes) == 576 and all(s.enumeration_complete for s in scopes)
    checkpoints = []
    for scope in scopes:
        i = int(scope.scope_key.split(":")[1])
        assert scope.raw_count == {0: 0, 1: 1, 2: 3, 3: 2}.get(i % 12, 1)
        assert len(scope.envelopes) == (2 if i % 12 in {1, 2} else 1)
        checkpoints.append([scope.scope_key, scope.cursor, scope.cursor_history,
                            scope.raw_count, scope.enumeration_complete, scope.outcome])
    assert state["peak"] == 1 if mode == "serial" else 1 < state["peak"] <= 20
    sample = {
        "mode": mode, "repetition": repetition, "scopes": 576, "physical_requests": 672,
        "posts": len(posts), "seconds": round(elapsed, 3), "http_peak": state["peak"],
        "connections": len(state["connections"]),
        "database_connection_samples": connection_samples,
        "sql_statements": sql_usage["statements"],
        "sql_execute_seconds_sum": round(sql_usage["seconds"], 3),
        "http_seconds_sum": round(sum(http_seconds), 3),
        "attempt_active_seconds_sum": round(sum(attempt_seconds), 3),
        "rss_peak_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "posts_sha256": digest(posts), "checkpoints_sha256": digest(checkpoints),
        "requests_sha256": digest(sorted(state["requests"], key=lambda p: json.dumps(p, sort_keys=True))),
    }
    # The hosted harness retains and compares all four measurements together.
    target = os.environ.get("PW_BACKFILL_WORKLOAD_RECEIPT")
    if target:
        with Path(target).open("a") as output:
            output.write(json.dumps(sample, sort_keys=True) + "\n")


@pytest.mark.parametrize("mode", ["serial", "parallel"])
def test_saturated_twenty_worker_workload(http_pages, mode):
    """Same8s provider latency in both modes; parallel must reach20 active calls."""
    job = job_for_scopes(40, request_cap=100, maximum=100)
    options = {"concurrency": 20, "starts_per_second": 20} if mode == "parallel" else None
    stop_sampling = threading.Event()
    memory_samples = []

    def sample_memory():
        while not stop_sampling.is_set():
            values = {}
            status_path = Path("/proc/self/status")
            if status_path.exists():
                status = status_path.read_text()
                for field in ("VmRSS", "Threads"):
                    match = re.search(rf"^{field}:\s+(\d+)", status, re.MULTILINE)
                    if match:
                        values[field] = int(match.group(1))
            for path in ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
                if Path(path).exists():
                    values["container_memory_bytes"] = int(Path(path).read_text())
                    break
            memory_samples.append(values)
            stop_sampling.wait(.2)

    def respond(params):
        index = int(re.search(r"marker(\d+)", params["query"]).group(1))
        time.sleep(8)
        body = page(str(index * 20 + 1))
        for offset in range(2, 21):
            body["tweets"] += page(str(index * 20 + offset))["tweets"]
        return body

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    started, cpu_started = time.monotonic(), time.process_time()
    connection_samples = []
    try:
        with http_pages(respond) as state:
            for _ in range(6):
                report = execute_job(job.pk, collection_options=options)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()")
                    connection_samples.append(cursor.fetchone()[0])
                if report["collection_drained"]:
                    break
            else:
                pytest.fail("saturated workload exceeded six attempts")
    finally:
        stop_sampling.set()
        sampler.join(timeout=5)
    elapsed, cpu_seconds = time.monotonic() - started, time.process_time() - cpu_started
    assert state["peak"] == (20 if mode == "parallel" else 1)
    at_twenty_seconds = sum(end[0] - start[0] for start, end in zip(
        state["activity"], state["activity"][1:]
    ) if start[1] == 20)
    if mode == "parallel":
        assert at_twenty_seconds >= .5, "twenty-way overlap was not sustained"
    assert len(state["requests"]) == 40
    assert CollectionRun.objects.filter(job=job).aggregate(n=Sum("request_count"))["n"] == 40
    ids = {str(index) for index in range(1, 801)}
    assert set(Post.objects.values_list("pk", flat=True)) == ids
    assert set(CollectionObservation.objects.filter(run__job=job).values_list("post_id", flat=True)) == ids
    brands = sorted(PostBrand.objects.values_list("post_id", "brand_id", "weight"))
    assert set(brands) == {(identifier, "qwen", 1.0) for identifier in ids}
    posts = list(Post.objects.order_by("tweet_id").values(
        "tweet_id", "text", "lang", "created_at", "created_at_epoch", "created_at_raw",
        "native_author_id", "author_handle", "tweet_type", "is_reply", "is_retweet", "is_quote",
    ))
    scopes = list(CollectionScopeRun.objects.filter(run_id=report["run_id"]).order_by("scope_key"))
    assert len(scopes) == 40 and all(s.enumeration_complete and s.raw_count == 20 for s in scopes)
    checkpoints = [[s.scope_key, s.cursor, s.cursor_history, s.raw_count,
                    s.enumeration_complete, s.outcome] for s in scopes]
    result = {
        "profile": "forty-scopes-twenty-posts-eight-second-http", "mode": mode,
        "scopes": 40, "physical_requests": 40, "posts": len(posts),
        "http_peak": state["peak"], "seconds": round(elapsed, 3),
        "seconds_with_twenty_http_active": round(at_twenty_seconds, 3),
        "process_cpu_seconds": round(cpu_seconds, 3),
        "process_rss_baseline_kib": memory_samples[0].get("VmRSS"),
        "process_rss_sampled_peak_kib": max((s.get("VmRSS", 0) for s in memory_samples), default=0),
        "process_threads_sampled_peak": max((s.get("Threads", 0) for s in memory_samples), default=0),
        "container_memory_sampled_peak_bytes": max((s.get("container_memory_bytes", 0) for s in memory_samples), default=0),
        "database_connection_samples": connection_samples,
        "resources_include_controlled_http_server": True,
        "posts_sha256": digest(posts), "brands_sha256": digest(brands),
        "checkpoints_sha256": digest(checkpoints),
        "requests_sha256": digest(sorted(state["requests"], key=lambda p: json.dumps(p, sort_keys=True))),
    }
    target = os.environ.get("PW_BACKFILL_WORKLOAD_RECEIPT")
    if target:
        with Path(target).open("a") as output:
            output.write(json.dumps(result, sort_keys=True) + "\n")
