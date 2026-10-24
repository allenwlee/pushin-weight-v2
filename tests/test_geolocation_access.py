"""Use a real login against the existing database, never SET ROLE as owner."""

import secrets
import uuid

import psycopg
import pytest
from django.db import connection, transaction
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
        parameters = {key: value for key, value in connection.get_connection_params().items() if key in {"dbname", "host", "port", "sslmode"}}
        with psycopg.connect(**parameters, user=role, password=password, autocommit=True) as serving:
            yield serving, role, owner, report
    finally:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_serving_login_reads_canonical_columns_but_cannot_reach_source_or_owner(serving_login):
    serving, role, owner, report = serving_login
    Post.objects.create(tweet_id="serving-geography", author_location="Springfield")
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
