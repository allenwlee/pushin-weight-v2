"""Source-only intake must not create collection work by itself."""

import uuid
from copy import deepcopy

import pytest

from core.models import StaffCollectionWork
from core.person_names import digest
from core.staff_assets.arrivals import catch_up, register_person
from core.staff_assets.intake import ingest_record
from tests.test_staff_library import record

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def source_only_record():
    data = record()
    for name in data["names"]:
        name.pop("selection", None)
        name.pop("review", None)
    person_id = uuid.uuid5(
        uuid.NAMESPACE_URL, "staff-library:source:" + data["source_key"]
    )
    role = deepcopy(data["affiliations"][0])
    source_url, evidence_text = role.pop("source_url"), role.pop("evidence_text")
    source_data = role.pop("source_data", {})
    role.pop("titles", [])
    role.setdefault("affiliation_type", "employment")
    role.setdefault("status", "unknown")
    role.setdefault("review_status", "pending")
    role.setdefault("observed_organization_name", role["brand_id"])
    data["collection_mode"] = "evidence_only"
    data["evidence_only"] = {
        "schema": "staff-evidence-only/v1",
        "claims": [
            {
                "claim_identity": digest([str(person_id), role]),
                "evidence_hash": digest([source_url, evidence_text, source_data]),
                "independent_before": False,
            }
        ],
    }
    return data


def test_source_only_intake_does_not_enqueue_even_after_catchup():
    data = source_only_record()
    intake, _ = ingest_record(data)
    assert not StaffCollectionWork.objects.exists()
    register_person(intake.person_id)
    catch_up(list_id="999999")
    assert not StaffCollectionWork.objects.exists()
    normal = record(source_key="independent:source", person_id=str(intake.person_id))
    normal["affiliations"][0]["source_url"] = "https://example.com/independent"
    ingest_record(normal)
    assert StaffCollectionWork.objects.filter(person_id=intake.person_id).exists()


def test_source_only_intake_rejects_unprepared_claim():
    data = source_only_record()
    data["evidence_only"]["claims"][0]["claim_identity"] = "0" * 64
    with pytest.raises(ValueError, match="prepared"):
        ingest_record(data)
    assert not StaffCollectionWork.objects.exists()


def test_source_only_evidence_does_not_requeue_independent_person():
    normal = record()
    original, _ = ingest_record(normal)
    before = list(
        StaffCollectionWork.objects.filter(person_id=original.person_id).values_list(
            "id", "fingerprint", "state"
        )
    )
    data = source_only_record()
    data["source_key"] = "source-only:second"
    data["person_id"] = str(original.person_id)
    data["affiliations"][0]["source_url"] = "https://example.com/other-source"
    role = deepcopy(data["affiliations"][0])
    source_url, evidence_text = role.pop("source_url"), role.pop("evidence_text")
    source_data = role.pop("source_data", {})
    role.pop("titles", [])
    role.setdefault("affiliation_type", "employment")
    role.setdefault("status", "unknown")
    role.setdefault("review_status", "pending")
    role.setdefault("observed_organization_name", role["brand_id"])
    data["evidence_only"]["claims"] = [
        {
            "claim_identity": digest([str(original.person_id), role]),
            "evidence_hash": digest([source_url, evidence_text, source_data]),
            "independent_before": True,
        }
    ]
    ingest_record(data)
    register_person(original.person_id)
    after = list(
        StaffCollectionWork.objects.filter(person_id=original.person_id).values_list(
            "id", "fingerprint", "state"
        )
    )
    assert after == before


def test_source_only_input_cannot_change_name_selection():
    data = source_only_record()
    data["names"][0]["selection"] = "primary"
    with pytest.raises(ValueError, match="selection"):
        ingest_record(data)
    assert not StaffCollectionWork.objects.exists()


def test_new_source_only_role_does_not_change_existing_work_context():
    from core.models import Brand

    original, _ = ingest_record(record())
    before = list(
        StaffCollectionWork.objects.filter(person_id=original.person_id).values_list(
            "id", "fingerprint", "state"
        )
    )
    Brand.objects.get_or_create(
        nickname="anthropic", defaults={"display_name": "Anthropic"}
    )
    data = source_only_record()
    data["source_key"] = "source-only:new-role"
    data["person_id"] = str(original.person_id)
    data["affiliations"][0]["brand_id"] = "anthropic"
    data["affiliations"][0]["source_url"] = "https://example.com/anthropic"
    role = deepcopy(data["affiliations"][0])
    source_url, evidence_text = role.pop("source_url"), role.pop("evidence_text")
    source_data = role.pop("source_data", {})
    role.pop("titles", [])
    role.setdefault("affiliation_type", "employment")
    role.setdefault("status", "current")
    role.setdefault("review_status", "pending")
    role.setdefault("observed_organization_name", role["brand_id"])
    data["evidence_only"]["claims"] = [
        {
            "claim_identity": digest([str(original.person_id), role]),
            "evidence_hash": digest([source_url, evidence_text, source_data]),
            "independent_before": False,
        }
    ]
    ingest_record(data)
    register_person(original.person_id)
    after = list(
        StaffCollectionWork.objects.filter(person_id=original.person_id).values_list(
            "id", "fingerprint", "state"
        )
    )
    assert after == before


def test_same_evidence_for_different_roles_preserves_independent_work():
    from core.models import Brand

    normal = record()
    original, _ = ingest_record(normal)
    before = list(
        StaffCollectionWork.objects.filter(person_id=original.person_id).values_list(
            "id", "fingerprint", "state"
        )
    )
    Brand.objects.get_or_create(
        nickname="another-lab", defaults={"display_name": "Another Lab"}
    )
    data = source_only_record()
    data["source_key"] = "source-only:same-evidence"
    data["person_id"] = str(original.person_id)
    data["affiliations"][0]["brand_id"] = "another-lab"
    role = deepcopy(data["affiliations"][0])
    url, evidence = role.pop("source_url"), role.pop("evidence_text")
    source_data = role.pop("source_data", {})
    role.pop("titles", [])
    role.setdefault("affiliation_type", "employment")
    role.setdefault("status", "unknown")
    role.setdefault("review_status", "pending")
    role.setdefault("observed_organization_name", role["brand_id"])
    data["evidence_only"]["claims"] = [
        {
            "claim_identity": digest([str(original.person_id), role]),
            "evidence_hash": digest([url, evidence, source_data]),
            "independent_before": False,
        }
    ]
    ingest_record(data)
    register_person(original.person_id)
    after = list(
        StaffCollectionWork.objects.filter(person_id=original.person_id).values_list(
            "id", "fingerprint", "state"
        )
    )
    assert after == before


@pytest.mark.parametrize("mutation", ["unknown_key", "duplicate", "stale_independence"])
def test_source_only_policy_fails_closed(mutation):
    data = source_only_record()
    if mutation == "unknown_key":
        data["evidence_only"]["extra"] = True
    elif mutation == "duplicate":
        data["evidence_only"]["claims"].append(dict(data["evidence_only"]["claims"][0]))
    else:
        data["evidence_only"]["claims"][0]["independent_before"] = True
    with pytest.raises(ValueError):
        ingest_record(data)
    assert not StaffCollectionWork.objects.exists()


def test_source_only_account_does_not_create_avatar_or_collection_work():
    from django.utils import timezone

    from core.models import Account, PersonAccount, PersonMedia
    from tests.person_factory import person_with_name

    person = person_with_name("Existing person")
    account = Account.objects.create(
        author_id="source-only-avatar",
        handle="sourceavatar",
        profile_picture="https://example.com/avatar.png",
    )
    PersonAccount.objects.create(
        person=person,
        account=account,
        resolution_status="confirmed",
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
    )
    data = source_only_record()
    data["person_id"] = str(person.pk)
    data["account_key"] = str(account.pk)
    role = deepcopy(data["affiliations"][0])
    source_url, evidence_text = role.pop("source_url"), role.pop("evidence_text")
    source_data = role.pop("source_data", {})
    role.pop("titles", [])
    role.setdefault("affiliation_type", "employment")
    role.setdefault("status", "current")
    role.setdefault("review_status", "pending")
    role.setdefault("observed_organization_name", role["brand_id"])
    data["evidence_only"]["claims"] = [
        {
            "claim_identity": digest([str(person.pk), role]),
            "evidence_hash": digest([source_url, evidence_text, source_data]),
            "independent_before": False,
        }
    ]
    ingest_record(data)
    catch_up(list_id="999999")
    assert not PersonMedia.objects.filter(person=person).exists()
    assert not StaffCollectionWork.objects.filter(person=person).exists()


def test_source_only_new_account_link_is_held_for_independent_person():
    from core.models import Account, PersonAccount, PersonMedia

    original, _ = ingest_record(record())
    before = list(
        StaffCollectionWork.objects.filter(person_id=original.person_id).values_list(
            "id", "fingerprint", "state"
        )
    )
    account = Account.objects.create(
        author_id="unlinked-source-avatar",
        handle="unlinked",
        profile_picture="https://example.com/avatar.png",
    )
    data = source_only_record()
    data["source_key"] = "source-only:unlinked-account"
    data["person_id"] = str(original.person_id)
    data["account_key"] = str(account.pk)
    intake, _ = ingest_record(data)
    assert intake.eligibility == "needs_review"
    assert not PersonAccount.objects.filter(
        person_id=original.person_id, account=account
    ).exists()
    catch_up(list_id="999999")
    assert not PersonMedia.objects.filter(
        person_id=original.person_id, original_url=account.profile_picture
    ).exists()
    assert (
        list(
            StaffCollectionWork.objects.filter(
                person_id=original.person_id
            ).values_list("id", "fingerprint", "state")
        )
        == before
    )
