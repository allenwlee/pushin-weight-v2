"""Strict ingestion-only source interpretation; unknown claims stay NULL.

The approved mapping input is bounded. A name being unique in our partial place
cache is not evidence that it is unique in the world. Provider aliases are never
automatically promoted into accepted free-form matches.
"""

import json
from functools import lru_cache
from pathlib import Path

from core.geolocations import normalized_place_wording, owner_default_geonames_id
from core.models import Geolocation


@lru_cache(maxsize=1)
def reviewed_location_inputs():
    return json.loads((Path(__file__).resolve().parent.parent / "data/geonames/resolution-inputs.json").read_text())


def source_geonames_id(value, *, context="freeform"):
    """Return an external import identity only for a reviewed source value."""
    if context not in {"freeform", "based_in", "country"}:
        raise ValueError("Unknown geography source context")
    if isinstance(value, dict):
        # A real country-only source object establishes that precision. Do not
        # stringify it, discard unknown keys, or silently coarsen a city claim.
        if set(value) <= {"country", "city", "admin_area"} and not value.get("city") and not value.get("admin_area"):
            return source_geonames_id(value.get("country"), context="country")
        return None
    wording = normalized_place_wording(value)
    if not wording:
        return None
    default = owner_default_geonames_id(wording)
    if default is not None:
        return default
    inputs = reviewed_location_inputs()
    if context == "country":
        code = value.strip().upper() if isinstance(value, str) else ""
        return inputs["country_codes"].get(code) or inputs["country_names"].get(wording)
    if context == "based_in":
        return inputs["based_in"].get(wording)
    return inputs["freeform"].get(wording)


def resolve_geolocation(value, *, context="freeform"):
    """Translate reviewed source wording to a cached local PK; never fetch."""
    identifier = source_geonames_id(value, context=context)
    if identifier is None:
        return None
    return Geolocation.objects.filter(geonames_id=identifier).values_list("pk", flat=True).first()
