import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    Company,
    CompanyAccount,
    Post,
    Role,
)

pytestmark = pytest.mark.django_db


def test_accounts_are_provider_scoped_and_generic_links_use_uuid():
    from core.account_identity import upsert_account

    role = Role.objects.create(key="official")
    x = upsert_account(
        source="x",
        external_identifier="123",
        handle="deepseek",
        account_kind="organization",
    )
    hf = upsert_account(
        source="hf",
        external_identifier="123",
        handle="deepseek",
        account_kind="organization",
    )
    assert x.pk != hf.pk
    assert x.author_id == "123" and hf.author_id is None
    assert Account.x.get(handle="deepseek").pk == x.pk
    brand = Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    company = Company.objects.create(nickname="deepseek", display_name="DeepSeek")
    BrandAccount.objects.create(brand=brand, account=hf, role=role)
    CompanyAccount.objects.create(company=company, account=hf, role=role)
    assert brand.accounts.get().account_id == hf.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        Account.objects.create(
            data_source_id="hf",
            external_identifier="123",
            normalized_identifier="123",
            identifier_kind="namespace",
            account_kind="organization",
        )


def test_native_x_post_path_keeps_wire_id_and_rejects_hf_author():
    from django.db import connection

    from core.account_identity import upsert_account

    x = upsert_account(source="x", external_identifier="456", handle="x-account")
    hf = upsert_account(source="hf", external_identifier="hf-lab", handle="hf-lab")
    post = Post.objects.create(
        tweet_id="100", author=x, text="real caller fixture", created_at=timezone.now()
    )
    post.refresh_from_db()
    assert post.author_id == x.pk
    assert post.native_author_id == "456"
    with connection.cursor() as c:
        c.execute(
            "INSERT INTO posts (tweet_id,author_id,text,created_at,fetched_at) VALUES ('101','456','raw writer fixture',now(),now())"
        )
    assert Post.objects.get(pk="101").author_id == x.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        Post.objects.create(
            tweet_id="102",
            author=hf,
            text="invalid X author",
            created_at=timezone.now(),
        )


def test_generic_identity_requires_source_and_renames_preserve_uuid():
    from core.account_identity import upsert_account

    with pytest.raises(ValueError):
        upsert_account(source="", external_identifier="namespace", handle="name")
    first = upsert_account(source="hf", external_identifier="namespace", handle="first")
    renamed = upsert_account(
        source="hf", external_identifier="namespace", handle="second"
    )
    assert renamed.pk == first.pk
    assert renamed.normalized_handle == "second"


def test_legacy_staff_manifest_still_excludes_official_accounts():
    from core.account_identity import upsert_account
    from core.staff_assets.intake import ingest_record
    from tests.test_staff_library import record

    role = Role.objects.create(key="official")
    payload = record(account_id="official-native", source_key="legacy-official")
    account = upsert_account(
        source="x", external_identifier="official-native", handle="lab"
    )
    upsert_account(source="hf", external_identifier="official-native", handle="lab")
    BrandAccount.objects.create(brand_id="deepseek", account=account, role=role)
    intake, created = ingest_record(payload)
    assert intake.eligibility == "official_account"
    assert intake.person_id is None and not created


def test_unknown_generic_manifest_key_cannot_create_a_person():
    import uuid

    from core.person_identity import manifest_person
    from tests.test_staff_library import record

    with pytest.raises(ValueError, match="not stored"):
        manifest_person(record(account_key=str(uuid.uuid4())), create=True)


def test_indexes_and_native_on_conflict_survive_uuid_conversion():
    from django.db import connection

    from core.account_identity import upsert_account

    Role.objects.create(key="official")
    Brand.objects.create(nickname="lab")
    x = upsert_account(source="x", external_identifier="789", handle="x-lab")
    with connection.cursor() as c:
        for _ in range(2):
            c.execute(
                "INSERT INTO brands_accounts (brand_id,accounts_id,role_id,added_at) VALUES ('lab','789','official',now()) ON CONFLICT (brand_id,accounts_id) DO NOTHING"
            )
        c.execute(
            "SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indexrelid='idx_posts_created_cover'::regclass"
        )
        assert "author_account_key" in c.fetchone()[0]
        c.execute("SELECT to_regclass('uniq_accounts_handle_lower')")
        assert c.fetchone()[0] is None
    assert BrandAccount.objects.get().account_id == x.pk
