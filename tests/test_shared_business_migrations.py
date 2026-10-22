"""Historical-to-reference upgrades preserve source meaning and retry identity."""

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0135_rg4_business_catalogues_expand")
NAME_CUTOVER = ("core", "0136_rg4_person_name_kind_cutover")
BUSINESS_CUTOVER = ("core", "0137_rg4_affiliation_opportunity_references")
EVENT_KIND_CUTOVER = ("core", "0138_rg4_event_kind_reference")
RELEASE_CUTOVER = ("core", "0139_rg4_release_meaning_references")


def _temporarily_lift_old_kind_check(table, constraint):
    """Inject drift into only the isolated rehearsal schema, then restore it."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid=%s::regclass AND conname=%s",
            [table, constraint],
        )
        definition = cursor.fetchone()[0]
        cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")
    return f"ALTER TABLE {table} ADD CONSTRAINT {constraint} {definition}"


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_person_name_cutover_preserves_fingerprints_and_both_writer_generations(
    migration_rehearsal_schema,
):
    old = MigrationExecutor(connection).loader.project_state([BASE]).apps
    old.get_model("core", "Language").objects.get_or_create(code="und")
    old.get_model("core", "Locale").objects.get_or_create(
        code="und",
        defaults={"language_id": "und"},
    )
    person = old.get_model("core", "Person").objects.create()
    old_names = old.get_model("core", "PersonName")
    original = old_names.objects.create(
        person=person,
        full_name="Name from source",
        locale_id="und",
        name_type="professional",
        fingerprint="a" * 64,
    )
    unsupported = old_names.objects.create(
        person=person,
        full_name="Another source spelling",
        locale_id="und",
        name_type="not_registered",
        fingerprint="b" * 64,
    )
    before = list(old_names.objects.order_by("id").values())
    with pytest.raises(RuntimeError, match="Unmapped person name kinds"):
        MigrationExecutor(connection).migrate([NAME_CUTOVER])
    assert list(old_names.objects.order_by("id").values()) == before
    assert NAME_CUTOVER not in MigrationExecutor(connection).loader.applied_migrations

    # Remove only this deliberate failure fixture before rehearsing known input.
    unsupported.delete()
    before = old_names.objects.get(pk=original.pk)
    MigrationExecutor(connection).migrate([NAME_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([NAME_CUTOVER]).apps
    names = current.get_model("core", "PersonName")
    migrated = names.objects.get(pk=original.pk)
    assert migrated.name_type_reference.code == "professional"
    assert migrated.fingerprint == before.fingerprint
    assert migrated.full_name == before.full_name
    assert migrated.created_at == before.created_at
    assert migrated.updated_at == before.updated_at

    # A still-running preceding image supplies only the retired scalar.
    legacy = old_names.objects.create(
        person=person,
        full_name="Romanized spelling",
        locale_id="und",
        name_type="romanized",
        fingerprint="c" * 64,
    )
    assert names.objects.get(pk=legacy.pk).name_type_reference.code == "romanized"

    # The new production caller supplies only the FK; its hash keeps the exact
    # pre-cutover string serialization, so a retry returns the same name.
    from core.models import Person
    from core.person_names import digest, record_name

    live_person = Person.objects.get(pk=person.pk)
    kwargs = {
        "full_name": "New writer spelling",
        "language": "und",
        "name_type": "professional",
        "source_kind": "owner",
        "source_reference": "test:name-kind",
        "source_text": "New writer spelling",
        "collection_method": "manual",
    }
    created = record_name(live_person, **kwargs)
    assert record_name(live_person, **kwargs).pk == created.pk
    assert created.fingerprint == digest(
        {
            "full_name": kwargs["full_name"],
            "language": "und",
            "name_type": "professional",
            "origin": "source",
            "derived_from_id": None,
        }
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT name_type FROM people_names WHERE id=%s", [created.pk])
        assert cursor.fetchone() == ("professional",)
    with pytest.raises(IntegrityError), transaction.atomic():
        old_names.objects.filter(pk=original.pk).update(name_type="romanized")
    assert names.objects.get(pk=original.pk).fingerprint == "a" * 64


@pytest.mark.parametrize("migration_rehearsal_schema", [NAME_CUTOVER], indirect=True)
def test_affiliation_and_opportunity_cutover_refuses_unknowns_and_bridges_writers(
    migration_rehearsal_schema,
):
    from django.utils import timezone

    old = MigrationExecutor(connection).loader.project_state([NAME_CUTOVER]).apps
    old.get_model("core", "Brand").objects.create(nickname="rg4-kind-test")
    person = old.get_model("core", "Person").objects.create()
    affiliations = old.get_model("core", "PersonBrandAffiliation")
    opportunities = old.get_model("core", "Opportunity")
    affiliation = affiliations.objects.create(
        person=person, brand_id="rg4-kind-test", affiliation_type="employment",
        observed_organization_name="Source employer", claim_identity="a" * 64,
    )
    now = timezone.now()
    opportunity = opportunities.objects.create(
        brand_id="rg4-kind-test", source_url="https://example.test/source",
        sponsor_name="Source sponsor", opportunity_type="contest",
        action_type="submit", benefit_type="prize", opportunity_identity="b" * 64,
        first_seen_at=now, last_seen_at=now, content_hash="c" * 64,
        extraction_version="source-v1", raw_payload={"opportunity_type": "contest"},
    )
    restore_affiliation_check = _temporarily_lift_old_kind_check(
        "people_brand_affiliations", "ck_pba_affiliation_type"
    )
    bad_affiliation = affiliations.objects.create(
        person=person, brand_id="rg4-kind-test", affiliation_type="unmapped_kind",
        observed_organization_name="Source employer", claim_identity="d" * 64,
    )
    with pytest.raises(RuntimeError, match="Unmapped people_brand_affiliations"):
        MigrationExecutor(connection).migrate([BUSINESS_CUTOVER])
    assert BUSINESS_CUTOVER not in MigrationExecutor(connection).loader.applied_migrations
    assert affiliations.objects.get(pk=bad_affiliation.pk).affiliation_type == "unmapped_kind"
    bad_affiliation.delete()
    with connection.cursor() as cursor:
        cursor.execute(restore_affiliation_check)
    restore_opportunity_check = _temporarily_lift_old_kind_check(
        "opportunities", "ck_opportunities_type"
    )
    bad_opportunity = opportunities.objects.create(
        brand_id="rg4-kind-test", source_url="https://example.test/unknown",
        sponsor_name="Source sponsor", opportunity_type="unmapped_kind",
        action_type="submit", benefit_type="prize", opportunity_identity="e" * 64,
        first_seen_at=now, last_seen_at=now, content_hash="f" * 64,
        extraction_version="source-v1", raw_payload={"opportunity_type": "unmapped_kind"},
    )
    with pytest.raises(RuntimeError, match="Unmapped opportunities"):
        MigrationExecutor(connection).migrate([BUSINESS_CUTOVER])
    assert opportunities.objects.get(pk=bad_opportunity.pk).raw_payload == {
        "opportunity_type": "unmapped_kind"
    }
    bad_opportunity.delete()
    with connection.cursor() as cursor:
        cursor.execute(restore_opportunity_check)
    before_affiliation = affiliations.objects.get(pk=affiliation.pk)
    before_opportunity = opportunities.objects.get(pk=opportunity.pk)

    MigrationExecutor(connection).migrate([BUSINESS_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([BUSINESS_CUTOVER]).apps
    mapped_affiliation = current.get_model("core", "PersonBrandAffiliation").objects.get(
        pk=affiliation.pk
    )
    mapped_opportunity = current.get_model("core", "Opportunity").objects.get(
        pk=opportunity.pk
    )
    assert mapped_affiliation.affiliation_type_reference.code == "employment"
    assert mapped_opportunity.opportunity_type_reference.code == "contest"
    assert affiliations.objects.get(pk=affiliation.pk).claim_identity == before_affiliation.claim_identity
    assert opportunities.objects.get(pk=opportunity.pk).raw_payload == before_opportunity.raw_payload
    assert opportunities.objects.get(pk=opportunity.pk).content_hash == before_opportunity.content_hash

    # The previous image can still insert using its scalar fields during drain.
    legacy_affiliation = affiliations.objects.create(
        person=person, brand_id="rg4-kind-test", affiliation_type="founder",
        observed_organization_name="Source employer", claim_identity="1" * 64,
    )
    legacy_opportunity = opportunities.objects.create(
        brand_id="rg4-kind-test", source_url="https://example.test/legacy",
        sponsor_name="Source sponsor", opportunity_type="grant",
        action_type="submit", benefit_type="funding", opportunity_identity="2" * 64,
        first_seen_at=now, last_seen_at=now, content_hash="3" * 64,
        extraction_version="source-v1", raw_payload={"opportunity_type": "grant"},
    )
    assert current.get_model("core", "PersonBrandAffiliation").objects.get(
        pk=legacy_affiliation.pk
    ).affiliation_type_reference.code == "founder"
    assert current.get_model("core", "Opportunity").objects.get(
        pk=legacy_opportunity.pk
    ).opportunity_type_reference.code == "grant"

    # The new image supplies only the reference; the old column remains in sync.
    new_affiliation = current.get_model("core", "PersonBrandAffiliation").objects.create(
        person_id=person.pk, brand_id="rg4-kind-test",
        affiliation_type_reference_id=current.get_model("core", "AffiliationType").objects.get(
            code="advisor"
        ).pk,
        observed_organization_name="Source employer", claim_identity="4" * 64,
    )
    new_opportunity = current.get_model("core", "Opportunity").objects.create(
        brand_id="rg4-kind-test", source_url="https://example.test/new",
        sponsor_name="Source sponsor",
        opportunity_type_reference_id=current.get_model("core", "OpportunityType").objects.get(
            code="discount"
        ).pk,
        action_type="apply", benefit_type="discount", opportunity_identity="5" * 64,
        first_seen_at=now, last_seen_at=now, content_hash="6" * 64,
        extraction_version="source-v1", raw_payload={"opportunity_type": "discount"},
    )
    assert affiliations.objects.get(pk=new_affiliation.pk).affiliation_type == "advisor"
    assert opportunities.objects.get(pk=new_opportunity.pk).opportunity_type == "discount"


@pytest.mark.parametrize("migration_rehearsal_schema", [BUSINESS_CUTOVER], indirect=True)
def test_dossier_kind_cutover_preserves_atomic_identity_and_both_writer_generations(
    migration_rehearsal_schema,
):
    old = MigrationExecutor(connection).loader.project_state([BUSINESS_CUTOVER]).apps
    old_dossiers = old.get_model("core", "EventDossier")
    original = old_dossiers.objects.create(
        event_kind="model_release", identity_key="a" * 64
    )
    before = old_dossiers.objects.get(pk=original.pk)
    restore_check = _temporarily_lift_old_kind_check(
        "event_dossiers", "ck_ed_kind"
    )
    unsupported = old_dossiers.objects.create(
        event_kind="unmapped_kind", identity_key="b" * 64
    )
    with pytest.raises(RuntimeError, match="Unmapped dossier event kinds"):
        MigrationExecutor(connection).migrate([EVENT_KIND_CUTOVER])
    assert EVENT_KIND_CUTOVER not in MigrationExecutor(connection).loader.applied_migrations
    assert old_dossiers.objects.get(pk=unsupported.pk).event_kind == "unmapped_kind"
    unsupported.delete()
    with connection.cursor() as cursor:
        cursor.execute(restore_check)

    MigrationExecutor(connection).migrate([EVENT_KIND_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([EVENT_KIND_CUTOVER]).apps
    dossiers = current.get_model("core", "EventDossier")
    mapped = dossiers.objects.get(pk=original.pk)
    assert mapped.event_kind_reference.code == "model_release"
    assert mapped.identity_key == before.identity_key
    assert mapped.first_seen_at == before.first_seen_at
    assert mapped.last_seen_at == before.last_seen_at

    legacy = old_dossiers.objects.create(
        event_kind="personnel_change", identity_key="c" * 64
    )
    assert dossiers.objects.get(pk=legacy.pk).event_kind_reference.code == "personnel_change"
    current_kind = current.get_model("core", "EventKind").objects.get(
        code="model_release"
    )
    created = dossiers.objects.create(
        event_kind_reference_id=current_kind.pk, identity_key="d" * 64
    )
    assert old_dossiers.objects.get(pk=created.pk).event_kind == "model_release"

    with pytest.raises(IntegrityError), transaction.atomic():
        old_dossiers.objects.filter(pk=original.pk).update(event_kind="personnel_change")
    with pytest.raises(IntegrityError), transaction.atomic():
        dossiers.objects.filter(pk=original.pk).update(
            event_kind_reference_id=current.get_model("core", "EventKind")
            .objects.get(code="personnel_change").pk
        )
    assert dossiers.objects.get(pk=original.pk).event_kind_reference.code == "model_release"


@pytest.mark.parametrize("migration_rehearsal_schema", [EVENT_KIND_CUTOVER], indirect=True)
def test_release_meanings_map_populated_rows_and_keep_both_writer_generations(
    migration_rehearsal_schema,
):
    from django.utils import timezone

    old = MigrationExecutor(connection).loader.project_state([EVENT_KIND_CUTOVER]).apps
    brand = old.get_model("core", "Brand").objects.create(nickname="rg4-release-test")
    releases = old.get_model("core", "ModelRelease")
    details = old.get_model("core", "ModelReleaseDetail")
    dossiers = old.get_model("core", "EventDossier")
    reviews = old.get_model("core", "EventDossierReview")
    now = timezone.now()

    def make_release(*, channel, identity):
        return releases.objects.create(
            brand=brand, observed_model_name="Source model", version="v1",
            release_channel=channel, release_identity=identity,
            first_seen_at=now, last_seen_at=now, extraction_version="source-v1",
        )

    def make_detail(*, dossier_identity, input_hash, detail_model, values):
        # The dossier integrity trigger validates the selected review, source
        # claim and typed detail together when their transaction commits.
        with transaction.atomic():
            dossier = dossiers.objects.create(
                event_kind_reference_id=old.get_model("core", "EventKind")
                .objects.get(code="model_release").pk,
                identity_key=dossier_identity,
            )
            post = old.get_model("core", "Post").objects.create(
                tweet_id="source-" + input_hash, text="Release claim"
            )
            source = old.get_model("core", "EventDossierSource").objects.create(
                event_dossier=dossier, post=post, linked_at=now
            )
            claim = old.get_model("core", "EventDossierClaim").objects.create(
                event_dossier_source=source, claim_kind="announcement",
                scope_key="source", claim_hash=input_hash,
                extraction_version="source-v1", recorded_at=now,
                assertion_text="Announced", source_excerpt="Release claim",
                source_hash="f" * 64,
            )
            review = reviews.objects.create(
                event_dossier=dossier, revision=1, reviewed_at=now,
                evidence_cutoff_at=now, method_version="source-v1", actor="reviewer",
                reason="Source review", input_hash=input_hash,
                display_title="Source title", review_state="provisional",
            )
            old.get_model("core", "EventDossierReviewClaim").objects.create(
                review=review, claim=claim, disposition="accepted", reason="Direct source"
            )
            detail = detail_model.objects.create(
                review_id=review.pk, observed_name="Source model",
                native_identifier="source/model", **values
            )
            dossier.current_review_id = review.pk
            dossier.save(update_fields=["current_review"])
        return detail

    release = make_release(channel="preview", identity="a" * 64)
    detail = make_detail(
        dossier_identity="b" * 64, input_hash="c" * 64,
        detail_model=details,
        values={
            "release_channel": "beta", "availability_state": "available",
            "disclosure_state": "announced",
        },
    )
    before_release = releases.objects.get(pk=release.pk)
    before_detail = details.objects.get(pk=detail.pk)
    unknown = make_release(channel="unmapped_kind", identity="d" * 64)
    with pytest.raises(RuntimeError, match="Unmapped model_releases.release_channel"):
        MigrationExecutor(connection).migrate([RELEASE_CUTOVER])
    assert releases.objects.get(pk=unknown.pk).release_channel == "unmapped_kind"
    assert RELEASE_CUTOVER not in MigrationExecutor(connection).loader.applied_migrations
    unknown.delete()

    MigrationExecutor(connection).migrate([RELEASE_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([RELEASE_CUTOVER]).apps
    mapped_release = current.get_model("core", "ModelRelease").objects.get(pk=release.pk)
    mapped_detail = current.get_model("core", "ModelReleaseDetail").objects.get(pk=detail.pk)
    assert mapped_release.release_maturity_reference.code == "preview"
    assert mapped_detail.release_maturity_reference.code == "beta"
    assert mapped_detail.release_availability_reference.code == "available"
    assert mapped_detail.release_disclosure_reference.code == "announced"
    assert releases.objects.get(pk=release.pk).release_identity == before_release.release_identity
    assert details.objects.get(pk=detail.pk).native_identifier == before_detail.native_identifier
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid="
            "'model_release_details'::regclass AND tgname='ed_frozen'"
        )
        assert cursor.fetchone() == ("O",)
    with pytest.raises(IntegrityError), transaction.atomic():
        details.objects.filter(pk=detail.pk).update(disclosure_state="unannounced")

    legacy = make_release(channel="stable", identity="e" * 64)
    assert current.get_model("core", "ModelRelease").objects.get(
        pk=legacy.pk
    ).release_maturity_reference.code == "stable"
    new = current.get_model("core", "ModelRelease").objects.create(
        brand_id=brand.pk, observed_model_name="New writer", version="v2",
        release_maturity_reference_id=current.get_model("core", "ReleaseMaturity")
        .objects.get(code="stable").pk,
        release_identity="f" * 64, first_seen_at=now, last_seen_at=now,
        extraction_version="source-v1",
    )
    assert releases.objects.get(pk=new.pk).release_channel == "stable"

    new_detail = make_detail(
        dossier_identity="1" * 64, input_hash="2" * 64,
        detail_model=current.get_model("core", "ModelReleaseDetail"),
        values={
            "release_maturity_reference_id": current.get_model(
                "core", "ReleaseMaturity"
            ).objects.get(code="stable").pk,
            "release_availability_reference_id": current.get_model(
                "core", "ReleaseAvailabilityState"
            ).objects.get(code="public_test").pk,
            "release_disclosure_reference_id": current.get_model(
                "core", "ReleaseDisclosureState"
            ).objects.get(code="unannounced").pk,
        },
    )
    old_detail = details.objects.get(pk=new_detail.pk)
    assert (old_detail.release_channel, old_detail.availability_state,
            old_detail.disclosure_state) == (
        "stable", "public_test", "unannounced"
    )
