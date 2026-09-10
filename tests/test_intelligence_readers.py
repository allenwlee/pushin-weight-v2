"""Stable read-shape tests for future recruiter and agent consumers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.intelligence_readers import (
    event_document,
    event_lifecycle,
    job_listing_document,
    opportunity_document,
    person_intelligence,
)
from core.models import (
    Account,
    AccountProfileSnapshot,
    Brand,
    BrandDiscoveryCandidate,
    Event,
    JobListing,
    JobListingEvidence,
    Opportunity,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    Post,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
CONTRACT = json.loads(
    (
        Path(__file__).parents[1]
        / "docs/reference/2026-09-10-203138-stage1c-intelligence-read-contract.json"
    ).read_text(encoding="utf-8")
)


def _assert_contract_root(name: str, document: dict):
    schema = CONTRACT["documents"][name]
    assert set(document) == set(schema["root_keys"])
    assert set(schema["example"]) == set(schema["root_keys"])
    for path in schema["required_paths"]:
        values = [document]
        for segment in path.split("."):
            is_array = segment.endswith("[]")
            key = segment.removesuffix("[]")
            next_values = []
            for value in values:
                assert isinstance(value, dict) and key in value, path
                child = value[key]
                if is_array:
                    assert isinstance(child, list), path
                    next_values.extend(child)
                else:
                    next_values.append(child)
            values = next_values
        assert values, path


def test_person_reader_separates_employment_and_keeps_profile_provenance(
    django_assert_num_queries,
):
    brand, _ = Brand.objects.get_or_create(
        nickname="anthropic", defaults={"display_name": "Anthropic"}
    )
    account = Account.objects.create(
        author_id="reader-anna", handle="a_nnawang", display_name="Anna Wang"
    )
    post = Post.objects.create(
        tweet_id="reader-personnel",
        author=account,
        text="I worked elsewhere and now at Anthropic.",
    )
    snapshot = AccountProfileSnapshot.objects.create(
        account=account,
        profile_hash="a" * 64,
        first_observed_at=NOW,
        last_observed_at=NOW,
        first_source_kind="post",
        first_source_post=post,
        handle="a_nnawang",
        display_name="Anna Wang",
        description="Researcher @Anthropic",
        affiliate_target_username="AnthropicAI",
        affiliate_label_description="Anthropic",
        affiliate_label_type="BusinessLabel",
        affiliate_display_type="Badge",
        present_fields=["description"],
        profile_data={"description": "Researcher @Anthropic"},
    )
    person = Person.objects.create(
        display_name="Anna Wang",
        date_of_birth="1987",
        date_of_birth_precision="year",
        sexs="female",
        nationality="American",
        ethnicity="Asian",
        primary_language="en",
    )
    PersonAccount.objects.create(
        person=person,
        account=account,
        is_primary=True,
        first_observed_at=NOW,
        last_observed_at=NOW,
        resolution_status="confirmed",
    )
    employment = PersonBrandAffiliation.objects.create(
        person=person,
        brand=brand,
        affiliation_type="employment",
        observed_organization_name="Anthropic PBC",
        title_raw="Researcher",
        status="current",
        claim_identity="b" * 64,
    )
    PersonBrandAffiliationEvidence.objects.create(
        affiliation=employment,
        source_profile_snapshot=snapshot,
        evidence_text="Researcher @Anthropic",
        observed_at=NOW,
        extraction_method="profile-affiliation-rules-v1",
        evidence_hash="c" * 64,
    )
    PersonBrandAffiliation.objects.create(
        person=person,
        brand=brand,
        affiliation_type="advisor",
        observed_organization_name="Anthropic",
        status="current",
        claim_identity="d" * 64,
    )

    with django_assert_num_queries(4):
        document = person_intelligence(person.pk)

    _assert_contract_root("person_intelligence", document)
    assert document["person"]["date_of_birth"] == {
        "value": "1987",
        "precision": "year",
    }
    assert document["person"]["sexs"] == "female"
    assert len(document["affiliations"]) == 2
    assert [row["affiliation_type"] for row in document["employment_history"]] == [
        "employment"
    ]
    evidence = document["employment_history"][0]["evidence"][0]
    assert evidence["observed_at"] == NOW.isoformat()
    assert evidence["profile_observation"]["business_affiliate_label"] == {
        "target_username": "AnthropicAI",
        "description": "Anthropic",
        "label_type": "BusinessLabel",
        "display_type": "Badge",
    }
    assert document["employment_history"][0]["start_date"] == {
        "value": None,
        "precision": "unknown",
    }


def test_job_reader_keeps_one_post_as_evidence_for_several_roles(
    django_assert_num_queries,
):
    post = Post.objects.create(tweet_id="reader-jobs", text="Two roles")
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="New AI Co",
        candidate_handles=["new_ai_co"],
        source_post=post,
        source_identities=["post:reader-jobs"],
        verification_status="pending",
        candidate_identity="e" * 64,
        first_observed_at=NOW,
        last_observed_at=NOW,
    )
    listings = []
    for index in range(2):
        listing = JobListing.objects.create(
            brand_discovery_candidate=candidate,
            hiring_organization="New AI Co",
            title=f"Research Engineer {index}",
            application_url=f"https://example.com/jobs/{index}",
            application_route_kind="direct_url",
            first_seen_at=NOW,
            last_seen_at=NOW,
            listing_identity=f"{index + 10:064x}",
        )
        JobListingEvidence.objects.create(
            listing=listing,
            source_post=post,
            source_relationship="third_party",
            evidence_text="Two roles",
            observed_at=NOW,
            extraction_method="structured_text",
            extraction_identity="job-v1",
            evidence_hash=f"{index + 20:064x}",
        )
        listings.append(listing)

    with django_assert_num_queries(2):
        first = job_listing_document(listings[0].pk)
    with django_assert_num_queries(2):
        second = job_listing_document(listings[1].pk)

    _assert_contract_root("job_listing_document", first)
    assert first["hiring_organization"] == "New AI Co"
    assert first["organization_review"]["verification_status"] == "pending"
    assert first["application"]["route_kind"] == "direct_url"
    assert first["evidence"][0]["source_post_id"] == post.pk
    assert second["evidence"][0]["source_post_id"] == post.pk


def test_event_and_opportunity_lifecycle_requires_explicit_aware_as_of():
    brand = Brand.objects.create(nickname="lifecycle", display_name="Lifecycle")
    post = Post.objects.create(tweet_id="reader-lifecycle", text="Join and win")
    event = Event.objects.create(
        brand=brand,
        source_post=post,
        title="Live workshop",
        organizer_name="Lifecycle",
        attendance_mode="online_live",
        start_value="2026-09-11T10:00:00+00:00",
        start_precision="datetime",
        end_value="2026-09-11T11:00:00+00:00",
        end_precision="datetime",
        first_seen_at=NOW,
        last_seen_at=NOW,
        event_identity="f" * 64,
    )
    opportunity = Opportunity.objects.create(
        brand=brand,
        related_event=event,
        source_post=post,
        sponsor_name="Lifecycle",
        opportunity_type="contest",
        action_type="submit",
        benefit_type="prize",
        open_value="2026-09-10T00:00:00+00:00",
        open_precision="datetime",
        close_value="2026-09-12T00:00:00+00:00",
        close_precision="datetime",
        first_seen_at=NOW,
        last_seen_at=NOW,
        opportunity_identity="0" * 64,
    )

    event_result = event_document(event.pk, as_of=NOW)
    opportunity_result = opportunity_document(opportunity.pk, as_of=NOW)
    _assert_contract_root("event_document", event_result)
    _assert_contract_root("opportunity_document", opportunity_result)
    assert event_result["lifecycle"] == "upcoming"
    assert (
        event_document(event.pk, as_of=datetime(2026, 9, 11, 10, 30, tzinfo=UTC))[
            "lifecycle"
        ]
        == "live"
    )
    assert (
        event_document(event.pk, as_of=datetime(2026, 9, 11, 12, 0, tzinfo=UTC))[
            "lifecycle"
        ]
        == "past"
    )
    assert opportunity_result["lifecycle"] == "open"
    assert (
        opportunity_document(opportunity.pk, as_of=datetime(2026, 9, 12, tzinfo=UTC))[
            "lifecycle"
        ]
        == "closed"
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        event_document(event.pk, as_of=NOW.replace(tzinfo=None))


def test_partial_dates_never_create_a_dynamic_lifecycle():
    brand = Brand.objects.create(nickname="partial", display_name="Partial")
    event = Event.objects.create(
        brand=brand,
        source_url="https://example.com/event",
        title="Conference",
        organizer_name="Partial",
        start_value="2026-10",
        start_precision="month",
        first_seen_at=NOW,
        last_seen_at=NOW,
        event_identity="1" * 64,
    )
    assert event_document(event.pk, as_of=NOW)["lifecycle"] == "unknown"

    malformed_legacy_event = Event(
        start_value="2026-10-01T10:00:00",
        start_precision="datetime",
        source_status="unknown",
    )
    assert event_lifecycle(malformed_legacy_event, as_of=NOW) == "unknown"

    event.source_status = "completed"
    event.save(update_fields=["source_status"])
    assert event_document(event.pk, as_of=NOW)["lifecycle"] == "past"

    opportunity = Opportunity.objects.create(
        brand=brand,
        source_url="https://example.com/offer",
        sponsor_name="Partial",
        opportunity_type="grant",
        action_type="apply",
        benefit_type="funding",
        source_status="closed",
        first_seen_at=NOW,
        last_seen_at=NOW,
        opportunity_identity="2" * 64,
    )
    assert opportunity_document(opportunity.pk, as_of=NOW)["lifecycle"] == "closed"


def test_source_status_is_used_without_inventing_an_event_end_time():
    brand = Brand.objects.create(nickname="status-only", display_name="Status Only")
    scheduled = Event.objects.create(
        brand=brand,
        source_url="https://example.com/scheduled",
        title="Scheduled session",
        organizer_name="Status Only",
        source_status="scheduled",
        first_seen_at=NOW,
        last_seen_at=NOW,
        event_identity="3" * 64,
    )
    started_without_end = Event.objects.create(
        brand=brand,
        source_url="https://example.com/started",
        title="Start only",
        organizer_name="Status Only",
        start_value="2026-09-09T10:00:00+00:00",
        start_precision="datetime",
        source_status="scheduled",
        first_seen_at=NOW,
        last_seen_at=NOW,
        event_identity="4" * 64,
    )
    open_opportunity = Opportunity.objects.create(
        brand=brand,
        source_url="https://example.com/open",
        sponsor_name="Status Only",
        opportunity_type="grant",
        action_type="apply",
        benefit_type="funding",
        source_status="open",
        first_seen_at=NOW,
        last_seen_at=NOW,
        opportunity_identity="5" * 64,
    )

    assert event_document(scheduled.pk, as_of=NOW)["lifecycle"] == "upcoming"
    assert event_document(started_without_end.pk, as_of=NOW)["lifecycle"] == "unknown"
    assert opportunity_document(open_opportunity.pk, as_of=NOW)["lifecycle"] == "open"
