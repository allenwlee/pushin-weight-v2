"""Prove the populated RG4 drop, its failure boundary, and final physical contract."""

import json

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.migrations._rg4_retirement_v1 import DROP_COLUMNS, DROP_TABLES

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
BASE = ("core", "0159_rg4_skip_unrelated_post_transition_rows")
TARGET = ("core", "0160_rg4_remove_superseded_storage")


def reported(owner, **values):
    from core.geolocation_evidence import write_source_evidence

    with transaction.atomic():
        write_source_evidence(owner, **values)


def columns():
    with connection.cursor() as cursor:
        cursor.execute("""SELECT c.relname,a.attname FROM pg_class c
            JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE c.relnamespace=current_schema()::regnamespace AND c.relkind='r'
              AND a.attnum>0 AND NOT a.attisdropped""")
        return set(cursor.fetchall())


def assert_removed(before):
    expected = {(table, column) for table, column in before
                if table not in DROP_TABLES and column not in DROP_COLUMNS.get(table, ())}
    assert columns() == expected
    with connection.cursor() as cursor:
        cursor.execute("""SELECT p.proname FROM pg_proc p WHERE p.pronamespace=current_schema()::regnamespace
            AND p.proname IN ('pw_geo_reported_bridge','pw_geo_legacy_reference','pw_geo_legacy_id',
                'pw_rg4_name_kind_bridge','pw_rg4_name_kind_identity','pw_job_location_legacy_invalidation')""")
        assert cursor.fetchall() == []


def old_job(key):
    from core.models import Brand, JobListing

    brand = Brand.objects.create(nickname=key, display_name=key)
    job = JobListing.objects.create(brand=brand, title="Preserve source", listing_identity=key,
                                    first_seen_at=timezone.now(), last_seen_at=timezone.now())
    with connection.cursor() as cursor:
        cursor.execute("UPDATE job_listings SET locations=%s::jsonb,locations_raw=%s WHERE id=%s",
                       [json.dumps(["India", "Springfield"]), "India; Springfield", job.pk])
    return job


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_populated_drop_preserves_sources_corrections_and_dossier_history(migration_rehearsal_schema):
    from core.event_dossiers import read_dossier
    from core.geolocation_evidence import source_evidence
    from core.models import (
        Account,
        Company,
        Geolocation,
        JobListingLocation,
        PersonText,
        Post,
        XAccountDetail,
    )
    from tests.person_factory import person_with_name
    from tests.test_event_dossiers import claim, dossier, review

    places = dict(Geolocation.objects.values_list("geonames_id", "pk"))
    account = Account.x.create(author_id="retire-account")
    detail = XAccountDetail.objects.create(account=account)
    reported(detail, reported_based_in="Korea")
    reported(account, reported_profile_location="Springfield")
    content = "Retained original body " * 5000
    post = Post.objects.create(tweet_id="retire-post", text=content, author=account,
                               entities={"urls": [{"expanded_url": "https://example.org/evidence"}]})
    with connection.cursor() as cursor:
        cursor.execute("UPDATE posts SET author_location='India' WHERE tweet_id=%s", [post.pk])
        cursor.execute("SELECT reported_author_location FROM posts WHERE tweet_id=%s", [post.pk])
        assert cursor.fetchone() == ("India",)
    # Make both sides change for the actual conflicting rolling-write boundary.
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE posts SET author_location='Congo',reported_author_location='Korea' WHERE tweet_id=%s", [post.pk])
    reported(post, reported_author_location="Springfield")
    Post.objects.filter(pk=post.pk).update(author_geolocation_id=places[1269750])
    company = Company.objects.create(nickname="retire-company")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE companies SET hq_country_id='JP' WHERE nickname=%s", [company.pk])
    Company.objects.filter(pk=company.pk).update(hq_geolocation_id=places[1814991])
    job = old_job("retire-job")
    person = person_with_name("Retained name")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE people SET nationality='possibly Japanese' WHERE id=%s", [person.pk])
    event = dossier("retirement-history")
    evidence = claim(event, key="retirement-announcement")
    first = review(event, evidence)
    before = columns()
    MigrationExecutor(connection).migrate([TARGET])
    assert_removed(before)
    post.refresh_from_db(); company.refresh_from_db(); account.refresh_from_db(); job.refresh_from_db()
    assert post.text == content and post.entities == {"urls": [{"expanded_url": "https://example.org/evidence"}]}
    assert source_evidence(post).reported_author_location == "Springfield"
    assert post.author_geolocation_id == places[1269750]  # Preserve explicit canonical correction.
    assert company.hq_geolocation_id == places[1814991]  # Stale old JP must not win.
    assert account.profile_location_id is None and account.based_in_location_id == places[1835841]
    occurrences = list(JobListingLocation.objects.filter(listing=job).order_by("ordinal"))
    assert [row.geolocation_id for row in occurrences] == [places[1269750], None]
    assert [source_evidence(row).reported_value for row in occurrences] == ["India", "Springfield"]
    assert json.loads(bytes(job.geolocation_source_archive.body)) == {
        "locations": ["India", "Springfield"], "reported_value": "India; Springfield",
    }
    assert PersonText.objects.filter(person=person, kind="reported_nationality", text="possibly Japanese").exists()
    second = review(event, evidence, expected_current_review_id=first.pk, reason="Post-drop revision")
    assert second.revision == 2 and read_dossier(event.pk, review_id=first.pk)["review"]["id"] == str(first.pk)
    reported(post, reported_author_location="Springfield")
    post.refresh_from_db(); assert post.author_geolocation_id == places[1269750]
    reported(post, reported_author_location=None)
    reported(detail, reported_based_in=None)
    post.refresh_from_db(); account.refresh_from_db()
    assert post.author_geolocation_id is None and account.based_in_location_id is None


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_failed_drop_rolls_back_ddl_but_retains_committed_job_capture(migration_rehearsal_schema):
    from core.models import JobListingLocation

    job = old_job("retire-interrupted")
    before = columns()

    def interrupt(execute, sql, params, many, context):
        if sql.startswith('ALTER TABLE "posts" DROP COLUMN'):
            raise RuntimeError("injected late DDL failure")
        return execute(sql, params, many, context)

    with pytest.raises(RuntimeError, match="injected late DDL"), connection.execute_wrapper(interrupt):
        MigrationExecutor(connection).migrate([TARGET])
    assert columns() == before
    assert not MigrationExecutor(connection).recorder.migration_qs.filter(app="core", name=TARGET[1]).exists()
    job.refresh_from_db()
    captured = job.geolocation_source_archive_id
    assert captured and JobListingLocation.objects.filter(listing=job).count() == 2
    MigrationExecutor(connection).migrate([TARGET])
    assert_removed(before)
    job.refresh_from_db()
    assert job.geolocation_source_archive_id == captured
    assert JobListingLocation.objects.filter(listing=job).count() == 2


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_drop_refuses_changed_preservation_guard_or_uncaptured_catalogue(migration_rehearsal_schema):
    before = columns()
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE posts DISABLE TRIGGER pw_geo_reported_bridge")
    with pytest.raises(RuntimeError, match="enabled source bridge"):
        MigrationExecutor(connection).migrate([TARGET])
    assert columns() == before
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE posts ENABLE TRIGGER pw_geo_reported_bridge")
        cursor.execute("UPDATE country_labels SET label=label || ' changed' WHERE country_code='JP'")
        assert cursor.rowcount
    with pytest.raises(RuntimeError, match="wording/policy snapshot"):
        MigrationExecutor(connection).migrate([TARGET])
    assert columns() == before


@pytest.mark.parametrize("migration_rehearsal_schema", [BASE], indirect=True)
def test_drop_bounds_a_live_writer_lock_and_can_resume(migration_rehearsal_schema):
    import psycopg
    from django.db import OperationalError

    before = columns()
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        path = cursor.fetchone()[0]
        cursor.execute("SHOW lock_timeout")
        original_timeout = cursor.fetchone()[0]
    with psycopg.connect(**connection.get_connection_params()) as writer:
        writer.execute("SELECT set_config('search_path', %s, false)", [path])
        writer.execute("LOCK TABLE posts IN ROW EXCLUSIVE MODE")
        with pytest.raises(OperationalError) as caught:
            MigrationExecutor(connection).migrate([TARGET])
        assert caught.value.__cause__.sqlstate == "55P03"
        assert columns() == before
        assert not MigrationExecutor(connection).recorder.migration_qs.filter(app="core", name=TARGET[1]).exists()
        writer.rollback()
    with connection.cursor() as cursor:
        cursor.execute("SHOW lock_timeout")
        assert cursor.fetchone()[0] == original_timeout
    MigrationExecutor(connection).migrate([TARGET])
    assert_removed(before)


def test_current_schema_has_no_retired_storage_or_nonprimary_geolocation_fk():
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND tablename=ANY(%s)", [list(DROP_TABLES)])
        assert cursor.fetchall() == []
        for table, retired in DROP_COLUMNS.items():
            cursor.execute("SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attname=ANY(%s) AND NOT attisdropped",
                           [table, list(retired)])
            assert cursor.fetchall() == [], table
        cursor.execute("SELECT confkey,convalidated FROM pg_constraint WHERE confrelid='geolocations'::regclass AND contype='f'")
        references = cursor.fetchall()
        assert len(references) == 16 and all(row == ([1], True) for row in references)
