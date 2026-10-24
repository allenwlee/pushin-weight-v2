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
            "SELECT country_code FROM accounts",
            "SELECT hq_country_id FROM companies",
            "SELECT * FROM country_labels",
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


def test_web_build_only_verifies_schema_with_actual_restricted_login(serving_login):
    from scripts.render_migrate import main
    serving, _role, _owner, _report = serving_login
    def forbidden(*args, **kwargs):
        raise AssertionError("Web build attempted owner connection or DDL")
    with patch.object(connections["default"], "connection", serving):
        assert main(
            environ={"DATABASE_URL": "postgresql://unused", "PW_DATABASE_ACCESS_MODE": "serving"},
            app_connection=connections["default"], connect=forbidden,
            execute_migrate=forbidden, setup_django=lambda: None,
        ) == 0


def test_reconciliation_refuses_to_repurpose_owner():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        owner = cursor.fetchone()[0]
    with pytest.raises(ValueError, match="separate dedicated"), transaction.atomic():
        apply_serving_grants(connection, owner)


@pytest.mark.parametrize("key", ["CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "MIGRATION_DATABASE_URL", "STAGING_REFRESH_SOURCE_DATABASE_URL"])
def test_serving_environment_rejects_secondary_database_credentials(key):
    from core.geolocation_access import verify_serving_environment
    with pytest.raises(ValueError, match="another database credential") as caught:
        verify_serving_environment({
            "PW_DATABASE_ACCESS_MODE": "serving", "DATABASE_URL": "postgresql://serving:<password>@db/app",
            key: "postgresql://owner:<do-not-print>@db/app",
        })
    assert "do-not-print" not in str(caught.value)


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


def test_populated_webpages_and_feeds_work_without_source_privileges(serving_login, client, monkeypatch):
    from datetime import timedelta

    from django.contrib.auth import get_user_model

    from core.job_locations import write_job_locations
    from core.models import Account, Event, Opportunity, OpportunityType
    from tests.general_helpers import NOW, classified_post, saved_commentary
    from tests.geolocation_factory import feed_places
    from tests.test_general_jobs_people import affiliation, job

    places = feed_places()
    account = Account.x.create(author_id="serving-pages", based_in_location=places["TW"])
    for index, category in enumerate(("events", "opportunities", "job_listings", "personnel_changes")):
        post = classified_post(str(9500 + index), category)
        saved_commentary(post)
        Post.objects.filter(pk=post.pk).update(author=account, created_at=NOW - timedelta(hours=1))
        if category == "events":
            Event.objects.create(brand_id="qwen", source_post=post, title="Serving event", event_identity="serving-event", first_seen_at=NOW, last_seen_at=NOW)
        elif category == "opportunities":
            Opportunity.objects.create(brand_id="qwen", source_post=post, sponsor_name="Qwen", opportunity_type_reference=OpportunityType.objects.get(code="free_credits"), action_type="apply", benefit_type="credits", benefit_text="Serving offer", opportunity_identity="serving-offer", first_seen_at=NOW, last_seen_at=NOW)
        elif category == "job_listings":
            listing = job(post, "Serving role")
            write_job_locations(listing, ["United States", "Springfield"])
        else:
            affiliation(post, "serving-person")
    monkeypatch.setattr("monitor.general_views.timezone.now", lambda: NOW)
    user = get_user_model().objects.create_user(username="serving-pages", email="reader@example.org", is_staff=True, is_superuser=True)
    client.force_login(user)
    serving, _role, _owner, _report = serving_login
    with patch.object(connections["default"], "connection", serving):
        for locale in ("en", "ja", "zh_hans"):
            for path in ("/", "/general/", "/brands/qwen/", "/stories/", "/posts/9502/", "/admin"):
                language = "zh-cn" if locale == "zh_hans" else locale
                response = client.get(f"{path}?lang={language}&locale={locale}", secure=True)
                assert response.status_code == 200, path
            for section in ("calendar", "free", "jobs", "moving"):
                response = client.get(f"/general/feed/?section={section}&lang={locale}", secure=True)
                assert response.status_code == 200
                assert response.json()["items"], section
                assert "Springfield" not in response.content.decode()
