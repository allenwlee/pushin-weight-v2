"""Reviewed family relations keep native repository and model identities distinct."""

import json

import pytest
from django.core.management import call_command

from core.account_identity import upsert_account
from core.collection_identity import review_github_mapping
from core.models import (
    Brand,
    BrandAccount,
    DataSource,
    MeasurementSubject,
    Product,
    Role,
    SourceSubjectMapping,
)
from tests.collection_fixtures import with_database_models
from tests.product_factory import product_type_fields

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@with_database_models
def identities():
    DataSource.objects.create(id="github", name="GitHub", source_type="model_adoption")
    brand = Brand.objects.create(nickname="fixture-brand")
    account = upsert_account(
        source="github",
        external_identifier="42",
        handle="publisher",
        account_kind="organization",
    )
    role, _ = Role.objects.get_or_create(key="official")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    product = Product.objects.create(
        brand=brand, repo_id="HFPublisher/Model", **product_type_fields(Product, "llm-model")
    )
    subject = MeasurementSubject.objects.create(subject_kind="product", product=product)
    repo = {
        "id": 123,
        "full_name": "publisher/family",
        "private": False,
        "owner": {"id": 42, "login": "publisher"},
    }
    return brand, account, subject, repo


@with_database_models
def admit(subject, repo, **kwargs):
    return review_github_mapping(
        subject=subject,
        repo=repo,
        role="family_repository",
        version_selector="v2",
        evidence_url="https://github.com/publisher/family",
        reviewed_by="test-reviewer",
        **kwargs,
    )


def test_github_account_identity_requires_canonical_native_id():
    DataSource.objects.create(id="github", name="GitHub", source_type="model_adoption")
    with pytest.raises(ValueError, match="native"):
        upsert_account(
            source="github", external_identifier="publisher", handle="publisher"
        )


def test_family_repository_maps_to_two_models_without_duplicate_native_identity():
    brand, account, subject, repo = identities()
    first = admit(subject, repo)
    second_product = Product.objects.create(
        brand=brand, repo_id="HFPublisher/Model2", **product_type_fields(Product, "llm-model")
    )
    second_subject = MeasurementSubject.objects.create(
        subject_kind="product", product=second_product
    )
    second = admit(second_subject, repo)
    assert first.pk != second.pk
    assert first.normalized_identifier == second.normalized_identifier == "123"
    assert first.contract_id is None and first.purpose == "catalog"
    assert first.publisher_account_id == account.pk
    assert subject.product.repo_id == "HFPublisher/Model"
    assert admit(subject, repo).pk == first.pk


def test_rename_is_alias_and_preserves_mapping_hash():
    _, _, subject, repo = identities()
    first = admit(subject, repo)
    renamed = {**repo, "full_name": "publisher/renamed"}
    second = admit(subject, renamed)
    assert first.pk == second.pk and first.mapping_hash == second.mapping_hash
    assert set(second.identifier_metadata["aliases"]) == {
        "publisher/family",
        "publisher/renamed",
    }


@pytest.mark.parametrize("first_role,second_role", [
    ("dedicated_model", "dedicated_model"),
    ("dedicated_model", "dedicated_product"),
    ("dedicated_product", "dedicated_model"),
    ("dedicated_product", "family_repository"),
])
def test_dedicated_native_identity_cannot_be_claimed_by_another_product(first_role, second_role):
    brand, _, subject, repo = identities()
    review_github_mapping(
        subject=subject,
        repo=repo,
        role=first_role,
        evidence_url="https://github.com/publisher/family",
        reviewed_by="test",
    )
    product = Product.objects.create(brand=brand, repo_id="Other/Model")
    another = MeasurementSubject.objects.create(subject_kind="product", product=product)
    with pytest.raises(ValueError, match="conflict"):
        review_github_mapping(
            subject=another,
            repo=repo,
            role=second_role,
            version_selector="v2" if second_role == "family_repository" else None,
            evidence_url="https://github.com/publisher/family",
            reviewed_by="test",
        )
    assert SourceSubjectMapping.objects.count() == 1


def test_dependency_and_unknown_owner_remain_unadmitted():
    _, _, subject, repo = identities()
    with pytest.raises(ValueError, match="dependency"):
        review_github_mapping(
            subject=subject,
            repo=repo,
            role="dependency",
            version_selector=None,
            evidence_url="https://github.com/publisher/family",
            reviewed_by="test",
        )
    changed = {
        **repo,
        "owner": {"id": 99, "login": "other"},
        "full_name": "other/family",
    }
    with pytest.raises(ValueError, match="ownership"):
        admit(subject, changed)
    assert SourceSubjectMapping.objects.count() == 0


def test_owner_transfer_requires_review_and_preserves_old_pin():
    brand, _, subject, repo = identities()
    first = admit(subject, repo)
    new_account = upsert_account(
        source="github",
        external_identifier="99",
        handle="other",
        account_kind="organization",
    )
    BrandAccount.objects.create(
        brand=brand, account=new_account, role=Role.objects.get(pk="official")
    )
    transferred = {
        **repo,
        "owner": {"id": 99, "login": "other"},
        "full_name": "other/family",
    }
    with pytest.raises(ValueError, match="transfer"):
        admit(subject, transferred)
    second = admit(subject, transferred, allow_owner_transfer=True)
    assert second.pk == first.pk and second.mapping_hash != first.mapping_hash
    assert (
        second.identifier_metadata["ownership_history"][0]["mapping_hash"]
        == first.mapping_hash
    )


def test_employee_account_link_does_not_establish_official_publisher_ownership():
    _, account, subject, repo = identities()
    role, _ = Role.objects.get_or_create(key="researcher")
    BrandAccount.objects.filter(account=account).update(role=role)
    with pytest.raises(ValueError, match="ownership"):
        admit(subject, repo)


def test_review_command_is_inert_until_apply_and_survives_input_removal(tmp_path):
    _, _, subject, repo = identities()
    recording = tmp_path / "review.json"
    recording.write_text(
        json.dumps(
            [
                {
                    "subject_id": str(subject.pk),
                    "repo": repo,
                    "role": "family_repository",
                    "version_selector": "v2",
                    "evidence_url": "https://github.com/publisher/family",
                }
            ]
        )
    )
    call_command("review_collection_mapping", str(recording), reviewed_by="operator")
    assert SourceSubjectMapping.objects.count() == 0
    call_command(
        "review_collection_mapping", str(recording), reviewed_by="operator", apply=True
    )
    recording.unlink()
    assert SourceSubjectMapping.objects.get().normalized_identifier == "123"
