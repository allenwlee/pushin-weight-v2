"""Persist fresh product-release reports as typed EventDossier claims.

The immutable intake packet preserves source wording for audit and correction.
This module makes no provider or model calls.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date

from django.db import transaction
from django.utils import timezone

from core.collection_capture import archive_document
from core.event_dossiers import identity_key
from core.models import (
    EventClaimKind,
    EventDossier,
    EventDossierClaim,
    EventDossierSource,
    EventKind,
    ReleaseMaturity,
)

CLAIM_FIELDS = frozenset(
    {
        "organization_name",
        "organization_handle",
        "release_precision",
        "brand_id",
        "source_url",
        "version",
        "release_value",
        "model_name",
        "candidate_repo_id",
        "categories",
        "confidence",
        "release_channel",
    }
)


def _validate_record(record):
    if not isinstance(record, dict) or not record.keys() <= CLAIM_FIELDS:
        raise ValueError("Unreviewed product-release extraction keys")
    if (
        not isinstance(record.get("model_name"), str)
        or not record["model_name"].strip()
    ):
        raise ValueError("Product-release extraction needs a model name")
    for name in (
        "organization_name",
        "organization_handle",
        "brand_id",
        "source_url",
        "version",
        "release_value",
        "candidate_repo_id",
        "release_channel",
        "release_precision",
    ):
        if (
            name in record
            and record[name] is not None
            and not isinstance(record[name], str)
        ):
            raise ValueError(f"Invalid product-release extraction {name}")
    if "categories" in record and (
        not isinstance(record["categories"], list)
        or any(not isinstance(value, str) for value in record["categories"])
    ):
        raise ValueError("Invalid product-release categories")
    if "confidence" in record and record["confidence"] is not None:
        if isinstance(record["confidence"], bool):
            raise ValueError("Invalid product-release confidence")
        qualitative = isinstance(record["confidence"], str) and record[
            "confidence"
        ] in {"low", "medium", "high"}
        if not qualitative:
            try:
                confidence = float(record["confidence"])
            except (TypeError, ValueError) as error:
                raise ValueError("Invalid product-release confidence") from error
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Invalid product-release confidence")
    return record


def _effective_fields(value, precision):
    fields = {"effective_precision": precision}
    if precision == "unknown":
        if value is not None:
            raise ValueError("Unknown release date must have no value")
    elif precision == "day":
        fields["effective_date"] = date.fromisoformat(value)
    elif precision == "month":
        year, month = value.split("-")
        fields.update(effective_year=int(year), effective_month=int(month))
    elif precision == "year":
        fields["effective_year"] = int(value)
    else:
        raise ValueError(f"Unsupported release date precision: {precision}")
    return fields


@transaction.atomic
def record_release_report(
    *,
    post,
    record,
    release_identity,
    observed_name,
    source_url,
    brand=None,
    candidate=None,
    maturity_code,
    release_value,
    release_precision,
    extraction_version,
):
    """Save one fresh source claim without writing the retired prototype tables."""
    if (brand is None) == (candidate is None):
        raise ValueError("Release report needs exactly one original owner")
    _validate_record(record)
    packet = {
        "schema": "product-release-intake-v1",
        "record": record,
        "source_post_id": post.pk,
        "release_identity": release_identity,
        "extraction_version": extraction_version,
    }
    body = json.dumps(
        packet, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    archive = archive_document(
        body,
        encoding="selected-json-canonical-v1",
        capture_kind="product_release_intake",
    )
    kind = EventKind.objects.get(code="product_release")
    key = identity_key("product-release-v1", release_identity)
    now = timezone.now()
    first_seen_at = post.fetched_at
    last_seen_at = post.fetched_at
    dossier, created = EventDossier.objects.get_or_create(
        identity_key=key,
        defaults={
            "event_kind_reference": kind,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "created_at": now,
        },
    )
    dossier = EventDossier.objects.select_for_update().get(pk=dossier.pk)
    if dossier.event_kind_reference_id != kind.pk:
        raise ValueError("Release report identity belongs to another kind")
    source, _ = EventDossierSource.objects.get_or_create(
        event_dossier=dossier, post=post, defaults={"linked_at": now}
    )
    excerpt = post.text or observed_name
    if not excerpt.strip():
        raise ValueError("Release report has no source excerpt")
    claim_hash = hashlib.sha256(
        f"product-release-intake-v1:{post.pk}:{archive.content_sha256}".encode()
    ).hexdigest()
    claim, claim_created = EventDossierClaim.objects.get_or_create(
        claim_hash=claim_hash,
        defaults={
            "event_dossier_source": source,
            "claim_kind_reference": EventClaimKind.objects.get(code="release_report"),
            "source_archive": archive,
            "reported_brand": brand,
            "reported_brand_discovery_candidate": candidate,
            "release_maturity_reference": ReleaseMaturity.objects.get(
                code=maturity_code
            ),
            "scope_key": release_identity,
            "extraction_version": extraction_version,
            "recorded_at": now,
            "assertion_text": observed_name,
            "source_excerpt": excerpt,
            "source_locator": source_url,
            "source_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
            **_effective_fields(release_value, release_precision),
        },
    )
    if (
        claim.event_dossier_source_id != source.pk
        or claim.source_archive_id != archive.pk
    ):
        raise ValueError("Release report claim identity collision")
    if dossier.last_seen_at < post.fetched_at:
        EventDossier.objects.filter(pk=dossier.pk).update(last_seen_at=post.fetched_at)
    return dossier, created, claim_created
