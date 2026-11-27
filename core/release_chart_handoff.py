"""Read the canonical release evidence shared by the collector and public chart."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from core.measurement_taxonomy import digest
from core.models import (
    EventDossier,
    EventDossierClaim,
    EventDossierReviewClaim,
    ProductReleaseDetail,
)
from core.product_release_dossiers import _read_pulse_packet
from core.product_release_pipeline import canonical_dossier


@dataclass(frozen=True)
class QualifiedRelease:
    dossier_id: UUID
    product_key: UUID
    brand_id: str
    date: date
    precision: str
    effective_at: datetime | None
    source: str
    claim_id: UUID
    review_id: UUID | None
    issuer_company_id: str | None
    fingerprint: str
    milestone_kind: str


_DATE_KINDS = ("source_stated_release", "announcement", "release_report")


def _bounded(rows, limit=256):
    result = list(rows[: limit + 1])
    if len(result) > limit:
        raise ValueError("Release evidence exceeds the bounded selection")
    return result


def _day(claim):
    if claim.effective_precision == "day":
        return claim.effective_date
    if claim.effective_precision == "datetime" and claim.effective_at:
        return claim.effective_at.astimezone(UTC).date()
    return None


def _dated_claim(rows, cutoff):
    # A publisher can announce on a different day from the stated release.
    # Within the same milestone, conflicting dates require resolution.
    for kind in _DATE_KINDS:
        relevant = [r for r in rows if r.claim_kind_reference.code == kind and _day(r)]
        if not relevant:
            continue
        instants = {r.effective_at for r in relevant if r.effective_at is not None}
        if len({_day(r) for r in relevant}) != 1 or len(instants) > 1:
            raise ValueError("Release evidence has conflicting dates")
        chosen = min(
            relevant, key=lambda r: (r.effective_at is None, r.recorded_at, str(r.pk))
        )
        if _day(chosen) > cutoff.astimezone(UTC).date() or (
            chosen.effective_at and chosen.effective_at > cutoff
        ):
            raise ValueError("Release milestone is after the requested cutoff")
        return chosen
    raise ValueError("Release has no qualified day or instant")


def _finding_evidence(claims, cutoff):
    """Use revision-bound projections where available, including on the web login."""
    grouped = defaultdict(list)
    anchors = {}
    for claim in claims:
        if not claim.source_archive_id:
            continue
        grouped[claim.event_dossier_source_id, claim.source_archive_id].append(claim)
        if not re.fullmatch(r"pulse-finding-v1:[0-9a-f]{64}", claim.scope_key):
            continue
        if not re.fullmatch(r"pulse-classified-findings-v1:[0-9a-f]{64}", claim.extraction_version):
            raise ValueError("Invalid release finding revision")
        group = (claim.event_dossier_source_id, claim.scope_key)
        previous = anchors.get(group)
        if previous is None or (claim.recorded_at, claim.pk) > (previous.recorded_at, previous.pk):
            anchors[group] = claim

    from core.pulse_readers import _latest_release_manifest

    # Publication can withdraw a finding with an empty saved manifest; even a
    # still-current anchor in this dossier must then stop supplying chart evidence.
    manifests = dict(EventDossierClaim.objects.filter(pk__in=[row.pk for row in anchors.values()])
                     .annotate(keys=Subquery(_latest_release_manifest(OuterRef("event_dossier_source__post_id"),
                                                                      cutoff=cutoff))).values_list("pk", "keys"))
    can_read_archive = None
    for anchor in anchors.values():
        key = anchor.scope_key.removeprefix("pulse-finding-v1:")
        manifest = manifests.get(anchor.pk)
        if manifest is not None and key not in manifest:
            continue
        archive = anchor.source_archive
        siblings = grouped[anchor.event_dossier_source_id, anchor.source_archive_id]
        if archive.capture_kind != "product_release_intake" or archive.encoding != "selected-json-canonical-v1":
            raise ValueError("Unexpected release finding archive")
        subtypes = [row.assertion_text for row in siblings if row.scope_key == f"pulse-novelty-v1:{key}"
                    and row.claim_kind_reference.code == "release_context"
                    and row.extraction_version == anchor.extraction_version]
        if subtypes:
            if len(subtypes) != 1 or subtypes[0] not in {"new_release", "historical_release", "availability_update", "unresolved"}:
                raise ValueError("Conflicting release subtype")
            yield anchor, siblings, subtypes[0], None
            continue
        if can_read_archive is None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT has_column_privilege(current_user, 'collection_evidence_archives', 'body', 'SELECT')")
                can_read_archive = cursor.fetchone()[0]
        finding = _read_pulse_packet(anchor)["finding"] if can_read_archive and archive.byte_count <= 512 * 1024 else None
        yield anchor, siblings, finding["novelty"] if finding else None, finding


def _assertion_claims(finding, siblings, anchor):
    # The producer keys each persisted assertion by the checksum of its exact archived row.
    evidence = {}
    for assertion in finding["assertions"]:
        if not isinstance(assertion, dict):
            raise ValueError("Invalid saved milestone")  # noqa: TRY004 - malformed persisted evidence
        body = json.dumps(
            assertion, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        suffix = hashlib.sha256(body).hexdigest()
        evidence[f"pulse-assertion-v1:{finding['finding_key']}:{suffix}"] = assertion
    for row in siblings:
        assertion = evidence.get(row.scope_key)
        if assertion is None or row.extraction_version != anchor.extraction_version:
            continue
        if (
            row.claim_kind_reference.code != assertion.get("claim_kind")
            or row.effective_precision != assertion.get("effective_precision")
            or (row.effective_date and row.effective_date.isoformat())
            != assertion.get("effective_date")
            or row.effective_at
            != (
                datetime.fromisoformat(assertion["effective_at"])
                if assertion.get("effective_at")
                else None
            )
        ):
            raise ValueError("Saved milestone disagrees with its source assertion")
        yield row


def _p2_evidence(claims, cutoff):
    """Read exact Product and version membership written by P2 for each declared release."""
    product_versions = set()
    identity_hashes = []
    milestones = []
    product = None
    for anchor, siblings, subtype, finding in _finding_evidence(claims, cutoff):
        if subtype not in {"new_release", "historical_release", "availability_update"}:
            continue
        key = anchor.scope_key.removeprefix("pulse-finding-v1:")
        prefix = f"pulse-event-member-v1:{key}:"
        members = [row for row in siblings if row.scope_key.startswith(prefix)
                   and row.extraction_version == "pulse-event-identity-v1" and row.reported_product_id]
        identities = {row.reported_product_id for row in siblings if row.scope_key == f"pulse-self-identity-v1:{key}"
                      and row.extraction_version == "pulse-product-identity-v1"}
        if not members and not identities:
            continue
        if len(members) != 1 or identities != {members[0].reported_product_id}:
            raise ValueError("Exact P2 release identity is pending or conflicting")
        member = members[0]
        suffix = member.scope_key.removeprefix(prefix)
        product = member.reported_product
        if not re.fullmatch(r"[0-9a-f]{64}", suffix) or anchor.reported_brand_id not in (None, product.brand_id):
            raise ValueError("Product version or owner conflicts with qualified release")
        product_versions.add((product.product_key, suffix))
        identity_hashes.append(member.claim_hash)
        if subtype == "availability_update":
            continue
        if finding is not None:
            from core.product_identity import _event_identity_hash

            if _event_identity_hash(product, finding) != suffix:
                raise ValueError("Product version conflicts with release archive")
            milestones.extend(_assertion_claims(finding, siblings, anchor))
        else:
            # Both projections and assertions were written from the same validated
            # source packet. Match source, archive, finding key and producer revision.
            assertion_prefix = f"pulse-assertion-v1:{key}:"
            milestones.extend(row for row in siblings if row.extraction_version == anchor.extraction_version
                              and row.scope_key.startswith(assertion_prefix)
                              and re.fullmatch(r"[0-9a-f]{64}", row.scope_key.removeprefix(assertion_prefix)))
    if len(product_versions) == 1:
        milestones.extend(row for row in claims if row.extraction_version == "pulse-historical-announcement-v1"
                          and row.scope_key == f"pulse-history-v1:{product.product_key}"
                          and row.reported_product_id == product.pk and row.reported_brand_id == product.brand_id
                          and row.event_dossier_source.post_id is not None
                          and row.claim_kind_reference.code in {"announcement", "source_stated_release"})
    if not product_versions:
        return None, [], []
    if len(product_versions) != 1:
        raise ValueError("Release has no unique qualified P2 product and milestone")
    return product, milestones, sorted(identity_hashes)


def _release_claims(event, cutoff):
    return (
        EventDossierClaim.objects.filter(
            event_dossier_source__event_dossier=event,
            event_dossier_source__linked_at__lte=cutoff,
            recorded_at__lte=cutoff,
        )
        .select_related(
            "source_archive",
            "event_dossier_source",
            "reported_product",
            "claim_kind_reference",
        )
        .defer("source_archive__body")
    )


def selected_p2_product(event_id):
    """Return current P2 identity even while its launch date is pending."""
    now = timezone.now()
    event = canonical_dossier(event_id)
    product, _, _ = _p2_evidence(_bounded(_release_claims(event, now)), now)
    return product


def resolve_release(dossier_id, *, cutoff=None):
    """Resolve current public release evidence as of an aware cutoff, without writes or network."""
    cutoff = timezone.now() if cutoff is None else cutoff
    if not isinstance(cutoff, datetime) or timezone.is_naive(cutoff):
        raise ValueError("Release cutoff must include a timezone")
    try:
        event = canonical_dossier(dossier_id)
    except (EventDossier.DoesNotExist, ValidationError, TypeError) as exc:
        raise ValueError("Unknown release") from exc
    if event.event_kind_reference.code != "product_release":
        raise ValueError("Dossier is not a product release")
    review = event.current_review
    latest = event.intake_decisions.order_by("-recorded_at", "-pk").first()
    if (
        latest
        and latest.outcome in {"scam", "non_release", "superseded"}
        and (not review or latest.recorded_at >= review.recorded_at)
    ):
        raise ValueError("Release intake is inactive")
    claims = _release_claims(event, cutoff)
    identity_hashes = []
    issuer_company = None
    if review:
        if review.review_state != "confirmed" or review.recorded_at > cutoff:
            raise ValueError("A current confirmed release review is required")
        detail = (
            ProductReleaseDetail.objects.select_related("product")
            .filter(review=review)
            .first()
        )
        if (
            detail is None
            or not detail.product_id
            or detail.disclosure_state == "unannounced"
        ):
            raise ValueError("Public release product is unresolved")
        product, issuer_company = detail.product, detail.release_issuer_company_id
        dates = _bounded(
            claims.filter(
                review_decisions__review=review,
                review_decisions__disposition="accepted",
                claim_kind_reference__code__in=_DATE_KINDS,
            )
        )
        approved_anchors = set(_bounded(EventDossierReviewClaim.objects.filter(
            review=review, disposition="accepted", claim__scope_key__startswith="pulse-finding-v1:",
        ).values_list("claim_id", flat=True)))
        if approved_anchors:
            anchors_and_subtypes = claims.filter(
                Q(scope_key__startswith="pulse-finding-v1:") | Q(scope_key__startswith="pulse-novelty-v1:"),
            )
            evidence = [(anchor, subtype) for anchor, _, subtype, _ in _finding_evidence(_bounded(anchors_and_subtypes), cutoff)
                        if anchor.pk in approved_anchors]
        else:
            evidence = []
        update_sources, other_sources, update_packets = set(), set(), set()
        for anchor, subtype in evidence:
            source_id = anchor.event_dossier_source_id
            if subtype == "availability_update":
                update_sources.add(source_id)
                key = anchor.scope_key.removeprefix("pulse-finding-v1:")
                update_packets.add((source_id, anchor.source_archive_id, anchor.extraction_version, key))
            else:
                other_sources.add(source_id)
        # A review can accept both a launch and a subsequent announcement of
        # API availability. A roundup can contain both findings on one source.
        update_only_sources = update_sources - other_sources
        dates = [
            row for row in dates if row.event_dossier_source_id not in update_only_sources
            and not (row.scope_key.startswith(("pulse-assertion-v1:", "pulse-finding-v1:"))
                     and (row.event_dossier_source_id, row.source_archive_id, row.extraction_version,
                          row.scope_key.split(":", 2)[1]) in update_packets)
        ]
        if any(
            row.reported_product_id not in (None, product.pk)
            or row.reported_brand_id not in (None, product.brand_id)
            for row in dates
        ):
            raise ValueError("Accepted claim conflicts with reviewed Product")
        source = "dossier-reviewed"
    else:
        product, dates, identity_hashes = _p2_evidence(_bounded(claims), cutoff)
        if product is None or not dates:
            raise ValueError("Release has no unique qualified P2 product and milestone")
        source = "p2-qualified"
    if product.brand_id and product.display_name and not product.repo_id:
        from core.product_preview_names import preview_redirects

        redirects = preview_redirects(
            [(product.pk, product.brand_id, product.display_name)], cutoff=cutoff, strict=True
        )
        if product.pk in redirects:
            product = type(product).objects.select_related("brand").get(pk=redirects[product.pk])
    if (
        not product.brand_id
        or product.brand.is_sentinel
        or product.private
        or product.disabled
    ):
        raise ValueError("Release lacks a public tracked Product")
    claim = _dated_claim(dates, cutoff)
    day = _day(claim)
    fingerprint = digest(
        [
            str(event.pk),
            str(product.product_key),
            str(event.current_review_id or ""),
            str(claim.pk),
            claim.claim_hash,
            source,
            day.isoformat(),
            identity_hashes,
        ]
    )
    return QualifiedRelease(
        event.pk,
        product.product_key,
        product.brand_id,
        day,
        claim.effective_precision,
        claim.effective_at,
        source,
        claim.pk,
        event.current_review_id,
        issuer_company,
        fingerprint,
        claim.claim_kind_reference.code,
    )


def lock_qualified_release(dossier_id, *, fingerprint):
    """Hold the lock used by dossier merges, reviews and claim writers through this write."""
    if not connection.in_atomic_block:
        raise ValueError("Release revalidation requires an active transaction")
    try:
        event = EventDossier.objects.select_for_update().get(pk=dossier_id)
    except EventDossier.DoesNotExist as exc:
        raise ValueError("Unknown release") from exc
    if event.merged_into_id:
        raise ValueError("Release was merged after preparation")
    current = resolve_release(event.pk)
    if current.fingerprint != fingerprint:
        raise ValueError("Release evidence changed after preparation")
    return current
