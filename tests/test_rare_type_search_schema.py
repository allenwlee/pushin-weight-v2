"""PostgreSQL contracts for the rare-type paid-search ledgers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction

from core.models import (
    Post,
    RareTypeDecision,
    RareTypeSearchDailyBudget,
    RareTypeSearchHit,
    RareTypeSearchRun,
    SearchQuery,
)
from core.rare_type_search import (
    HitSerializationError,
    claim_decision,
    complete_decision,
    expire_hit_payloads,
    fail_decision,
    mark_search_dispatched,
    mark_search_failed,
    persist_hit_batch,
    reserve_decision_budget,
    reserve_search_run,
    settle_decision_budget,
    settle_search_return,
)
from x_monitor.apify import _normalize_tweet

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
LANE = "rare_types"


def _query(suffix: str = "base") -> SearchQuery:
    return SearchQuery.objects.create(query_id=f"rare-{suffix}")


def _reserve(*, slot_start=NOW, query=None, lane=LANE, daily_credit_limit=6000):
    query = query or _query(str(slot_start.timestamp()))
    return reserve_search_run(
        lane=lane,
        slot_start=slot_start,
        source_query=query,
        query_string="(joined OR hiring) min_faves:0",
        query_hash="a" * 64,
        query_version="rare-types-v2-2026-09-22",
        environment="test",
        release_sha="166f7bf",
        now=slot_start,
        daily_credit_limit=daily_credit_limit,
    )


def test_run_constraints_and_first_window_are_durable():
    reservation = _reserve()
    assert reservation.created is True
    assert reservation.run.status == RareTypeSearchRun.Status.RESERVED
    assert reservation.run.window_start == NOW - timedelta(minutes=15)
    assert reservation.run.window_end == NOW
    assert reservation.run.attempted_start == NOW - timedelta(minutes=15)
    assert reservation.run.attempted_end == NOW
    assert reservation.run.raw_result_count is None
    assert reservation.run.reserved_credits == 300
    assert reservation.run.source_query.query_id.startswith("rare-")
    assert RareTypeSearchDailyBudget.objects.get().search_credits_reserved == 300

    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeSearchRun.objects.create(
            lane=LANE,
            slot_start=NOW,
            source_query=_query("duplicate"),
            query_string="different",
            query_hash="b" * 64,
            query_version="v2",
            window_start=NOW,
            window_end=NOW + timedelta(minutes=15),
            attempted_start=NOW,
            attempted_end=NOW + timedelta(minutes=15),
            reserved_credits=300,
            environment="test",
            release_sha="b" * 7,
        )


def test_next_window_caps_catchup_and_records_older_gap():
    first = _reserve(slot_start=NOW)
    mark_search_failed(first.run.pk, error_code="pre_dispatch", now=NOW)
    second = _reserve(slot_start=NOW + timedelta(hours=2), query=_query("gap"))
    assert second.run.window_start == NOW + timedelta(hours=1, minutes=30)
    assert second.run.window_end == NOW + timedelta(hours=2)
    assert second.run.has_coverage_gap is True
    assert second.run.gap_start == NOW
    assert second.run.gap_end == NOW + timedelta(hours=1, minutes=30)


def test_before_dispatch_failure_releases_budget_but_after_dispatch_is_unknown():
    before = _reserve(slot_start=NOW)
    assert mark_search_failed(before.run.pk, error_code="planner_failed", now=NOW)
    before.run.refresh_from_db()
    assert before.run.status == RareTypeSearchRun.Status.FAILED
    assert RareTypeSearchDailyBudget.objects.get().search_credits_reserved == 0

    after = _reserve(
        slot_start=NOW + timedelta(minutes=15), query=_query("after-dispatch")
    )
    assert mark_search_dispatched(after.run.pk, now=NOW + timedelta(minutes=15))
    assert mark_search_failed(
        after.run.pk, error_code="response_lost", now=NOW + timedelta(minutes=16)
    )
    after.run.refresh_from_db()
    assert after.run.status == RareTypeSearchRun.Status.USAGE_UNKNOWN
    assert after.run.request_count == 1
    assert RareTypeSearchDailyBudget.objects.get().search_credits_reserved == 300
    assert (
        _reserve(
            slot_start=NOW + timedelta(minutes=15), query=_query("same-slot")
        ).created
        is False
    )


def test_failed_and_truncated_attempts_record_gaps_without_losing_older_gap():
    first = _reserve()
    mark_search_dispatched(first.run.pk, now=NOW)
    assert mark_search_failed(first.run.pk, error_code="timeout", now=NOW)
    first.run.refresh_from_db()
    assert (first.run.gap_start, first.run.gap_end) == (
        NOW - timedelta(minutes=15),
        NOW,
    )
    assert first.run.complete_start is None

    later = _reserve(slot_start=NOW + timedelta(hours=2), query=_query("truncated-gap"))
    original_gap_start = later.run.gap_start
    mark_search_dispatched(later.run.pk, now=NOW + timedelta(hours=2))
    settle_search_return(
        later.run.pk,
        raw_count=20,
        normalized_count=4,
        truncated=True,
        now=NOW + timedelta(hours=2),
    )
    later.run.refresh_from_db()
    assert later.run.gap_start == original_gap_start == NOW
    assert later.run.gap_end == NOW + timedelta(hours=2)
    assert "catchup_capped_30m" in later.run.gap_reason
    assert "provider_truncated" in later.run.gap_reason


@pytest.mark.parametrize(
    "slot_offset, raw_count, expected", [(0, 0, 15), (15, 1, 15), (30, 20, 300)]
)
def test_return_settles_against_raw_paid_count_with_floor(
    slot_offset, raw_count, expected
):
    reserved = _reserve(slot_start=NOW + timedelta(minutes=slot_offset))
    mark_search_dispatched(reserved.run.pk, now=NOW)
    assert settle_search_return(
        reserved.run.pk,
        raw_count=raw_count,
        normalized_count=min(raw_count, 3),
        truncated=False,
        now=NOW + timedelta(seconds=1),
    )
    reserved.run.refresh_from_db()
    assert reserved.run.confirmed_credits is None
    assert reserved.run.estimated_credits == expected
    budget = RareTypeSearchDailyBudget.objects.get()
    assert budget.search_credits_reserved == 0
    assert budget.search_credits_accounted == expected
    assert reserved.run.status == (
        RareTypeSearchRun.Status.EMPTY
        if raw_count == 0
        else RareTypeSearchRun.Status.RETURNED
    )


def test_same_slot_race_reserves_once_and_different_slots_share_daily_gate():
    query = _query("races")
    day_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

    def reserve(slot):
        close_old_connections()
        try:
            result = _reserve(
                slot_start=slot, query=query, daily_credit_limit=28800
            )
            return result.created, result.reason
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = list(pool.map(reserve, [day_start, day_start]))
    assert sorted(created for created, _ in same) == [False, True]
    assert RareTypeSearchDailyBudget.objects.get().search_credits_reserved == 300

    slots = [day_start + timedelta(minutes=15 * index) for index in range(1, 96)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        different = list(pool.map(reserve, slots))
    assert all(created for created, _ in different)
    assert RareTypeSearchRun.objects.count() == 96
    budget = RareTypeSearchDailyBudget.objects.get()
    assert budget.search_credits_reserved == 28800


def test_hit_batch_is_allowlisted_linkable_and_post_delete_preserves_audit():
    reservation = _reserve()
    mark_search_dispatched(reservation.run.pk, now=NOW)
    hits = persist_hit_batch(
        reservation.run.pk,
        [
            {
                "id": "provider-1",
                "text": "I joined Example AI",
                "lang": "en",
                "headers": {"Authorization": "Bearer secret"},
                "email": "private@example.com",
                "author": {
                    "id": "author-1",
                    "userName": "public_handle",
                    "name": "Public Name",
                    "description": "Public profile",
                    "private_phone": "+1-555-0100",
                },
            }
        ],
        now=NOW,
        raw_count=1,
    )
    assert len(hits) == 1
    hit = hits[0]
    assert hit.public_payload["author"] == {
        "id": "author-1",
        "userName": "public_handle",
        "name": "Public Name",
        "description": "Public profile",
    }
    assert "headers" not in hit.public_payload
    assert "email" not in hit.public_payload
    assert hit.source_query_hash == "a" * 64

    post = Post.objects.create(tweet_id="provider-1", text="saved")
    hit.post = post
    hit.save(update_fields=["post"])
    post.delete()
    hit.refresh_from_db()
    assert hit.post_id is None
    assert hit.provider_post_id == "provider-1"


def test_normalized_provider_result_is_primary_payload_contract_and_hash_is_semantic():
    provider = {
        "id": "normalized-1",
        "text": "I joined Example AI https://example.ai/announcement",
        "lang": "en",
        "createdAt": "Tue Sep 22 11:58:00 +0000 2026",
        "likeCount": 10,
        "retweetCount": 2,
        "author": {
            "id": "account-1",
            "userName": "builder",
            "name": "Builder Name",
            "description": "Building AI",
            "privatePhone": "+1-secret",
        },
        "quoted_tweet": {
            "id": "quote-1",
            "text": "Welcome to the team",
            "author": {"userName": "example_ai"},
        },
        "headers": {"Authorization": "Bearer secret"},
    }
    normalized = _normalize_tweet(provider)
    reservation = _reserve()
    mark_search_dispatched(reservation.run.pk, now=NOW)
    first = persist_hit_batch(
        reservation.run.pk,
        [normalized],
        raw_count=20,
        normalized_count=1,
        now=NOW,
    )[0]
    assert first.public_payload["author_id"] == "account-1"
    assert first.public_payload["author_handle"] == "builder"
    assert first.public_payload["author_description"] == "Building AI"
    assert first.public_payload["quoted_text"] == "Welcome to the team"
    assert first.public_payload["quoted_status_id"] == "quote-1"
    assert "https://example.ai/announcement" in first.public_payload["source_urls"]
    assert "headers" not in first.public_payload
    reservation.run.refresh_from_db()
    assert reservation.run.raw_result_count == 20
    assert reservation.run.normalized_result_count == 1
    assert reservation.run.has_coverage_gap is False
    assert reservation.run.complete_start == reservation.run.attempted_start

    second_run = _reserve(slot_start=NOW + timedelta(minutes=15), query=_query("hash"))
    mark_search_dispatched(second_run.run.pk, now=NOW + timedelta(minutes=15))
    metrics_changed = {**normalized, "like_count": 999, "retweet_count": 777}
    second = persist_hit_batch(
        second_run.run.pk,
        [metrics_changed],
        raw_count=1,
        normalized_count=1,
        now=NOW + timedelta(minutes=15),
    )[0]
    assert second.content_hash == first.content_hash

    third_run = _reserve(
        slot_start=NOW + timedelta(minutes=30), query=_query("hash-bio")
    )
    mark_search_dispatched(third_run.run.pk, now=NOW + timedelta(minutes=30))
    bio_changed = {**normalized, "author_description": "Now at Example AI"}
    third = persist_hit_batch(
        third_run.run.pk,
        [bio_changed],
        raw_count=1,
        normalized_count=1,
        now=NOW + timedelta(minutes=30),
    )[0]
    assert third.content_hash != first.content_hash


def test_unknown_raw_paid_volume_retains_full_reservation_but_saves_normalized_hits():
    reservation = _reserve()
    mark_search_dispatched(reservation.run.pk, now=NOW)
    hits = persist_hit_batch(
        reservation.run.pk,
        [{"id": f"normalized-{index}", "text": "saved"} for index in range(4)],
        raw_count=None,
        normalized_count=4,
        now=NOW,
    )
    assert len(hits) == 4
    reservation.run.refresh_from_db()
    assert reservation.run.status == RareTypeSearchRun.Status.USAGE_UNKNOWN
    assert reservation.run.raw_result_count is None
    assert reservation.run.normalized_result_count == 4
    assert reservation.run.estimated_credits is None
    assert RareTypeSearchDailyBudget.objects.get().search_credits_reserved == 300


def test_unknown_raw_volume_persistence_failure_is_visible_and_keeps_reservation():
    reservation = _reserve()
    mark_search_dispatched(reservation.run.pk, now=NOW)
    with pytest.raises(IntegrityError):
        persist_hit_batch(
            reservation.run.pk,
            [
                {"id": "duplicate", "text": "first"},
                {"id": "duplicate", "text": "second"},
            ],
            raw_count=None,
            normalized_count=2,
            now=NOW,
        )
    assert RareTypeSearchHit.objects.count() == 0
    reservation.run.refresh_from_db()
    assert reservation.run.status == RareTypeSearchRun.Status.USAGE_UNKNOWN
    assert reservation.run.error_code == "hit_persistence_failed"
    assert reservation.run.has_coverage_gap is True
    assert reservation.run.complete_start is None
    assert RareTypeSearchDailyBudget.objects.get().search_credits_reserved == 300


def test_serialization_failure_rolls_back_entire_batch_and_keeps_unknown_spend():
    reservation = _reserve()
    mark_search_dispatched(reservation.run.pk, now=NOW)
    malformed = {"author": {"id": {"private": "not-a-public-scalar"}}}
    with pytest.raises(HitSerializationError):
        persist_hit_batch(
            reservation.run.pk,
            [{"id": "good", "text": "ok"}, {"id": "bad", **malformed}],
            now=NOW,
            raw_count=2,
        )
    assert RareTypeSearchHit.objects.count() == 0
    reservation.run.refresh_from_db()
    assert reservation.run.status == RareTypeSearchRun.Status.FAILED
    assert reservation.run.error_code == "hit_serialization_failed"
    assert reservation.run.raw_result_count == 2
    assert reservation.run.estimated_credits == 30
    budget = RareTypeSearchDailyBudget.objects.get()
    assert budget.search_credits_reserved == 0
    assert budget.search_credits_accounted == 30


def test_payload_expiry_is_explicit_and_keeps_minimal_audit():
    reservation = _reserve()
    mark_search_dispatched(reservation.run.pk, now=NOW)
    hit = persist_hit_batch(
        reservation.run.pk,
        [{"id": "provider-expire", "text": "full available source text"}],
        now=NOW,
        raw_count=1,
    )[0]
    assert expire_hit_payloads(now=NOW + timedelta(days=31)) == 1
    hit.refresh_from_db()
    assert hit.public_payload == {}
    assert hit.original_text == ""
    assert hit.payload_expired_at is not None
    assert hit.gate_state == RareTypeSearchHit.GateState.EXPIRED_UNPROCESSED
    assert hit.provider_post_id == "provider-expire"
    assert hit.content_hash


def test_payload_expiry_expires_every_unresolved_state_but_preserves_completed_audit():
    reservation = _reserve()
    mark_search_dispatched(reservation.run.pk, now=NOW)
    hits = persist_hit_batch(
        reservation.run.pk,
        [
            {"id": "pending", "text": "one"},
            {"id": "failed", "text": "two"},
            {"id": "review", "text": "three"},
            {"id": "junk", "text": "four"},
            {"id": "kept", "text": "five"},
        ],
        raw_count=5,
        normalized_count=5,
        now=NOW,
    )
    states = [
        RareTypeSearchHit.GateState.DECISION_PENDING,
        RareTypeSearchHit.GateState.PROVIDER_FAILED,
        RareTypeSearchHit.GateState.REVIEW_NEEDED,
        RareTypeSearchHit.GateState.JUNK,
        RareTypeSearchHit.GateState.KEPT,
    ]
    for hit, state in zip(hits, states, strict=True):
        hit.gate_state = state
        hit.save(update_fields=["gate_state"])
    assert expire_hit_payloads(now=NOW + timedelta(days=31)) == 5
    actual = dict(
        RareTypeSearchHit.objects.values_list("provider_post_id", "gate_state")
    )
    assert actual == {
        "pending": "expired_unprocessed",
        "failed": "expired_unprocessed",
        "review": "expired_unprocessed",
        "junk": "junk",
        "kept": "kept",
    }


def test_decision_claim_is_single_owner_reuses_complete_and_versions_identity():
    kwargs = {
        "provider_post_id": "provider-1",
        "content_hash": "c" * 64,
        "model": "typesafe/jev-1.13-20260917",
        "question_version": "questions-v1",
        "threshold_version": "thresholds-v1",
        "now": NOW,
        "lease_seconds": 60,
    }

    def claim(owner):
        close_old_connections()
        try:
            result = claim_decision(owner=owner, **kwargs)
            return result.claimed, result.decision.pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ["worker-a", "worker-b"]))
    assert sorted(claimed for claimed, _ in claims) == [False, True]
    assert len({pk for _, pk in claims}) == 1
    decision = RareTypeDecision.objects.get()
    assert complete_decision(
        decision.pk,
        owner=decision.claim_owner,
        fence=decision.claim_fence,
        response_id="response-1",
        probabilities={"ai_related": 0.98, "personnel": 0.91},
        derived_types=["personnel_changes"],
        input_tokens=42,
        output_tokens=7,
        cost_usd=Decimal("0.0012"),
        latency_ms=220,
        now=NOW + timedelta(seconds=1),
    )
    reused = claim_decision(owner="worker-c", **kwargs)
    assert reused.reused is True
    assert reused.claimed is False
    assert RareTypeDecision.objects.count() == 1

    changed = claim_decision(
        owner="worker-c", **{**kwargs, "question_version": "questions-v2"}
    )
    assert changed.claimed is True
    assert RareTypeDecision.objects.count() == 2


def test_decision_errors_wait_15_minutes_and_exhaust_to_review_not_junk():
    claim = claim_decision(
        provider_post_id="provider-error",
        content_hash="d" * 64,
        model="jev",
        question_version="q1",
        threshold_version="t1",
        owner="worker-a",
        now=NOW,
        lease_seconds=60,
    )
    assert fail_decision(
        claim.decision.pk,
        owner="worker-a",
        fence=claim.decision.claim_fence,
        error_code="timeout",
        uncertain=True,
        now=NOW + timedelta(seconds=1),
    )
    claim.decision.refresh_from_db()
    assert claim.decision.status == RareTypeDecision.Status.PENDING
    assert claim.decision.next_attempt_at == NOW + timedelta(minutes=15, seconds=1)
    early = claim_decision(
        provider_post_id="provider-error",
        content_hash="d" * 64,
        model="jev",
        question_version="q1",
        threshold_version="t1",
        owner="worker-b",
        now=NOW + timedelta(minutes=14),
    )
    assert early.claimed is False
    retry = claim_decision(
        provider_post_id="provider-error",
        content_hash="d" * 64,
        model="jev",
        question_version="q1",
        threshold_version="t1",
        owner="worker-b",
        now=NOW + timedelta(minutes=16),
    )
    assert retry.claimed is True
    assert fail_decision(
        retry.decision.pk,
        owner="worker-b",
        fence=retry.decision.claim_fence,
        error_code="malformed",
        uncertain=True,
        now=NOW + timedelta(minutes=16, seconds=1),
    )
    retry.decision.refresh_from_db()
    assert retry.decision.status == RareTypeDecision.Status.REVIEW_NEEDED
    assert retry.decision.attempts == 2


def test_expired_short_lease_still_waits_until_next_15_minute_retry_slot():
    kwargs = {
        "provider_post_id": "lease-wait",
        "content_hash": "1" * 64,
        "model": "jev",
        "question_version": "q1",
        "threshold_version": "t1",
    }
    first = claim_decision(owner="worker-a", now=NOW, lease_seconds=60, **kwargs)
    assert first.claimed
    after_lease = claim_decision(
        owner="worker-b", now=NOW + timedelta(seconds=61), lease_seconds=60, **kwargs
    )
    assert after_lease.claimed is False
    assert after_lease.reason == "retry_not_due"
    next_slot = claim_decision(
        owner="worker-b", now=NOW + timedelta(minutes=15), lease_seconds=60, **kwargs
    )
    assert next_slot.claimed is True
    assert next_slot.decision.attempts == 2


def test_decimal_decision_budget_reserves_settles_and_retains_unknown_usage():
    reservation = _reserve()
    tiny = Decimal("0.000019992")
    assert reserve_decision_budget(reservation.run.pk, amount_usd=tiny)
    reservation.run.refresh_from_db()
    assert reservation.run.decision_usd_reserved == tiny
    assert settle_decision_budget(
        reservation.run.pk,
        reserved_usd=tiny,
        accounted_usd=Decimal("0.000018991"),
        confirmed_usd=Decimal("0.000018991"),
    )
    reservation.run.refresh_from_db()
    assert reservation.run.decision_usd_reserved == 0
    assert reservation.run.decision_usd_accounted == Decimal("0.000018991")
    assert reservation.run.decision_usd_confirmed == Decimal("0.000018991")

    unknown = Decimal("0.001000000")
    assert reserve_decision_budget(reservation.run.pk, amount_usd=unknown)
    reservation.run.refresh_from_db()
    assert reservation.run.decision_usd_reserved == unknown
    budget = RareTypeSearchDailyBudget.objects.get()
    assert budget.decision_usd_reserved == unknown


def test_database_enforces_hit_and_decision_identities():
    reservation = _reserve()
    hit = RareTypeSearchHit.objects.create(
        run=reservation.run,
        provider_post_id="same",
        content_hash="e" * 64,
        payload_expires_at=NOW + timedelta(days=30),
        source_query_hash="a" * 64,
        source_query_version="v1",
        source_window_start=NOW,
        source_window_end=NOW + timedelta(minutes=15),
        fetched_at=NOW,
    )
    assert hit.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeSearchHit.objects.create(
            run=reservation.run,
            provider_post_id="same",
            content_hash="f" * 64,
            payload_expires_at=NOW + timedelta(days=30),
            source_query_hash="a" * 64,
            source_query_version="v1",
            source_window_start=NOW,
            source_window_end=NOW + timedelta(minutes=15),
            fetched_at=NOW,
        )


def test_database_rejects_half_null_intervals_and_claims():
    reservation = _reserve()
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeSearchRun.objects.filter(pk=reservation.run.pk).update(
            raw_result_count=0
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeSearchRun.objects.filter(pk=reservation.run.pk).update(
            complete_start=NOW - timedelta(minutes=15), complete_end=None
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeSearchRun.objects.filter(pk=reservation.run.pk).update(
            has_coverage_gap=True,
            gap_start=NOW - timedelta(minutes=15),
            gap_end=None,
            gap_reason="malformed",
        )

    claim = claim_decision(
        provider_post_id="malformed-claim",
        content_hash="9" * 64,
        model="jev",
        question_version="q1",
        threshold_version="t1",
        owner="worker-a",
        now=NOW,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeDecision.objects.filter(pk=claim.decision.pk).update(
            claim_expires_at=None
        )


@pytest.mark.parametrize(
    "status, normalized_count",
    [
        (RareTypeSearchRun.Status.RETURNED, 1),
        (RareTypeSearchRun.Status.EMPTY, 0),
    ],
)
def test_database_rejects_null_raw_count_for_known_return_states(
    status, normalized_count
):
    reservation = _reserve()
    with pytest.raises(IntegrityError), transaction.atomic():
        RareTypeSearchRun.objects.filter(pk=reservation.run.pk).update(
            status=status,
            request_count=1,
            dispatched_at=NOW,
            returned_at=NOW,
            raw_result_count=None,
            normalized_result_count=normalized_count,
            estimated_credits=15,
        )


def test_z_additive_migration_preserves_populated_prior_schema():
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    old_target = [("core", "0044_merge_20260918_1344")]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    OldQuery = old_apps.get_model("core", "SearchQuery")
    OldPost = old_apps.get_model("core", "Post")
    OldQuery.objects.create(query_id="migration-preserved-query")
    OldPost.objects.create(tweet_id="migration-preserved-post", text="keep me")

    executor = MigrationExecutor(connection)
    current_targets = [
        node for node in executor.loader.graph.leaf_nodes() if node[0] == "core"
    ]
    executor.migrate(current_targets)
    assert SearchQuery.objects.filter(query_id="migration-preserved-query").exists()
    assert Post.objects.filter(
        tweet_id="migration-preserved-post", text="keep me"
    ).exists()
    assert RareTypeSearchRun.objects.count() == 0
