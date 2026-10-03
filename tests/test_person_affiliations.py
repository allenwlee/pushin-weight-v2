import pytest
from django.db import IntegrityError, transaction

from core.models import PersonBrandAffiliation, StaffCollectionWork
from core.staff_assets.dossier import dossier_records
from core.staff_assets.intake import ingest_record
from core.staff_assets.population import staff_population
from tests.test_staff_library import record

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def role(
    person, *, status="current", title="Research lead", affiliation_type="employment"
):
    import uuid

    return PersonBrandAffiliation.objects.create(
        person=person,
        brand_id="deepseek",
        affiliation_type=affiliation_type,
        observed_organization_name="DeepSeek",
        status=status,
        title_raw=title,
        claim_identity=uuid.uuid4().hex,
    )


def replace(old, new, **kwargs):
    from core.person_affiliations import replace_claim

    return replace_claim(
        old.pk, new.pk, reviewer="Allen", reason="Reviewed departure source", **kwargs
    )


def test_departure_updates_population_dossier_and_pending_work_together():
    intake, _ = ingest_record(record())
    old = intake.person.brand_affiliations.get()
    departure = role(intake.person, status="former")
    replace(old, departure)
    assert str(intake.person_id) not in staff_population(list_id=0)["people"]
    entry = dossier_records(brand_id="deepseek")[0]
    assert entry["scope"] == "history"
    assert len(entry["roles"]) == 1
    assert PersonBrandAffiliation.objects.filter(person=intake.person).count() == 2
    assert not StaffCollectionWork.objects.filter(
        person=intake.person, state="queued"
    ).exists()


def test_promotion_preserves_founder_and_other_jobs():
    intake, _ = ingest_record(record())
    old = intake.person.brand_affiliations.get()
    founder = role(intake.person, affiliation_type="founder", title="Founder")
    promotion = role(intake.person, title="研究主管")
    replace(old, promotion)
    from core.person_affiliations import active_claims

    assert set(
        active_claims().filter(person=intake.person).values_list("pk", flat=True)
    ) == {founder.pk, promotion.pk}
    assert dossier_records(brand_id="deepseek")[0]["scope"] == "current"
    queued = StaffCollectionWork.objects.filter(person=intake.person, state="queued")
    assert queued.exists()
    assert all(
        old.pk not in [r["id"] for r in work.context["roles"]] for work in queued
    )


def test_unreviewed_contradiction_does_not_automatically_replace_current_job():
    intake, _ = ingest_record(record())
    role(intake.person, status="former")
    assert dossier_records(brand_id="deepseek")[0]["scope"] == "current"
    assert len(dossier_records(brand_id="deepseek")[0]["roles"]) == 2


def test_return_to_employer_preserves_unknown_dates_and_review_chain():
    intake, _ = ingest_record(record())
    old = intake.person.brand_affiliations.get()
    left = role(intake.person, status="former")
    returned = role(intake.person, title="Returned researcher")
    replace(old, left)
    replace(left, returned)
    assert dossier_records(brand_id="deepseek")[0]["scope"] == "current"
    old.refresh_from_db()
    assert old.superseded_by_id == left.pk and old.start_date is None
    with pytest.raises(ValueError, match="cycle|replaced"):
        replace(returned, old)


def test_replacement_refuses_another_person_and_rolls_back():
    intake, _ = ingest_record(record())
    other, _ = ingest_record(record(source_key="other:person"))
    old = intake.person.brand_affiliations.get()
    new = other.person.brand_affiliations.get()
    with pytest.raises(ValueError, match="person|organization"):
        replace(old, new)
    old.refresh_from_db()
    assert old.superseded_by_id is None


def test_preview_is_read_only_and_repeat_review_is_idempotent():
    intake, _ = ingest_record(record())
    old = intake.person.brand_affiliations.get()
    new = role(intake.person, status="former")
    replace(old, new, apply=False)
    old.refresh_from_db()
    assert old.superseded_by_id is None
    replace(old, new)
    replace(old, new)
    old.refresh_from_db()
    assert old.superseded_by_id == new.pk


def test_person_intelligence_lists_only_active_employment_after_replacement():
    from core.intelligence_readers import person_intelligence

    intake, _ = ingest_record(record())
    person = intake.person
    current = person.brand_affiliations.get()
    pending = role(person, title="Unreviewed second role")
    replacement = role(person, status="former", title="Former researcher")
    replace(current, replacement)

    document = person_intelligence(person.pk)

    history_ids = {row["id"] for row in document["employment_history"]}
    assert history_ids == {pending.pk, replacement.pk}
    stored = {row["id"]: row for row in document["affiliations"]}
    assert stored[current.pk]["status"] == "current"
    assert stored[current.pk]["active"] is False
    assert stored[current.pk]["superseded_by"] == replacement.pk
    assert stored[pending.pk]["active"] is True
    assert stored[pending.pk]["review_status"] == "pending"
    assert stored[replacement.pk]["active"] is True


def test_database_rejects_cross_person_replacement():
    intake, _ = ingest_record(record())
    other, _ = ingest_record(record(source_key="other:person"))
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonBrandAffiliation.objects.filter(person=intake.person).update(
            superseded_by=other.person.brand_affiliations.get()
        )
