"""Provider references preserve source spelling and reject another source's ID."""

from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from core.account_vocabulary import code_for
from core.models import Account, DataSource, XAccountDetail
from core.profile_snapshots import (
    profile_observation_from_account,
    profile_observation_from_post,
)
from core.source_vocabulary import reference_id
from monitor.cycle import _upsert_post

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_x_observation_creates_typed_reference_and_same_profile_code():
    result = Account.apply_observation(
        author_id="rg5-account",
        observed_author_id="rg5-account",
        source="post",
        observed_at=datetime(2026, 10, 25, tzinfo=UTC),
        candidates={"verified_type": "Business"},
        present_fields={"verified_type"},
    )
    account = result.account
    assert result.applied_fields == ("verified_type",)
    assert account.verified_type.data_source_id == "x"
    assert (
        profile_observation_from_account(account).profile_data["verified_type"]
        == "Business"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE x_account_details SET verified_type='' WHERE account_key=%s",
            [account.pk],
        )
    account.refresh_from_db()
    assert account.verified_type_id is not None
    assert code_for(account, "verified_type") == ""
    assert profile_observation_from_account(account).profile_data["verified_type"] == ""
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    other = reference_id("account_verification_types", "hf", "Business")
    with pytest.raises(IntegrityError), transaction.atomic():
        XAccountDetail.objects.filter(account=account).update(verified_type_id=other)


def test_post_profile_serializes_lookup_code_without_changing_source_shape():
    account = Account.objects.create(author_id="rg5-post")
    reference = reference_id("account_verification_types", "x", "Business")
    post, created = _upsert_post(
        {"id": "rg5-post", "author_verified_type": "Business"}, account
    )
    assert created and post.author_verified_type_id == reference
    observation = profile_observation_from_post(post)
    assert observation.profile_data["verified_type"] == "Business"
    assert observation.raw_profile_payload["author_verified_type"] == "Business"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT author_verified_type FROM posts WHERE tweet_id=%s", [post.pk]
        )
        assert cursor.fetchone() == ("Business",)


def test_profile_reference_prevents_parent_account_source_changes():
    from core.models import AccountProfileSnapshot

    for source in ("hf", "github"):
        DataSource.objects.get_or_create(
            pk=source, defaults={"name": source, "source_type": "model_adoption"}
        )
    account = Account.objects.create(
        data_source_id="hf", external_identifier="rg5-profile"
    )
    AccountProfileSnapshot.objects.create(
        account=account,
        profile_hash="a" * 64,
        first_observed_at=datetime(2026, 10, 25, tzinfo=UTC),
        last_observed_at=datetime(2026, 10, 25, tzinfo=UTC),
        first_source_kind="fixture",
        verified_type_id=reference_id("account_verification_types", "hf", "verified"),
    )
    with pytest.raises(IntegrityError, match="pinned"), transaction.atomic():
        Account.objects.filter(pk=account.pk).update(data_source_id="github")


def test_candidate_batch_reads_verification_catalogue_once():
    from core.official_company_candidates import candidate_priorities

    verification = reference_id("account_verification_types", "x", "Business")
    accounts = [
        Account.objects.create(
            author_id=f"rg5-batch-{i}", verified_type_id=verification
        )
        for i in range(8)
    ]
    accounts = list(Account.objects.filter(pk__in=[row.pk for row in accounts]))
    with CaptureQueriesContext(connection) as queries:
        priorities = candidate_priorities(accounts)
    assert set(priorities.values()) == {1}
    reads = [
        row["sql"]
        for row in queries
        if 'FROM "account_verification_types"' in row["sql"]
    ]
    assert len(reads) == 1
