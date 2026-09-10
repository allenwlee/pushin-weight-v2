"""Stable internal read shapes for Stage 1C intelligence data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db.models import Prefetch

from core.models import (
    Event,
    JobListing,
    JobListingEvidence,
    Opportunity,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


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
    return {
        "id": row.pk,
        "brand_id": row.brand_id,
        "organization_name": row.observed_organization_name,
        "organization_handle": row.observed_organization_handle,
        "affiliation_type": row.affiliation_type,
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
    affiliations = PersonBrandAffiliation.objects.prefetch_related(
        Prefetch("evidence", queryset=evidence)
    ).order_by("brand_id", "id")
    person = Person.objects.prefetch_related(
        Prefetch("brand_affiliations", queryset=affiliations),
        Prefetch(
            "account_links",
            queryset=PersonAccount.objects.select_related("account").order_by(
                "account_id"
            ),
        ),
    ).get(pk=person_id)
    all_affiliations = [_affiliation(row) for row in person.brand_affiliations.all()]
    return {
        "person": {
            "id": str(person.pk),
            "display_name": person.display_name,
            "display_names": {
                "en": person.display_name_en,
                "zh-cn": person.display_name_zh_cn,
                "ja": person.display_name_ja,
            },
            "date_of_birth": _effective_date(
                person.date_of_birth, person.date_of_birth_precision
            ),
            "sexs": person.sexs,
            "nationality": person.nationality,
            "ethnicity": person.ethnicity,
            "primary_language": person.primary_language,
            "accounts": [
                {
                    "author_id": link.account_id,
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
            row for row in all_affiliations if row["affiliation_type"] == "employment"
        ],
    }


def job_listing_document(listing_id: int) -> dict[str, Any]:
    listing = (
        JobListing.objects.select_related("brand", "brand_discovery_candidate")
        .prefetch_related(
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
            "job_function": listing.job_function,
            "seniority": listing.seniority,
            "employment_type": listing.employment_type,
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
            "workplace_type": listing.workplace_type,
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
            "currency": listing.salary_currency,
            "period": listing.salary_period,
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
        "organization_ai_relationship": listing.organization_ai_relationship,
        "role_ai_relationship": listing.role_ai_relationship,
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
        "source_timezone": event.source_timezone,
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
        "opportunity_type": row.opportunity_type,
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
        "source_timezone": row.source_timezone,
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
