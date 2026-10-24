"""Rehearse shared-place creation without advancing the shared public schema."""

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0147_rg4_restore_selected_scalar_fields")
TARGET = ("core", "0148_rg4_geolocation_owners")


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_new_geography_owners_import_beside_preserved_legacy_data(migration_rehearsal_schema):
    from core.geolocations import import_geonames_documents, load_pinned_geonames

    old = MigrationExecutor(connection).loader.project_state([BASE]).apps
    Country = old.get_model("core", "Country")
    before = list(Country.objects.order_by("pk").values())
    assert before
    MigrationExecutor(connection).migrate([TARGET])
    current = MigrationExecutor(connection).loader.project_state([TARGET]).apps
    assert current.get_model("core", "Geolocation").objects.count() == 0
    documents, metadata, roots = load_pinned_geonames(settings.BASE_DIR / "data" / "geonames")
    identities = import_geonames_documents(documents, country_metadata=metadata, selected_ids=roots)
    assert identities[203312] and identities[1835841]
    assert list(Country.objects.order_by("pk").values()) == before
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM geolocations WHERE geonames_id=ANY(%s)", [[203312, 1835841]])
        assert cursor.fetchone() == (2,)
        cursor.execute("SELECT confkey FROM pg_constraint WHERE conrelid='geolocation_alternate_names'::regclass AND confrelid='geolocations'::regclass")
        assert cursor.fetchall() == [([1],)]


@pytest.mark.parametrize("migration_rehearsal_schema", [("core", "0149_rg4_geolocation_claims")], indirect=True)
def test_populated_geography_mapping_preserves_source_and_policy(migration_rehearsal_schema):
    import hashlib
    import json

    from django.db import transaction
    from django.utils import timezone

    baseline = ("core", "0149_rg4_geolocation_claims")
    target = ("core", "0150_rg4_geolocation_mapping")
    old = MigrationExecutor(connection).loader.project_state([baseline]).apps
    model = lambda name: old.get_model("core", name)
    now = timezone.now()
    account = model("Account").objects.create(
        data_source_id="x", external_identifier="909090", normalized_identifier="909090",
        author_id="909090", location="San Francisco, CA", country_id="US",
    )
    model("XAccountDetail").objects.create(account_id=account.pk, account_based_in="Congo")
    post = model("Post").objects.create(tweet_id="geo-migration", author_id=account.pk, author_location="Springfield")
    source_profile = {"location": "India", "description": "Source profile"}
    profile_hash = hashlib.sha256(json.dumps(source_profile, sort_keys=True).encode()).hexdigest()
    snapshot = model("AccountProfileSnapshot").objects.create(
        account_id=account.pk, profile_hash=profile_hash, first_observed_at=now, last_observed_at=now,
        first_source_kind="post", first_source_post_id=post.pk, location="India", profile_data=source_profile,
    )
    company = model("Company").objects.create(nickname="geo-test", hq_country_reference_id="JP")
    brand = model("Brand").objects.create(nickname="geo-test", display_name="Geo Test")
    person = model("Person").objects.create()
    affiliation = model("PersonBrandAffiliation").objects.create(
        person_id=person.pk, brand_id=brand.pk,
        affiliation_type_reference_id=model("AffiliationType").objects.get(code="employment").pk,
        location="India", claim_identity="geography-migration-claim",
    )
    text = model("PersonText").objects.create(
        person_id=person.pk, kind="reported_nationality", language="en", text="Japanese citizen",
        source_reference="https://example.test/bio", version_hash="f" * 64, observed_at=now, origin="source",
    )
    with transaction.atomic():
        citizenship = model("PersonCitizenship").objects.create(person_id=person.pk, country_id="JP", is_primary=True)
        evidence = model("PersonCitizenshipEvidence").objects.create(citizenship=citizenship, person_text=text)
    source_locations = [{"city": None, "country": "India", "admin_area": None}, "Springfield"]
    job = model("JobListing").objects.create(
        brand_id=brand.pk, hiring_organization="Geo Test", title="Role", listing_identity="migration-location-job",
        first_seen_at=now, last_seen_at=now, locations=source_locations, locations_raw="India; Springfield",
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_class WHERE relnamespace=current_schema()::regnamespace AND relkind='r'")
        table_count = cursor.fetchone()[0]
    MigrationExecutor(connection).migrate([target])
    current = MigrationExecutor(connection).loader.project_state([target]).apps
    places = dict(current.get_model("core", "Geolocation").objects.values_list("geonames_id", "pk"))
    for row, field, external in (
        (account, "profile_location_id", 5391959), (account, "based_in_location_id", 203312),
        (post, "author_geolocation_id", None), (snapshot, "geolocation_id", 1269750),
        (company, "hq_geolocation_id", 1861060), (affiliation, "geolocation_id", 1269750),
        (citizenship, "geolocation_id", 1861060),
    ):
        row.refresh_from_db()
        assert getattr(row, field) == places.get(external)
    assert account.location == "San Francisco, CA" and post.author_location == "Springfield"
    assert snapshot.profile_data == source_profile and snapshot.profile_hash == profile_hash
    assert model("PersonCitizenshipEvidence").objects.get(pk=evidence.pk).person_text_id == text.pk
    job.refresh_from_db()
    assert job.locations == source_locations and job.locations_raw == "India; Springfield"
    occurrences = list(current.get_model("core", "JobListingLocation").objects.filter(listing_id=job.pk).order_by("ordinal"))
    assert [row.geolocation_id for row in occurrences] == [places[1269750], None]
    assert all(row.observed_at is None for row in occurrences)
    captured = json.loads(bytes(occurrences[0].source_archive.body))
    assert captured["locations"] == source_locations
    taiwan = current.get_model("core", "Geolocation").objects.get(geonames_id=1668284)
    assert taiwan.current_policy.display_parent.geonames_id == 1814991
    assert taiwan.current_policy.flag_mode == 1 and taiwan.current_policy.label_mode == 1
    assert taiwan.current_policy.country_attribution == 0
    assert current.get_model("core", "AccountBasedInMapping").objects.get(value="East Asia").geolocation_id == places[7729894]
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_class WHERE relnamespace=current_schema()::regnamespace AND relkind='r'")
        assert cursor.fetchone()[0] == table_count  # Source projections add no tables.


@pytest.mark.parametrize("migration_rehearsal_schema", [("core", "0156_rg4_unknown_job_location_observations")], indirect=True)
def test_reference_cutover_catches_late_old_writes_and_keeps_source(migration_rehearsal_schema):
    from django.utils import timezone

    baseline = ("core", "0156_rg4_unknown_job_location_observations")
    target = ("core", "0157_rg4_geolocation_reference_cutover")
    old = MigrationExecutor(connection).loader.project_state([baseline]).apps
    places = dict(old.get_model("core", "Geolocation").objects.values_list("geonames_id", "pk"))
    Company = old.get_model("core", "Company")
    company = Company.objects.create(nickname="late-company", hq_country_reference_id="JP", hq_geolocation_id=places[1814991])
    Account = old.get_model("core", "Account")
    account = Account.objects.create(data_source_id="x", external_identifier="late", normalized_identifier="late", country_id="US")
    old.get_model("core", "XAccountDetail").objects.create(account_id=account.pk)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE x_account_details SET account_based_in='Congo' WHERE account_key=%s", [account.pk])
    brand = old.get_model("core", "Brand").objects.create(nickname="late", display_name="Late")
    job = old.get_model("core", "JobListing").objects.create(
        brand=brand, title="Late", listing_identity="late-job", first_seen_at=timezone.now(), last_seen_at=timezone.now(),
    )
    with connection.cursor() as cursor:
        cursor.execute("UPDATE job_listings SET locations=%s::jsonb,locations_raw=%s WHERE id=%s", ['["India","Springfield"]', "India; Springfield", job.pk])
    MigrationExecutor(connection).migrate([target])
    current = MigrationExecutor(connection).loader.project_state([target]).apps
    assert current.get_model("core", "Company").objects.get(pk=company.pk).hq_geolocation_id == places[1861060]
    assert current.get_model("core", "Account").objects.get(pk=account.pk).based_in_location_id == places[203312]
    occurrences = list(current.get_model("core", "JobListingLocation").objects.filter(listing_id=job.pk).order_by("ordinal"))
    assert [row.geolocation_id for row in occurrences] == [places[1269750], None]
    assert all(row.observed_at is None for row in occurrences)
    # The still-running old image can change its old columns. The bridge updates
    # only actual source changes, while a new image writes local PKs directly.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE companies SET hq_country_id='US' WHERE nickname=%s", [company.pk])
        cursor.execute("UPDATE x_account_details SET account_based_in='Springfield' WHERE account_key=%s", [account.pk])
    assert current.get_model("core", "Company").objects.get(pk=company.pk).hq_geolocation_id == places[6252001]
    assert current.get_model("core", "Account").objects.get(pk=account.pk).based_in_location_id is None
    new = current.get_model("core", "Company").objects.create(nickname="new-company", hq_geolocation_id=places[1861060])
    new.refresh_from_db()
    assert new.hq_geolocation_id == places[1861060]
    with connection.cursor() as cursor:
        cursor.execute("SELECT locations_raw FROM job_listings WHERE id=%s", [job.pk])
        assert cursor.fetchone()[0] == "India; Springfield"
