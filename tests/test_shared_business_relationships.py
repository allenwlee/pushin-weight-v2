"""Shared business meanings remain separate, constrained PostgreSQL identities."""

import pytest
from django.db import IntegrityError, connection, transaction

from core import models

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.mark.parametrize(
    "model_name",
    [
        "AffiliationType",
        "OpportunityType",
        "EventKind",
        "EventClaimKind",
        "ReleaseMaturity",
        "ReleaseAccessChannel",
        "ReleaseAvailabilityState",
        "PersonnelChangeType",
    ],
)
def test_business_meaning_cannot_be_rewritten_through_bulk_or_sql(model_name):
    catalogue = getattr(models, model_name)
    row = catalogue.objects.create(code="test_supported_meaning")
    with pytest.raises(IntegrityError), transaction.atomic():
        catalogue.objects.filter(pk=row.pk).update(code="different_meaning")
    table = connection.ops.quote_name(catalogue._meta.db_table)
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(f"UPDATE {table} SET id = id + 1000000 WHERE id = %s", [row.pk])
    with pytest.raises(IntegrityError), transaction.atomic():
        catalogue.objects.bulk_create([catalogue(code="not a canonical code")])
    row.refresh_from_db()
    assert row.code == "test_supported_meaning"


def test_same_spelling_has_distinct_business_owners():
    affiliation, _ = models.AffiliationType.objects.get_or_create(code="other")
    opportunity, _ = models.OpportunityType.objects.get_or_create(code="other")
    assert affiliation._meta.db_table != opportunity._meta.db_table
    with pytest.raises(IntegrityError), transaction.atomic():
        models.AffiliationType.objects.create(code=affiliation.code)


@pytest.mark.parametrize("domain", ["affiliation", "opportunity"])
def test_extracted_business_kind_uses_catalogue_without_changing_retry_identity(domain):
    from core.geolocation_evidence import source_evidence
    from core.intelligence_readers import opportunity_document, person_intelligence
    from core.targeted_extraction import _persist_opportunities, _persist_personnel
    from tests.test_targeted_extraction import _post

    post = _post("business-kind-" + domain)
    record = {"brand_id": "anthropic", "organization_name": "Anthropic"}
    if domain == "affiliation":
        record.update(
            person_name="Anna Wang", person_handle="a_nnawang",
            affiliation_type="employment", status="current",
        )
        persist, owner = _persist_personnel, models.PersonBrandAffiliation
        field, code = "affiliation_type_reference", "employment"
        identity = "claim_identity"
    else:
        record.update(
            opportunity_type="contest", action_type="submit", benefit_type="prize",
        )
        persist, owner = _persist_opportunities, models.Opportunity
        field, code = "opportunity_type_reference", "contest"
        identity = "opportunity_identity"

    persist(post, [record], "business-reference-test")
    row = owner.objects.get()
    assert getattr(row, field).code == code
    saved_identity = getattr(row, identity)
    persist(post, [record], "business-reference-test")
    assert owner.objects.count() == 1
    row.refresh_from_db()
    assert getattr(row, identity) == saved_identity
    if domain == "affiliation":
        assert person_intelligence(row.person_id)["affiliations"][0]["affiliation_type"] == code
        assert source_evidence(row.evidence.get()).extracted_claim_data == record
    else:
        assert opportunity_document(row.pk, as_of=post.fetched_at)["opportunity_type"] == code
        assert row.raw_payload == record

    # Bulk writes cannot bypass the shared identity. Force deferred FKs inside
    # the savepoint so a violation cannot escape into test teardown.
    with pytest.raises(IntegrityError), transaction.atomic():
        owner.objects.filter(pk=row.pk).update(**{field + "_id": -1})
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
