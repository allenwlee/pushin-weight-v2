"""Bounded locale mapping for existing owner/language label records."""

from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Lower

from core.locale_identity import app_edition_locale_key
from core.models import CountryLabel, Locale, RegionLabel

OWNERS = {
    "country_labels": (CountryLabel, "country_id"),
    "region_labels": (RegionLabel, "region_id"),
}


def map_geography_label_locales(
    *,
    owner,
    database="default",
    batch_size=500,
    max_batches=10,
    after_owner_key=None,
    after_lang=None,
    apply=False,
):
    if owner not in OWNERS:
        raise ValueError("Owner must be country_labels or region_labels")
    if not 1 <= batch_size <= 10000 or not 1 <= max_batches <= 10000:
        raise ValueError("Positive bounded batch limits required")
    if (after_owner_key is None) != (after_lang is None) or (
        after_owner_key is not None and (not after_owner_key or not after_lang)
    ):
        raise ValueError("Both nonempty cursor parts are required together")
    model, owner_field = OWNERS[owner]
    catalogue = (
        Locale.objects.using(database)
        .alias(key=Lower("code"))
        .filter(key=OuterRef("_locale_key"))
        .values("pk")[:1]
    )
    rows = (
        model.objects.using(database)
        .alias(_locale_key=app_edition_locale_key())
        .annotate(_resolved_locale=Subquery(catalogue))
    )
    collision_count = (
        rows.filter(_resolved_locale__isnull=False)
        .values(owner_field, "_resolved_locale")
        .annotate(row_count=Count("*"))
        .filter(row_count__gt=1)
        .count()
    )
    if apply and collision_count:
        raise ValueError("Owner/locale collisions require resolution before mapping")
    eligible = rows.filter(
        locale_reference__isnull=True, _resolved_locale__isnull=False
    )
    examined = updated = 0
    for _ in range(max_batches):
        with transaction.atomic(using=database):
            page = eligible
            if after_owner_key is not None:
                page = page.filter(
                    Q(**{owner_field + "__gt": after_owner_key})
                    | Q(**{owner_field: after_owner_key, "lang__gt": after_lang})
                )
            keys = list(
                page.order_by(owner_field, "lang").values_list(owner_field, "lang")[
                    :batch_size
                ]
            )
            if not keys:
                break
            if apply:
                # Recheck both the composite key and current raw-language lookup.
                updated += eligible.filter(pk__in=keys).update(
                    locale_reference_id=Subquery(catalogue)
                )
            examined += len(keys)
            after_owner_key, after_lang = keys[-1]
    return {
        "owner": owner,
        "apply": apply,
        "examined": examined,
        "updated": updated,
        "after_owner_key": after_owner_key,
        "after_lang": after_lang,
        "remaining_resolvable": eligible.count(),
        "collision_count": collision_count,
        "unmatched_count": rows.filter(_resolved_locale__isnull=True).count(),
    }
