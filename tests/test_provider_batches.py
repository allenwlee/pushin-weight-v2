"""PostgreSQL ownership, bounded membership and durable inference admission."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.models import (
    CollectionObservation,
    CollectionRun,
    OriginalContentCall,
    OriginalContentRun,
    Post,
    PostEnrichmentState,
    ProviderBatch,
)
from tests.test_backfill_collection import ready_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def batch():
    job = ready_job()
    return ProviderBatch.objects.create(
        source_collection_job=job,
        group_key="group-1",
        transport="batch",
        source_definition_hash=job.definition_sha256,
        cohort_hash="a" * 64,
        manifest_hash="b" * 64,
        provider="deepinfra",
        model="test-model",
        endpoint="/v1/chat/completions",
        request_profile="test-profile",
        deadline_at=timezone.now() + timedelta(hours=72),
        policy={"max_usd": "5"},
    )


def call_values(batch):
    return {
        "provider_batch": batch,
        "stage": "translation",
        "batch_key": "request-1",
        "request_identity": "request-1",
        "request_hash": "c" * 64,
        "member_post_ids": ["1"],
        "import_state": "pending",
        "reserved_at": timezone.now(),
    }


def test_call_requires_exactly_one_real_owner_and_bounded_members(batch):
    for change in (
        {"provider_batch": None},
        {"member_post_ids": []},
        {"member_post_ids": [str(i) for i in range(21)]},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            OriginalContentCall.objects.create(**(call_values(batch) | change))
    row = OriginalContentCall.objects.create(**call_values(batch))
    assert row.run_id is None and row.provider_batch_id == batch.pk
    assert (
        OriginalContentCall.objects.filter(member_post_ids__contains=["1"]).get() == row
    )


def test_direct_group_cannot_invent_remote_batch_ids(batch):
    batch.transport = "direct"
    batch.provider_batch_id = "invented"
    with pytest.raises(IntegrityError), transaction.atomic():
        batch.save()
    batch.provider_batch_id = ""
    batch.save()


def test_post_membership_preserves_old_observation_constraints(batch):
    job = batch.source_collection_job
    post = Post.objects.create(tweet_id="1", text="Qwen", lang="en")
    run = CollectionRun.objects.create(
        job=job,
        ingestion_key="d" * 64,
        lease_token=uuid4(),
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    values = {
        "run": run,
        "post": post,
        "source_identifier": "1",
        "source_subject_kind": "post",
        "observation_key": "e" * 64,
    }
    CollectionObservation.objects.create(**values)
    for change in (
        {"post": None},
        {"source_identifier": "wrong"},
        {"source_subject_kind": "aggregate"},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            CollectionObservation.objects.create(
                **(values | change | {"observation_key": "f" * 64})
            )


def test_unknown_model_cost_is_retained_and_parent_is_not_an_extra_charge(batch):
    from monitor.original_content import budget_totals

    row = OriginalContentCall.objects.create(
        **call_values(batch),
        reserved_usd=Decimal("0.2"),
        budget_scope="test-enrichment",
        budget_day=timezone.now().date(),
    )
    assert row.actual_usd is None
    totals = budget_totals(scope="test-enrichment", day=timezone.now().date())
    assert totals["reserved_usd"] == Decimal("0.2")
    assert totals["calls"] == 1


def test_authored_owner_and_budget_readers_keep_original_behavior(batch):
    from monitor.original_content import budget_totals

    run = OriginalContentRun.objects.create(
        source_cycle_id="authored-1",
        window_days=7,
        facts_as_of=timezone.now(),
        packet_schema_version=1,
        snapshot={},
    )
    authored = OriginalContentCall.objects.create(
        run=run,
        stage="editor",
        request_identity="authored-call",
        request_hash="a" * 64,
        reserved_at=timezone.now(),
        reserved_usd=Decimal("0.3"),
        budget_day=timezone.now().date(),
    )
    assert authored.provider_batch_id is None and authored.member_post_ids == []
    assert budget_totals("headlines", timezone.now().date())["reserved_usd"] == Decimal(
        "0.3"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OriginalContentCall.objects.create(**(call_values(batch) | {"run": run}))


def test_old_runtime_can_insert_authored_call_without_new_columns():
    run = OriginalContentRun.objects.create(
        source_cycle_id="old-writer",
        window_days=7,
        facts_as_of=timezone.now(),
        packet_schema_version=1,
        snapshot={},
    )
    row = OriginalContentCall.objects.create(
        run=run,
        stage="editor",
        request_identity="new-writer",
        request_hash="a" * 64,
        reserved_at=timezone.now(),
    )
    excluded = {
        "id",
        "provider_batch",
        "member_post_ids",
        "import_state",
        "import_evidence",
    }
    columns = [
        f.column
        for f in OriginalContentCall._meta.concrete_fields
        if f.name not in excluded
    ]
    quote = connection.ops.quote_name
    expressions = [
        "%s" if c in {"request_identity", "batch_key"} else quote(c) for c in columns
    ]
    values = [
        "old-writer-row" if c == "request_identity" else "old-writer-batch"
        for c in columns
        if c in {"request_identity", "batch_key"}
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO original_content_calls ({', '.join(map(quote, columns))}) SELECT {', '.join(expressions)} FROM original_content_calls WHERE id=%s",
            [*values, row.pk],
        )
    old = OriginalContentCall.objects.get(request_identity="old-writer-row")
    assert old.member_post_ids == [] and old.import_state == "not_applicable"
    assert old.import_evidence == {} and old.provider_batch_id is None


@pytest.fixture
def admitted(batch):
    from core.provider_batches import (
        claim_batch,
        own_historical_posts,
        record_post_membership,
    )

    batch.policy = {
        "max_usd": "5",
        "max_control_requests": 5,
        "max_model_requests": 5,
        "max_attempts": 3,
        "prices": {"test-model": ["1", "1"]},
    }
    batch.save()
    job = batch.source_collection_job
    post = Post.objects.create(tweet_id="1", text="Qwen", lang="en")
    PostEnrichmentState.objects.create(post=post)
    run = CollectionRun.objects.create(
        job=job,
        ingestion_key="d" * 64,
        lease_token=uuid4(),
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    with transaction.atomic():
        record_post_membership(run, None, ["1"])
    own_historical_posts(job, ["1"])
    from core.provider_batches import post_snapshot

    request = {
        "snapshots": {"1": post_snapshot(post)},
        "hash": "c" * 64,
        "body": {"model": "test-model", "max_tokens": 100, "messages": []},
        "kind": "text",
        "context": {
            "stage": "translation",
            "post_ids": ["1"],
            "source_fingerprint": "d" * 64,
            "target_language": "ja",
            "chunk_index": 0,
        },
    }
    return batch, claim_batch(batch.pk, owner="first"), request


def test_failed_physical_retry_retains_prior_reservation_and_new_identity(admitted):
    from core.provider_batches import reserve_requests

    batch, claim, request = admitted
    first = reserve_requests(claim, [request])[0]
    first.state, first.error_code, first.import_state = (
        "failed",
        "pre_send:fixture",
        "error",
    )
    first.save()
    second = reserve_requests(claim, [request])[0]
    assert first.request_identity != second.request_identity
    assert second.provenance["attempt"] == 2
    assert (
        batch.calls.aggregate(
            total=__import__("django.db.models", fromlist=["Sum"]).Sum("reserved_usd")
        )["total"]
        == first.reserved_usd * 2
    )


def test_same_member_work_with_different_pack_hash_is_not_rebought(admitted):
    from core.provider_batches import BatchAdmissionError, reserve_requests

    _, claim, request = admitted
    reserve_requests(claim, [request])
    with pytest.raises(BatchAdmissionError, match="member_work_already_outstanding"):
        reserve_requests(claim, [request | {"hash": "e" * 64}])
    assert OriginalContentCall.objects.count() == 1


def test_admission_spend_and_control_limits_commit_before_http(admitted):
    from core.provider_batches import (
        BatchAdmissionError,
        control_start,
        reserve_requests,
    )

    batch, claim, request = admitted
    batch.policy["max_usd"] = "0.000001"
    batch.policy["max_control_requests"] = 0
    batch.save(update_fields=["policy"])
    with pytest.raises(BatchAdmissionError, match="campaign_allowance"):
        reserve_requests(claim, [request])
    with pytest.raises(BatchAdmissionError, match="control_allowance"):
        control_start(claim, "POST", "/batches")
    batch.refresh_from_db()
    assert batch.control_requests == 0 and not batch.calls.exists()


def test_expired_batch_claim_cannot_import_after_takeover(admitted):
    from core.provider_batches import StaleBatchClaim, claim_batch, import_response

    batch, old, _ = admitted
    ProviderBatch.objects.filter(pk=batch.pk).update(
        claimed_at=timezone.now() - timedelta(minutes=4),
        claim_expires_at=timezone.now() - timedelta(minutes=1),
    )
    new = claim_batch(batch.pk, owner="second")
    assert new.fence > old.fence
    with pytest.raises(StaleBatchClaim):
        import_response(old, {"custom_id": "irrelevant"})
