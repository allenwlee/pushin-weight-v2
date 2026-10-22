"""Populated account-first and provider-first paths meet without losing evidence."""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from tests.test_account_extensions_migration import historical_account

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0082_collection_catalog_mappings")
ACCOUNTS = ("core", "0084_shared_publisher_accounts")
BATCHES = ("core", "0085_provider_batch_enrichment")
MERGE = ("core", "0086_merge_account_provider_batch")


@pytest.mark.parametrize("first", [ACCOUNTS, BATCHES], ids=["accounts-first", "batch-first"])
@pytest.mark.usefixtures("isolated_migration_database")
def test_populated_branches_merge_preserving_identity_and_paid_evidence(first):
    MigrationExecutor(connection).migrate([BASE])
    old = MigrationExecutor(connection).loader.project_state([BASE]).apps
    account = historical_account(old, "merge-x", statuses_count=17,
                                 account_based_in="Japan")
    profile = old.get_model("core", "AccountProfileSnapshot").objects.create(
        account_id=account.pk, profile_hash="a" * 64,
        first_observed_at=timezone.now(), last_observed_at=timezone.now(),
        profile_data={"statuses_count": 17},
    )
    profile_before = old.get_model("core", "AccountProfileSnapshot").objects.values().get(pk=profile.pk)
    company = old.get_model("core", "Company").objects.create(nickname="merge-lab")
    org = old.get_model("core", "HFOrg").objects.create(
        namespace="MergeLab", company=company, confirmed=True, discovered_via="reviewed",
    )
    product = old.get_model("core", "Product").objects.create(repo_id="MergeLab/Model", hf_org=org)
    authored = old.get_model("core", "OriginalContentRun").objects.create(
        source_cycle_id="merge-authored", window_days=7, facts_as_of=timezone.now(),
        packet_schema_version=1, snapshot={},
    )
    authored_call = old.get_model("core", "OriginalContentCall").objects.create(
        run=authored, stage="editor", request_identity="merge-authored-call",
        request_hash="b" * 64, reserved_at=timezone.now(), reserved_usd=Decimal("0.3"),
    )
    authored_before = old.get_model("core", "OriginalContentCall").objects.values().get(pk=authored_call.pk)
    # This proof stops at 0086. Today's registration helper reads later source
    # and job columns, so seed the relationship with this migration's models.
    definition = {"fixture": "account-provider-merge"}
    job = old.get_model("core", "CollectionJob").objects.create(
        job_key="merge-evidence", source_id="x", purpose="content",
        operation="x_backfill", mode="historical", state="ready",
        definition=definition,
        definition_sha256=hashlib.sha256(
            json.dumps(definition, sort_keys=True).encode()
        ).hexdigest(),
    )

    def create_group(apps):
        group = apps.get_model("core", "ProviderBatch").objects.create(
            source_collection_job_id=job.pk, source_definition_hash=job.definition_sha256,
            group_key="merge-group", transport="direct", cohort_hash="c" * 64,
            manifest_hash="d" * 64, provider="deepinfra", model="test-model",
            endpoint="/v1/chat/completions", request_profile="test-profile",
            deadline_at=timezone.now() + timedelta(hours=1), policy={"max_usd": "2"},
        )
        call = apps.get_model("core", "OriginalContentCall").objects.create(
            provider_batch_id=group.pk, stage="translation", batch_key="merge-request",
            request_identity="e" * 64, request_hash="f" * 64,
            reserved_at=timezone.now(), reserved_usd=Decimal("0.2"),
            member_post_ids=["merge-post"], import_state="pending",
        )
        return group.pk, apps.get_model("core", "OriginalContentCall").objects.values().get(pk=call.pk)

    MigrationExecutor(connection).migrate([first])
    if first == BATCHES:
        group_id, call_before = create_group(MigrationExecutor(connection).loader.project_state([BATCHES]).apps)
    MigrationExecutor(connection).migrate([MERGE])
    final = MigrationExecutor(connection).loader.project_state([MERGE]).apps
    if first == ACCOUNTS:
        group_id, call_before = create_group(final)

    def verify():
        Account = final.get_model("core", "Account")
        detail = final.get_model("core", "XAccountDetail").objects.get(pk=account.pk)
        assert detail.statuses_count == 17 and detail.account_based_in == "Japan"
        assert final.get_model("core", "AccountProfileSnapshot").objects.values().get(pk=profile.pk) == profile_before
        moved = final.get_model("core", "Product").objects.get(pk=product.pk)
        publisher = Account.objects.get(pk=moved.publisher_account_id)
        assert moved.product_key == product.product_key
        assert publisher.data_source_id == "hf" and publisher.normalized_identifier == "mergelab"
        assert final.get_model("core", "CompanyAccount").objects.get(
            account_id=publisher.pk, company_id=company.pk,
        ).ownership_confirmed
        assert final.get_model("core", "ProviderBatch").objects.get(pk=group_id).policy == {"max_usd": "2"}
        Call = final.get_model("core", "OriginalContentCall")
        assert Call.objects.values().get(pk=call_before["id"]) == call_before
        assert Call.objects.values(*authored_before).get(pk=authored_call.pk) == authored_before

    verify()
    # Reversing the empty merge changes only migration bookkeeping. Both
    # existing evidence-bearing branches stay applied and all data stays exact.
    MigrationExecutor(connection).migrate([ACCOUNTS, BATCHES])
    verify()
    MigrationExecutor(connection).migrate([MERGE])
    verify()
