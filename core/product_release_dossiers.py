"""Idempotent transfer of saved product-release reports into EventDossiers.

The archived packet preserves the exact legacy extraction and its clocks. The
claim and its typed references are the ordinary read surface; packets are only
for audit and correction. This module makes no provider or model calls.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.collection_capture import archive_document
from core.event_dossiers import identity_key
from core.models import (
    EventClaimKind,
    EventDossier,
    EventDossierClaim,
    EventDossierSource,
    EventKind,
    ModelRelease,
    ProductVerificationProposal,
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


RELEASE_FIELDS = frozenset(
    {
        "id",
        "brand_id",
        "brand_discovery_candidate_id",
        "observed_model_name",
        "version",
        "release_maturity_id",
        "release_value",
        "release_precision",
        "release_identity",
        "first_seen_at",
        "last_seen_at",
        "extraction_version",
        "review_status",
        "created_at",
        "updated_at",
    }
)
EVIDENCE_FIELDS = frozenset(
    {
        "id",
        "release_id",
        "source_post_id",
        "source_url",
        "observed_at",
        "observed_claim",
        "evidence_hash",
        "extraction_version",
        "created_at",
    }
)


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported release packet value: {type(value).__name__}")


def _row(row, fields):
    values = {
        field.column: getattr(row, field.attname)
        for field in row._meta.concrete_fields
        if field.column in fields
    }
    if values.keys() != fields:
        raise ValueError(f"Unexpected legacy row shape: {fields ^ values.keys()}")
    return values


def _packet(release, evidence):
    _validate_record(evidence.observed_claim)
    release_values = _row(release, RELEASE_FIELDS)
    evidence_values = _row(evidence, EVIDENCE_FIELDS)
    if (
        evidence_values["release_id"] != release.pk
        or release_values["release_identity"] != release.release_identity
    ):
        raise ValueError("Release packet identity mismatch")
    document = {
        "schema": "product-release-legacy-v1",
        "release": release_values,
        "evidence": evidence_values,
    }
    body = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
        allow_nan=False,
    ).encode("utf-8")
    # The strict key sets above are checked for historical and fresh packets.
    return archive_document(
        body,
        encoding="legacy-json-canonical-v1",
        capture_kind="product_release_legacy",
    )


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
    # During the cutover, an old report may predate this fresh observation.
    legacy = ModelRelease.objects.filter(release_identity=release_identity).first()
    if legacy is not None and legacy.review_status != "pending":
        raise ValueError("Reviewed legacy release needs an explicit review mapping")
    first_seen_at = legacy.first_seen_at if legacy else post.fetched_at
    last_seen_at = (
        max(legacy.last_seen_at, post.fetched_at) if legacy else post.fetched_at
    )
    dossier, created = EventDossier.objects.get_or_create(
        identity_key=key,
        defaults={
            "event_kind_reference": kind,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "created_at": legacy.created_at if legacy else now,
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


@transaction.atomic
def transfer_release(release_id: int) -> tuple[int, int]:
    """Map one locked legacy release and every saved evidence/proposal row."""
    release = ModelRelease.objects.select_for_update().get(pk=release_id)
    if release.review_status != "pending":
        raise ValueError("Reviewed legacy release needs an explicit review mapping")
    kind = EventKind.objects.filter(code="product_release").first()
    if kind is None:
        kind = EventKind.objects.get(code="model_release")
    claim_kind = EventClaimKind.objects.get(code="release_report")
    key = identity_key("product-release-v1", release.release_identity)
    dossier, created = EventDossier.objects.get_or_create(
        identity_key=key,
        defaults={
            "event_kind_reference": kind,
            "first_seen_at": release.first_seen_at,
            "last_seen_at": release.last_seen_at,
            "created_at": release.created_at,
        },
    )
    dossier = EventDossier.objects.select_for_update().get(pk=dossier.pk)
    if dossier.event_kind_reference_id != kind.pk:
        raise ValueError("Release identity belongs to another dossier kind")
    if dossier.first_seen_at != release.first_seen_at:
        raise ValueError("Release first-seen clock changed after dossier creation")
    evidence_rows = list(
        release.evidence.select_for_update()
        .select_related("source_post")
        .order_by("pk")
    )
    if not evidence_rows:
        raise ValueError(f"Release {release.pk} has no source evidence")
    new_claims = 0
    for evidence in evidence_rows:
        source, _ = EventDossierSource.objects.get_or_create(
            event_dossier=dossier,
            post_id=evidence.source_post_id,
            defaults={"linked_at": evidence.created_at},
        )
        archive = _packet(release, evidence)
        excerpt = evidence.source_post.text or evidence.observed_claim.get("model_name")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ValueError(f"Release evidence {evidence.pk} has no excerpt")
        claim_hash = hashlib.sha256(
            f"product-release-evidence-v1:{evidence.pk}:{archive.content_sha256}".encode()
        ).hexdigest()
        claim, inserted = EventDossierClaim.objects.get_or_create(
            claim_hash=claim_hash,
            defaults={
                "event_dossier_source": source,
                "claim_kind_reference": claim_kind,
                "source_archive": archive,
                "reported_brand_id": release.brand_id,
                "reported_brand_discovery_candidate_id": release.brand_discovery_candidate_id,
                "release_maturity_reference_id": release.release_maturity_reference_id,
                "scope_key": release.release_identity,
                "extraction_version": evidence.extraction_version,
                "recorded_at": evidence.created_at,
                "assertion_text": release.observed_model_name,
                "source_excerpt": excerpt,
                "source_locator": evidence.source_url,
                "source_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
                **_effective_fields(release.release_value, release.release_precision),
            },
        )
        if (
            claim.event_dossier_source_id != source.pk
            or claim.source_archive_id != archive.pk
        ):
            raise ValueError("Release evidence hash collision or owner mismatch")
        if evidence.rg7_claim_id != claim.pk:
            evidence.rg7_claim = claim
            evidence.save(update_fields=["rg7_claim"])
        new_claims += int(inserted)
    if dossier.last_seen_at < release.last_seen_at:
        EventDossier.objects.filter(pk=dossier.pk).update(
            last_seen_at=release.last_seen_at
        )
    if release.rg7_dossier_id != dossier.pk:
        release.rg7_dossier = dossier
        release.save(update_fields=["rg7_dossier"])
    ProductVerificationProposal.objects.filter(source_release=release).exclude(
        source_dossier=dossier
    ).update(source_dossier=dossier)
    return int(created), new_claims


def pending_release_ids(*, limit: int = 100) -> list[int]:
    """The mapping columns are durable replay cursors invalidated by old writers."""
    return list(
        ModelRelease.objects.filter(
            Q(rg7_dossier__isnull=True)
            | Q(evidence__id__isnull=False, evidence__rg7_claim__isnull=True)
            | Q(
                product_verification_proposals__id__isnull=False,
                product_verification_proposals__source_dossier__isnull=True,
            ),
        )
        .order_by("pk")
        .values_list("pk", flat=True)
        .distinct()[:limit]
    )


def transfer_pending(*, batch_size: int = 100) -> dict[str, int]:
    result = {"releases": 0, "dossiers_created": 0, "claims_created": 0}
    while ids := pending_release_ids(limit=batch_size):
        for release_id in ids:
            dossiers, claims = transfer_release(release_id)
            result["releases"] += 1
            result["dossiers_created"] += dossiers
            result["claims_created"] += claims
    return result
