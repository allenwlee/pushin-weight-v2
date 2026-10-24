"""Use a real login against the existing database, never SET ROLE as owner."""

import secrets
import uuid
from unittest.mock import patch

import psycopg
import pytest
from django.db import ProgrammingError, connection, connections, transaction
from psycopg import sql

from core.geolocation_access import apply_serving_grants
from core.models import Post

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def serving_login():
    role = "pw_geo_test_" + uuid.uuid4().hex[:16]
    password = secrets.token_urlsafe(32)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        owner = cursor.fetchone()[0]
        cursor.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
    try:
        with transaction.atomic():
            report = apply_serving_grants(connection, role)
        parameters = {key: value for key, value in connection.get_connection_params().items() if key not in {"user", "password"}}
        with psycopg.connect(**parameters, user=role, password=password, autocommit=True) as serving:
            yield serving, role, owner, report
    finally:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_serving_login_reads_canonical_columns_but_cannot_reach_source_or_owner(serving_login):
    serving, role, owner, report = serving_login
    from core.geolocation_evidence import write_source_evidence

    with transaction.atomic():
        post = Post.objects.create(tweet_id="serving-geography")
        write_source_evidence(post, reported_author_location="Springfield")
    assert report["role"] == role and report["relations_checked"] > 0
    with serving.cursor() as cursor:
        cursor.execute("SELECT current_user,session_user")
        assert cursor.fetchone() == (role, role)
        cursor.execute("SELECT tweet_id,author_geolocation_id FROM posts WHERE tweet_id='serving-geography'")
        assert cursor.fetchone() == ("serving-geography", None)
        for query in (
            "SELECT reported_author_location FROM posts",
            "SELECT author_location FROM posts",
            "SELECT raw_profile_payload FROM account_profile_snapshots",
            "SELECT profile_data FROM account_profile_snapshots",
            "SELECT raw_payload FROM job_listings",
            "SELECT body FROM collection_evidence_archives",
            "SELECT extracted_claim_data FROM people_brand_affiliation_evidence",
            "SELECT raw_payload FROM collection_runs",
            "CREATE TABLE public.forbidden_serving_table (id bigint)",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(query)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(owner)))


def test_reconciliation_refuses_to_repurpose_owner():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        owner = cursor.fetchone()[0]
    with pytest.raises(ValueError, match="separate dedicated"), transaction.atomic():
        apply_serving_grants(connection, owner)


def test_job_orm_document_uses_local_places_without_source_access(serving_login):
    from django.utils import timezone

    from core.collection_capture import archive_document
    from core.geolocation_evidence import source_evidence
    from core.intelligence_readers import job_listing_document
    from core.job_locations import write_job_locations
    from core.models import Brand, Geolocation, GeolocationAlternateName, JobListing

    archive = archive_document(b"India test source")
    place = Geolocation.objects.create(geonames_id=1269750, place_kind=4, source_archive=archive)
    GeolocationAlternateName.objects.create(
        geolocation=place, locale_id="en", name="India", is_preferred=True, source_archive=archive,
    )
    brand = Brand.objects.create(nickname="serving-job", display_name="Serving job")
    listing = JobListing.objects.create(
        brand=brand, hiring_organization="Serving job", title="Researcher",
        first_seen_at=timezone.now(), last_seen_at=timezone.now(), listing_identity="serving-job",
    )
    write_job_locations(listing, ["India", "Springfield"])
    serving, _role, _owner, _report = serving_login
    with patch.object(connections["default"], "connection", serving):
        document = job_listing_document(listing.pk)
        assert document["location"]["values"] == [{"id": place.pk, "label": "India"}]
        assert "Springfield" not in str(document)
        with pytest.raises(ProgrammingError, match="permission denied"):
            source_evidence(listing)
