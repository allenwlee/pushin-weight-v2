import pytest

from core.models import Account, Company, CompanyAccount, DataSource
from core.publisher_accounts import get_publisher, register_publisher

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def publisher_source():
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )


def test_namespace_candidate_stays_unconfirmed_and_has_unknown_kind():
    company = Company.objects.create(nickname="publisher-fixture")
    publisher, _ = register_publisher(
        source="hf",
        identifier="MixedCase",
        company=company,
        discovered_via="https://fixture.example/discovery",
    )
    assert get_publisher(source="hf", identifier="mixedcase").pk == publisher.pk
    assert publisher.ownership_confirmed is False
    assert publisher.account.account_kind == "unknown"
    assert publisher.account.created_at is None
    with pytest.raises(CompanyAccount.DoesNotExist):
        get_publisher(source="hf", identifier="mixedcase", confirmed=True)


def test_registration_preserves_identity_and_review_on_repeat():
    company = Company.objects.create(nickname="publisher-fixture")
    publisher, _ = register_publisher(
        source="hf",
        identifier="Fixture",
        company=company,
        confirmed=True,
    )
    publisher.account.provider_metadata["unrelated"] = "kept"
    publisher.account.save(update_fields=["provider_metadata"])
    repeated, created = register_publisher(
        source="hf", identifier="fixture", company=company
    )
    assert not created
    assert repeated.account_id == publisher.account_id
    assert repeated.ownership_confirmed is True
    assert repeated.account.provider_metadata["unrelated"] == "kept"


def test_registration_refuses_conflicting_company_without_new_rows():
    company = Company.objects.create(nickname="publisher-fixture")
    other = Company.objects.create(nickname="publisher-other")
    register_publisher(source="hf", identifier="Fixture", company=company)
    with pytest.raises(ValueError, match="ownership"):
        register_publisher(source="hf", identifier="fixture", company=other)
    assert CompanyAccount.objects.count() == 1
    assert Account.objects.filter(data_source_id="hf").count() == 1
