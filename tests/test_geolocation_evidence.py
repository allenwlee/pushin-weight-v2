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
    post = Post.objects.create(tweet_id="geo-evidence")
    write_source_evidence(post, reported_author_location="India")
    post.refresh_from_db()
    assert post.author_geolocation_id == selected[1269750].pk
    assert source_evidence(post).reported_author_location == "India"
    with transaction.atomic():
        write_source_evidence(post, reported_author_location="Springfield")
    post.refresh_from_db()
    assert post.author_geolocation_id is None
    assert not hasattr(post, "author_location")
    with connection.cursor() as cursor:
        cursor.execute("SELECT author_location FROM posts WHERE tweet_id=%s", [post.pk])
        assert cursor.fetchone()[0] == "Springfield"  # Preceding deployed image remains compatible until drop.
        cursor.execute("UPDATE posts SET author_location='Korea' WHERE tweet_id=%s", [post.pk])
    post.refresh_from_db()
    assert post.author_geolocation_id == selected[1835841].pk
    assert source_evidence(post).reported_author_location == "Korea"
    with transaction.atomic():
        write_source_evidence(post, reported_author_location=None)
    post.refresh_from_db()
    assert post.author_geolocation_id is None and source_evidence(post).reported_author_location is None
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE posts SET author_location='India',reported_author_location='Korea' WHERE tweet_id=%s", [post.pk])


def test_based_in_defaults_are_distinct_from_profile_location_and_clear_when_changed():
    selected = places()
    account = Account.x.create(author_id="818181")
    write_source_evidence(account, reported_profile_location="India")
    detail = XAccountDetail.objects.create(account=account)
    write_source_evidence(detail, reported_based_in="Korea")
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


def test_location_only_writes_preserve_payloads_and_identity_changes_still_validate():
    import json

    selected = places()
    account = Account.x.create(author_id="location-identity-a")
    other = Account.x.create(author_id="location-identity-b")
    post = Post.objects.create(tweet_id="location-identity", author=account,
                               entities={"urls": [{"expanded_url": "https://example.org/source"}]})
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN (ANALYZE,FORMAT JSON) UPDATE posts SET reported_author_location='India' WHERE tweet_id=%s", [post.pk])
        result = cursor.fetchone()[0]
        result = json.loads(result) if isinstance(result, str) else result
        triggers = {row["Trigger Name"] for row in result[0].get("Triggers", [])}
        assert "pw_geo_reported_bridge" in triggers and "benchmark_account_link" not in triggers
        cursor.execute("UPDATE posts SET author_id=%s WHERE tweet_id=%s", [other.author_id, post.pk])
    post.refresh_from_db()
    assert post.author_id == other.pk and post.native_author_id == other.author_id
    assert post.author_geolocation_id == selected[1269750].pk
    assert post.entities == {"urls": [{"expanded_url": "https://example.org/source"}]}
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE posts SET author_id='missing-native-identity' WHERE tweet_id=%s", [post.pk])
    Post.objects.filter(pk=post.pk).update(author=account)
    post.refresh_from_db()
    assert post.native_author_id == account.author_id
    foreign = Account.objects.create(data_source_id="hf", external_identifier="location-foreign",
                                     normalized_identifier="location-foreign", identifier_kind="namespace")
    with pytest.raises(IntegrityError), transaction.atomic():
        Post.objects.filter(pk=post.pk).update(author=foreign)


def test_harvest_profile_call_chain_preserves_fingerprint_and_clears_ambiguous_location():
    from django.utils import timezone

    from core.profile_snapshots import profile_observation_from_payload, record_profile_snapshot
    from monitor.cycle import _upsert_account, _upsert_post

    selected = places()
    raw = {
        "id": "location-pipeline", "author_id": "636363", "author_handle": "geo_person",
        "author_location": "India", "_author_present_fields": ["author_location"],
    }
    account = _upsert_account(raw)
    post, _ = _upsert_post(raw, account=account)
    observation = profile_observation_from_payload(raw)
    snapshot, created, _ = record_profile_snapshot(
        account=account, observation=observation, observed_at=timezone.now(), source_kind="post", source_post=post,
    )
    account.refresh_from_db()
    assert created and snapshot.profile_hash == observation.profile_hash
    assert snapshot.geolocation_id == account.profile_location_id == post.author_geolocation_id == selected[1269750].pk
    assert source_evidence(snapshot).profile_data == observation.profile_data
    changed = {**raw, "author_location": "Springfield"}
    _upsert_account(changed)
    _upsert_post(changed, account=account)
    account.refresh_from_db()
    post.refresh_from_db()
    snapshot.refresh_from_db()
    assert account.profile_location_id is None and post.author_geolocation_id is None
    assert snapshot.geolocation_id == selected[1269750].pk
    assert snapshot.profile_hash == observation.profile_hash
    assert source_evidence(account).reported_profile_location == "Springfield"
