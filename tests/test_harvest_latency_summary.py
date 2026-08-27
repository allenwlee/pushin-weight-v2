from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from monitor.harvest_summary import (
    HARVEST_COHORT_PREFIX,
    HARVEST_SUMMARY_PREFIX,
    SummaryValidationError,
    build_cohort_receipt,
    build_summary_envelope,
    parse_cohort_line,
    parse_summary_line,
    provider_late_evidence,
    serialize_cohort_receipt,
    serialize_summary_envelope,
    summarize_latency,
)


def _rehash(value: dict) -> dict:
    unsigned = {key: item for key, item in value.items() if key != "hash"}
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    value["hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return value


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
    assert first["schema_version"] == "2"
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


def test_parser_accepts_historical_v1_but_rejects_v2_fields_claimed_as_v1():
    current = build_summary_envelope(
        {
            "run_id": "versioned-run",
            "post_fetch": {
                "n_translated": 1,
                "n_enrichment_claimed": 1,
            },
            "metrics_refresh": {
                "n_due": 1,
                "n_refreshed": 1,
                "n_errors": 0,
            },
        }
    )
    historical = json.loads(json.dumps(current))
    historical["schema_version"] = "1"
    historical["summary"]["post_fetch"].pop("n_enrichment_claimed")
    historical["summary"]["metrics_refresh"].pop("n_errors")
    _rehash(historical)

    assert parse_summary_line(
        HARVEST_SUMMARY_PREFIX
        + json.dumps(historical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    ) == historical

    historical["summary"]["post_fetch"]["n_enrichment_claimed"] = 1
    _rehash(historical)
    with pytest.raises(SummaryValidationError, match="unknown post_fetch fields"):
        parse_summary_line(
            HARVEST_SUMMARY_PREFIX
            + json.dumps(
                historical,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )


def test_nonempty_cycle_cohort_receipt_round_trips_and_correlates_to_summary():
    summary = {
        "run_id": "cohort-run",
        "totals": {"n_inserted": 2},
        "post_fetch": {
            "n_enrichment_claimed": 2,
            "n_enrichment_claimed_current_cycle": 2,
            "n_enrichment_claimed_carryover": 0,
            "n_enrichment_succeeded": 2,
            "n_enrichment_succeeded_current_cycle": 2,
            "n_enrichment_succeeded_carryover": 0,
            "n_enrichment_pending": 0,
            "n_enrichment_pending_current_cycle": 0,
            "n_enrichment_pending_carryover": 0,
            "n_enrichment_failed": 0,
            "n_enrichment_failed_current_cycle": 0,
            "n_enrichment_failed_carryover": 0,
            "inserted_post_ids": ["200", "100"],
            "enrichment_current_cycle_post_ids": ["200", "100"],
            "enrichment_carryover_post_ids": [],
            "enrichment_state_facts": [
                {
                    "post_id": post_id,
                    "lane": "current_cycle",
                    "translation_status": "succeeded",
                    "classification_status": "succeeded",
                    "output_complete": True,
                }
                for post_id in ("200", "100")
            ],
        },
    }
    envelope = build_summary_envelope(
        summary, service_id="cron-1", deploy_sha="abc123"
    )

    receipt = build_cohort_receipt(summary, envelope=envelope)

    assert receipt is not None
    line = serialize_cohort_receipt(receipt)
    assert line.startswith(HARVEST_COHORT_PREFIX)
    assert parse_cohort_line(line, summary_envelope=envelope) == receipt
    assert receipt["inserted_post_ids"] == ["100", "200"]
    assert receipt["summary_hash"] == envelope["hash"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt: receipt.update(run_id="different-run"),
        lambda receipt: receipt["current_cycle_post_ids"].append("999"),
        lambda receipt: receipt["enrichment_state_facts"][0].update(
            lane="carryover"
        ),
        lambda receipt: receipt["inserted_post_ids"].append(
            "postgresql://secret"
        ),
    ],
)
def test_cohort_receipt_rejects_identity_fact_and_sensitive_mismatches(mutate):
    summary = {
        "run_id": "cohort-run",
        "totals": {"n_inserted": 1},
        "post_fetch": {
            "n_enrichment_claimed": 1,
            "n_enrichment_claimed_current_cycle": 1,
            "n_enrichment_claimed_carryover": 0,
            "n_enrichment_succeeded": 1,
            "n_enrichment_succeeded_current_cycle": 1,
            "n_enrichment_succeeded_carryover": 0,
            "n_enrichment_pending": 0,
            "n_enrichment_pending_current_cycle": 0,
            "n_enrichment_pending_carryover": 0,
            "n_enrichment_failed": 0,
            "n_enrichment_failed_current_cycle": 0,
            "n_enrichment_failed_carryover": 0,
            "inserted_post_ids": ["100"],
            "enrichment_current_cycle_post_ids": ["100"],
            "enrichment_carryover_post_ids": [],
            "enrichment_state_facts": [
                {
                    "post_id": "100",
                    "lane": "current_cycle",
                    "translation_status": "succeeded",
                    "classification_status": "succeeded",
                    "output_complete": True,
                }
            ],
        },
    }
    envelope = build_summary_envelope(summary)
    receipt = build_cohort_receipt(summary, envelope=envelope)
    assert receipt is not None
    mutate(receipt)
    _rehash(receipt)

    with pytest.raises(SummaryValidationError):
        parse_cohort_line(
            HARVEST_COHORT_PREFIX
            + json.dumps(
                receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            summary_envelope=envelope,
        )


def test_envelope_carries_all_enrichment_lane_counts_without_post_ids():
    post_fetch = {
        "n_enrichment_claimed": 5,
        "n_enrichment_claimed_current_cycle": 3,
        "n_enrichment_claimed_carryover": 2,
        "n_enrichment_succeeded": 3,
        "n_enrichment_succeeded_current_cycle": 2,
        "n_enrichment_succeeded_carryover": 1,
        "n_enrichment_pending": 1,
        "n_enrichment_pending_current_cycle": 1,
        "n_enrichment_pending_carryover": 0,
        "n_enrichment_failed": 1,
        "n_enrichment_failed_current_cycle": 0,
        "n_enrichment_failed_carryover": 1,
        "n_enrichment_deferred": 4,
        "n_enrichment_quarantined": 1,
        "inserted_post_ids": ["must-not-cross-summary-boundary"],
        "enrichment_current_cycle_post_ids": ["must-not-cross-either"],
    }

    envelope = build_summary_envelope(
        {"run_id": "run-lanes", "status": "completed", "post_fetch": post_fetch}
    )
    line = serialize_summary_envelope(envelope)
    parsed = parse_summary_line(line)

    assert parsed["summary"]["post_fetch"] == {
        key: value for key, value in post_fetch.items() if key.startswith("n_")
    }
    assert "must-not-cross" not in line


@pytest.mark.parametrize(
    "mutate",
    [
        lambda envelope: envelope["summary"]["post_fetch"].update(
            n_enrichment_claimed=-1
        ),
        lambda envelope: envelope["summary"]["post_fetch"].update(
            unknown_count=1
        ),
        lambda envelope: envelope.update(service_id="unsafe\nservice"),
        lambda envelope: envelope.update(
            service_id="postgresql://user:password@example.invalid/db"
        ),
    ],
)
def test_summary_serializer_rejects_invalid_enrichment_or_identity_values(mutate):
    envelope = build_summary_envelope(
        {
            "run_id": "run-lanes",
            "status": "completed",
            "post_fetch": {"n_enrichment_claimed": 1},
        }
    )
    mutate(envelope)

    with pytest.raises(SummaryValidationError):
        serialize_summary_envelope(envelope)


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
