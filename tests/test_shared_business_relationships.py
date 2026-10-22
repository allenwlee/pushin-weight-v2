"""Shared business meanings remain separate, constrained PostgreSQL identities."""

import pytest
from django.db import IntegrityError, connection, transaction

from core import models

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.mark.parametrize(
    "model_name",
    [
        "PersonNameType",
        "AffiliationType",
        "OpportunityType",
        "EventKind",
        "EventClaimKind",
        "ReleaseMaturity",
        "ReleaseAccessChannel",
        "ReleaseAvailabilityState",
        "ReleaseDisclosureState",
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
