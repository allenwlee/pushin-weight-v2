from datetime import UTC, datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
OLD = [("core", "0082_collection_catalog_mappings")]
X_DETAILS = [("core", "0083_account_extensions")]


def historical_account(apps, identifier, source="x", **values):
    apps.get_model("core", "DataSource").objects.get_or_create(
        pk=source, defaults={"name": source, "source_type": "social"}
    )
    return apps.get_model("core", "Account").objects.create(
        data_source_id=source,
        external_identifier=identifier,
        normalized_identifier=identifier.casefold() if source == "hf" else identifier,
        author_id=identifier if source == "x" else None,
        identifier_kind="namespace" if source == "hf" else "provider_id",
        **values,
    )


@pytest.mark.usefixtures("isolated_migration_database")
def test_x_move_and_reverse_preserve_all_fields_and_snapshot():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    MigrationExecutor(connection).migrate(OLD)
    old = executor.loader.project_state(OLD).apps
    stamp = datetime(2026, 8, 1, tzinfo=UTC)
    account = historical_account(
        old,
        "migration-x",
        is_blue_verified=False,
        statuses_count=0,
        protected=False,
        account_based_in="Japan",
        account_based_in_fetched_at=stamp,
        username_changes_count=0,
        affiliate_label_description="Official affiliate",
    )
    historical_account(old, "SomePublisher", "hf")
    snapshot_model = old.get_model("core", "AccountProfileSnapshot")
    snapshot = snapshot_model.objects.create(
        account_id=account.pk,
        profile_hash="a" * 64,
        first_observed_at=stamp,
        last_observed_at=stamp,
        profile_data={"author_is_blue_verified": False},
    )
    evidence = snapshot_model.objects.get(pk=snapshot.pk).__dict__.copy()
    evidence.pop("_state")
    try:
        MigrationExecutor(connection).migrate(X_DETAILS)
        new = executor.loader.project_state(X_DETAILS).apps
        detail = new.get_model("core", "XAccountDetail").objects.get(pk=account.pk)
        names = [f.name for f in detail._meta.concrete_fields if f.name != "account"]
        assert len(names) == 33
        assert {n: getattr(detail, n) for n in names} == {
            n: getattr(account, n) for n in names
        }
        assert new.get_model("core", "XAccountDetail").objects.count() == 1
        assert new.get_model("core", "Account").objects.count() == 2
        actual = (
            new.get_model("core", "AccountProfileSnapshot")
            .objects.get(pk=snapshot.pk)
            .__dict__.copy()
        )
        actual.pop("_state")
        assert actual == evidence
        MigrationExecutor(connection).migrate(OLD)
        restored = old.get_model("core", "Account").objects.get(pk=account.pk)
        assert {n: getattr(restored, n) for n in names} == {
            n: getattr(account, n) for n in names
        }
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.usefixtures("isolated_migration_database")
def test_non_x_detail_evidence_refuses_migration_without_loss():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    MigrationExecutor(connection).migrate(OLD)
    old = executor.loader.project_state(OLD).apps
    account = historical_account(old, "Publisher", "hf", statuses_count=0)
    try:
        with pytest.raises(RuntimeError, match="Non-X"):
            MigrationExecutor(connection).migrate(X_DETAILS)
        assert (
            old.get_model("core", "Account").objects.get(pk=account.pk).statuses_count
            == 0
        )
        assert "x_account_details" not in connection.introspection.table_names()
    finally:
        old.get_model("core", "Account").objects.filter(pk=account.pk).update(
            statuses_count=None
        )
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.usefixtures("isolated_migration_database")
def test_hf_retirement_preserves_linked_and_pending_publishers_and_products():
    target = [("core", "0084_shared_publisher_accounts")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    MigrationExecutor(connection).migrate(X_DETAILS)
    old = executor.loader.project_state(X_DETAILS).apps
    company = old.get_model("core", "Company").objects.create(nickname="migration-lab")
    account = historical_account(
        old, "LinkedLab", "hf", provider_metadata={"independent": "keep"}
    )
    stamp = datetime(2026, 7, 1, tzinfo=UTC)
    Org = old.get_model("core", "HFOrg")
    linked = Org.objects.create(
        namespace="LinkedLab",
        company=company,
        account=account,
        confirmed=True,
        discovered_via="reviewed",
    )
    pending = Org.objects.create(
        namespace="PendingLab",
        company=company,
        confirmed=False,
        discovered_via="candidate",
    )
    Org.objects.all().update(added_at=stamp)
    products = [
        old.get_model("core", "Product").objects.create(
            repo_id=f"{org.pk}/Model", hf_org=org
        )
        for org in (linked, pending)
    ]
    try:
        MigrationExecutor(connection).migrate(target)
        new = executor.loader.project_state(target).apps
        assert "hf_orgs" not in connection.introspection.table_names()
        Account = new.get_model("core", "Account")
        Link = new.get_model("core", "CompanyAccount")
        existing = Account.objects.get(pk=account.pk)
        assert existing.provider_metadata["independent"] == "keep"
        assert (
            existing.provider_metadata["namespace_discovery_evidence"]["added_at"]
            == stamp.isoformat()
        )
        candidate = Account.objects.get(
            data_source_id="hf", normalized_identifier="pendinglab"
        )
        assert candidate.account_kind == "unknown"
        assert candidate.created_at is None
        assert candidate.first_seen_at == stamp
        for original, publisher, confirmed in zip(
            products, (existing, candidate), (True, False)
        ):
            moved = new.get_model("core", "Product").objects.get(pk=original.pk)
            assert moved.product_key == original.product_key
            assert moved.publisher_account_id == publisher.pk
            link = Link.objects.get(account_id=publisher.pk, company_id=company.pk)
            assert link.ownership_confirmed is confirmed
            assert link.added_at == stamp
        MigrationExecutor(connection).migrate(X_DETAILS)
        restored = old.get_model("core", "HFOrg")
        assert restored.objects.get(pk="LinkedLab").account_id == account.pk
        assert restored.objects.get(pk="PendingLab").account_id is None
        assert restored.objects.get(pk="PendingLab").confirmed is False
        assert restored.objects.get(pk="PendingLab").discovered_via == "candidate"
        assert restored.objects.get(pk="PendingLab").added_at == stamp
        assert (
            old.get_model("core", "Product").objects.get(pk=products[1].pk).hf_org_id
            == "PendingLab"
        )
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.usefixtures("isolated_migration_database")
def test_hf_identity_conflict_refuses_retirement_atomically():
    target = [("core", "0084_shared_publisher_accounts")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    MigrationExecutor(connection).migrate(X_DETAILS)
    old = executor.loader.project_state(X_DETAILS).apps
    company = old.get_model("core", "Company").objects.create(nickname="migration-lab")
    account = historical_account(old, "WrongNamespace", "hf")
    org = old.get_model("core", "HFOrg").objects.create(
        namespace="Publisher", company=company, account=account
    )
    try:
        with pytest.raises(RuntimeError, match="identity conflict"):
            MigrationExecutor(connection).migrate(target)
        assert "hf_orgs" in connection.introspection.table_names()
        assert (
            old.get_model("core", "HFOrg").objects.get(pk=org.pk).account_id
            == account.pk
        )
        assert "publisher_account_key" not in {
            c.name
            for c in connection.introspection.get_table_description(
                connection.cursor(), "products"
            )
        }
    finally:
        old.get_model("core", "HFOrg").objects.filter(pk=org.pk).update(account=None)
        MigrationExecutor(connection).migrate(latest)
