from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


CALL_A = {
    "brand_id": "*",
    "call_id": "A",
    "call_kind": "list",
    "bucket": "",
    "query_id": "A",
}


def _call_state(identity=None):
    from core.models import CallState

    return CallState.objects.create(**(identity or CALL_A))


def _normalize(
    *,
    original_since,
    original_until,
    remaining_since=None,
    remaining_until=None,
    identity=None,
    pending_limit=8,
    quarantined_limit=4,
    state="pending",
):
    from core.models import HarvestBacklogWindow

    return HarvestBacklogWindow.objects.normalize_residual(
        call_identity=identity or CALL_A,
        original_since=original_since,
        original_until=original_until,
        remaining_since=remaining_since or original_since,
        remaining_until=remaining_until or original_until,
        reason_code="page_cap",
        pending_limit=pending_limit,
        quarantined_limit=quarantined_limit,
        state=state,
    )


def test_backlog_interval_constraints_and_metadata_only_contract():
    from core.models import HarvestBacklogWindow

    field_names = {field.name for field in HarvestBacklogWindow._meta.fields}
    assert {
        "brand_id",
        "call_id",
        "call_kind",
        "bucket",
        "query_id",
        "original_since",
        "original_until",
        "remaining_since",
        "remaining_until",
        "state",
        "attempts",
        "claim_owner",
        "claim_run_id",
        "claim_expires_at",
        "quarantine_reason",
    } <= field_names
    assert not field_names & {
        "tweet_body",
        "tweet_bodies",
        "post_text",
        "provider_payload",
        "raw_payload",
    }

    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        HarvestBacklogWindow.objects.create(
            brand_id="*",
            call_id="A",
            call_kind="list",
            bucket="",
            query_id="A",
            original_since=now,
            original_until=now - timedelta(minutes=1),
            remaining_since=now,
            remaining_until=now - timedelta(minutes=1),
            reason_code="page_cap",
        )


def test_backlog_claims_are_skip_locked_and_expired_claims_recover_pending():
    from core.models import HarvestBacklogWindow

    now = timezone.now()
    window = HarvestBacklogWindow.objects.create(
        brand_id="*",
        call_id="A",
        call_kind="list",
        bucket="",
        query_id="A",
        original_since=now - timedelta(hours=1),
        original_until=now,
        remaining_since=now - timedelta(hours=1),
        remaining_until=now,
        reason_code="page_cap",
    )

    claimed = HarvestBacklogWindow.objects.claim_next(
        owner="worker-1",
        run_id="run-1",
        now=now,
        claim_expires_at=now + timedelta(minutes=1),
    )
    assert claimed is not None
    assert claimed.pk == window.pk
    assert claimed.state == "claimed"
    assert claimed.attempts == 1

    recovered = HarvestBacklogWindow.objects.recover_expired_claims(
        now=now + timedelta(minutes=2)
    )
    assert recovered == 1
    window.refresh_from_db()
    assert window.state == "pending"
    assert window.claim_owner == ""
    assert window.claim_run_id == ""
    assert window.claim_expires_at is None


@pytest.mark.parametrize(
    ("original_offsets", "remaining_offsets"),
    [
        ((10, 0), (10, 0)),
        ((0, 10), (8, 2)),
        ((0, 10), (-1, 5)),
        ((0, 10), (5, 11)),
    ],
)
def test_normalize_residual_rejects_invalid_or_outside_bounds_without_writes(
    original_offsets, remaining_offsets
):
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    with pytest.raises(ValueError):
        _normalize(
            original_since=base + timedelta(seconds=original_offsets[0]),
            original_until=base + timedelta(seconds=original_offsets[1]),
            remaining_since=base + timedelta(seconds=remaining_offsets[0]),
            remaining_until=base + timedelta(seconds=remaining_offsets[1]),
        )
    assert HarvestBacklogWindow.objects.count() == 0


def test_normalize_residual_exact_duplicate_is_idempotent():
    from core.models import HarvestBacklogWindow

    _call_state()
    start = timezone.now()
    end = start + timedelta(minutes=5)

    created = _normalize(original_since=start, original_until=end)
    duplicate = _normalize(original_since=start, original_until=end)

    assert created.outcome == "created"
    assert created.ownership_recorded
    assert duplicate.outcome == "duplicate"
    assert duplicate.ownership_recorded
    assert duplicate.window_id == created.window_id
    assert HarvestBacklogWindow.objects.count() == 1


def test_normalize_residual_coalesces_overlapping_pending_windows():
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    first = _normalize(
        original_since=base,
        original_until=base + timedelta(seconds=10),
    )
    merged = _normalize(
        original_since=base + timedelta(seconds=5),
        original_until=base + timedelta(seconds=20),
    )

    assert first.outcome == "created"
    assert merged.outcome == "coalesced"
    assert merged.ownership_recorded
    assert merged.merged_count == 2
    row = HarvestBacklogWindow.objects.get()
    assert row.remaining_since == base
    assert row.remaining_until == base + timedelta(seconds=20)


def test_normalize_residual_coalesces_one_second_adjacency():
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    _normalize(
        original_since=base,
        original_until=base + timedelta(seconds=10),
    )
    result = _normalize(
        original_since=base + timedelta(seconds=11),
        original_until=base + timedelta(seconds=20),
    )

    assert result.outcome == "coalesced"
    assert HarvestBacklogWindow.objects.count() == 1
    row = HarvestBacklogWindow.objects.get()
    assert row.remaining_since == base
    assert row.remaining_until == base + timedelta(seconds=20)


def test_normalize_residual_keeps_full_call_identities_isolated():
    from core.models import HarvestBacklogWindow

    call_b = {**CALL_A, "brand_id": "deepseek", "call_id": "B1", "call_kind": "search", "query_id": "B1"}
    _call_state()
    _call_state(call_b)
    base = timezone.now()
    _normalize(original_since=base, original_until=base + timedelta(minutes=1))
    second = _normalize(
        identity=call_b,
        original_since=base,
        original_until=base + timedelta(minutes=1),
    )

    assert second.outcome == "created"
    assert HarvestBacklogWindow.objects.count() == 2


@pytest.mark.parametrize("protected_state", ["quarantined", "waived"])
def test_normalize_residual_never_merges_protected_ownership(protected_state):
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    protected = HarvestBacklogWindow.objects.create(
        **CALL_A,
        original_since=base,
        original_until=base + timedelta(seconds=10),
        remaining_since=base,
        remaining_until=base + timedelta(seconds=10),
        state=protected_state,
        reason_code="protected",
    )
    result = _normalize(
        original_since=base + timedelta(seconds=5),
        original_until=base + timedelta(seconds=20),
    )

    assert result.outcome == "created"
    protected.refresh_from_db()
    assert protected.state == protected_state
    assert protected.remaining_until == base + timedelta(seconds=10)
    assert HarvestBacklogWindow.objects.filter(state="pending").count() == 1


def test_normalize_residual_refuses_disjoint_work_at_pending_capacity():
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    _normalize(
        original_since=base,
        original_until=base + timedelta(seconds=10),
        pending_limit=1,
    )
    refused = _normalize(
        original_since=base + timedelta(seconds=20),
        original_until=base + timedelta(seconds=30),
        pending_limit=1,
    )

    assert refused.outcome == "capacity_refused"
    assert not refused.ownership_recorded
    assert refused.window_id is None
    assert HarvestBacklogWindow.objects.count() == 1


def test_normalize_residual_refuses_quarantined_work_at_capacity():
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    _normalize(
        original_since=base,
        original_until=base + timedelta(seconds=10),
        state="quarantined",
        quarantined_limit=1,
    )
    refused = _normalize(
        original_since=base + timedelta(seconds=20),
        original_until=base + timedelta(seconds=30),
        state="quarantined",
        quarantined_limit=1,
    )

    assert refused.outcome == "capacity_refused"
    assert not refused.ownership_recorded
    assert HarvestBacklogWindow.objects.count() == 1


def test_normalize_residual_coalesces_quarantined_adjacency():
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    _normalize(
        original_since=base,
        original_until=base + timedelta(seconds=10),
        state="quarantined",
    )
    merged = _normalize(
        original_since=base + timedelta(seconds=11),
        original_until=base + timedelta(seconds=20),
        state="quarantined",
    )

    assert merged.outcome == "coalesced"
    assert merged.ownership_recorded
    assert HarvestBacklogWindow.objects.filter(state="quarantined").count() == 1
    row = HarvestBacklogWindow.objects.get(state="quarantined")
    assert row.remaining_since == base
    assert row.remaining_until == base + timedelta(seconds=20)


def test_normalize_residual_claimed_work_counts_against_pending_capacity():
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    created = _normalize(
        original_since=base,
        original_until=base + timedelta(seconds=10),
        pending_limit=1,
    )
    HarvestBacklogWindow.objects.filter(pk=created.window_id).update(state="claimed")

    refused = _normalize(
        original_since=base + timedelta(seconds=20),
        original_until=base + timedelta(seconds=30),
        pending_limit=1,
    )

    assert refused.outcome == "capacity_refused"
    assert not refused.ownership_recorded
    assert HarvestBacklogWindow.objects.count() == 1


def test_normalize_residual_participates_in_callers_outer_rollback():
    from core.models import HarvestBacklogWindow

    _call_state()
    base = timezone.now()
    with pytest.raises(RuntimeError), transaction.atomic():
        _normalize(
            original_since=base,
            original_until=base + timedelta(minutes=1),
        )
        raise RuntimeError("simulate cursor-transfer rollback")

    assert HarvestBacklogWindow.objects.count() == 0


def test_membership_is_unique_by_list_and_author_and_keeps_account_fk():
    from core.models import Account, TwitterListMembership

    account = Account.objects.create(author_id="author-1", handle="official")
    now = timezone.now()
    TwitterListMembership.objects.create(
        list_id=123,
        account=account,
        active=True,
        first_seen_at=now,
        last_seen_at=now,
        source="call_a",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        TwitterListMembership.objects.create(
            list_id=123,
            account=account,
            active=False,
            first_seen_at=now,
            last_seen_at=now,
            source="snapshot",
        )

    account.delete()
    assert not TwitterListMembership.objects.filter(list_id=123).exists()


def test_enrichment_state_is_one_to_one_and_stores_no_payload():
    from core.models import Post, PostEnrichmentState

    post = Post.objects.create(tweet_id="tweet-1", text="not copied into state")
    state = PostEnrichmentState.objects.create(post=post)

    assert state.translation_status == "pending"
    assert state.classification_status == "pending"
    assert state.translation_attempts == 0
    assert state.classification_attempts == 0
    assert PostEnrichmentState.objects.filter(post=post).count() == 1
    field_names = {field.name for field in PostEnrichmentState._meta.fields}
    assert not field_names & {
        "post_text",
        "provider_payload",
        "model_output",
        "raw_payload",
    }


def _backfill_job(key: str):
    from core.models import BackfillJob

    now = timezone.now().replace(microsecond=0)
    return BackfillJob.objects.create(
        key=key,
        requested_since=now - timedelta(hours=2),
        requested_until=now,
        selection_mode=BackfillJob.SelectionMode.EXPLICIT,
        selection_params={},
        selected_intervals=[
            {
                "since": (now - timedelta(hours=2)).isoformat(),
                "until": now.isoformat(),
            }
        ],
        brand_filter=[],
        plan_signature="a" * 64,
    )


def _job_window(job, *, offset_minutes: int = 0):
    from core.models import HarvestBacklogWindow

    end = timezone.now().replace(microsecond=0) - timedelta(minutes=offset_minutes)
    start = end - timedelta(minutes=15)
    return HarvestBacklogWindow.objects.create(
        backfill_job=job,
        **CALL_A,
        original_since=start,
        original_until=end,
        remaining_since=start,
        remaining_until=end,
        reason_code="operator_backfill",
    )


def test_scheduled_and_job_claims_are_strictly_scoped():
    from core.models import HarvestBacklogWindow

    now = timezone.now()
    scheduled = HarvestBacklogWindow.objects.create(
        **CALL_A,
        original_since=now - timedelta(minutes=15),
        original_until=now,
        remaining_since=now - timedelta(minutes=15),
        remaining_until=now,
        reason_code="page_cap",
    )
    job = _backfill_job("scope-job")
    owned = _job_window(job, offset_minutes=30)

    scheduled_claim = HarvestBacklogWindow.objects.claim_next(
        owner="scheduled",
        run_id="scheduled-run",
        claim_expires_at=now + timedelta(minutes=1),
    )
    assert scheduled_claim.pk == scheduled.pk

    job_claim = HarvestBacklogWindow.objects.claim_next(
        owner="backfill",
        run_id="backfill-run",
        claim_expires_at=now + timedelta(minutes=1),
        backfill_job=job,
    )
    assert job_claim.pk == owned.pk


def test_identical_windows_are_unique_within_but_not_across_jobs():
    from core.models import HarvestBacklogWindow

    first_job = _backfill_job("first-job")
    second_job = _backfill_job("second-job")
    first = _job_window(first_job)
    HarvestBacklogWindow.objects.create(
        backfill_job=second_job,
        **CALL_A,
        original_since=first.original_since,
        original_until=first.original_until,
        remaining_since=first.remaining_since,
        remaining_until=first.remaining_until,
        reason_code="operator_backfill",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        HarvestBacklogWindow.objects.create(
            backfill_job=first_job,
            **CALL_A,
            original_since=first.original_since,
            original_until=first.original_until,
            remaining_since=first.remaining_since,
            remaining_until=first.remaining_until,
            reason_code="operator_backfill",
        )

    assert HarvestBacklogWindow.objects.count() == 2


def test_expired_claim_recovery_does_not_cross_ownership_scopes():
    from core.models import HarvestBacklogWindow

    now = timezone.now()
    job = _backfill_job("expired-job")
    owned = _job_window(job)
    HarvestBacklogWindow.objects.filter(pk=owned.pk).update(
        state="claimed",
        claim_owner="backfill",
        claim_run_id="old-run",
        claimed_at=now - timedelta(minutes=2),
        claim_expires_at=now - timedelta(minutes=1),
    )

    assert HarvestBacklogWindow.objects.recover_expired_claims(now=now) == 0
    owned.refresh_from_db()
    assert owned.state == "claimed"

    assert (
        HarvestBacklogWindow.objects.recover_expired_claims(
            now=now,
            backfill_job=job,
        )
        == 1
    )
    owned.refresh_from_db()
    assert owned.state == "pending"


def test_deleting_one_job_cascades_only_its_windows():
    from core.models import HarvestBacklogWindow

    first_job = _backfill_job("delete-first")
    second_job = _backfill_job("keep-second")
    first = _job_window(first_job, offset_minutes=30)
    second = _job_window(second_job)

    first_job.delete()

    assert not HarvestBacklogWindow.objects.filter(pk=first.pk).exists()
    assert HarvestBacklogWindow.objects.filter(pk=second.pk).exists()
