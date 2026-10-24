from datetime import timedelta

import pytest
from django.utils import timezone

from core.collection_capture import archive_document
from core.geolocation_readers import country_places, descendant_places
from core.models import Account, Actor, Geolocation, GeolocationPolicy, Post
from monitor.views import _filter_home_posts_queryset, _normalize_home_filters
from tests.geolocation_factory import feed_places

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_country_and_region_filters_take_local_ids_without_inventing_membership():
    places = feed_places()
    source = archive_document(b"Geographic hierarchy fixture")
    east_asia = Geolocation.objects.create(geonames_id=7729894, place_kind=3, source_archive=source)
    places["CN"].geographical_parent = east_asia
    places["CN"].save(update_fields=["geographical_parent"])
    city = Geolocation.objects.create(place_kind=6, country=places["CN"], source_archive=source)
    now = timezone.now()
    for key, place in (("china", places["CN"]), ("city", city), ("taiwan", places["TW"])):
        account = Account.x.create(author_id="geolocation-filter-" + key, based_in_location=place)
        Post.objects.create(tweet_id=key, author=account, created_at=now - timedelta(seconds=1))
    assert set(country_places([places["CN"].pk]).values_list("pk", flat=True)) == {places["CN"].pk, city.pk}
    # A display-parent policy does not assert citizenship or geographic ancestry.
    assert places["TW"].pk not in descendant_places([east_asia.pk]).values_list("pk", flat=True)
    for key, selected in (("country", places["CN"].pk), ("region", east_asia.pk)):
        filters = _normalize_home_filters({key: [str(selected)]})
        assert filters[key] == [selected]
        rows = _filter_home_posts_queryset(1, filters, now=now)
        assert set(rows.values_list("pk", flat=True)) == {"china", "city"}
    for invalid in ("CN", "eastern-asia", "0", "-1", str(2**63)):
        filters = _normalize_home_filters({"country": [invalid]})
        assert filters["country"] == []
        assert not _filter_home_posts_queryset(1, filters, now=now).exists()


def test_country_filter_uses_explicit_policy_override_or_withholding():
    places = feed_places()
    source = archive_document(b"Country attribution policy fixture")
    city = Geolocation.objects.create(place_kind=6, country=places["CN"], source_archive=source)
    actor = Actor.objects.get(actor_key="feed-geolocation-fixture")
    override = GeolocationPolicy.objects.create(
        geolocation=city, actor=actor, decided_at=timezone.now(), source_archive=source,
        country_attribution=1, country=places["US"],
    )
    city.current_policy = override
    city.save(update_fields=["current_policy"])
    assert country_places([places["US"].pk]).filter(pk=city.pk).exists()
    assert not country_places([places["CN"].pk]).filter(pk=city.pk).exists()
    withheld = GeolocationPolicy.objects.create(
        geolocation=city, supersedes=override, actor=actor, decided_at=timezone.now(),
        source_archive=source, country_attribution=2,
    )
    city.current_policy = withheld
    city.save(update_fields=["current_policy"])
    assert not country_places([places["CN"].pk, places["US"].pk]).filter(pk=city.pk).exists()
