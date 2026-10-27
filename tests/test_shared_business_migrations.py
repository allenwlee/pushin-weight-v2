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
PERSONNEL_CUTOVER = ("core", "0140_rg4_personnel_change_kind_reference")
CLAIM_CUTOVER = ("core", "0141_rg4_dossier_claim_kind_reference")
CLAIM_SCOPE_CUTOVER = ("core", "0142_rg4_scoped_claim_references")
CITIZENSHIP_CUTOVER = ("core", "0143_rg4_person_citizenship_evidence")
NATIONALITY_BRIDGE = ("core", "0144_rg4_nationality_old_writer_bridge")


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


@pytest.mark.parametrize("migration_rehearsal_schema", [RELEASE_CUTOVER], indirect=True)
def test_personnel_kind_cutover_keeps_completed_reviews_and_writer_compatibility(
    migration_rehearsal_schema,
):
    from django.utils import timezone

    old = MigrationExecutor(connection).loader.project_state([RELEASE_CUTOVER]).apps
    details = old.get_model("core", "PersonnelChangeDetail")
    now = timezone.now()

    def completed_detail(*, key, detail_model, values):
        with transaction.atomic():
            dossier = old.get_model("core", "EventDossier").objects.create(
                event_kind_reference_id=old.get_model("core", "EventKind")
                .objects.get(code="personnel_change").pk,
                identity_key=key * 64,
            )
            post = old.get_model("core", "Post").objects.create(
                tweet_id="personnel-source-" + key, text="Personnel claim"
            )
            source = old.get_model("core", "EventDossierSource").objects.create(
                event_dossier=dossier, post=post, linked_at=now
            )
            claim = old.get_model("core", "EventDossierClaim").objects.create(
                event_dossier_source=source, claim_kind="announcement",
                scope_key="source", claim_hash=key * 64,
                extraction_version="source-v1", recorded_at=now,
                assertion_text="Joined", source_excerpt="Personnel claim",
                source_hash="f" * 64,
            )
            review = old.get_model("core", "EventDossierReview").objects.create(
                event_dossier=dossier, revision=1, reviewed_at=now,
                evidence_cutoff_at=now, method_version="source-v1", actor="reviewer",
                reason="Source review", input_hash=key * 64,
                display_title="Personnel update", review_state="provisional",
            )
            old.get_model("core", "EventDossierReviewClaim").objects.create(
                review=review, claim=claim, disposition="accepted", reason="Direct source"
            )
            detail = detail_model.objects.create(
                review_id=review.pk, observed_person_name="Source person", **values
            )
            dossier.current_review_id = review.pk
            dossier.save(update_fields=["current_review"])
        return detail

    original = completed_detail(
        key="a", detail_model=details, values={"change_kind": "move"}
    )
    before = details.objects.get(pk=original.pk)
    MigrationExecutor(connection).migrate([PERSONNEL_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([PERSONNEL_CUTOVER]).apps
    mapped = current.get_model("core", "PersonnelChangeDetail").objects.get(
        pk=original.pk
    )
    assert mapped.change_type_reference.code == "move"
    assert details.objects.get(pk=original.pk).observed_person_name == before.observed_person_name
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid="
            "'personnel_change_details'::regclass AND tgname='ed_frozen'"
        )
        assert cursor.fetchone() == ("O",)
    with pytest.raises(IntegrityError), transaction.atomic():
        details.objects.filter(pk=original.pk).update(change_kind="join")

    legacy = completed_detail(
        key="b", detail_model=details, values={"change_kind": "leave"}
    )
    assert current.get_model("core", "PersonnelChangeDetail").objects.get(
        pk=legacy.pk
    ).change_type_reference.code == "leave"
    new = completed_detail(
        key="c", detail_model=current.get_model("core", "PersonnelChangeDetail"),
        values={
            "change_type_reference_id": current.get_model(
                "core", "PersonnelChangeType"
            ).objects.get(code="promotion").pk,
        },
    )
    assert details.objects.get(pk=new.pk).change_kind == "promotion"


@pytest.mark.parametrize("migration_rehearsal_schema", [PERSONNEL_CUTOVER], indirect=True)
def test_claim_kind_cutover_preserves_hashes_and_both_writer_generations(
    migration_rehearsal_schema,
):
    old = MigrationExecutor(connection).loader.project_state([PERSONNEL_CUTOVER]).apps
    dossier = old.get_model("core", "EventDossier").objects.create(
        event_kind_reference_id=old.get_model("core", "EventKind")
        .objects.get(code="model_release").pk,
        identity_key="a" * 64,
    )
    post = old.get_model("core", "Post").objects.create(
        tweet_id="claim-cutover-source", text="Repository appeared"
    )
    source = old.get_model("core", "EventDossierSource").objects.create(
        event_dossier=dossier, post=post
    )
    claims = old.get_model("core", "EventDossierClaim")

    def create_old(kind, marker):
        return claims.objects.create(
            event_dossier_source=source, claim_kind=kind,
            scope_key="repository", claim_hash=marker * 64,
            extraction_version="source-v1", assertion_text="Repository appeared",
            source_excerpt="Repository appeared", source_hash="f" * 64,
        )

    original = create_old("repository_created", "b")
    unsupported = create_old("unregistered_kind", "c")
    with pytest.raises(RuntimeError, match="Unmapped dossier claim kind"):
        MigrationExecutor(connection).migrate([CLAIM_CUTOVER])
    assert claims.objects.get(pk=original.pk).claim_hash == "b" * 64
    assert CLAIM_CUTOVER not in MigrationExecutor(connection).loader.applied_migrations
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid="
            "'event_dossier_claims'::regclass AND tgname='ed_frozen'"
        )
        assert cursor.fetchone() == ("O",)
        # Remove only the intentionally invalid rehearsal row. A real unknown
        # claim must be resolved by a reviewed catalogue amendment, not deleted.
        cursor.execute("ALTER TABLE event_dossier_claims DISABLE TRIGGER ed_frozen")
        cursor.execute(
            "DELETE FROM event_dossier_claims WHERE id=%s", [unsupported.pk]
        )
        cursor.execute("ALTER TABLE event_dossier_claims ENABLE TRIGGER ed_frozen")

    MigrationExecutor(connection).migrate([CLAIM_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state([CLAIM_CUTOVER]).apps
    mapped = current.get_model("core", "EventDossierClaim").objects.get(
        pk=original.pk
    )
    assert mapped.claim_kind_reference.code == "repository_created"
    assert mapped.claim_hash == original.claim_hash
    assert mapped.source_excerpt == original.source_excerpt
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid="
            "'event_dossier_claims'::regclass AND tgname='ed_frozen'"
        )
        assert cursor.fetchone() == ("O",)
    with pytest.raises(IntegrityError), transaction.atomic():
        claims.objects.filter(pk=original.pk).update(claim_kind="announcement")

    legacy = create_old("announcement", "d")
    assert current.get_model("core", "EventDossierClaim").objects.get(
        pk=legacy.pk
    ).claim_kind_reference.code == "announcement"
    new = current.get_model("core", "EventDossierClaim").objects.create(
        event_dossier_source_id=source.pk,
        claim_kind_reference_id=current.get_model("core", "EventClaimKind")
        .objects.get(code="availability").pk,
        scope_key="api", claim_hash="e" * 64,
        extraction_version="source-v1", assertion_text="API available",
        source_excerpt="Repository appeared", source_hash="f" * 64,
    )
    assert claims.objects.get(pk=new.pk).claim_kind == "availability"


@pytest.mark.parametrize("migration_rehearsal_schema", [CLAIM_CUTOVER], indirect=True)
def test_scoped_claim_cutover_keeps_timezone_and_source_evidence(
    migration_rehearsal_schema,
):
    old = MigrationExecutor(connection).loader.project_state([CLAIM_CUTOVER]).apps
    old.get_model("core", "TimeZone").objects.get_or_create(code="Asia/Tokyo")
    dossier = old.get_model("core", "EventDossier").objects.create(
        event_kind_reference_id=old.get_model("core", "EventKind")
        .objects.get(code="model_release").pk,
        identity_key="a" * 64,
    )
    post = old.get_model("core", "Post").objects.create(
        tweet_id="scoped-claim-source", text="Available in Japan"
    )
    source = old.get_model("core", "EventDossierSource").objects.create(
        event_dossier=dossier, post=post
    )
    kinds = old.get_model("core", "EventClaimKind")
    claims = old.get_model("core", "EventDossierClaim")

    def create_old(zone, marker):
        return claims.objects.create(
            event_dossier_source=source,
            claim_kind_reference_id=kinds.objects.get(code="availability").pk,
            event_timezone=zone, scope_key="JP", claim_hash=marker * 64,
            extraction_version="source-v1", assertion_text="Available in Japan",
            source_excerpt="Available in Japan", source_hash="f" * 64,
        )

    original = create_old("Asia/Tokyo", "b")
    unsupported = create_old("Unknown/Unregistered", "c")
    with pytest.raises(RuntimeError, match="Unmapped dossier claim timezone"):
        MigrationExecutor(connection).migrate([CLAIM_SCOPE_CUTOVER])
    assert claims.objects.get(pk=original.pk).event_timezone == "Asia/Tokyo"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid="
            "'event_dossier_claims'::regclass AND tgname='ed_frozen'"
        )
        assert cursor.fetchone() == ("O",)
        cursor.execute("ALTER TABLE event_dossier_claims DISABLE TRIGGER ed_frozen")
        cursor.execute(
            "DELETE FROM event_dossier_claims WHERE id=%s", [unsupported.pk]
        )
        cursor.execute("ALTER TABLE event_dossier_claims ENABLE TRIGGER ed_frozen")

    MigrationExecutor(connection).migrate([CLAIM_SCOPE_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state(
        [CLAIM_SCOPE_CUTOVER]
    ).apps
    mapped = current.get_model("core", "EventDossierClaim").objects.get(
        pk=original.pk
    )
    assert mapped.event_timezone_reference_id == "Asia/Tokyo"
    assert mapped.claim_hash == original.claim_hash
    assert mapped.source_excerpt == original.source_excerpt
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid="
            "'event_dossier_claims'::regclass AND tgname='ed_frozen'"
        )
        assert cursor.fetchone() == ("O",)
    legacy = create_old("Asia/Tokyo", "d")
    assert current.get_model("core", "EventDossierClaim").objects.get(
        pk=legacy.pk
    ).event_timezone_reference_id == "Asia/Tokyo"
    new = current.get_model("core", "EventDossierClaim").objects.create(
        event_dossier_source_id=source.pk,
        claim_kind_reference_id=kinds.objects.get(code="availability").pk,
        event_timezone_reference_id="Asia/Tokyo",
        release_access_channel_reference_id=current.get_model(
            "core", "ReleaseAccessChannel"
        ).objects.get(code="api").pk,
        scope_key="JP", claim_hash="e" * 64,
        extraction_version="source-v1", assertion_text="API available in Japan",
        source_excerpt="Available in Japan", source_hash="f" * 64,
    )
    assert claims.objects.get(pk=new.pk).event_timezone == "Asia/Tokyo"
    assert current.get_model("core", "EventDossierClaim").objects.get(
        pk=new.pk
    ).release_access_channel_reference.code == "api"


@pytest.mark.parametrize("migration_rehearsal_schema", [CLAIM_SCOPE_CUTOVER], indirect=True)
def test_citizenship_cutover_preserves_ambiguous_nationality_as_source_text(
    migration_rehearsal_schema,
):
    old = MigrationExecutor(connection).loader.project_state([CLAIM_SCOPE_CUTOVER]).apps
    person = old.get_model("core", "Person").objects.create(
        nationality="Japanese and American?"
    )
    absent = old.get_model("core", "Person").objects.create()
    MigrationExecutor(connection).migrate([CITIZENSHIP_CUTOVER])
    current = MigrationExecutor(connection).loader.project_state(
        [CITIZENSHIP_CUTOVER]
    ).apps
    retained = current.get_model("core", "PersonText").objects.get(
        person_id=person.pk,
        kind="reported_nationality",
        source_reference="legacy:people.nationality",
    )
    assert retained.text == "Japanese and American?"
    assert retained.origin == "unknown"
    assert retained.language == "und"
    assert current.get_model("core", "PersonCitizenship").objects.count() == 0
    assert current.get_model("core", "PersonText").objects.filter(
        person_id=absent.pk, kind="reported_nationality"
    ).count() == 0
    assert old.get_model("core", "Person").objects.get(
        pk=person.pk
    ).nationality == "Japanese and American?"

    MigrationExecutor(connection).migrate([NATIONALITY_BRIDGE])
    old_writer = old.get_model("core", "Person").objects.create(
        nationality="Reported Korean"
    )
    retained_rows = current.get_model("core", "PersonText").objects.filter(
        person_id=old_writer.pk, kind="reported_nationality"
    )
    assert list(retained_rows.values_list("text", flat=True)) == ["Reported Korean"]
    old_writer.nationality = "Reported Japanese"
    old_writer.save(update_fields=["nationality"])
    assert set(retained_rows.values_list("text", flat=True)) == {
        "Reported Korean", "Reported Japanese"
    }
    with pytest.raises(IntegrityError), transaction.atomic():
        old_writer.nationality = None
        old_writer.save(update_fields=["nationality"])


@pytest.mark.parametrize(
    "migration_rehearsal_schema", [("core", "0146_rg4_career_site_source_type")],
    indirect=True,
)
def test_selected_scalar_restoration_preserves_rows_and_completed_review(
    migration_rehearsal_schema,
):
    from django.utils import timezone

    baseline = ("core", "0146_rg4_career_site_source_type")
    target = ("core", "0147_rg4_restore_selected_scalar_fields")
    old = MigrationExecutor(connection).loader.project_state([baseline]).apps
    person = old.get_model("core", "Person").objects.create()
    old.get_model("core", "Language").objects.get_or_create(code="und")
    old.get_model("core", "Locale").objects.get_or_create(
        code="und", defaults={"language_id": "und"},
    )
    names = old.get_model("core", "PersonName")
    kind = old.get_model("core", "PersonNameType").objects.get(code="professional")
    original = names.objects.create(
        person=person, full_name="Original source name", locale_id="und",
        name_type_reference=kind, fingerprint="a" * 64,
    )
    now = timezone.now()
    with transaction.atomic():
        event = old.get_model("core", "EventDossier").objects.create(
            event_kind_reference=old.get_model("core", "EventKind").objects.get(
                code="model_release"
            ),
            identity_key="d" * 64,
        )
        post = old.get_model("core", "Post").objects.create(
            tweet_id="scalar-restoration", text="Original release claim"
        )
        source = old.get_model("core", "EventDossierSource").objects.create(
            event_dossier=event, post=post, linked_at=now
        )
        evidence = old.get_model("core", "EventDossierClaim").objects.create(
            event_dossier_source=source,
            claim_kind_reference=old.get_model("core", "EventClaimKind").objects.get(
                code="announcement"
            ),
            scope_key="source", claim_hash="e" * 64,
            extraction_version="historical-v1", recorded_at=now,
            assertion_text="Announced", source_excerpt="Original release claim",
            source_hash="f" * 64,
        )
        saved = old.get_model("core", "EventDossierReview").objects.create(
            event_dossier=event, revision=1, reviewed_at=now,
            evidence_cutoff_at=now, method_version="historical-v1",
            actor="reviewer", reason="Original source",
            input_hash="1" * 64, display_title="Source model",
            review_state="provisional",
        )
        old.get_model("core", "EventDossierReviewClaim").objects.create(
            review=saved, claim=evidence, disposition="accepted",
            reason="Direct source",
        )
        old.get_model("core", "ModelReleaseDetail").objects.create(
            review=saved, observed_name="Source model",
            native_identifier="source/model",
            release_maturity_reference=old.get_model(
                "core", "ReleaseMaturity"
            ).objects.get(code="unknown"),
            release_availability_reference=old.get_model(
                "core", "ReleaseAvailabilityState"
            ).objects.get(code="unknown"),
            release_disclosure_reference=old.get_model(
                "core", "ReleaseDisclosureState"
            ).objects.get(code="announced"),
        )
        event.current_review_id = saved.pk
        event.save(update_fields=["current_review"])

    def stored_rows():
        rows = []
        with connection.cursor() as cursor:
            for table, key in (
                ("people_names", "id"), ("model_release_details", "review_id"),
                ("event_dossier_reviews", "id"),
            ):
                cursor.execute(f"SELECT row_to_json(r)::text FROM {table} r ORDER BY {key}")
                rows.append(cursor.fetchall())
        return rows

    before = stored_rows()
    MigrationExecutor(connection).migrate([target])
    assert stored_rows() == before
    current = MigrationExecutor(connection).loader.project_state([target]).apps
    restored = current.get_model("core", "PersonName").objects.get(pk=original.pk)
    assert restored.name_type == "professional"
    assert restored.fingerprint == "a" * 64
    details = current.get_model("core", "ModelReleaseDetail")
    assert details.objects.get(pk=saved.pk).disclosure_state == "announced"
    # The preceding image remains usable throughout the cutover window.
    later = names.objects.create(
        person=person, full_name="Later preceding-image name", locale_id="und",
        name_type_reference=kind, fingerprint="b" * 64,
    )
    assert current.get_model("core", "PersonName").objects.get(pk=later.pk).name_type == "professional"
    assert names.objects.get(pk=original.pk).name_type_reference.code == "professional"
    with pytest.raises(IntegrityError), transaction.atomic():
        details.objects.filter(pk=saved.pk).update(disclosure_state="unannounced")
    with pytest.raises(IntegrityError), transaction.atomic():
        names.objects.filter(pk=original.pk).update(
            name_type_reference=old.get_model("core", "PersonNameType").objects.get(code="romanized")
        )
