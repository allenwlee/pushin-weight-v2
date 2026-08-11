from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from monitor.harvest_summary import (
    HARVEST_SUMMARY_PREFIX,
    SummaryValidationError,
    build_summary_envelope,
    parse_summary_line,
    provider_late_evidence,
    serialize_summary_envelope,
    summarize_latency,
)


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_cycle_persist_stamps_server_commit_clock():
    from monitor.cycle import CycleRunner
    from x_monitor.config import Config

    item = {
        "id": "clocked-post",
        "author_id": "clocked-author",
        "author_handle": "clocked-author",
        "text": "DeepSeek release",
        "created_at": _dt(1),
        "_api_received_at": _dt(100),
        "_api_received_monotonic": 100.0,
        "_api_page_number": 1,
        "brand_ids": [],
        "mentions": [],
        "classifications": {},
    }
    runner = CycleRunner(cfg=Config(enabled_models=["deepseek"], daily_ceiling=100))

    inserted, updated, attributed, failed = runner._persist_items([item])

    assert (inserted, updated, attributed, failed) == (1, 0, 0, 0)
    assert item["_db_committed_at"]
    latency = summarize_latency(
        [{
            "tweet_id": item["id"],
            "api_received_at": item["_api_received_at"],
            "db_committed_at": item["_db_committed_at"],
            "created_at": item["created_at"],
        }]
    )
    assert latency["eligible_count"] == 1


def _dt(second: int) -> str:
    return datetime.fromtimestamp(second, tz=UTC).isoformat()


def test_latency_uses_page_receipt_and_commit_not_provider_created_at():
    observations = [
        {
            "tweet_id": "one",
            "api_received_at": _dt(100),
            "db_committed_at": _dt(102),
            "created_at": _dt(1),
            "post_fetched_at": _dt(200),
        },
        {
            "tweet_id": "two",
            "api_received_at": _dt(110),
            "db_committed_at": _dt(111),
            "created_at": _dt(2),
            "post_fetched_at": _dt(201),
        },
    ]

    result = summarize_latency(observations)

    assert result["eligible_count"] == 2
    assert result["api_to_db_max_ms"] == 2000
    assert result["api_to_db_p95_ms"] == 2000
    assert result["observations"] == [
        {
            "tweet_id": "one",
            "api_received_at": _dt(100),
            "db_committed_at": _dt(102),
            "api_to_db_ms": 2000,
        },
        {
            "tweet_id": "two",
            "api_received_at": _dt(110),
            "db_committed_at": _dt(111),
            "api_to_db_ms": 1000,
        },
    ]


def test_duplicate_tweet_observations_keep_each_page_receipt_commit_pair():
    result = summarize_latency(
        [
            {
                "tweet_id": "same",
                "api_received_at": _dt(100),
                "db_committed_at": _dt(103),
            },
            {
                "tweet_id": "same",
                "api_received_at": _dt(120),
                "db_committed_at": _dt(121),
            },
        ]
    )

    assert result["eligible_count"] == 2
    assert [row["api_received_at"] for row in result["observations"]] == [
        _dt(100),
        _dt(120),
    ]


def test_envelope_is_deterministic_hashed_and_structurally_redacted():
    summary = {
        "run_id": "run-1",
        "status": "degraded",
        "started_at": _dt(100),
        "finished_at": _dt(105),
        "planned_calls": [{"call_id": "A", "call_kind": "list"}],
        "calls": [
            {
                "call_id": "A",
                "status": "completed",
                "n_results": 1,
                "not_include_drops": 2,
                "llm_drops": 3,
            }
        ],
        "degraded": {
            "cursor": "postgresql://user:password@example/db?sslmode=require",
            "provider": "Authorization: Bearer fake-token",
            "nested": {"api_key": "ordinary-fake-secret"},
        },
        "errors": ["multiline\nprovider body should not escape"],
    }

    first = build_summary_envelope(summary, service_id="cron-1", deploy_sha="abc123")
    second = build_summary_envelope(summary, service_id="cron-1", deploy_sha="abc123")

    assert first == second
    assert set(first) == {"schema_version", "service_id", "deploy_sha", "run_id", "summary", "hash"}
    line = serialize_summary_envelope(first)
    assert line.startswith(HARVEST_SUMMARY_PREFIX)
    assert "postgresql://" not in line
    assert "Authorization" not in line
    assert "fake-token" not in line
    assert "ordinary-fake-secret" not in line
    assert "provider body" not in line

    with_latency = build_summary_envelope(
        {
            **summary,
            "latency": {
                "observations": [{
                    "tweet_id": "one",
                    "api_received_at": _dt(100),
                    "db_committed_at": _dt(102),
                    "api_to_db_ms": 2000,
                }],
                "eligible_count": 1,
                "api_to_db_p95_ms": 2000,
                "api_to_db_max_ms": 2000,
            },
        }
    )
    assert with_latency["summary"]["latency"]["api_to_db"] == [{
        "tweet_id": "one",
        "api_received_at": _dt(100),
        "db_committed_at": _dt(102),
        "api_to_db_ms": 2000,
    }]

    unsigned = {key: value for key, value in first.items() if key != "hash"}
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert first["hash"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert parse_summary_line(line) == first


def test_parser_rejects_unknown_fields_and_bad_hash():
    envelope = build_summary_envelope({"run_id": "run-1", "status": "completed"})
    unknown = dict(envelope, extra="not allowed")
    with pytest.raises(SummaryValidationError):
        parse_summary_line(serialize_summary_envelope(unknown))

    tampered = dict(envelope, hash="0" * 64)
    with pytest.raises(SummaryValidationError):
        parse_summary_line(serialize_summary_envelope(tampered))


def test_provider_late_requires_healthy_matching_bounds_and_absence():
    prior = {
        "call_id": "B1",
        "status": "completed",
        "window_since": 100,
        "window_until": 200,
        "truncated": False,
    }
    evidence = provider_late_evidence(
        tweet_id="late-1",
        prior_call=prior,
        query_bounds={"since": 100, "until": 200},
        query_bounds_match=True,
        list_bounds_match=True,
        returned_tweet_ids=["other"],
    )
    assert evidence is not None
    assert evidence["tweet_id_absent"] is True
    assert provider_late_evidence(
        tweet_id="late-1",
        prior_call={**prior, "truncated": True},
        query_bounds={"since": 100, "until": 200},
        query_bounds_match=True,
        list_bounds_match=True,
        returned_tweet_ids=[],
    ) is None
    assert provider_late_evidence(
        tweet_id="other",
        prior_call=prior,
        query_bounds={"since": 100, "until": 200},
        query_bounds_match=True,
        list_bounds_match=True,
        returned_tweet_ids=["other"],
    ) is None
