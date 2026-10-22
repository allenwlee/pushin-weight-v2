"""Transactional dossier intake and completed reviews; no collection or model calls.

Review callers supply the exact claims used. Reading a historical review never
substitutes a live post's text for its preserved claim excerpts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import (
    CollectionObservation,
    EventClaimKind,
    EventDossier,
    EventDossierClaim,
    EventDossierReview,
    EventDossierReviewClaim,
    EventDossierSource,
    EventKind,
    ModelReleaseDetail,
    PersonBrandAffiliation,
    PersonnelChangeDetail,
    PersonnelChangeType,
    Post,
    ReleaseAccessChannel,
    ReleaseAvailabilityState,
    ReleaseDisclosureState,
    ReleaseMaturity,
    TimeZone,
)


class StaleReview(ValueError):
    """The caller's review base or evidence cutoff is no longer current."""


@dataclass(frozen=True)
class ClaimDecision:
    claim_id: UUID
    disposition: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class ModelReleaseInput:
    observed_name: str
    native_identifier: str
    product_key: UUID | None = None
    version_label: str | None = None
    variant: str | None = None
    release_channel: str = "unknown"
    availability_state: str = "unknown"
    disclosure_state: str = "unknown"
    release_issuer_company_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class PersonnelChangeInput:
    observed_person_name: str
    change_kind: str
    person_id: UUID | None = None
    from_affiliation_id: int | None = None
    to_affiliation_id: int | None = None
    from_organization_name: str | None = None
    to_organization_name: str | None = None
    from_title: str | None = None
    to_title: str | None = None


def _encode(value):
    if isinstance(value, datetime):
        _aware(value)
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (date, UUID, Decimal)):
        return str(value)
    raise TypeError(f"Unsupported dossier input: {type(value).__name__}")


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=_encode,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def identity_key(namespace: str, native_identity: str) -> str:
    if not namespace.strip() or not native_identity.strip():
        raise ValueError("Namespace and atomic native identity are required")
    return _digest(["event-dossier-key-v1", namespace, native_identity])


def _aware(value):
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise ValueError("Dossier timestamps must be timezone-aware")


def _validate(row):
    try:
        row.full_clean()
    except ValidationError as error:
        raise ValueError(str(error)) from error
    return row


def _insert(row):
    _validate(row)
    row.save(force_insert=True)
    return row


@transaction.atomic
def create_dossier(*, event_kind: str, identity_key: str) -> EventDossier:
    now = timezone.now()
    try:
        kind = EventKind.objects.get(code=event_kind)
    except EventKind.DoesNotExist as error:
        raise ValueError("Unknown event kind") from error
    row, created = EventDossier.objects.get_or_create(
        identity_key=identity_key,
        defaults={
            "event_kind_reference": kind,
            "first_seen_at": now,
            "last_seen_at": now,
        },
    )
    if row.event_kind_reference_id != kind.pk:
        raise ValueError("Dossier identity already belongs to another event kind")
    if created:
        _validate(row)
    return row


@transaction.atomic
def attach_source(
    dossier_id, *, post_id=None, observation_id=None
) -> EventDossierSource:
    if (post_id is None) == (observation_id is None):
        raise ValueError("Supply exactly one Post or CollectionObservation")
    event = EventDossier.objects.select_for_update().get(pk=dossier_id)
    if event.merged_into_id:
        raise ValueError("Attach sources to the canonical dossier")
    if observation_id is not None:
        observation = CollectionObservation.objects.get(pk=observation_id)
        if observation.post_id is not None:
            post_id, observation_id = observation.post_id, None
    if post_id is not None:
        Post.objects.get(pk=post_id)
    row, _ = EventDossierSource.objects.get_or_create(
        event_dossier=event,
        post_id=post_id,
        collection_observation_id=observation_id,
    )
    EventDossier.objects.filter(pk=event.pk).update(last_seen_at=timezone.now())
    return row


@transaction.atomic
def add_claim(
    source_id,
    *,
    claim_kind: str,
    scope_key: str,
    assertion_text: str,
    source_excerpt: str,
    extraction_version: str,
    source_locator: str | None = None,
    event_timezone: str | None = None,
    access_channel: str | None = None,
    effective_precision: str = "unknown",
    effective_at: datetime | None = None,
    effective_date: date | None = None,
    effective_year: int | None = None,
    effective_month: int | None = None,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> EventDossierClaim:
    source = EventDossierSource.objects.get(pk=source_id)
    try:
        kind = EventClaimKind.objects.get(code=claim_kind)
    except EventClaimKind.DoesNotExist as error:
        raise ValueError("Unknown dossier claim kind") from error
    if event_timezone:
        try:
            ZoneInfo(event_timezone)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Unknown event timezone") from error
        timezone_reference = TimeZone.objects.filter(pk=event_timezone).first()
        if timezone_reference is None:
            raise ValueError("Unregistered event timezone")
    else:
        timezone_reference = None
    if access_channel is not None:
        channel_reference = ReleaseAccessChannel.objects.filter(
            code=access_channel
        ).first()
        if channel_reference is None:
            raise ValueError("Unknown release access channel")
    else:
        channel_reference = None
    for value in (effective_at, not_before, not_after):
        if value is not None:
            _aware(value)
    values = {
        "event_dossier_source_id": source.pk,
        "claim_kind": claim_kind,
        "scope_key": scope_key,
        "assertion_text": assertion_text,
        "source_excerpt": source_excerpt,
        "extraction_version": extraction_version,
        "source_locator": source_locator,
        "event_timezone": event_timezone,
        "effective_precision": effective_precision,
        "effective_at": effective_at,
        "effective_date": effective_date,
        "effective_year": effective_year,
        "effective_month": effective_month,
        "not_before": not_before,
        "not_after": not_after,
        "source_hash": hashlib.sha256(source_excerpt.encode()).hexdigest(),
    }
    if access_channel is not None:
        values["access_channel"] = access_channel
    claim_hash = _digest(["event-dossier-claim-v1", values])
    # Serialize claims for this dossier as well as its source attachments/reviews.
    event = EventDossier.objects.select_for_update().get(pk=source.event_dossier_id)
    if event.merged_into_id:
        raise ValueError("Add claims to the canonical dossier")
    existing = EventDossierClaim.objects.filter(claim_hash=claim_hash).first()
    if existing:
        return existing
    values.pop("claim_kind")
    values.pop("event_timezone")
    values.pop("access_channel", None)
    return _insert(EventDossierClaim(
        claim_hash=claim_hash, claim_kind_reference=kind,
        event_timezone_reference=timezone_reference,
        release_access_channel_reference=channel_reference,
        **values,
    ))


@transaction.atomic
def complete_review(
    dossier_id,
    *,
    expected_current_review_id,
    display_title: str,
    review_state: str,
    evidence_cutoff_at: datetime,
    method_version: str,
    actor: str,
    reason: str,
    claims: list[ClaimDecision],
    model_release: ModelReleaseInput | None = None,
    personnel_change: PersonnelChangeInput | None = None,
    significance_score: Decimal | None = None,
    ranking_method: str = "",
    run_id: int | None = None,
    reviewed_at: datetime | None = None,
) -> EventDossierReview:
    _aware(evidence_cutoff_at)
    if reviewed_at is not None:
        _aware(reviewed_at)
    event = EventDossier.objects.select_for_update().get(pk=dossier_id)
    if event.merged_into_id:
        raise ValueError("Review the canonical dossier")
    if not claims or any(not isinstance(c, ClaimDecision) for c in claims):
        raise ValueError("A completed review needs explicit claim decisions")
    if len({str(c.claim_id) for c in claims}) != len(claims):
        raise ValueError("A claim may occur only once in a review")
    if (significance_score is None) != (not ranking_method):
        raise ValueError("A ranking score requires its ranking method")
    if event.event_kind_reference.code == "model_release":
        if (
            not isinstance(model_release, ModelReleaseInput)
            or personnel_change is not None
        ):
            raise ValueError("Model release kind requires only model details")
    elif (
        not isinstance(personnel_change, PersonnelChangeInput)
        or model_release is not None
    ):
        raise ValueError("Personnel kind requires only personnel details")
    decisions = sorted((asdict(c) for c in claims), key=lambda c: str(c["claim_id"]))
    decision = {
        "display_title": display_title,
        "review_state": review_state,
        "evidence_cutoff_at": evidence_cutoff_at,
        "method_version": method_version,
        "actor": actor,
        "reason": reason,
        "significance_score": significance_score,
        "ranking_method": ranking_method,
        "run_id": run_id,
    }
    digest = _digest(
        [
            "event-dossier-review-v1",
            decision,
            decisions,
            asdict(model_release) if model_release else None,
            asdict(personnel_change) if personnel_change else None,
            reviewed_at,
        ]
    )
    existing = event.reviews.filter(input_hash=digest).first()
    if existing:
        return existing
    expected = (
        UUID(str(expected_current_review_id))
        if expected_current_review_id is not None
        else None
    )
    if event.current_review_id != expected:
        raise StaleReview("The current dossier review changed; reassess this evidence")
    previous = event.current_review
    if previous and evidence_cutoff_at < previous.evidence_cutoff_at:
        raise StaleReview("An older evidence cutoff cannot replace the current review")
    evidence = list(
        EventDossierClaim.objects.select_related("event_dossier_source").filter(
            pk__in=[c.claim_id for c in claims]
        )
    )
    if len(evidence) != len(claims) or any(
        c.event_dossier_source.event_dossier_id != event.pk for c in evidence
    ):
        raise ValueError("Every claim must belong to this dossier")
    if any(
        c.recorded_at > evidence_cutoff_at
        or c.event_dossier_source.linked_at > evidence_cutoff_at
        for c in evidence
    ):
        raise ValueError("Review evidence was captured after its cutoff")
    now = timezone.now()
    saved = _insert(
        EventDossierReview(
            event_dossier=event,
            revision=previous.revision + 1 if previous else 1,
            supersedes=previous,
            input_hash=digest,
            reviewed_at=reviewed_at or now,
            recorded_at=now,
            **decision,
        )
    )
    for item in claims:
        _insert(
            EventDossierReviewClaim(
                review=saved,
                claim_id=item.claim_id,
                disposition=item.disposition,
                reason=item.reason,
            )
        )
    if model_release:
        detail = asdict(model_release)
        detail["product_id"] = detail.pop("product_key")
        detail["release_maturity_reference"] = ReleaseMaturity.objects.get(
            code=detail.pop("release_channel")
        )
        detail["release_availability_reference"] = ReleaseAvailabilityState.objects.get(
            code=detail.pop("availability_state")
        )
        detail["release_disclosure_reference"] = ReleaseDisclosureState.objects.get(
            code=detail.pop("disclosure_state")
        )
        _insert(ModelReleaseDetail(review=saved, **detail))
    else:
        detail = asdict(personnel_change)
        detail["change_type_reference"] = PersonnelChangeType.objects.get(
            code=detail.pop("change_kind")
        )
        roles = PersonBrandAffiliation.objects.filter(
            pk__in=[detail["from_affiliation_id"], detail["to_affiliation_id"]]
        )
        if any(role.person_id != detail["person_id"] for role in roles):
            raise ValueError("Personnel affiliations must belong to the same person")
        _insert(PersonnelChangeDetail(review=saved, **detail))
    EventDossier.objects.filter(pk=event.pk).update(current_review=saved)
    return saved


def _columns(row):
    if row is None:
        return None
    return {
        field.column: (
            _encode(value) if isinstance(value, (date, UUID, Decimal)) else value
        )
        for field in row._meta.concrete_fields
        for value in [getattr(row, field.attname)]
    }


def _release_columns(row):
    if row is None:
        return None
    result = _columns(row)
    for column, name, reference in (
        ("release_maturity_id", "release_channel", "release_maturity_reference"),
        ("availability_state_id", "availability_state", "release_availability_reference"),
        ("disclosure_state_id", "disclosure_state", "release_disclosure_reference"),
    ):
        result.pop(column)
        result[name] = getattr(row, reference).code
    return result


def _personnel_columns(row):
    if row is None:
        return None
    result = _columns(row)
    result.pop("change_kind_id")
    result["change_kind"] = row.change_type_reference.code
    return result


def _claim_columns(row):
    result = _columns(row)
    result.pop("claim_kind_id")
    result["claim_kind"] = row.claim_kind_reference.code
    result.pop("event_timezone_id")
    result["event_timezone"] = (
        row.event_timezone_reference.code if row.event_timezone_reference_id else None
    )
    result.pop("access_channel_id")
    result["access_channel"] = (
        row.release_access_channel_reference.code
        if row.release_access_channel_reference_id else None
    )
    return result


def read_dossier(dossier_id, *, review_id=None) -> dict:
    """Read the selected or named completed review with its frozen used claims.

    Announcement, repository, download and other milestone kinds remain separate
    claims. No release timestamp, normalized measurement or projection is inferred.
    """
    event = EventDossier.objects.get(pk=dossier_id)
    dossier = _columns(event)
    dossier.pop("event_kind_id")
    dossier["event_kind"] = event.event_kind_reference.code
    selected_id = review_id if review_id is not None else event.current_review_id
    if selected_id is None:
        return {
            "dossier": dossier,
            "review": None,
            "claims": [],
            "sources": [],
            "model_release": None,
            "personnel_change": None,
        }
    saved = event.reviews.get(pk=selected_id)
    decisions = saved.claim_decisions.select_related(
        "claim__event_dossier_source", "claim__claim_kind_reference",
        "claim__event_timezone_reference", "claim__release_access_channel_reference",
    ).order_by("claim_id")
    claims, sources = [], {}
    for decision in decisions:
        source = decision.claim.event_dossier_source
        claims.append(
            {
                **_claim_columns(decision.claim),
                "disposition": decision.disposition,
                "disposition_reason": decision.reason,
            }
        )
        sources[source.pk] = _columns(source)
    return {
        "dossier": dossier,
        "review": _columns(saved),
        "claims": claims,
        "sources": [sources[key] for key in sorted(sources)],
        "model_release": _release_columns(getattr(saved, "model_release", None)),
        "personnel_change": _personnel_columns(getattr(saved, "personnel_change", None)),
    }
