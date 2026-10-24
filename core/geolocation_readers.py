"""Canonical geography selection for serving; never interpret source wording."""

from django.db.models import BigIntegerField, Case, F, Value, When
from django.db.models.expressions import RawSQL

from core.models import Geolocation, GeolocationPolicy


def country_places(identifiers):
    """Place IDs whose current country attribution matches selected local IDs."""
    return Geolocation.objects.annotate(
        attributed_country_id=Case(
            When(current_policy__country_attribution=GeolocationPolicy.Attribution.WITHHOLD, then=Value(None)),
            When(current_policy__country_attribution=GeolocationPolicy.Attribution.OVERRIDE, then=F("current_policy__country_id")),
            When(place_kind=Geolocation.Kind.COUNTRY_AREA, then=F("pk")),
            default=F("country_id"), output_field=BigIntegerField(),
        )
    ).filter(attributed_country_id__in=identifiers).values("pk")


def descendant_places(identifiers):
    """Follow imported local ancestry; missing edges imply no membership."""
    return Geolocation.objects.filter(pk__in=RawSQL(
        """WITH RECURSIVE selected(id) AS (
          SELECT id FROM geolocations WHERE id=ANY(%s::bigint[])
          UNION
          SELECT child.id FROM geolocations child JOIN selected parent
            ON child.geographical_parent_id=parent.id
            OR child.administrative_parent_id=parent.id
            OR child.country_id=parent.id
        ) SELECT id FROM selected""",
        [list(identifiers)], output_field=BigIntegerField(),
    )).values("pk")
