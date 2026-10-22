"""Stable internal read shapes for Stage 1C intelligence data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db.models import F, Prefetch

from core.job_vocabulary import (
    classification_prefetches,
    classification_text,
    reported_compensation,
)
from core.models import (
    Event,
    EventEvidence,
    JobListing,
    JobListingEvidence,
    ModelRelease,
    ModelReleaseEvidence,
    Opportunity,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    PersonCitizenship,
    PersonNameSelection,
    PersonText,
    Post,
    PostBrandClassificationState,
    PostBrandProduct,
    ProductVerificationProposal,
    RareTypeCategoryAssignment,
)


def model_release_document(release_id: int) -> dict[str, Any]:
    """Return one canonical release with source evidence and honest counts."""
    release = (
        ModelRelease.objects.select_related("brand", "brand_discovery_candidate")
        .prefetch_related(
            Prefetch(
                "evidence",
                queryset=ModelReleaseEvidence.objects.order_by("observed_at", "id"),
            )
        )
        .get(pk=release_id)
    )
    evidence = list(release.evidence.all())
    post_ids = sorted({row.source_post_id for row in evidence})
    candidate = release.brand_discovery_candidate
    return {
        "id": release.pk,
        "owner": {
            "brand_id": release.brand_id,
            "candidate_id": release.brand_discovery_candidate_id,
            "observed_name": candidate.observed_name if candidate else None,
            "reviewed_brand_id": candidate.reviewed_brand_id if candidate else None,
        },
        "observed_model_name": release.observed_model_name,
        "version": release.version,
        "channel": release.release_maturity_reference.code,
        "release_date": _effective_date(
            release.release_value, release.release_precision
        ),
        "review_status": release.review_status,
        "counts": {
            "canonical_records": 1,
            "evidence": len(evidence),
            "posts": len(post_ids),
        },
        "evidence": [
            {
                "id": row.pk,
                "source_post_id": row.source_post_id,
                "source_url": row.source_url,
                "observed_at": _iso(row.observed_at),
                "claim": row.observed_claim,
                "extraction_version": row.extraction_version,
            }
            for row in evidence
        ],
    }


def rare_type_post_document(post_id: str) -> dict[str, Any]:
    """Read source-linked categories, Products, and unresolved Product work."""
    post = Post.objects.filter(pk=post_id).only("tweet_id", "source_query_id").first()
    categories = (
        RareTypeCategoryAssignment.objects.filter(post_id=post_id)
        .select_related("brand_discovery_candidate")
        .order_by("brand_id", "brand_discovery_candidate_id", "category", "id")
    )
    products = (
        PostBrandProduct.objects.filter(post_id=post_id)
        .select_related("product")
        .order_by("brand_id", "product_id")
    )
    proposals = (
        ProductVerificationProposal.objects.filter(source_post_id=post_id)
        .select_related("resolved_product")
        .order_by("id")
    )
    classifications = PostBrandClassificationState.objects.filter(
        post_id=post_id
    ).order_by("brand_id")
    release_ids = ModelReleaseEvidence.objects.filter(
        source_post_id=post_id
    ).values_list("release_id", flat=True)
    event_ids = EventEvidence.objects.filter(source_post_id=post_id).values_list(
        "event_id", flat=True
    )
    job_ids = JobListingEvidence.objects.filter(source_post_id=post_id).values_list(
        "listing_id", flat=True
    )
    affiliation_ids = PersonBrandAffiliationEvidence.objects.filter(
        source_post_id=post_id
    ).values_list("affiliation_id", flat=True)
    return {
        "post_id": str(post_id),
        "exists": post is not None,
        "source_query_id": post.source_query_id if post else None,
        "classification": [
            {
                "brand_id": row.brand_id,
                "outcome": row.outcome,
                "contract_version": row.contract_version,
                "taxonomy_version": row.taxonomy_version,
                "prompt_version": row.prompt_version,
                "model": row.model,
                "classified_at": _iso(row.classified_at),
            }
            for row in classifications
        ],
        "categories": [
            {
                "brand_id": row.brand_id,
                "candidate_id": row.brand_discovery_candidate_id,
                "observed_owner": row.brand_discovery_candidate.observed_name
                if row.brand_discovery_candidate
                else None,
                "reviewed_brand_id": row.brand_discovery_candidate.reviewed_brand_id
                if row.brand_discovery_candidate
                else None,
                "category": row.category,
                "classification_version": row.classification_version,
                "source_evidence": row.source_evidence,
            }
            for row in categories
        ],
        "products": [
            {
                "brand_id": row.brand_id,
                "product_id": row.product_id,
                "product_key": str(row.product.product_key),
                "repo_id": row.product.repo_id,
                "name": row.observed_name,
                "type": row.product.type,
                "policy_version": row.verification_policy_version,
                "source_evidence": row.source_evidence,
            }
            for row in products
        ],
        "product_proposals": [
            {
                "id": row.pk,
                "observed_name": row.observed_name,
                "candidate_repo_id": row.candidate_repo_id,
                "hf_outcome": row.hf_outcome,
                "review_status": row.review_status,
                "resolved_product_id": row.resolved_product_id,
                "resolved_product_key": (
                    str(row.resolved_product.product_key)
                    if row.resolved_product_id
                    else None
                ),
                "brand_id": row.proposed_brand_id,
                "candidate_id": row.proposed_candidate_id,
                "policy_version": row.policy_version,
                "rule_trace": row.rule_trace,
                "attempted_at": _iso(row.attempted_at),
                "next_attempt_at": _iso(row.next_attempt_at),
                "reviewed_at": _iso(row.reviewed_at),
            }
            for row in proposals
        ],
        "domain_records": {
            "model_releases": [
                model_release_document(release_id)
                for release_id in sorted(set(release_ids))
            ],
            "events": list(
                Event.objects.filter(pk__in=event_ids)
                .order_by("id")
                .values("id", "title", "brand_id", "brand_discovery_candidate_id")
            ),
            "opportunities": list(
                Opportunity.objects.filter(source_post_id=post_id)
                .order_by("id")
                .values(
                    "id",
                    "brand_id",
                    "brand_discovery_candidate_id",
                    opportunity_type=F("opportunity_type_reference__code"),
                )
            ),
            "job_listings": list(
                JobListing.objects.filter(pk__in=job_ids)
                .order_by("id")
                .values("id", "title", "brand_id", "brand_discovery_candidate_id")
            ),
            "affiliations": list(
                PersonBrandAffiliation.objects.filter(pk__in=affiliation_ids)
                .order_by("id")
                .values(
                    "id",
                    "person_id",
                    "brand_id",
                    "brand_discovery_candidate_id",
                    "status",
                    affiliation_type=F("affiliation_type_reference__code"),
                )
            ),
        },
    }


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _reported_source_timezone(record: Event | Opportunity) -> str | None:
    payload = record.raw_payload
    if isinstance(payload, dict) and "source_timezone" in payload:
        value = payload["source_timezone"]
        if value is None:
            return None
        normalized = str(value).strip()[:64]
        return normalized or None
    return record.source_timezone_reference_id


def _effective_date(value: str | None, precision: str) -> dict[str, Any]:
    return {"value": value, "precision": precision}


def _evidence(row: PersonBrandAffiliationEvidence) -> dict[str, Any]:
    snapshot = row.source_profile_snapshot
    return {
        "id": row.pk,
        "source_post_id": row.source_post_id,
        "source_profile_snapshot_id": row.source_profile_snapshot_id,
        "source_url": row.source_url,
        "profile_observation": (
            {
                "id": snapshot.pk,
                "profile_hash": snapshot.profile_hash,
                "first_observed_at": _iso(snapshot.first_observed_at),
                "last_observed_at": _iso(snapshot.last_observed_at),
                "handle": snapshot.handle,
                "display_name": snapshot.display_name,
                "description": snapshot.description,
                "profile_bio_text": snapshot.profile_bio_text,
                "business_affiliate_label": {
                    "target_username": snapshot.affiliate_target_username,
                    "description": snapshot.affiliate_label_description,
                    "label_type": snapshot.affiliate_label_type,
                    "display_type": snapshot.affiliate_display_type,
                },
            }
            if snapshot is not None
            else None
        ),
        "evidence_text": row.evidence_text,
        "observed_at": _iso(row.observed_at),
        "extraction_method": row.extraction_method,
        "confidence": row.confidence,
        "review_status": row.review_status,
        "extraction_model": row.extraction_model,
        "extraction_prompt_version": row.extraction_prompt_version,
    }


def _affiliation(row: PersonBrandAffiliation) -> dict[str, Any]:
    from core.person_affiliations import is_active_claim
    candidate = row.brand_discovery_candidate
    return {
        "id": row.pk,
        "brand_id": row.brand_id,
        "brand_discovery_candidate_id": row.brand_discovery_candidate_id,
        "organization_review": (
            {
                "candidate_id": candidate.pk,
                "observed_name": candidate.observed_name,
                "candidate_handles": candidate.candidate_handles,
                "verification_status": candidate.verification_status,
                "reviewed_brand_id": candidate.reviewed_brand_id,
            }
            if candidate is not None
            else None
        ),
        "organization_name": row.observed_organization_name,
        "organization_handle": row.observed_organization_handle,
        "affiliation_type": row.affiliation_type_reference.code,
        "active": is_active_claim(row),
        "superseded_by": row.superseded_by_id,
        "status": row.status,
        "title": {
            "raw": row.title_raw,
            "normalized": row.title_normalized,
        },
        "department": row.department,
        "team": row.team,
        "job_function": row.job_function,
        "seniority": row.seniority,
        "employment_type": row.employment_type,
        "location": row.location,
        "workplace_type": row.workplace_type,
        "description": row.description,
        "start_date": _effective_date(row.start_date, row.start_date_precision),
        "end_date": _effective_date(row.end_date, row.end_date_precision),
        "confidence": row.confidence,
        "review_status": row.review_status,
        "source_system": row.source_system,
        "external_id": row.external_id,
        "evidence": [_evidence(item) for item in row.evidence.all()],
    }


def person_intelligence(person_id) -> dict[str, Any]:
    evidence = PersonBrandAffiliationEvidence.objects.select_related(
        "source_profile_snapshot"
    ).order_by("observed_at", "id")
    affiliations = (
        PersonBrandAffiliation.objects.select_related(
            "brand_discovery_candidate", "affiliation_type_reference"
        )
        .prefetch_related(Prefetch("evidence", queryset=evidence))
        .order_by("brand_id", "id")
    )
    from core.person_names import selected_name_for

    person = Person.objects.select_related("primary_name", "english_name").prefetch_related(
        Prefetch(
            "name_selections",
            queryset=PersonNameSelection.objects.select_related("name"),
        ),
        Prefetch("brand_affiliations", queryset=affiliations),
        Prefetch(
            "texts",
            queryset=PersonText.objects.filter(
                kind="reported_nationality", origin="unknown"
            )
            .order_by("-observed_at", "-id"),
            to_attr="reported_nationality_texts",
        ),
        Prefetch(
            "citizenships",
            queryset=PersonCitizenship.objects.select_related("country")
            .order_by("-is_primary", "country_id"),
        ),
        Prefetch(
            "account_links",
            queryset=PersonAccount.objects.select_related("account").order_by(
                "account_id"
            ),
        ),
    ).get(pk=person_id)
    if person.merged_into_id:
        from core.person_identity import canonical_person
        return person_intelligence(canonical_person(person.merged_into_id).pk)
    all_affiliations = [_affiliation(row) for row in person.brand_affiliations.all()]
    return {
        "person": {
            "id": str(person.pk),
            "display_name": selected_name_for(person, "und") or "Unreviewed person",
            "display_names": {
                "en": selected_name_for(person, "en"),
                "zh-cn": selected_name_for(person, "zh-Hans"),
                "ja": selected_name_for(person, "ja"),
            },
            "date_of_birth": _effective_date(
                person.date_of_birth, person.date_of_birth_precision
            ),
            "sex": person.sex,
            "nationality": (
                person.reported_nationality_texts[0].text
                if person.reported_nationality_texts else None
            ),
            "citizenships": [
                {"country_code": row.country_id, "is_primary": row.is_primary}
                for row in person.citizenships.all()
            ],
            "ethnicity": person.ethnicity,
            "primary_language": person.primary_language,
            "accounts": [
                {
                    "author_id": link.account.author_id,
                    "handle": link.account.handle,
                    "is_primary": link.is_primary,
                    "resolution_status": link.resolution_status,
                    "confidence": link.confidence,
                }
                for link in person.account_links.all()
            ],
        },
        "affiliations": all_affiliations,
        "employment_history": [
            row
            for row in all_affiliations
            if row["affiliation_type"] == "employment" and row["active"]
        ],
    }


def job_listing_document(listing_id: int) -> dict[str, Any]:
    listing = (
        JobListing.objects.select_related("brand", "brand_discovery_candidate", "salary_period_reference")
        .prefetch_related(
            *classification_prefetches(),
            Prefetch(
                "evidence",
                queryset=JobListingEvidence.objects.order_by("observed_at", "id"),
            )
        )
        .get(pk=listing_id)
    )
    candidate = listing.brand_discovery_candidate
    return {
        "id": listing.pk,
        "brand_id": listing.brand_id,
        "brand_discovery_candidate_id": listing.brand_discovery_candidate_id,
        "organization_review": (
            {
                "candidate_id": candidate.pk,
                "observed_name": candidate.observed_name,
                "candidate_handles": candidate.candidate_handles,
                "verification_status": candidate.verification_status,
                "reviewed_brand_id": candidate.reviewed_brand_id,
            }
            if candidate is not None
            else None
        ),
        "hiring_organization": listing.hiring_organization,
        "title": listing.title,
        "description": {
            "html": listing.description_html,
            "text": listing.description_text,
        },
        "organization": {
            "department": listing.department,
            "team": listing.team,
            "job_function": classification_text(listing, "job_function"),
            "seniority": classification_text(listing, "seniority"),
            "employment_type": classification_text(listing, "employment_type"),
        },
        "source": {
            "name": listing.source_name,
            "listing_id": listing.source_listing_id,
            "canonical_url": listing.canonical_url,
        },
        "application": {
            "url": listing.application_url,
            "route_kind": listing.application_route_kind,
            "contact": listing.application_contact,
            "resolution_status": listing.application_resolution_status,
        },
        "location": {
            "raw": listing.locations_raw,
            "values": listing.locations,
            "workplace_type": classification_text(listing, "workplace_type"),
            "remote_applicant_restrictions": listing.remote_applicant_restrictions,
        },
        "compensation": {
            "raw": listing.salary_text,
            "minimum": str(listing.salary_min)
            if listing.salary_min is not None
            else None,
            "maximum": str(listing.salary_max)
            if listing.salary_max is not None
            else None,
            "currency": listing.salary_currency_reference_id or reported_compensation(listing, "salary_currency"),
            "period": reported_compensation(listing, "salary_period") or (
                listing.salary_period_reference.code if listing.salary_period_reference_id else None
            ),
        },
        "status": listing.status,
        "posted_at": _iso(listing.posted_at),
        "updated_source_at": _iso(listing.updated_source_at),
        "expires_at": _iso(listing.expires_at),
        "closed_at": _iso(listing.closed_at),
        "first_seen_at": _iso(listing.first_seen_at),
        "last_seen_at": _iso(listing.last_seen_at),
        "campaign_openings": listing.campaign_openings,
        "role_openings": listing.role_openings,
        "skills": listing.skills,
        "responsibilities": listing.responsibilities,
        "qualifications": listing.qualifications,
        "education_requirements": listing.education_requirements,
        "experience_requirements": listing.experience_requirements,
        "benefits": listing.benefits,
        "eligibility": listing.eligibility,
        "source_language": listing.source_language,
        "organization_ai_relationship": classification_text(listing, "organization_ai_relationship"),
        "role_ai_relationship": classification_text(listing, "role_ai_relationship"),
        "extraction": {
            "version": listing.extraction_version,
            "confidence": listing.extraction_confidence,
        },
        "evidence": [
            {
                "id": row.pk,
                "source_post_id": row.source_post_id,
                "source_url": row.source_url,
                "media_url": row.media_url,
                "linked_urls": row.linked_urls,
                "source_relationship": row.source_relationship,
                "observed_author_handle": row.observed_author_handle,
                "observed_author_display_name": row.observed_author_display_name,
                "evidence_text": row.evidence_text,
                "observed_at": _iso(row.observed_at),
                "extraction_method": row.extraction_method,
                "image_derived_fields": row.image_derived_fields,
                "confidence": row.confidence,
                "extraction_identity": row.extraction_identity,
            }
            for row in listing.evidence.all()
        ],
    }


def _parse_temporal(value: str | None, precision: str) -> datetime | None:
    if value is None or precision != "datetime":
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def event_lifecycle(event: Event, *, as_of: datetime) -> str:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if event.source_status in {"cancelled", "postponed"}:
        return event.source_status
    if event.source_status == "completed":
        return "past"
    start = _parse_temporal(event.start_value, event.start_precision)
    end = _parse_temporal(event.end_value, event.end_precision)
    if end is not None and as_of >= end:
        return "past"
    if start is not None and as_of < start:
        return "upcoming"
    if start is not None and as_of >= start:
        if end is not None:
            return "live" if as_of < end else "past"
        return "live" if event.source_status == "live" else "unknown"
    if event.source_status == "scheduled":
        return "upcoming"
    if event.source_status == "live":
        return "live"
    return "unknown"


def opportunity_lifecycle(opportunity: Opportunity, *, as_of: datetime) -> str:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if opportunity.source_status == "cancelled":
        return "cancelled"
    if opportunity.source_status == "closed":
        return "closed"
    opens = _parse_temporal(opportunity.open_value, opportunity.open_precision)
    closes = _parse_temporal(opportunity.close_value, opportunity.close_precision)
    if closes is not None and as_of >= closes:
        return "closed"
    if opens is not None and as_of < opens:
        return "upcoming"
    if opens is not None or closes is not None:
        return "open"
    if opportunity.source_status == "upcoming":
        return "upcoming"
    if opportunity.source_status == "open":
        return "open"
    return "unknown"


def event_document(event_id: int, *, as_of: datetime) -> dict[str, Any]:
    event = Event.objects.get(pk=event_id)
    return {
        "id": event.pk,
        "brand_id": event.brand_id,
        "title": event.title,
        "attendance_mode": event.attendance_mode,
        "attendance_url": event.attendance_url,
        "organizer": {
            "name": event.organizer_name,
            "handle": event.organizer_handle,
        },
        "location": {
            "physical": event.physical_location,
            "virtual": event.virtual_location,
        },
        "start": _effective_date(event.start_value, event.start_precision),
        "end": _effective_date(event.end_value, event.end_precision),
        "source_status": event.source_status,
        "source_timezone": _reported_source_timezone(event),
        "source_schedule_text": event.source_schedule_text,
        "lifecycle": event_lifecycle(event, as_of=as_of),
        "as_of": as_of.isoformat(),
        "source_post_id": event.source_post_id,
        "source_url": event.source_url,
        "first_seen_at": _iso(event.first_seen_at),
        "last_seen_at": _iso(event.last_seen_at),
        "review_status": event.review_status,
        "extraction": {
            "version": event.extraction_version,
            "confidence": event.extraction_confidence,
        },
    }


def opportunity_document(opportunity_id: int, *, as_of: datetime) -> dict[str, Any]:
    row = Opportunity.objects.get(pk=opportunity_id)
    return {
        "id": row.pk,
        "brand_id": row.brand_id,
        "related_event_id": row.related_event_id,
        "opportunity_type": row.opportunity_type_reference.code,
        "action_type": row.action_type,
        "action_url": row.action_url,
        "sponsor": {
            "name": row.sponsor_name,
            "handle": row.sponsor_handle,
        },
        "benefit": {
            "type": row.benefit_type,
            "value": str(row.benefit_value) if row.benefit_value is not None else None,
            "currency": row.benefit_currency,
            "text": row.benefit_text,
        },
        "opens": _effective_date(row.open_value, row.open_precision),
        "closes": _effective_date(row.close_value, row.close_precision),
        "source_status": row.source_status,
        "source_timezone": _reported_source_timezone(row),
        "source_availability_text": row.source_availability_text,
        "eligibility": row.eligibility,
        "geographic_restrictions": row.geographic_restrictions,
        "lifecycle": opportunity_lifecycle(row, as_of=as_of),
        "as_of": as_of.isoformat(),
        "source_post_id": row.source_post_id,
        "source_url": row.source_url,
        "first_seen_at": _iso(row.first_seen_at),
        "last_seen_at": _iso(row.last_seen_at),
        "review_status": row.review_status,
        "extraction": {
            "version": row.extraction_version,
            "confidence": row.extraction_confidence,
        },
    }
