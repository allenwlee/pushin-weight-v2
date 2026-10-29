"""Persist inclusive source candidates and explicitly reconcile release identities.

Detection creates pending evidence. Confirmation is a separate evidenced review,
which must establish the publisher and its control of the announcing account.
"""

from __future__ import annotations

import re
from dataclasses import asdict

from django.db import connection, transaction

from core import models
from core.event_dossiers import (
    ClaimDecision,
    ProductReleaseInput,
    _digest,
    add_claim,
    attach_source,
    complete_review,
    create_dossier,
    identity_key,
)
from core.product_release_intake import detect
from core.product_release_milestones import METHOD as MILESTONE_METHOD
from core.product_release_milestones import extract_milestones
from core.product_release_sources import StoredSource

METHOD = "product-release-persistence-v1"


def canonical_dossier(dossier_id):
    seen = set()
    while dossier_id not in seen:
        seen.add(dossier_id)
        row = models.EventDossier.objects.get(pk=dossier_id)
        if row.merged_into_id is None:
            return row
        dossier_id = row.merged_into_id
    raise ValueError("Existing dossier merge cycle")


@transaction.atomic
def record_intake_decision(
    dossier_id, *, claim_id, outcome, actor, reason, method_version=METHOD
):
    if outcome not in {"pending", "non_release", "scam", "superseded"}:
        raise ValueError("Unknown intake outcome; confirmation requires a review")
    if any(not value.strip() for value in (actor, reason, method_version)):
        raise ValueError("Intake decisions require actor, reason and method")
    event = models.EventDossier.objects.select_for_update().get(pk=dossier_id)
    claim = models.EventDossierClaim.objects.get(pk=claim_id)
    if claim.event_dossier_source.event_dossier_id != event.pk:
        raise ValueError("Intake evidence belongs to another dossier")
    values = {
        "supporting_claim_id": claim.pk,
        "outcome": outcome,
        "actor": actor,
        "reason": reason,
        "method_version": method_version,
    }
    row, _ = models.EventDossierIntakeDecision.objects.get_or_create(
        event_dossier=event,
        input_hash=_digest(values),
        defaults=values,
    )
    return row


def _known_dossiers(source):
    sources = models.EventDossierSource.objects.filter(
        post_id=source.post_id,
        collection_observation_id=source.observation_id,
        claims__claim_kind_reference__code="release_report",
        event_dossier__event_kind_reference__code="product_release",
    )
    return {
        canonical_dossier(pk).pk
        for pk in sources.values_list("event_dossier_id", flat=True)
    }


def _observed_publisher(source, linked):
    """Retain a source's self-attribution, separately from verification."""
    if not source.post_id:
        return
    post = models.Post.objects.get(pk=source.post_id)
    if not post.author_handle or not re.search(
        r"\b(?:we|I)(?:['’](?:ve|re|m))?\s+(?:(?:are|am|have|today|now)\s+)?(?:releas|launch|announc|introduc|publish)|我们.*(?:发布|推出)",
        post.text or "",
        re.IGNORECASE,
    ):
        return
    brands = (
        list(
            models.BrandCompany.objects.filter(
                company__accounts__account_id=post.author_id,
                company__accounts__ownership_confirmed=True,
            )
            .values_list("brand_id", flat=True)
            .distinct()
        )
        if post.author_id
        else []
    )
    candidate_id = None
    brand_id = brands[0] if len(brands) == 1 else None
    if not brand_id:
        from core.targeted_extraction import _organization_candidate

        candidate, _ = _organization_candidate(
            post=post,
            name=post.author_name or post.author_handle,
            handle=post.author_handle,
            confidence=None,
        )
        candidate_id = candidate.pk
    add_claim(
        linked.pk,
        claim_kind="release_context",
        scope_key="observed_publisher",
        assertion_text=f"Source author {post.author_handle} describes its own release; ownership still requires verification",
        source_excerpt=post.text,
        source_locator=source.source_url,
        extraction_version=METHOD,
        reported_brand_id=brand_id,
        reported_candidate_id=candidate_id,
    )


@transaction.atomic
def persist_source(source: StoredSource):
    candidate = detect(source.record)
    if candidate is None:
        return {
            "source": source.record.identity,
            "disposition": "no_signal",
            "dossier_ids": [],
        }
    dossier_ids = _known_dossiers(source)
    if not dossier_ids:
        event = create_dossier(
            event_kind="product_release",
            identity_key=identity_key(
                "product-release-source-v1", ":".join(source.record.identity)
            ),
            first_seen_at=source.stored_at,
        )
        dossier_ids = {canonical_dossier(event.pk).pk}
    texts = {item.locator: item for item in source.record.texts}
    by_locator = {}
    for signal in candidate.signals:
        by_locator.setdefault(signal.locator, []).append(signal)
    for dossier_id in sorted(dossier_ids, key=str):
        linked = attach_source(
            dossier_id, post_id=source.post_id, observation_id=source.observation_id
        )
        _observed_publisher(source, linked)
        first_claim = None
        for locator, signals in sorted(by_locator.items()):
            text = texts.get(locator)
            excerpt = (
                text.text if text else "; ".join(sorted({s.excerpt for s in signals}))
            )
            claim = add_claim(
                linked.pk,
                claim_kind="release_signal",
                scope_key=locator,
                assertion_text="Release candidate from "
                + ", ".join(sorted({s.kind for s in signals})),
                source_excerpt=excerpt,
                source_locator=source.source_url,
                extraction_version=candidate.rule_version,
            )
            first_claim = first_claim or claim
            # Family-wide statements must be assigned explicitly to each release.
            # Saved translations/commentary never become independent dated proof.
            if len(dossier_ids) == 1 and text and text.kind == "raw":
                for milestone in extract_milestones(
                    text.text, published_at=source.published_at
                ):
                    add_claim(
                        linked.pk,
                        claim_kind=milestone.kind,
                        scope_key=locator,
                        assertion_text=milestone.excerpt,
                        source_excerpt=milestone.excerpt,
                        source_locator=source.source_url,
                        extraction_version=MILESTONE_METHOD,
                        effective_precision=milestone.precision,
                        effective_at=milestone.effective_at,
                        effective_date=milestone.effective_date,
                        access_channel=milestone.access_channel,
                    )
        # An explicit upstream decision is required for exclusion; lack of posts
        # or an unrecognized name is never a fraud decision.
        reason = (
            source.record.fraud.reason
            if source.record.fraud
            else "Release signal retained; product identity and publisher require reconciliation"
        )
        latest = (
            models.EventDossierIntakeDecision.objects.filter(
                event_dossier_id=dossier_id
            )
            .order_by("-recorded_at", "-pk")
            .first()
        )
        # New observations do not silently undo a reviewed exclusion.
        if not latest or latest.outcome not in {"non_release", "scam"}:
            record_intake_decision(
                dossier_id,
                claim_id=first_claim.pk,
                outcome="scam" if source.record.fraud else "pending",
                actor=METHOD,
                reason=reason
                + (
                    "; cautions=" + ",".join(candidate.cautions)
                    if candidate.cautions
                    else ""
                ),
            )
    return {
        "source": source.record.identity,
        "disposition": candidate.disposition,
        "dossier_ids": sorted(map(str, dossier_ids)),
        "input_hash": _digest(asdict(source.record)),
        "cautions": candidate.cautions,
        "references": [asdict(ref) for ref in candidate.references],
    }


def _copy_claim(claim, source_id):
    return add_claim(
        source_id,
        claim_kind=claim.claim_kind_reference.code,
        scope_key=claim.scope_key,
        assertion_text=claim.assertion_text,
        source_excerpt=claim.source_excerpt,
        source_locator=claim.source_locator,
        extraction_version=claim.extraction_version,
        event_timezone=claim.event_timezone_reference_id,
        access_channel=claim.release_access_channel_reference.code
        if claim.release_access_channel_reference_id
        else None,
        effective_precision=claim.effective_precision,
        effective_at=claim.effective_at,
        effective_date=claim.effective_date,
        effective_year=claim.effective_year,
        effective_month=claim.effective_month,
        not_before=claim.not_before,
        not_after=claim.not_after,
        reported_brand_id=claim.reported_brand_id,
        reported_candidate_id=claim.reported_brand_discovery_candidate_id,
        source_archive_id=claim.source_archive_id,
        release_maturity_id=claim.release_maturity_reference_id,
    )


@transaction.atomic
def merge_dossiers(source_id, target_id, *, actor, reason):
    # A shared advisory lock serializes merge-graph changes before row locks;
    # immutable evidence is copied by semantic identity, never moved or deleted.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(64382061)")
    source = models.EventDossier.objects.get(pk=source_id)
    target = canonical_dossier(target_id)
    if source.pk == target.pk:
        raise ValueError("A dossier merge cannot target itself or form a cycle")
    rows = {
        row.pk: row
        for row in models.EventDossier.objects.select_for_update()
        .filter(pk__in=[source.pk, target.pk])
        .order_by("pk")
    }
    source, target = rows[source.pk], rows[target.pk]
    if source.merged_into_id:
        if canonical_dossier(source.pk).pk == target.pk:
            return target
        raise ValueError("A dossier merge cannot be reassigned")
    if source.event_kind_reference_id != target.event_kind_reference_id:
        raise ValueError("A dossier merge must preserve event kind")
    first_claim = None
    for linked in source.sources.order_by("pk"):
        destination = attach_source(
            target.pk,
            post_id=linked.post_id,
            observation_id=linked.collection_observation_id,
        )
        for claim in linked.claims.select_related(
            "claim_kind_reference", "release_access_channel_reference"
        ).order_by("pk"):
            first_claim = first_claim or claim
            _copy_claim(claim, destination.pk)
    if first_claim is None:
        raise ValueError("A merge needs evidence")
    record_intake_decision(
        source.pk,
        claim_id=first_claim.pk,
        outcome="superseded",
        actor=actor,
        reason=f"{reason}; canonical={target.pk}",
    )
    models.EventDossier.objects.filter(pk=source.pk).update(merged_into=target)
    return target


@transaction.atomic
def review_release(
    dossier_id,
    *,
    release: ProductReleaseInput,
    claim_ids,
    actor,
    reason,
    evidence_cutoff_at,
    state="provisional",
    significance_score=None,
):
    """Complete an assessed release; strong claims need explicit ownership proof."""
    event = canonical_dossier(dossier_id)
    event = models.EventDossier.objects.select_for_update().get(pk=event.pk)
    claims = list(
        models.EventDossierClaim.objects.filter(
            pk__in=claim_ids, event_dossier_source__event_dossier=event
        ).select_related(
            "claim_kind_reference",
            "event_dossier_source__post",
            "event_dossier_source__collection_observation__resource_snapshot",
        )
    )
    if len(claims) != len(set(map(str, claim_ids))):
        raise ValueError("Review claims must exist in this dossier")
    if state == "confirmed":
        issuer = release.release_issuer_company_id
        by_kind = {}
        for claim in claims:
            by_kind.setdefault(claim.claim_kind_reference.code, []).append(claim)
        entity_proof = any(
            c.scope_key == f"company:{issuer}" and c.source_locator
            for c in by_kind.get("publisher_verification", [])
        )
        official_assertion = False
        for claim in by_kind.get("announcement", []) + by_kind.get(
            "source_stated_release", []
        ):
            source = claim.event_dossier_source
            account_id = (
                source.post.author_id
                if source.post_id
                else getattr(
                    getattr(source.collection_observation, "resource_snapshot", None),
                    "publisher_account_id",
                    None,
                )
            )
            control = any(
                c.scope_key == f"account:{account_id}:company:{issuer}"
                and c.source_locator
                for c in by_kind.get("source_ownership", [])
            )
            if (
                account_id
                and control
                and models.CompanyAccount.objects.filter(
                    account_id=account_id, company_id=issuer, ownership_confirmed=True
                ).exists()
            ):
                official_assertion = True
        if not issuer or not entity_proof or not official_assertion:
            raise ValueError(
                "Confirmation requires verified publisher identity and source ownership evidence"
            )
        if release.availability_state == "available" and not by_kind.get(
            "availability"
        ):
            raise ValueError("Availability requires its own evidence")
    # Complete_review hashes cutoff and inputs; pass a stable reviewed_at so an
    # unchanged assessed packet is a no-op, including after the current pointer moves.
    return complete_review(
        event.pk,
        expected_current_review_id=event.current_review_id,
        display_title=release.observed_name,
        review_state=state,
        evidence_cutoff_at=evidence_cutoff_at,
        reviewed_at=evidence_cutoff_at,
        method_version=METHOD,
        actor=actor,
        reason=reason,
        claims=[
            ClaimDecision(c.pk, "accepted", "Source checked in release assessment")
            for c in sorted(claims, key=lambda c: str(c.pk))
        ],
        product_release=release,
        significance_score=significance_score,
        ranking_method="release-significance-v1"
        if significance_score is not None
        else "",
    )
