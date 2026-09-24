"""Source-only Product updates. Callers retain their own qualification rules."""

from __future__ import annotations

from copy import deepcopy

from django.db import transaction
from django.utils import timezone

from core.models import Product

FIELD_KEYS = {
    "author": ("author",),
    "sha": ("sha",),
    "private": ("private",),
    "gated": ("gated",),
    "disabled": ("disabled",),
    "pipeline_tag": ("pipeline_tag", "pipelineTag"),
    "library_name": ("library_name", "libraryName"),
    "downloads": ("downloads",),
    "downloads_all_time": ("downloads_all_time", "downloadsAllTime"),
    "likes": ("likes",),
    "trending_score": ("trending_score", "trendingScore"),
    "paperswithcode_id": ("paperswithcode_id", "paperswithcodeId"),
    "created_at": ("created_at", "createdAt"),
    "last_modified": ("last_modified", "lastModified"),
    "tags": ("tags",),
    "siblings": ("siblings",),
    "card_data": ("card_data", "cardData"),
    "config": ("config",),
    "spaces": ("spaces",),
}
ALIASES = {key: keys[0] for keys in FIELD_KEYS.values() for key in keys}


def source_fields(payload):
    return {
        field: next(payload[key] for key in keys if key in payload)
        for field, keys in FIELD_KEYS.items()
        if any(key in payload for key in keys)
    }


def priority(key, group):
    if key == "siblings":
        return {"listing": 0, "expanded": 2, "detail": 3}[group]
    return {"listing": 0, "detail": 2, "expanded": 3}[group]


@transaction.atomic
def apply_metadata(product, payload, *, group, observation=None):
    """Reload under lock; never save curated fields from a caller's stale object."""
    current = Product.objects.select_for_update().get(pk=product.pk)
    metadata = deepcopy(current.hf_metadata or {})
    fields = metadata.setdefault("fields", {})
    owners = metadata.setdefault("field_sources", {})
    raw = dict(current.raw or {})
    # Rows imported before the ledger migration have no field provenance. Their
    # existing rich columns must not be flattened by the first lean listing.
    for column in ("siblings", "card_data", "config", "spaces"):
        key = FIELD_KEYS[column][0]
        value = getattr(current, column)
        if key not in owners and value is not None:
            fields[key] = value
            owners[key] = "detail"
    accepted = {}
    for key, value in payload.items():
        canonical = ALIASES.get(key, key)
        old = owners.get(canonical)
        if old and priority(canonical, group) < priority(canonical, old):
            continue
        fields[canonical] = value
        owners[canonical] = group
        accepted[key] = value
        # Remove stale spelling of the same provider key; preserve all other evidence.
        for alias, target in ALIASES.items():
            if target == canonical and alias != key:
                raw.pop(alias, None)
        raw[key] = value
    metadata.setdefault("groups", {})[group] = {
        "observed_at": timezone.now().isoformat(),
        "sha": payload.get("sha"),
        "observation": deepcopy(observation),
    }
    values = source_fields(accepted)
    values.update(raw=raw, hf_metadata=metadata)
    for field, value in values.items():
        setattr(current, field, value)
    current.save(update_fields=[*values, "updated_at"])
    return current
