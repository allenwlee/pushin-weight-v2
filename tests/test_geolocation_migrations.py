"""Rehearse shared-place creation without advancing the shared public schema."""

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0147_rg4_restore_selected_scalar_fields")
TARGET = ("core", "0148_rg4_geolocation_owners")


@pytest.mark.parametrize("migration_rehearsal_schema", [("core", "0158_rg4_scope_geography_write_triggers")], indirect=True)
def test_post_source_updates_skip_transition_capture_but_date_changes_still_invalidate(migration_rehearsal_schema):
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    baseline = ("core", "0158_rg4_scope_geography_write_triggers")
    old = MigrationExecutor(connection).loader.project_state([baseline]).apps
    State = old.get_model("core", "MaterializationState")
    Post = old.get_model("core", "Post")
    earliest = timezone.now() - timedelta(days=10)
    State.objects.update_or_create(pk="home.brand_time_counts.v1", defaults={"source_generation":10,"dirty_since":None})
    Post.objects.bulk_create([
        Post(tweet_id=f"home-source-{index}", created_at=earliest + timedelta(days=index))
        for index in range(3)
    ])
    # Recreate the already-deployed old trigger; fresh historical installs also
    # receive the performance repair before their geography copies begin.
    with connection.cursor() as cursor:
        cursor.execute("""DROP TRIGGER home_counts_update ON posts;
            CREATE TRIGGER home_counts_update AFTER UPDATE ON posts
            REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
            FOR EACH STATEMENT EXECUTE FUNCTION home_counts_invalidate()""")
    MigrationExecutor(connection).migrate([("core", "0159_rg4_skip_unrelated_post_transition_rows")])
    with connection.cursor() as cursor:
        cursor.execute("""SELECT tgoldtable,tgnewtable,(tgtype::int & 1)
            FROM pg_trigger WHERE tgrelid='posts'::regclass AND tgname='home_counts_update'""")
        assert cursor.fetchone() == (None, None, 1)
        cursor.execute("UPDATE posts SET reported_author_location='Springfield',like_count=7")
    state = State.objects.get(pk="home.brand_time_counts.v1")
    assert state.source_generation == 10 and state.dirty_since is None
    Post.objects.update(created_at=earliest + timedelta(days=20))
    state.refresh_from_db()
    assert state.source_generation == 13 and state.dirty_since == earliest
    with transaction.atomic():
        Post.objects.update(created_at=earliest - timedelta(days=1))
        transaction.set_rollback(True)
    state.refresh_from_db()
    assert state.source_generation == 13 and state.dirty_since == earliest
    with connection.cursor() as cursor:
        cursor.execute("UPDATE posts SET created_at=NULL WHERE tweet_id='home-source-0'")
        cursor.execute("UPDATE posts SET tweet_id='home-source-renamed' WHERE tweet_id='home-source-1'")
    state.refresh_from_db()
    assert state.source_generation == 15 and state.dirty_since == earliest


@pytest.mark.parametrize("migration_rehearsal_schema", [("core", "0150_rg4_geolocation_mapping")], indirect=True)
def test_source_copy_resumes_committed_small_batches_without_skipping_unresolved_rows(migration_rehearsal_schema):
    import psycopg

    baseline = ("core", "0150_rg4_geolocation_mapping")
    target = ("core", "0151_rg4_reported_location_bridges")
    old = MigrationExecutor(connection).loader.project_state([baseline]).apps
    india = old.get_model("core", "Geolocation").objects.get(geonames_id=1269750).pk
    Post = old.get_model("core", "Post")
    Post.objects.bulk_create([
        Post(tweet_id=f"source-batch-{index:04d}", author_location=("India", "Springfield", "")[index % 3],
             author_geolocation_id=(india if index % 3 == 0 else None) if index < 150
                 else (india if index % 3 else None))
        for index in range(205)
    ])
    writes = 0
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        rehearsal_path = cursor.fetchone()[0]
        cursor.execute("SELECT current_setting('gin_pending_list_limit')")
        original_pending_limit = cursor.fetchone()[0]

    def fail_second_copy(execute, sql, params, many, context):
        nonlocal writes
        if 'UPDATE "posts" owner SET "reported_author_location"' in sql:
            writes += 1
            if writes == 1:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_size_bytes(current_setting('gin_pending_list_limit')),current_setting('statement_timeout')")
                    assert cursor.fetchone() == (65536, "30s")
                # Selection and update remain one transaction: an independent
                # old-source writer cannot change a selected row between them.
                with psycopg.connect(**connection.get_connection_params(), autocommit=True) as other:
                    other.execute("SELECT set_config('search_path',%s,false)", [rehearsal_path])
                    other.execute("SET lock_timeout='100ms'")
                    with pytest.raises(psycopg.errors.LockNotAvailable):
                        other.execute("UPDATE posts SET author_location='Congo' WHERE tweet_id='source-batch-0000'")
            if writes == 2:
                raise RuntimeError("simulated interruption between committed source batches")
        return execute(sql, params, many, context)

    with pytest.raises(RuntimeError, match="simulated interruption"), connection.execute_wrapper(fail_second_copy):
        MigrationExecutor(connection).migrate([target])
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM posts WHERE reported_author_location IS NOT NULL")
        assert cursor.fetchone()[0] == 100
        cursor.execute("SELECT 1 FROM django_migrations WHERE app='core' AND name=%s", [target[1]])
        assert cursor.fetchone() is None
    MigrationExecutor(connection).migrate([target])
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('gin_pending_list_limit')")
        assert cursor.fetchone()[0] == original_pending_limit
        cursor.execute("SELECT author_location,reported_author_location,author_geolocation_id FROM posts ORDER BY tweet_id")
        rows = cursor.fetchall()
    assert len(rows) == 205
    assert all(old == new and reference == (india if old == "India" else None) for old, new, reference in rows)


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
    from importlib import import_module

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
    # Simulate loss of the process after committed DDL, before Django records
    # completion. A retry must preserve data and finish the same migration.
    migration = import_module("core.migrations.0157_rg4_geolocation_reference_cutover")
    with connection.schema_editor(atomic=True) as editor:
        migration.install(old, editor)
        editor.execute(migration.IMMUTABLE_CITIZENSHIP)
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


@pytest.mark.parametrize("migration_rehearsal_schema", [("core", "0150_rg4_geolocation_mapping")], indirect=True)
def test_source_bridge_retries_after_committed_install(migration_rehearsal_schema):
    from importlib import import_module

    baseline = ("core", "0150_rg4_geolocation_mapping")
    target = ("core", "0151_rg4_reported_location_bridges")
    old = MigrationExecutor(connection).loader.project_state([baseline]).apps
    places = dict(old.get_model("core", "Geolocation").objects.values_list("geonames_id", "pk"))
    late = old.get_model("core", "Account").objects.create(
        data_source_id="x", external_identifier="late-before-bridge", normalized_identifier="late-before-bridge",
        location="India", profile_location_id=places[1814991],
    )
    cleared = old.get_model("core", "Account").objects.create(
        data_source_id="x", external_identifier="cleared-before-bridge", normalized_identifier="cleared-before-bridge",
        location=None, profile_location_id=places[1269750],
    )
    account = old.get_model("core", "Account").objects.create(
        data_source_id="x", external_identifier="retry-geo", normalized_identifier="retry-geo", location="India",
    )
    migration = import_module("core.migrations.0151_rg4_reported_location_bridges")
    with connection.schema_editor(atomic=True) as editor:
        migration.install(old, editor)
    # An old writer may commit while the mapper is being restarted.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE accounts SET location='Springfield' WHERE account_key=%s", [account.pk])
    MigrationExecutor(connection).migrate([target])
    with connection.cursor() as cursor:
        cursor.execute("SELECT location,reported_profile_location,profile_location_id FROM accounts WHERE account_key=%s", [account.pk])
        assert cursor.fetchone() == ("Springfield", "Springfield", None)
    late.refresh_from_db()
    cleared.refresh_from_db()
    assert late.profile_location_id == places[1269750]
    assert cleared.profile_location_id is None
