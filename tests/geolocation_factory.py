"""Explicit canonical places for reader/browser tests; no provider calls."""

from django.utils import timezone

from core.collection_capture import archive_document
from core.models import Actor, Geolocation, GeolocationAlternateName, GeolocationPolicy
from core.shared_vocabulary import seed_shared_vocabulary


def wire_place(*, identifier=100, code=None, labels=None, parent=None, parent_only=False, kind=4):
    place = Geolocation(id=identifier, iso2_country_code=code, place_kind=kind)
    place._prefetched_objects_cache = {"alternate_names": [
        GeolocationAlternateName(id=index, locale_id=locale, name=name, is_preferred=True)
        for index, (locale, name) in enumerate((labels or {}).items(), 1)
    ]}
    place.current_policy = (
        GeolocationPolicy(id=identifier, display_parent=parent, display_relationship=2 if parent_only else 1,
                          flag_mode=1 if parent_only else 0, label_mode=1 if parent_only else 0)
        if parent else None
    )
    return place


def feed_places():
    seed_shared_vocabulary(catalogues=("languages", "locales"))
    source = archive_document(b"Deterministic canonical feed geography fixture")
    actor, _ = Actor.objects.get_or_create(actor_kind="system", actor_key="feed-geolocation-fixture")
    rows = {}
    values = {
        "CN": (1814991, 4, "China", "中国", "中国"),
        "AU": (2077456, 4, "Australia", "澳大利亚", "オーストラリア"),
        "US": (6252001, 4, "United States of America", "美利坚合众国", "米国"),
        "HK": (1819730, 4, "China, Hong Kong Special Administrative Region", "中国香港特别行政区", "香港"),
        "TW": (1668284, 4, "Taiwan", "台湾", "台湾"),
        "AX": (661882, 4, "Åland Islands", "奥兰群岛", "オーランド諸島"),
        "europe": (6255148, 2, "Europe", "欧洲", "ヨーロッパ"),
    }
    for key, (external, kind, en, zh, ja) in values.items():
        row, _ = Geolocation.objects.get_or_create(
            geonames_id=external, defaults={"place_kind": kind, "source_archive": source,
                                          "iso2_country_code": key if kind == 4 else None},
        )
        for locale, label in (("en", en), ("zh-Hans", zh), ("ja", ja)):
            GeolocationAlternateName.objects.get_or_create(
                geolocation=row, locale_id=locale, name=label,
                defaults={"is_preferred": True, "source_archive": source},
            )
        rows[key] = row
    for key in ("HK", "TW"):
        row = rows[key]
        if row.current_policy_id is None:
            policy = GeolocationPolicy.objects.create(
                geolocation=row, actor=actor, decided_at=timezone.now(), source_archive=source,
                display_parent=rows["CN"], display_relationship=2 if key == "TW" else 1,
                flag_mode=1 if key == "TW" else 0, label_mode=1 if key == "TW" else 0,
            )
            row.current_policy = policy
            row.save(update_fields=["current_policy"])
    return rows
