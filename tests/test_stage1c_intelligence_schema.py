"""PostgreSQL regression net for the additive Stage 1C intelligence schema."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import (
    Account,
    AccountProfileSnapshot,
    Brand,
    BrandDiscoveryCandidate,
    Event,
    JobDiscoveryRun,
    JobListing,
    JobListingEvidence,
    Opportunity,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    PersonnelDiscoveryRun,
    Post,
    SearchQuery,
    TargetedExtractionAttempt,
    TargetedExtractionState,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _assert_integrity_error(create):
    with pytest.raises(IntegrityError), transaction.atomic():
        create()


def test_people_schema_preserves_reduced_precision_and_owner_named_sexs_column():
    year_only = Person.objects.create(
        display_name="Year Only",
        date_of_birth="1987",
        date_of_birth_precision="year",
        sexs="female",
        nationality="Korean",
        ethnicity="Korean",
        primary_language="ko",
    )
    unknown = Person.objects.create(display_name="Unknown")

    assert year_only.date_of_birth == "1987"
    assert year_only.sexs == "female"
    assert unknown.date_of_birth is None
    assert unknown.date_of_birth_precision == "unknown"
    assert Person._meta.get_field("sexs").column == "sexs"
    _assert_integrity_error(
        lambda: Person.objects.create(
            display_name="Bad precision",
            date_of_birth="1987",
            date_of_birth_precision="day",
        )
    )


def test_person_account_confirmed_and_primary_uniqueness_is_database_enforced():
    now = timezone.now()
    account = Account.objects.create(author_id="person-account-one", handle="one")
    second = Account.objects.create(author_id="person-account-two", handle="two")
    person = Person.objects.create(display_name="One")
    other_person = Person.objects.create(display_name="Two")
    PersonAccount.objects.create(
        person=person,
        account=account,
        is_primary=True,
        first_observed_at=now,
        last_observed_at=now,
        resolution_status="confirmed",
    )

    _assert_integrity_error(
        lambda: PersonAccount.objects.create(
            person=other_person,
            account=account,
            first_observed_at=now,
            last_observed_at=now,
            resolution_status="confirmed",
        )
    )
    _assert_integrity_error(
        lambda: PersonAccount.objects.create(
            person=person,
            account=second,
            is_primary=True,
            first_observed_at=now,
            last_observed_at=now,
            resolution_status="confirmed",
        )
    )
    assert PersonAccount._meta.get_field("account").column == "author_id"
    assert tuple(PersonAccount._meta.pk.field_names) == ("person", "account")


def test_profile_and_affiliation_evidence_keep_observation_separate_from_dates():
    now = timezone.now()
    account = Account.objects.create(author_id="anna-account", handle="a_nnawang")
    post = Post.objects.create(
        tweet_id="anna-transition",
        author=account,
        text="I worked at Google DeepMind and now at Anthropic.",
        created_at=now,
    )
    snapshot = AccountProfileSnapshot.objects.create(
        account=account,
        profile_hash="a" * 64,
        first_observed_at=now,
        last_observed_at=now,
        first_source_kind="post",
        first_source_post=post,
        present_fields=["description"],
        profile_data={"description": "Researcher"},
    )
    brand = Brand.objects.create(nickname="anthropic", display_name="Anthropic")
    person = Person.objects.create(display_name="Anna Wang")
    affiliation = PersonBrandAffiliation.objects.create(
        person=person,
        brand=brand,
        affiliation_type="employment",
        observed_organization_name="Anthropic",
        status="current",
        claim_identity="b" * 64,
    )
    evidence = PersonBrandAffiliationEvidence.objects.create(
        affiliation=affiliation,
        source_post=post,
        source_profile_snapshot=snapshot,
        evidence_text=post.text or "",
        observed_at=now,
        extraction_method="structured_text",
        evidence_hash="c" * 64,
    )

    assert affiliation.start_date is None
    assert affiliation.start_date_precision == "unknown"
    assert evidence.observed_at == now
    _assert_integrity_error(
        lambda: PersonBrandAffiliationEvidence.objects.create(
            affiliation=affiliation,
            observed_at=now,
            extraction_method="structured_text",
            evidence_hash="d" * 64,
        )
    )


def test_one_source_post_can_support_many_distinct_job_rows():
    now = timezone.now()
    brand = Brand.objects.create(nickname="jobs-brand", display_name="Jobs")
    post = Post.objects.create(tweet_id="many-roles", text="23 open roles")
    listings = [
        JobListing.objects.create(
            brand=brand,
            hiring_organization="Jobs",
            title=f"Role {index}",
            application_url=f"https://example.com/jobs/{index}",
            application_route_kind="direct_url",
            first_seen_at=now,
            last_seen_at=now,
            listing_identity=f"{index:064x}",
        )
        for index in range(23)
    ]
    JobListingEvidence.objects.bulk_create(
        [
            JobListingEvidence(
                listing=listing,
                source_post=post,
                source_relationship="official",
                evidence_text="23 open roles",
                observed_at=now,
                extraction_method="structured_text",
                extraction_identity="stage1c-job-v1",
                evidence_hash=f"{index + 100:064x}",
            )
            for index, listing in enumerate(listings)
        ]
    )

    assert JobListing.objects.count() == 23
    assert JobListingEvidence.objects.filter(source_post=post).count() == 23
    assert (
        JobListingEvidence.objects.filter(source_post=post)
        .values_list("source_post_id", flat=True)
        .distinct()
        .count()
        == 1
    )


def test_events_opportunities_and_discovery_runs_keep_distinct_identities():
    now = timezone.now()
    brand = Brand.objects.create(nickname="events-brand", display_name="Events")
    post = Post.objects.create(tweet_id="event-and-opportunity", text="Join and win")
    event = Event.objects.create(
        brand=brand,
        source_post=post,
        title="Live hackathon",
        organizer_name="Events",
        attendance_mode="online_live",
        start_value="2026-09-20T10:00:00+09:00",
        start_precision="datetime",
        first_seen_at=now,
        last_seen_at=now,
        event_identity="e" * 64,
    )
    opportunity = Opportunity.objects.create(
        brand=brand,
        related_event=event,
        source_post=post,
        sponsor_name="Events",
        opportunity_type="contest",
        action_type="submit",
        benefit_type="prize",
        close_value="2026-09-30",
        close_precision="day",
        first_seen_at=now,
        last_seen_at=now,
        opportunity_identity="f" * 64,
    )
    query = SearchQuery.objects.create(query_id="stage1c-jobs-en", keywords={})
    job_run = JobDiscoveryRun.objects.create(
        run_identity="1" * 64,
        run_id="run-1",
        query=query,
        query_text="AI jobs",
        query_hash="2" * 64,
        query_pack_version="jobs-v1",
        provider_boundary="twitterapi",
        language="en",
        query_family="role",
        window_start=now,
        window_end=now + timedelta(hours=1),
        extracted_listing_count=23,
    )
    personnel_run = PersonnelDiscoveryRun.objects.create(
        run_identity="3" * 64,
        run_id="run-1",
        query=query,
        query_text="joined AI lab",
        query_hash="4" * 64,
        query_pack_version="personnel-v1",
        provider_boundary="twitterapi",
        language="en",
        query_family="transition",
        window_start=now,
        window_end=now + timedelta(hours=1),
        extracted_affiliation_count=2,
        extracted_evidence_count=2,
    )

    assert event.opportunities.get() == opportunity
    assert job_run.extracted_listing_count == 23
    assert personnel_run.extracted_affiliation_count == 2
    _assert_integrity_error(
        lambda: Event.objects.create(
            brand=brand,
            source_post=post,
            title="Bad confidence",
            organizer_name="Events",
            first_seen_at=now,
            last_seen_at=now,
            event_identity="0" * 64,
            extraction_confidence=1.1,
        )
    )
    _assert_integrity_error(
        lambda: Opportunity.objects.create(
            brand=brand,
            source_post=post,
            sponsor_name="Events",
            opportunity_type="contest",
            action_type="submit",
            benefit_type="prize",
            first_seen_at=now,
            last_seen_at=now,
            opportunity_identity="9" * 64,
            extraction_confidence=-0.1,
        )
    )
    _assert_integrity_error(
        lambda: JobDiscoveryRun.objects.create(
            run_identity="5" * 64,
            run_id="bad-window",
            query=query,
            query_text="AI jobs",
            query_hash="6" * 64,
            query_pack_version="jobs-v1",
            provider_boundary="twitterapi",
            language="en",
            query_family="role",
            window_start=now,
            window_end=now,
        )
    )


def test_job_organization_ownership_and_choice_values_are_database_enforced():
    now = timezone.now()
    brand = Brand.objects.create(nickname="owned-job-brand", display_name="Owned")
    source_post = Post.objects.create(tweet_id="candidate-source", text="We are hiring")
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="New AI Company",
        source_post=source_post,
        candidate_identity="7" * 64,
        first_observed_at=now,
        last_observed_at=now,
    )
    listing_fields = {
        "hiring_organization": "New AI Company",
        "title": "Research Engineer",
        "first_seen_at": now,
        "last_seen_at": now,
    }

    _assert_integrity_error(
        lambda: JobListing.objects.create(
            **listing_fields,
            listing_identity="8" * 64,
        )
    )
    _assert_integrity_error(
        lambda: JobListing.objects.create(
            **listing_fields,
            brand=brand,
            brand_discovery_candidate=candidate,
            listing_identity="9" * 64,
        )
    )
    _assert_integrity_error(
        lambda: JobListing.objects.create(
            **listing_fields,
            brand=brand,
            status="maybe",
            listing_identity="a" * 64,
        )
    )
    _assert_integrity_error(
        lambda: JobListing.objects.create(
            **listing_fields,
            brand=brand,
            campaign_openings=0,
            listing_identity="b" * 64,
        )
    )
    _assert_integrity_error(
        lambda: JobListing.objects.create(
            **listing_fields,
            brand=brand,
            salary_min=-1,
            listing_identity="c" * 64,
        )
    )


def test_comparable_affiliation_dates_cannot_run_backwards():
    brand = Brand.objects.create(nickname="date-brand", display_name="Dates")
    person = Person.objects.create(display_name="Date Person")

    _assert_integrity_error(
        lambda: PersonBrandAffiliation.objects.create(
            person=person,
            brand=brand,
            affiliation_type="employment",
            observed_organization_name="Dates",
            start_date="2026-09",
            start_date_precision="month",
            end_date="2026-08",
            end_date_precision="month",
            claim_identity="d" * 64,
        )
    )


def test_affiliation_requires_exactly_one_known_or_candidate_organization():
    person = Person.objects.create(display_name="Organization Person")
    brand = Brand.objects.create(nickname="known-org", display_name="Known Org")
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="Candidate Org",
        candidate_identity="e" * 64,
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
    )
    common = {
        "person": person,
        "affiliation_type": "employment",
        "observed_organization_name": "Organization",
    }

    _assert_integrity_error(
        lambda: PersonBrandAffiliation.objects.create(
            **common,
            claim_identity="f" * 64,
        )
    )
    _assert_integrity_error(
        lambda: PersonBrandAffiliation.objects.create(
            **common,
            brand=brand,
            brand_discovery_candidate=candidate,
            claim_identity="0" * 64,
        )
    )


def test_targeted_extraction_role_and_status_are_database_enforced():
    post = Post.objects.create(tweet_id="bad-targeted-state", text="Join us")

    _assert_integrity_error(
        lambda: TargetedExtractionState.objects.create(
            post=post,
            role="made_up_role",
            model="test-model",
            prompt_version="targeted-v1",
            content_identity="b" * 64,
        )
    )
    _assert_integrity_error(
        lambda: TargetedExtractionState.objects.create(
            post=post,
            role="event_extraction",
            status="maybe",
            model="test-model",
            prompt_version="targeted-v1",
            content_identity="c" * 64,
        )
    )

    state = TargetedExtractionState.objects.create(
        post=post,
        role="event_extraction",
        model="test-model",
        prompt_version="targeted-v1",
        content_identity="d" * 64,
    )
    _assert_integrity_error(
        lambda: TargetedExtractionAttempt.objects.create(
            state=state,
            attempt_identity="e" * 64,
            attempted_at=timezone.now(),
            outcome="maybe",
            model="test-model",
            prompt_version="targeted-v1",
        )
    )
