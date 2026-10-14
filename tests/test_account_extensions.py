from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection, transaction

from core.models import Account, DataSource, XAccountDetail

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_x_details_keep_zero_false_and_shared_identity():
    account = Account.objects.create(
        author_id="x-extensions-1", is_blue_verified=False, statuses_count=0
    )
    detail = XAccountDetail.objects.get(account=account)
    assert detail.pk == account.pk
    assert detail.is_blue_verified is False
    assert detail.statuses_count == 0
    account.refresh_from_db()
    assert account.statuses_count == 0
    assert "statuses_count" not in {f.name for f in Account._meta.fields}


def test_split_write_rolls_back_parent_when_detail_save_fails():
    account = Account.objects.create(author_id="x-extensions-2", bio="before")
    account.bio = "after"
    account.verified_type = "Business"
    with patch.object(
        XAccountDetail, "save", side_effect=RuntimeError("detail failed")
    ):
        with pytest.raises(RuntimeError, match="detail failed"):
            account.save(update_fields=["bio", "verified_type"])
    account.refresh_from_db()
    assert account.bio == "before"
    assert account.verified_type is None


def test_details_reject_non_x_accounts_in_python_and_database():
    DataSource.objects.get_or_create(
        pk="github", defaults={"name": "GitHub", "source_type": "social"}
    )
    account = Account.objects.create(
        data_source_id="github", external_identifier="987654321"
    )
    account.statuses_count = 0
    with pytest.raises(ValueError, match="X"):
        account.save()
    with pytest.raises(IntegrityError), transaction.atomic():
        XAccountDetail.objects.create(account=account, statuses_count=0)


def test_parent_source_cannot_change_with_x_details():
    account = Account.objects.create(author_id="x-extensions-3", protected=False)
    DataSource.objects.get_or_create(
        pk="github", defaults={"name": "GitHub", "source_type": "social"}
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Account.objects.filter(pk=account.pk).update(
            data_source_id="github", author_id=None
        )


def test_detail_save_does_not_overwrite_fields_from_another_instance():
    account = Account.objects.create(author_id="x-extensions-4", statuses_count=1)
    other = Account.objects.get(pk=account.pk)
    other.statuses_count = 2
    other.save(update_fields=["statuses_count"])
    account.protected = False
    account.save(update_fields=["protected"])
    account.refresh_from_db()
    assert account.statuses_count == 2
    assert account.protected is False


def test_deferred_parent_loading_preserves_pending_detail_update():
    original = Account.objects.create(author_id="x-extensions-5")
    account = Account.objects.only("account_key").get(pk=original.pk)
    account.is_blue_verified = False
    account.save(update_fields=["is_blue_verified"])
    original.refresh_from_db()
    assert original.is_blue_verified is False


def test_current_details_share_parent_deletion_lifecycle_for_sql_writers():
    account = Account.objects.create(author_id="x-extensions-6", statuses_count=2)
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM accounts WHERE account_key = %s", [account.pk])
    assert not XAccountDetail.objects.filter(pk=account.pk).exists()
