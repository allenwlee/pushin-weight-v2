"""Frozen existing-data mapping for RG4. No network, guessed places or old graph."""

import hashlib
import json
from pathlib import Path

from django.db import connections, transaction
from django.utils import timezone

from ._rg4_geography_write_performance_v1 import (
    finish_post_batch,
    identity_triggers,
    prepare_post_index,
    write_batch_options,
)
from ._rg4_geonames_v1 import (
    archive_document,
    import_geonames_documents,
    load_pinned_geonames,
    normalized_place_wording,
)
from ._rg4_home_count_write_v1 import install as home_count_update_trigger

INPUT_HASHES = {
    "manifest.json": "b00d8e6df23e644e97bca0a5d0145661c74fdd58eed1f12b159b793c946bd0e3",
    "resolution-inputs.json": "24438930319c42f12a4bb5ea2302d8d75d1fc2d66886f798bc6eb633ef34473b",
}
RELATIONSHIPS = {
    "special_administrative_region": 1, "owner_display_context": 2,
    "us_insular_area": 3, "french_overseas": 4, "british_overseas_territory": 5,
    "crown_dependency": 6, "kingdom_constituent_country": 7, "netherlands_public_body": 8,
}
OWNER_DEFAULTS = {"korea": 1835841, "congo": 203312}


def capture(apps, value):
    return archive_document(
        apps, json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(),
        encoding="legacy-json-canonical-v1", capture_kind="legacy_snapshot",
    )


def resolve(inputs, local_ids, value, context="freeform"):
    if isinstance(value, dict):
        if set(value) <= {"country", "city", "admin_area"} and not value.get("city") and not value.get("admin_area"):
            return resolve(inputs, local_ids, value.get("country"), "country")
        return None
    key = normalized_place_wording(value)
    external = OWNER_DEFAULTS.get(key)
    if external is None:
        if context == "country":
            external = inputs["country_codes"].get(key.upper()) or inputs["country_names"].get(key)
        else:
            external = inputs[context].get(key)
    return local_ids.get(external)


def prepare(apps, connection):
    directory = Path(__file__).resolve().parents[2] / "data/geonames"
    for filename, expected in INPUT_HASHES.items():
        if hashlib.sha256((directory / filename).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen RG4 geographic input changed: " + filename)
    inputs = json.loads((directory / "resolution-inputs.json").read_bytes())
    documents, metadata, roots = load_pinned_geonames(directory)
    with transaction.atomic(using=connection.alias):
        local_ids = import_geonames_documents(apps, documents, country_metadata=metadata, selected_ids=roots)
        country_ids = {code: local_ids[external] for external, code in metadata.items() if external in local_ids}
        region_ids = {key: local_ids.get(external) for key, external in inputs["legacy_region_geonames_ids"].items()}
        preserve_labels_and_policies(apps, country_ids, region_ids)
    return inputs, local_ids, country_ids, region_ids


def preserve_labels_and_policies(apps, country_ids, region_ids):
    Country = apps.get_model("core", "Country")
    Region = apps.get_model("core", "Region")
    Name = apps.get_model("core", "GeolocationAlternateName")
    Place = apps.get_model("core", "Geolocation")
    Policy = apps.get_model("core", "GeolocationPolicy")
    Actor = apps.get_model("core", "Actor")
    country_rows = list(Country.objects.order_by("pk").values())
    labels = []
    for model, owner in (("CountryLabel", "country_id"), ("RegionLabel", "region_id")):
        labels.extend({"owner": owner, **row} for row in apps.get_model("core", model).objects.order_by(owner, "locale_reference_id").values())
    original = capture(apps, {
        "meaning": "Existing country display policy and translated wording; old membership is retired, not recreated.",
        "countries": country_rows, "regions": list(Region.objects.order_by("pk").values()), "labels": labels,
    })
    for row in labels:
        target = (country_ids if row["owner"] == "country_id" else region_ids).get(row[row["owner"]])
        if target is None:
            continue  # Exact source wording remains in the captured legacy catalogue.
        locale = row["locale_reference_id"]
        Name.objects.filter(geolocation_id=target, locale_id=locale).update(is_preferred=False)
        Name.objects.update_or_create(
            geolocation_id=target, locale_id=locale, name=row["label"],
            defaults={"is_preferred": True, "is_historical": False, "source_archive_id": original.pk},
        )
    actor, _ = Actor.objects.get_or_create(actor_kind="system", actor_key="rg4-geolocation-migration")
    for row in country_rows:
        parent_code = row["display_parent_country_id"]
        if not parent_code:
            continue
        location = Place.objects.get(pk=country_ids[row["code"]])
        if location.current_policy_id is not None:
            continue  # Import cannot supersede a local decision.
        taiwan = row["code"] == "TW"
        policy = Policy.objects.create(
            geolocation_id=location.pk, actor_id=actor.pk, decided_at=timezone.now(), source_archive_id=original.pk,
            dispute_state=1 if taiwan else 0, country_attribution=0,
            display_relationship=RELATIONSHIPS[row["display_parent_relationship_type"]],
            display_parent_id=country_ids[parent_code], flag_mode=1 if taiwan else 0, label_mode=1 if taiwan else 0,
        )
        Place.objects.filter(pk=location.pk).update(current_policy_id=policy.pk)


def map_rows(model, field, sources, interpret, *, batch_size=100, prepare_batch=None):
    """Keyset batches, current-row locks and no changes to source/hash fields."""
    # A just-added nullable indexed column has no statistics. PostgreSQL can
    # estimate IS NULL at 0.5% while it actually matches the whole table, then
    # repeatedly scan/sort that table instead of advancing through its PK.
    connection = connections[model.objects.db]
    prepare_post_index(connection, model._meta.db_table)
    quote = connection.ops.quote_name
    with connection.cursor() as statistics:
        statistics.execute(
            f"ANALYZE {quote(model._meta.db_table)} ({quote(model._meta.get_field(field).column)})"
        )
    cursor = None
    scanned = mapped = 0
    pending_index_rows = 0
    while True:
        with transaction.atomic(using=model.objects.db):
            with connection.cursor() as options:
                write_batch_options(options, model._meta.db_table)
            query = model.objects.filter(**{field + "__isnull": True}).order_by("pk")
            if cursor is not None:
                query = query.filter(pk__gt=cursor)
            rows = list(query.select_for_update().only("pk", field, *sources)[:batch_size])
            if not rows:
                break
            context = prepare_batch(rows) if prepare_batch else None
            changed = []
            for row in rows:
                target = interpret(row, context) if prepare_batch else interpret(row)
                if target is not None:
                    setattr(row, field + "_id", target)
                    changed.append(row)
            if changed:
                model.objects.bulk_update(changed, [field], batch_size=batch_size)
            cursor = rows[-1].pk
            scanned += len(rows)
            mapped += len(changed)
        pending_index_rows = finish_post_batch(
            connection, model._meta.db_table, pending_index_rows, len(changed),
        )
        if scanned % 5000 == 0:
            print(f"RG4 {model._meta.db_table}.{field}: scanned={scanned} mapped={mapped}", flush=True)
    finish_post_batch(connection, model._meta.db_table, pending_index_rows, finish=True)
    print(f"RG4 {model._meta.db_table}.{field}: complete scanned={scanned} mapped={mapped}", flush=True)


def forward(apps, schema_editor):
    with transaction.atomic(using=schema_editor.connection.alias):
        schema_editor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
        identity_triggers(schema_editor)
        home_count_update_trigger(apps, schema_editor)
    inputs, local_ids, country_ids, region_ids = prepare(apps, schema_editor.connection)
    def model(name):
        return apps.get_model("core", name)
    for name, field, raw in (
        ("Account", "profile_location", "location"),
        ("Post", "author_geolocation", "author_location"),
        ("AccountProfileSnapshot", "geolocation", "location"),
        ("PersonBrandAffiliation", "geolocation", "location"),
    ):
        map_rows(model(name), field, [raw], lambda row, source=raw: resolve(inputs, local_ids, getattr(row, source)))
    map_rows(model("Company"), "hq_geolocation", ["hq_country_reference"], lambda row: country_ids.get(row.hq_country_reference_id))
    map_rows(model("PersonCitizenship"), "geolocation", ["country"], lambda row: country_ids[row.country_id])
    map_rows(model("AccountBasedInMapping"), "geolocation", ["value"], lambda row: resolve(inputs, local_ids, row.value, "based_in"))
    # User About wording owns the current based-in claim. Never infer it from a
    # free-form profile or overwrite an existing explicitly selected place.
    def based_in_sources(rows):
        return dict(model("XAccountDetail").objects.select_for_update().filter(
            account_id__in=[row.pk for row in rows],
        ).values_list("account_id", "account_based_in"))

    def based_in_target(row, sources):
        value = sources.get(row.pk)
        if normalized_place_wording(value):
            return resolve(inputs, local_ids, value, "based_in")
        return country_ids.get(row.country_id) or region_ids.get(row.based_in_region_id)

    map_rows(
        model("Account"), "based_in_location", ["country", "based_in_region"],
        based_in_target, prepare_batch=based_in_sources,
    )
    for listing in model("JobListing").objects.only("id", "locations", "locations_raw").iterator(chunk_size=1000):
        with transaction.atomic(using=schema_editor.connection.alias):
            listing = model("JobListing").objects.select_for_update().get(pk=listing.pk)
            if model("JobListingLocation").objects.filter(listing_id=listing.pk).exists():
                continue
            values = listing.locations or ([listing.locations_raw] if listing.locations_raw and listing.locations_raw.strip() else [])
            if not isinstance(values, list):
                raise TypeError("A legacy job location is not an array")
            if not values:
                continue
            source = capture(apps, {"locations": listing.locations, "reported_value": listing.locations_raw})
            for ordinal, value in enumerate(values):
                model("JobListingLocation").objects.create(
                    listing_id=listing.pk, source_archive_id=source.pk, ordinal=ordinal,
                    observed_at=None, recorded_at=timezone.now(),
                    geolocation_id=resolve(inputs, local_ids, value),
                    reported_value=value if isinstance(value, str) else None,
                )
