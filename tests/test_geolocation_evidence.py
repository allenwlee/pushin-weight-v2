import pytest
from django.db import IntegrityError, connection, transaction

from core.collection_capture import archive_document
from core.geolocation_evidence import source_evidence, write_source_evidence
from core.geolocation_resolution import reviewed_location_inputs, source_geonames_id
from core.models import Account, Geolocation, Post, XAccountDetail

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def places():
    archive = archive_document(b"source geography fixture")
    return {
        identifier: Geolocation.objects.create(geonames_id=identifier, place_kind=4, source_archive=archive)
        for identifier in (1269750, 1835841, 203312)
    }


def test_changed_reported_source_clears_obsolete_reference_in_bulk_and_orm():
    selected = places()
    post = Post.objects.create(tweet_id="geo-evidence", author_location="India")
    post.refresh_from_db()
    assert post.author_geolocation_id == selected[1269750].pk
    assert source_evidence(post).reported_author_location == "India"
    with transaction.atomic():
        write_source_evidence(post, reported_author_location="Springfield")
    post.refresh_from_db()
    assert post.author_geolocation_id is None
    assert post.author_location == "Springfield"  # Preceding image remains compatible until final drop.
    Post.objects.filter(pk=post.pk).update(author_location="Korea")
    post.refresh_from_db()
    assert post.author_geolocation_id == selected[1835841].pk
    assert source_evidence(post).reported_author_location == "Korea"
    with transaction.atomic():
        write_source_evidence(post, reported_author_location=None)
    post.refresh_from_db()
    assert post.author_geolocation_id is None and post.author_location is None
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE posts SET author_location='India',reported_author_location='Korea' WHERE tweet_id=%s", [post.pk])


def test_based_in_defaults_are_distinct_from_profile_location_and_clear_when_changed():
    selected = places()
    account = Account.x.create(author_id="818181", location="India")
    detail = XAccountDetail.objects.create(account=account, account_based_in="Korea")
    account.refresh_from_db()
    assert account.profile_location_id == selected[1269750].pk
    assert account.based_in_location_id == selected[1835841].pk
    with transaction.atomic():
        write_source_evidence(detail, reported_based_in="Congo")
    account.refresh_from_db()
    assert account.based_in_location_id == selected[203312].pk
    assert account.profile_location_id == selected[1269750].pk
    with transaction.atomic():
        write_source_evidence(detail, reported_based_in="North Korea")
    account.refresh_from_db()
    assert account.based_in_location_id is None  # No imported NK place, and never South Korea.
    assert source_evidence(detail).reported_based_in == "North Korea"


def test_database_and_python_resolution_agree_for_reviewed_inputs():
    selected = places()
    for context in ("freeform", "based_in"):
        values = list(reviewed_location_inputs()[context]) + ["Korea", "Congo", "Springfield", "CA", "Remote"]
        values += ["\u00a0" + value.upper() + "\u00a0" for value in values]
        with connection.cursor() as cursor:
            cursor.execute("SELECT value,pw_geo_source_id(value,%s) FROM unnest(%s::text[]) value", [context, values])
            actual = cursor.fetchall()
        for value, target in actual:
            external = source_geonames_id(value, context=context)
            expected = selected[external].pk if external in selected else None
            assert target == expected, (context, value)


def test_source_projection_cannot_insert_or_replace_parent_identity():
    from core.geolocation_evidence import PostLocationEvidence

    post = Post.objects.create(tweet_id="geo-source-owner")
    with pytest.raises(TypeError, match="existing canonical owner"):
        PostLocationEvidence(tweet_id=post.pk, reported_author_location="India").save()
    with pytest.raises(ValueError, match="explicit source fields"):
        write_source_evidence(post, tweet_id="different-owner")
