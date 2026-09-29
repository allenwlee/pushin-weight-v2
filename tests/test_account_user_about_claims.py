from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connections
from django.test import override_settings
from django.utils import timezone

from core.models import Account, AccountUserAboutClaim, Post
from monitor.twitterapi.user_about import (
    FetchBatchResult,
    FetchOutcome,
    FetchSelection,
    UserAboutObservation,
)
from monitor.twitterapi.user_about_service import (
    claim_account,
    due_new_account_selections,
    fetch_apply_user_about_batch,
    settle_outcome,
)
from x_monitor.twitterapi_credentials import TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_first_stored_post_controls_due_selection_for_precreated_account():
    watermark = timezone.now() - timedelta(minutes=5)
    due = Account.objects.create(author_id="101", handle="fresh")
    old = Account.objects.create(author_id="102", handle="old")
    Post.objects.create(tweet_id="1001", author=due)
    Post.objects.create(tweet_id="1002", author=old)
    Post.objects.filter(tweet_id="1002").update(
        fetched_at=watermark - timedelta(minutes=1)
    )
    Post.objects.create(tweet_id="1003", author=old)

    selections = due_new_account_selections(watermark=watermark, limit=10)

    assert [(item.author_id, item.handle) for item in selections] == [("101", "fresh")]


def test_claim_is_exclusive_and_success_empty_checkpoints():
    account = Account.objects.create(author_id="201", handle="empty")
    first = claim_account(author_id=account.author_id, owner="worker-one")

    assert first is not None
    assert claim_account(author_id=account.author_id, owner="worker-two") is None
    observed_at = timezone.now()
    settled = settle_outcome(
        author_id=account.author_id,
        owner="worker-one",
        outcome=FetchOutcome(
            author_id=account.author_id,
            observation=UserAboutObservation(
                author_id=account.author_id,
                candidates={
                    "account_based_in": "",
                    "country_code": None,
                    "based_in_region_key": None,
                    "account_based_in_fetched_at": observed_at,
                },
                present_fields={
                    "account_based_in",
                    "country_code",
                    "based_in_region_key",
                    "account_based_in_fetched_at",
                },
            ),
            reason="success",
            status_code=200,
            latency_ms=1,
        ),
    )

    account.refresh_from_db()
    assert settled is not None and not settled.identity_rejected
    assert account.account_based_in_fetched_at == observed_at
    assert claim_account(author_id=account.author_id, owner="worker-two") is None


def test_malformed_success_cannot_mark_account_fetched_without_checkpoint():
    account = Account.objects.create(author_id="203", handle="malformed")
    assert claim_account(author_id=account.author_id, owner="worker-one") is not None

    assert settle_outcome(
        author_id=account.author_id,
        owner="worker-one",
        outcome=FetchOutcome("203", None, "success", 200, 1),
    ) is None

    account.refresh_from_db()
    assert account.account_based_in_fetched_at is None
    assert account.user_about_claim.state == AccountUserAboutClaim.State.QUARANTINED
    assert account.user_about_claim.last_reason == "schema_drift"


def test_two_database_connections_cannot_claim_the_same_account():
    account = Account.objects.create(author_id="202", handle="race")
    barrier = Barrier(2)

    def contend(owner):
        barrier.wait()
        try:
            return claim_account(author_id=account.author_id, owner=owner) is not None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(contend, ("scheduled", "manual")))

    assert sorted(results) == [False, True]


def test_expired_active_claim_is_uncertain_and_stale_owner_cannot_write():
    account = Account.objects.create(author_id="301", handle="pending")
    claim_account(author_id=account.author_id, owner="worker-one", lease_seconds=1)
    later = timezone.now() + timedelta(seconds=2)

    assert (
        claim_account(author_id=account.author_id, owner="worker-two", now=later)
        is None
    )
    assert (
        settle_outcome(
            author_id=account.author_id,
            owner="worker-two",
            outcome=FetchOutcome(
                author_id=account.author_id,
                observation=None,
                reason="connection_error",
                status_code=None,
                latency_ms=1,
            ),
            now=later,
        )
        is None
    )


def test_retry_and_quarantine_claim_states_keep_failure_semantics():
    retry_account = Account.objects.create(author_id="302", handle="retry")
    quarantine_account = Account.objects.create(author_id="303", handle="quarantine")
    assert claim_account(author_id="302", owner="scheduled") is not None
    assert claim_account(author_id="303", owner="scheduled") is not None

    assert (
        settle_outcome(
            author_id="302",
            owner="scheduled",
            outcome=FetchOutcome("302", None, "connection_error", None, 1),
        )
        is None
    )
    assert (
        settle_outcome(
            author_id="303",
            owner="scheduled",
            outcome=FetchOutcome("303", None, "schema_drift", 200, 1),
        )
        is None
    )

    retry_claim = retry_account.user_about_claim
    quarantine_claim = quarantine_account.user_about_claim
    assert retry_claim.state == AccountUserAboutClaim.State.RETRY_DUE
    assert retry_claim.next_eligible_at > timezone.now()
    assert quarantine_claim.state == AccountUserAboutClaim.State.QUARANTINED
    assert quarantine_claim.next_eligible_at is None
    assert claim_account(author_id="302", owner="manual") is None
    assert claim_account(author_id="303", owner="manual") is None


def test_explicit_manual_refresh_reclaims_fetched_account_without_scheduled_due():
    account = Account.objects.create(
        author_id="304",
        handle="refresh",
        account_based_in_fetched_at=timezone.now() - timedelta(days=1),
    )
    claim = AccountUserAboutClaim.objects.create(
        account=account,
        state=AccountUserAboutClaim.State.FETCHED,
        owner="earlier",
    )

    assert claim_account(author_id="304", owner="scheduled") is None
    refreshed = claim_account(author_id="304", owner="manual", refresh=True)

    assert refreshed is not None
    assert refreshed.state == AccountUserAboutClaim.State.ACTIVE
    assert refreshed.owner == "manual"
    assert refreshed.admissions == claim.admissions + 1


def test_shared_batch_uses_real_claim_and_observation_gateway_with_fake_http():
    account = Account.objects.create(author_id="401", handle="captured")
    captured = []

    async def fake_fetch(selections, **kwargs):
        captured.append(
            ([(item.author_id, item.handle) for item in selections], kwargs)
        )
        observation = UserAboutObservation(
            author_id=account.author_id,
            candidates={
                "account_based_in": "",
                "country_code": None,
                "based_in_region_key": None,
                "account_based_in_fetched_at": timezone.now(),
            },
            present_fields={
                "account_based_in",
                "country_code",
                "based_in_region_key",
                "account_based_in_fetched_at",
            },
        )
        return FetchBatchResult(
            outcomes=[
                FetchOutcome(
                    author_id=account.author_id,
                    observation=observation,
                    reason="success",
                    status_code=200,
                    latency_ms=1,
                )
            ],
            attempts=1,
            retries=0,
            projected_credits=18,
            latencies_ms=[1],
            wall_seconds=0.01,
            stop_reason=None,
        )

    result = fetch_apply_user_about_batch(
        [FetchSelection(author_id=account.author_id, handle=account.handle)],
        api_key="test-key",
        rate_qps=1,
        concurrency=1,
        max_attempts=1,
        max_credits=18,
        max_wall_seconds=30,
        fetcher=fake_fetch,
    )

    account.refresh_from_db()
    assert captured[0][0] == [("401", "captured")]
    assert captured[0][1]["api_key"] == "test-key"
    assert result.batch.attempts == 1
    assert result.deferred_claims == 0
    assert account.account_based_in_fetched_at is not None


def test_unexpected_batch_identity_leaves_claim_uncertain():
    account = Account.objects.create(author_id="402", handle="requested")

    async def wrong_fetch(selections, **kwargs):
        return FetchBatchResult(
            outcomes=[
                FetchOutcome(
                    author_id="999",
                    observation=None,
                    reason="success",
                    status_code=200,
                    latency_ms=1,
                )
            ],
            attempts=1,
            retries=0,
            projected_credits=18,
            latencies_ms=[1],
            wall_seconds=0.01,
            stop_reason=None,
        )

    with pytest.raises(ValueError, match="invalid selection set"):
        fetch_apply_user_about_batch(
            [FetchSelection(author_id=account.author_id, handle=account.handle)],
            api_key="test-key",
            rate_qps=1,
            concurrency=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=30,
            fetcher=wrong_fetch,
        )

    account.refresh_from_db()
    assert account.account_based_in_fetched_at is None
    assert account.user_about_claim.state == "uncertain"


@override_settings(OLLIJA_STAGING_MODE=True)
def test_manual_command_defers_an_account_claimed_by_scheduled_lane(
    tmp_path, monkeypatch
):
    account = Account.objects.create(author_id="403", handle="overlap")
    eligible = Account.objects.create(author_id="404", handle="eligible")
    assert claim_account(author_id=account.author_id, owner="scheduled") is not None
    monkeypatch.setenv(TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV, "test-key")

    async def fetch_eligible(selections, **kwargs):
        assert [selection.author_id for selection in selections] == [eligible.author_id]
        return FetchBatchResult(
            outcomes=[
                FetchOutcome(
                    author_id=eligible.author_id,
                    observation=None,
                    reason="not_found",
                    status_code=404,
                    latency_ms=1,
                )
            ],
            attempts=1,
            retries=0,
            projected_credits=18,
            latencies_ms=[1],
            wall_seconds=0.01,
            stop_reason=None,
        )

    with (
        patch(
            "monitor.management.commands.backfill_account_based_in._required_migrations_applied",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in._is_authorized_executor",
            return_value=True,
        ),
        patch(
            "monitor.management.commands.backfill_account_based_in.fetch_user_about_batch",
            side_effect=fetch_eligible,
        ),
    ):
        call_command(
            "backfill_account_based_in",
            apply=True,
            limit=1,
            max_attempts=1,
            max_credits=18,
            max_wall_seconds=60,
            max_qps=1,
            provider_qps=1,
            json_report=str(tmp_path / "report.json"),
            markdown_report=str(tmp_path / "report.md"),
            stdout=StringIO(),
        )

    account.refresh_from_db()
    assert account.account_based_in_fetched_at is None
    assert AccountUserAboutClaim.objects.get(account=account).owner == "scheduled"
    assert '"attempted": 1' in (tmp_path / "report.json").read_text()
