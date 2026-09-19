"""Upgrade proof for candidate-backed person affiliations."""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

BEFORE = [("core", "0038_split_translation_synthesis_ja")]
AFTER = [("core", "0039_affiliation_candidate_and_integrity_guards")]


def test_migration_preserves_known_brand_rows_and_allows_candidate_rows():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Brand = old_apps.get_model("core", "Brand")
        Person = old_apps.get_model("core", "Person")
        Affiliation = old_apps.get_model("core", "PersonBrandAffiliation")
        brand = Brand.objects.create(nickname="migration-org", display_name="Org")
        person = Person.objects.create(id=uuid.uuid4(), display_name="Known Person")
        known = Affiliation.objects.create(
            person=person,
            brand=brand,
            affiliation_type="employment",
            observed_organization_name="Org",
            claim_identity="a" * 64,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps
        Candidate = apps.get_model("core", "BrandDiscoveryCandidate")
        Affiliation = apps.get_model("core", "PersonBrandAffiliation")
        known = Affiliation.objects.get(pk=known.pk)
        assert known.brand_id == "migration-org"
        assert known.brand_discovery_candidate_id is None

        now = timezone.now()
        candidate = Candidate.objects.create(
            observed_name="Candidate Org",
            candidate_identity="b" * 64,
            first_observed_at=now,
            last_observed_at=now,
        )
        candidate_row = Affiliation.objects.create(
            person_id=person.pk,
            brand_discovery_candidate_id=candidate.pk,
            affiliation_type="employment",
            observed_organization_name="Candidate Org",
            claim_identity="c" * 64,
        )
        assert candidate_row.brand_id is None

        with pytest.raises(IntegrityError), transaction.atomic():
            Affiliation.objects.create(
                person_id=person.pk,
                affiliation_type="employment",
                observed_organization_name="Missing Org",
                claim_identity="d" * 64,
            )
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
