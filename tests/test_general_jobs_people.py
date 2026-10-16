import json

import pytest

from core.models import (
    JobListing,
    JobListingEvidence,
    Person,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
)
from monitor.general_readers import general_feed
from tests.general_helpers import NOW, classified_post

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def job(post, key, **overrides):
    listing = JobListing.objects.create(
        **(
            {
                "brand_id": "qwen",
                "hiring_organization": "Qwen",
                "title": key,
                "listing_identity": key,
                "first_seen_at": NOW,
                "last_seen_at": NOW,
                "status": "open",
                "application_url": "https://example.org/apply",
            }
            | overrides
        )
    )
    JobListingEvidence.objects.create(
        listing=listing,
        source_post=post,
        source_relationship="official",
        observed_at=NOW,
        extraction_method="structured_text",
        extraction_identity=key,
        evidence_hash=key,
    )
    return listing


def affiliation(
    post,
    key,
    *,
    person=None,
    review="confirmed",
    evidence_review="confirmed",
    **overrides,
):
    person = person or Person.objects.create(
        display_name="Alex Kim",
        date_of_birth="1990",
        date_of_birth_precision="year",
        sex="female",
    )
    claim = PersonBrandAffiliation.objects.create(
        **(
            {
                "person": person,
                "brand_id": "qwen",
                "affiliation_type": "employment",
                "observed_organization_name": "Qwen",
                "title_raw": "Researcher",
                "status": "current",
                "claim_identity": key,
                "review_status": review,
                "start_date": "2026-11",
                "start_date_precision": "month",
            }
            | overrides
        )
    )
    PersonBrandAffiliationEvidence.objects.create(
        affiliation=claim,
        source_post=post,
        source_url="https://example.org/source",
        observed_at=NOW,
        evidence_text="Joining next month",
        extraction_method="fixture",
        evidence_hash=key,
        review_status=evidence_review,
    )
    return claim


def test_jobs_use_fetch_age_with_exact_24_hour_boundary_and_multiple_facts():
    first = classified_post("3101", age=23.999)
    classified_post("3102", age=24)
    classified_post("3103", age=24)
    job(first, "Research engineer")
    job(first, "Product designer", status="closed", closed_at=NOW)
    job(first, "Official site", source_key="official-site")
    items = general_feed("jobs", as_of=NOW)["items"]
    assert [row["id"] for row in items] == ["3101", "3102", "3103"]
    assert [row["recent"] for row in items] == [True, False, False]
    assert len(items[0]["facts"]) == 2
    assert {row["state"] for row in items[0]["facts"]} == {"open", "closed"}
    assert items[0]["age_seconds"] == pytest.approx(23.999 * 3600)


def test_people_require_source_linked_nonrejected_nonsuperseded_claims_and_label_uncertainty():
    post = classified_post("3201", "personnel_changes")
    confirmed = affiliation(post, "confirmed")
    advisor = affiliation(post, "advisor", review="pending", affiliation_type="advisor")
    affiliation(post, "rejected-claim", review="rejected")
    affiliation(post, "rejected-evidence", evidence_review="rejected")
    affiliation(
        post,
        "superseded",
        person=confirmed.person,
        superseded_by=confirmed,
        superseded_at=NOW,
        superseded_by_reviewer="fixture",
        supersession_reason="Corrected title",
    )
    affiliation(None, "profile-only", person=confirmed.person)
    classified_post("3202", "business_finance")
    items = general_feed("moving", as_of=NOW)["items"]
    assert [row["id"] for row in items] == [post.pk]
    facts = items[0]["facts"]
    assert {row["id"] for row in facts} == {confirmed.pk, advisor.pk}
    assert len({row["person_id"] for row in facts}) == 2
    pending = next(row for row in facts if row["id"] == advisor.pk)
    assert not pending["confirmed"]
    assert pending["relationship"] == "advisor"
    assert pending["start"] == {"value": "2026-11", "precision": "month"}
    assert pending["portrait"] is None
    public = json.dumps(items)
    assert (
        "date_of_birth" not in public
        and "female" not in public
        and "review_note" not in public
    )


def test_old_personnel_post_without_linked_identity_remains_honest():
    post = classified_post("3301", "personnel_changes", age=9000)
    affiliation(None, "same-name")
    item = general_feed("moving", as_of=NOW)["items"][0]
    assert item["id"] == post.pk and item["facts"] == []
