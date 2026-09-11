"""Provider-free tests for classification-gated rare-signal extraction."""

from __future__ import annotations

import pytest

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
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    Post,
    PostBrand,
    TargetedExtractionAttempt,
    TargetedExtractionState,
)
from core.profile_snapshots import capture_post_profile_snapshot
from core.targeted_extraction import (
    build_targeted_extraction_calls,
    run_targeted_extractions,
)
from x_monitor.config import TargetedExtractionConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _config():
    config = TargetedExtractionConfig()
    config.enabled = True
    return config


def test_replay_sensitive_targeted_roles_use_v2_identities():
    roles = _config().roles
    assert roles["job_listing_extraction"].prompt_version == (
        "job-listing-extraction-v2"
    )
    assert roles["personnel_change_extraction"].prompt_version == (
        "personnel-change-extraction-v2"
    )
    assert roles["profile_affiliation_extraction"].prompt_version == (
        "profile-affiliation-extraction-v2"
    )


def _post(
    tweet_id="targeted",
    *,
    text="Source text",
    brand_ids=("anthropic",),
    source_urls=(),
    author_handle="a_nnawang",
):
    account = Account.objects.create(
        author_id=f"author-{tweet_id}",
        handle=author_handle,
        display_name="Anna Wang",
    )
    post = Post.objects.create(
        tweet_id=tweet_id,
        author=account,
        author_handle=account.handle,
        author_name=account.display_name,
        text=text,
        entities={"urls": [{"expanded_url": url} for url in source_urls]},
    )
    for brand_id in brand_ids:
        brand, _ = Brand.objects.get_or_create(
            nickname=brand_id, defaults={"display_name": brand_id}
        )
        PostBrand.objects.create(post=post, brand=brand)
    return post


def test_negative_post_makes_zero_targeted_calls():
    post = _post()
    called = []
    result = run_targeted_extractions(
        post=post,
        post_types={"opinions_reactions"},
        config=_config(),
        calls={"event_extraction": lambda *args: called.append(args)},
        max_calls=20,
    )
    assert result.calls_made == 0
    assert called == []
    assert TargetedExtractionState.objects.count() == 0


def test_ambiguous_profile_candidate_routes_to_profile_extractor_without_images():
    post = _post("profile-candidate", text="A normal unrelated post")
    snapshot = AccountProfileSnapshot.objects.create(
        account=post.author,
        profile_hash="a" * 64,
        first_observed_at=post.fetched_at,
        last_observed_at=post.fetched_at,
        first_source_kind="post",
        first_source_post=post,
        handle="a_nnawang",
        display_name="Anna Wang",
        description="Researcher @Anthropic",
        profile_image_url="https://example.com/profile.jpg",
        affiliate_badge_image_url="https://example.com/badge.jpg",
        present_fields=["description", "profile_image_url"],
        profile_data={"description": "Researcher @Anthropic"},
    )
    person = Person.objects.create(display_name="Anna Wang")
    candidate = PersonBrandAffiliation.objects.create(
        person=person,
        brand_id="anthropic",
        affiliation_type="other",
        observed_organization_name="Anthropic",
        status="unknown",
        claim_identity="b" * 64,
    )
    PersonBrandAffiliationEvidence.objects.create(
        affiliation=candidate,
        source_profile_snapshot=snapshot,
        evidence_text="Researcher @Anthropic",
        observed_at=post.fetched_at,
        extracted_claim_data={"candidate_role": "unknown"},
        extraction_method="profile-affiliation-rules-v1",
        evidence_hash="c" * 64,
    )
    requests = []

    def provider(system, user, model, max_tokens):
        requests.append((system, user, model, max_tokens))
        return {
            "records": [
                {
                    "person_name": "Anna Wang",
                    "person_handle": "a_nnawang",
                    "brand_id": "anthropic",
                    "organization_name": "Anthropic",
                    "affiliation_type": "employment",
                    "status": "current",
                    "start_date": None,
                    "start_date_precision": "unknown",
                    "end_date": None,
                    "end_date_precision": "unknown",
                    "confidence": 0.8,
                }
            ]
        }

    result = run_targeted_extractions(
        post=post,
        post_types={"opinions_reactions"},
        config=_config(),
        calls={"profile_affiliation_extraction": provider},
        max_calls=20,
    )

    assert result.calls_made == 1
    assert result.records_written == 1
    assert (
        TargetedExtractionState.objects.get().role == "profile_affiliation_extraction"
    )
    request_text = requests[0][1]
    assert "Researcher @Anthropic" in request_text
    assert "profile.jpg" not in request_text
    assert "badge.jpg" not in request_text


def test_invalid_choice_fails_atomically_and_records_sanitized_attempt():
    post = _post("bad-event", text="Attend our live session")

    result = run_targeted_extractions(
        post=post,
        post_types={"events"},
        config=_config(),
        calls={
            "event_extraction": lambda *args: {
                "records": [
                    {
                        "brand_id": "anthropic",
                        "organization_name": "Anthropic",
                        "title": "Session",
                        "attendance_mode": "watch_async",
                    }
                ]
            }
        },
        max_calls=20,
    )

    assert result.failed_roles == ("event_extraction",)
    assert Event.objects.count() == 0
    attempt = TargetedExtractionAttempt.objects.get()
    assert attempt.outcome == "failed"
    assert attempt.error_code == "ValueError"
    assert not hasattr(attempt, "source_text")


def test_one_post_can_create_23_jobs_once_with_source_evidence():
    source_urls = tuple(f"https://example.com/jobs/{index}" for index in range(23))
    post = _post(
        "jobs-23",
        text="We are hiring for 23 roles.",
        source_urls=source_urls,
    )
    records = [
        {
            "brand_id": "anthropic",
            "organization_name": "Anthropic",
            "title": f"Research Engineer {index}",
            "application_url": f"https://example.com/jobs/{index}",
            "application_route_kind": "direct_url",
            "status": "open",
            "locations": [],
            "confidence": 0.9,
        }
        for index in range(23)
    ]
    calls = []

    def provider(*args):
        calls.append(args)
        return {
            "records": records,
            "usage": {"input_tokens": 100, "output_tokens": 200},
        }

    first = run_targeted_extractions(
        post=post,
        post_types={"job_listings"},
        config=_config(),
        calls={"job_listing_extraction": provider},
        max_calls=20,
    )
    second = run_targeted_extractions(
        post=post,
        post_types={"job_listings"},
        config=_config(),
        calls={"job_listing_extraction": provider},
        max_calls=20,
    )

    assert first.calls_made == 1
    assert first.records_written == 23
    assert second.calls_made == 0
    assert len(calls) == 1
    assert JobListing.objects.count() == 23
    assert JobListingEvidence.objects.filter(source_post=post).count() == 23
    attempt = TargetedExtractionAttempt.objects.get()
    assert attempt.input_tokens == 100
    assert attempt.output_tokens == 200
    assert not hasattr(attempt, "source_text")


def test_later_job_evidence_converges_on_listing_and_advances_last_seen():
    canonical_url = "https://example.com/jobs/researcher"
    first = _post(
        "job-evidence-first",
        text="Anthropic is hiring a researcher.",
        source_urls=(canonical_url,),
        author_handle="job_source_first",
    )
    later = _post(
        "job-evidence-later",
        text="The Anthropic researcher role is still open.",
        source_urls=(canonical_url,),
        author_handle="job_source_later",
    )
    later.fetched_at = first.fetched_at.replace(year=first.fetched_at.year + 1)
    later.save(update_fields=["fetched_at"])
    first_record = {
        "brand_id": "anthropic",
        "organization_name": "Anthropic",
        "title": "Researcher",
        "canonical_url": canonical_url,
        "application_url": canonical_url,
        "application_route_kind": "direct_url",
        "status": "unknown",
    }
    later_record = {
        **first_record,
        "status": "open",
        "posted_at": "2026-09-10T01:00:00Z",
        "education_requirements": "Doctorate or equivalent experience",
        "experience_requirements": "Published machine-learning research",
        "locations": ["San Francisco"],
    }

    for post, record in ((first, first_record), (later, later_record)):
        result = run_targeted_extractions(
            post=post,
            post_types={"job_listings"},
            config=_config(),
            calls={
                "job_listing_extraction": (
                    lambda *_args, record=record: {"records": [record]}
                )
            },
            max_calls=20,
        )
        assert result.failed_roles == ()

    listing = JobListing.objects.get()
    assert listing.first_seen_at == first.fetched_at
    assert listing.last_seen_at == later.fetched_at
    assert listing.status == "open"
    assert listing.posted_at.isoformat() == "2026-09-10T01:00:00+00:00"
    assert listing.education_requirements == "Doctorate or equivalent experience"
    assert listing.experience_requirements == "Published machine-learning research"
    assert listing.locations == ["San Francisco"]
    assert listing.evidence.count() == 2


def test_job_extraction_keeps_source_timestamps_and_requirements():
    application_url = "https://example.com/jobs/source-fields"
    post = _post(
        "job-source-fields",
        text="Apply for our research role.",
        source_urls=(application_url,),
    )
    result = run_targeted_extractions(
        post=post,
        post_types={"job_listings"},
        config=_config(),
        calls={
            "job_listing_extraction": lambda *_args: {
                "records": [
                    {
                        "brand_id": "anthropic",
                        "organization_name": "Anthropic",
                        "title": "Research Engineer",
                        "application_url": application_url,
                        "application_route_kind": "direct_url",
                        "posted_at": "2026-09-10T01:00:00Z",
                        "updated_source_at": "2026-09-10T11:00:00+09:00",
                        "expires_at": "2026-10-01T00:00:00Z",
                        "education_requirements": "Bachelor's degree or equivalent",
                        "experience_requirements": "Three years of Python",
                    }
                ]
            }
        },
        max_calls=20,
    )

    assert result.failed_roles == ()
    listing = JobListing.objects.get()
    assert listing.posted_at.isoformat() == "2026-09-10T01:00:00+00:00"
    assert listing.updated_source_at.isoformat() == "2026-09-10T02:00:00+00:00"
    assert listing.expires_at.isoformat() == "2026-10-01T00:00:00+00:00"
    assert listing.education_requirements == "Bachelor's degree or equivalent"
    assert listing.experience_requirements == "Three years of Python"


def test_job_fallback_identity_normalizes_case_whitespace_and_location_order():
    records = [
        {
            "brand_id": "anthropic",
            "organization_name": "Anthropic",
            "title": "Research Engineer",
            "application_route_kind": "direct_message",
            "locations": ["Tokyo", "Remote"],
        },
        {
            "brand_id": "anthropic",
            "organization_name": "  ANTHROPIC  ",
            "title": "research   engineer",
            "application_route_kind": "direct_message",
            "locations": ["remote", "TOKYO"],
        },
    ]
    for index, record in enumerate(records):
        post = _post(
            f"normalized-job-{index}",
            text="Anthropic is hiring a research engineer in Tokyo or remotely.",
            author_handle=f"normalized_source_{index}",
        )
        result = run_targeted_extractions(
            post=post,
            post_types={"job_listings"},
            config=_config(),
            calls={
                "job_listing_extraction": (
                    lambda *_args, record=record: {"records": [record]}
                )
            },
            max_calls=20,
        )
        assert result.failed_roles == ()

    assert JobListing.objects.count() == 1
    assert JobListingEvidence.objects.count() == 2


def test_anna_transition_keeps_current_and_former_with_unknown_dates():
    Brand.objects.create(nickname="google_deepmind", display_name="Google DeepMind")
    post = _post(
        "anna",
        text="I worked at Google DeepMind and now at Anthropic.",
        brand_ids=("anthropic", "google_deepmind"),
    )
    records = [
        {
            "person_name": "Anna Wang",
            "person_handle": "a_nnawang",
            "brand_id": "anthropic",
            "organization_name": "Anthropic",
            "affiliation_type": "employment",
            "status": "current",
            "start_date": None,
            "start_date_precision": "unknown",
            "end_date": None,
            "end_date_precision": "unknown",
            "confidence": 0.95,
        },
        {
            "person_name": "Anna Wang",
            "person_handle": "a_nnawang",
            "brand_id": "google_deepmind",
            "organization_name": "Google DeepMind",
            "affiliation_type": "employment",
            "status": "former",
            "start_date": None,
            "start_date_precision": "unknown",
            "end_date": None,
            "end_date_precision": "unknown",
            "confidence": 0.95,
        },
    ]
    result = run_targeted_extractions(
        post=post,
        post_types={"personnel_changes"},
        config=_config(),
        calls={"personnel_change_extraction": lambda *args: {"records": records}},
        max_calls=20,
    )

    assert result.records_written == 2
    affiliations = list(PersonBrandAffiliation.objects.order_by("brand_id"))
    assert [(row.brand_id, row.status) for row in affiliations] == [
        ("anthropic", "current"),
        ("google_deepmind", "former"),
    ]
    assert all(row.start_date is None and row.end_date is None for row in affiliations)
    assert all(row.start_date_precision == "unknown" for row in affiliations)
    assert PersonBrandAffiliationEvidence.objects.filter(source_post=post).count() == 2


def test_untracked_personnel_organization_keeps_affiliation_and_evidence():
    post = _post(
        "untracked-personnel",
        text="Lee Jiyin has joined New AI Co.",
        brand_ids=(),
        author_handle="industry_news",
    )
    result = run_targeted_extractions(
        post=post,
        post_types={"personnel_changes"},
        config=_config(),
        calls={
            "personnel_change_extraction": lambda *_args: {
                "records": [
                    {
                        "person_name": "Lee Jiyin",
                        "person_handle": "lee_jiyin",
                        "brand_id": None,
                        "organization_name": "New AI Co",
                        "organization_handle": "new_ai_co",
                        "affiliation_type": "employment",
                        "status": "current",
                        "start_date": None,
                        "start_date_precision": "unknown",
                        "end_date": None,
                        "end_date_precision": "unknown",
                        "confidence": 0.91,
                    }
                ]
            }
        },
        max_calls=20,
    )

    assert result.records_written == 1
    assert result.evidence_written == 1
    assert result.organization_candidates_written == 1
    candidate = BrandDiscoveryCandidate.objects.get()
    affiliation = PersonBrandAffiliation.objects.get()
    assert affiliation.brand_id is None
    assert affiliation.brand_discovery_candidate == candidate
    assert affiliation.observed_organization_name == "New AI Co"
    assert affiliation.evidence.get().source_post == post


@pytest.mark.parametrize(
    ("post_type", "role", "record"),
    [
        (
            "personnel_changes",
            "personnel_change_extraction",
            {
                "person_name": "Date Person",
                "brand_id": "anthropic",
                "organization_name": "Anthropic",
                "affiliation_type": "employment",
                "status": "current",
                "start_date": "2026-99-99",
                "start_date_precision": "day",
            },
        ),
        (
            "events",
            "event_extraction",
            {
                "brand_id": "anthropic",
                "organization_name": "Anthropic",
                "title": "Backwards event",
                "attendance_mode": "online_live",
                "start_value": "2026-09-20",
                "start_precision": "day",
                "end_value": "2026-09-19",
                "end_precision": "day",
            },
        ),
        (
            "opportunities",
            "opportunity_extraction",
            {
                "brand_id": "anthropic",
                "organization_name": "Anthropic",
                "opportunity_type": "contest",
                "action_type": "submit",
                "benefit_type": "prize",
                "open_value": "2026-13",
                "open_precision": "month",
            },
        ),
        (
            "job_listings",
            "job_listing_extraction",
            {
                "brand_id": "anthropic",
                "organization_name": "Anthropic",
                "title": "Naive timestamp role",
                "application_route_kind": "direct_message",
                "posted_at": "2026-09-10T01:00:00",
            },
        ),
    ],
)
def test_invalid_source_dates_fail_the_role_atomically(post_type, role, record):
    post = _post(
        f"bad-date-{role}",
        text="Source with a malformed or backwards date.",
    )
    result = run_targeted_extractions(
        post=post,
        post_types={post_type},
        config=_config(),
        calls={role: lambda *_args: {"records": [record]}},
        max_calls=20,
    )

    assert result.failed_roles == (role,)
    assert not Event.objects.exists()
    assert not Opportunity.objects.exists()
    assert not JobListing.objects.exists()
    assert not PersonBrandAffiliation.objects.exists()


def test_self_authored_personnel_reuses_person_created_by_profile_capture():
    post = _post(
        "self-authored-profile-first",
        text="I joined Anthropic.",
    )
    raw = {
        "author_id": post.author_id,
        "author_handle": post.author_handle,
        "author_name": post.author_name,
        "author_description": "Researcher at @Anthropic",
        "_author_present_fields": [
            "author_handle",
            "author_name",
            "author_description",
        ],
    }
    capture_post_profile_snapshot(post=post, raw=raw)
    existing_person = Person.objects.get()

    response = {
        "records": [
            {
                "person_name": "Anna Wang",
                "person_handle": "a_nnawang",
                "brand_id": "anthropic",
                "organization_name": "Anthropic",
                "affiliation_type": "employment",
                "status": "current",
                "start_date": None,
                "start_date_precision": "unknown",
                "end_date": None,
                "end_date_precision": "unknown",
                "confidence": 0.95,
            }
        ]
    }
    result = run_targeted_extractions(
        post=post,
        post_types={"personnel_changes"},
        config=_config(),
        calls={"personnel_change_extraction": lambda *args: response},
        max_calls=20,
    )

    assert result.records_written == 1
    assert Person.objects.count() == 1
    assert Person.objects.get().pk == existing_person.pk
    assert post.author.person_links.get().person_id == existing_person.pk


def test_profile_capture_reuses_person_created_by_self_authored_personnel():
    post = _post(
        "self-authored-targeted-first",
        text="I joined Anthropic.",
    )
    response = {
        "records": [
            {
                "person_name": "Anna Wang",
                "person_handle": "a_nnawang",
                "brand_id": "anthropic",
                "organization_name": "Anthropic",
                "affiliation_type": "employment",
                "status": "current",
                "start_date": None,
                "start_date_precision": "unknown",
                "end_date": None,
                "end_date_precision": "unknown",
                "confidence": 0.95,
            }
        ]
    }
    run_targeted_extractions(
        post=post,
        post_types={"personnel_changes"},
        config=_config(),
        calls={"personnel_change_extraction": lambda *args: response},
        max_calls=20,
    )
    existing_person = Person.objects.get()

    capture_post_profile_snapshot(
        post=post,
        raw={
            "author_id": post.author_id,
            "author_handle": post.author_handle,
            "author_name": post.author_name,
            "author_description": "Researcher at @Anthropic",
            "_author_present_fields": [
                "author_handle",
                "author_name",
                "author_description",
            ],
        },
    )

    assert Person.objects.count() == 1
    assert Person.objects.get().pk == existing_person.pk


def test_official_handle_announcement_and_later_self_post_share_one_person():
    official = _post(
        "official-announcement-first",
        text="Anna Wang @a_nnawang has joined Anthropic.",
        author_handle="anthropic_official",
    )
    self_post = _post(
        "self-announcement-second",
        text="I joined Anthropic.",
        author_handle="a_nnawang",
    )
    record = {
        "person_name": "Anna Wang",
        "person_handle": "a_nnawang",
        "brand_id": "anthropic",
        "organization_name": "Anthropic",
        "affiliation_type": "employment",
        "status": "current",
        "start_date": None,
        "start_date_precision": "unknown",
        "end_date": None,
        "end_date_precision": "unknown",
        "confidence": 0.95,
    }

    run_targeted_extractions(
        post=official,
        post_types={"personnel_changes"},
        config=_config(),
        calls={"personnel_change_extraction": lambda *_args: {"records": [record]}},
        max_calls=20,
    )
    capture_post_profile_snapshot(
        post=self_post,
        raw={
            "author_id": self_post.author_id,
            "author_handle": self_post.author_handle,
            "author_name": self_post.author_name,
            "author_description": "Researcher at @Anthropic",
            "_author_present_fields": [
                "author_handle",
                "author_name",
                "author_description",
            ],
        },
    )
    run_targeted_extractions(
        post=self_post,
        post_types={"personnel_changes"},
        config=_config(),
        calls={"personnel_change_extraction": lambda *_args: {"records": [record]}},
        max_calls=20,
    )

    assert Person.objects.count() == 1
    assert PersonBrandAffiliation.objects.count() == 2
    assert PersonBrandAffiliationEvidence.objects.count() == 3
    assert self_post.author.person_links.get().person_id == Person.objects.get().pk


def test_profile_account_link_is_reused_by_later_official_handle_announcement():
    profile_post = _post(
        "profile-before-official",
        text="A normal post.",
        author_handle="a_nnawang",
    )
    capture_post_profile_snapshot(
        post=profile_post,
        raw={
            "author_id": profile_post.author_id,
            "author_handle": profile_post.author_handle,
            "author_name": profile_post.author_name,
            "author_description": "Researcher at @Anthropic",
            "_author_present_fields": [
                "author_handle",
                "author_name",
                "author_description",
            ],
        },
    )
    existing_person = Person.objects.get()
    official = _post(
        "official-after-profile",
        text="Anna Wang @a_nnawang has joined Anthropic.",
        author_handle="anthropic_official",
    )

    run_targeted_extractions(
        post=official,
        post_types={"personnel_changes"},
        config=_config(),
        calls={
            "personnel_change_extraction": lambda *_args: {
                "records": [
                    {
                        "person_name": "Anna Wang",
                        "person_handle": "a_nnawang",
                        "brand_id": "anthropic",
                        "organization_name": "Anthropic",
                        "affiliation_type": "employment",
                        "status": "current",
                        "start_date": None,
                        "start_date_precision": "unknown",
                        "end_date": None,
                        "end_date_precision": "unknown",
                        "confidence": 0.95,
                    }
                ]
            },
        },
        max_calls=20,
    )

    assert Person.objects.count() == 1
    assert Person.objects.get().pk == existing_person.pk


def test_event_and_opportunity_multi_label_routes_once_each():
    post = _post("dual", text="Attend live and submit by Friday to win credits.")
    responses = {
        "event_extraction": {
            "records": [
                {
                    "brand_id": "anthropic",
                    "organization_name": "Anthropic",
                    "title": "Live workshop",
                    "attendance_mode": "online_live",
                    "start_value": "2026-09-18T10:00:00+09:00",
                    "start_precision": "datetime",
                    "end_value": None,
                    "end_precision": "unknown",
                    "source_status": "scheduled",
                }
            ]
        },
        "opportunity_extraction": {
            "records": [
                {
                    "brand_id": "anthropic",
                    "organization_name": "Anthropic",
                    "opportunity_type": "contest",
                    "action_type": "submit an essay",
                    "benefit_type": "free_credits",
                    "benefit_text": "$300 in credits",
                    "close_value": "2026-09-19",
                    "close_precision": "day",
                    "source_status": "open",
                }
            ]
        },
    }
    call_counts = {role: 0 for role in responses}

    def call_for(role):
        def call(*_args):
            call_counts[role] += 1
            return responses[role]

        return call

    result = run_targeted_extractions(
        post=post,
        post_types={"events", "opportunities"},
        config=_config(),
        calls={role: call_for(role) for role in responses},
        max_calls=20,
    )

    assert result.calls_made == 2
    assert call_counts == {"event_extraction": 1, "opportunity_extraction": 1}
    event = Event.objects.get()
    opportunity = Opportunity.objects.get()
    assert event.attendance_mode == "online_live"
    assert opportunity.action_type == "submit an essay"
    assert opportunity.related_event == event


def test_invalid_url_fails_atomically_and_records_sanitized_attempt():
    post = _post("invalid-job")
    response = {
        "records": [
            {
                "brand_id": "anthropic",
                "organization_name": "Anthropic",
                "title": "Researcher",
                "application_url": "javascript:alert(1)",
            }
        ]
    }
    result = run_targeted_extractions(
        post=post,
        post_types={"job_listings"},
        config=_config(),
        calls={"job_listing_extraction": lambda *args: response},
        max_calls=20,
    )
    assert result.failed_roles == ("job_listing_extraction",)
    assert JobListing.objects.count() == 0
    assert TargetedExtractionState.objects.get().status == "failed"
    attempt = TargetedExtractionAttempt.objects.get()
    assert attempt.error_code == "ValueError"
    assert {field.name for field in attempt._meta.fields}.isdisjoint(
        {"prompt", "source_text", "response"}
    )


def test_valid_but_unobserved_url_fails_source_binding():
    post = _post("unobserved-job-url")
    result = run_targeted_extractions(
        post=post,
        post_types={"job_listings"},
        config=_config(),
        calls={
            "job_listing_extraction": lambda *args: {
                "records": [
                    {
                        "brand_id": "anthropic",
                        "organization_name": "Anthropic",
                        "title": "Researcher",
                        "application_url": "https://invented.example/jobs/1",
                    }
                ]
            }
        },
        max_calls=20,
    )
    assert result.failed_roles == ("job_listing_extraction",)
    assert JobListing.objects.count() == 0


def test_known_brand_id_must_be_present_in_source_evidence():
    Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    post = _post("invented-brand", text="Anthropic is hiring.")
    result = run_targeted_extractions(
        post=post,
        post_types={"job_listings"},
        config=_config(),
        calls={
            "job_listing_extraction": lambda *args: {
                "records": [
                    {
                        "brand_id": "deepseek",
                        "organization_name": "DeepSeek",
                        "title": "Researcher",
                        "application_route_kind": "direct_message",
                    }
                ]
            }
        },
        max_calls=20,
    )

    assert result.failed_roles == ("job_listing_extraction",)
    assert JobListing.objects.count() == 0


def test_unknown_organization_candidate_keeps_every_source_and_seen_boundary():
    later = _post(
        "candidate-later",
        text="New AI Co is hiring a researcher. Apply by direct message.",
        brand_ids=(),
    )
    earlier = _post(
        "candidate-earlier",
        text="New AI Co is hiring an engineer. Apply by direct message.",
        brand_ids=(),
        author_handle="candidate_source_earlier",
    )
    earlier.fetched_at = later.fetched_at.replace(year=later.fetched_at.year - 1)
    earlier.save(update_fields=["fetched_at"])
    responses = {
        later.pk: {
            "records": [
                {
                    "brand_id": None,
                    "organization_name": "New AI Co",
                    "organization_handle": "new_ai_co",
                    "title": "Researcher",
                    "application_route_kind": "direct_message",
                }
            ]
        },
        earlier.pk: {
            "records": [
                {
                    "brand_id": None,
                    "organization_name": "New AI Co",
                    "organization_handle": "new_ai_co",
                    "title": "Engineer",
                    "application_route_kind": "direct_message",
                }
            ]
        },
    }

    for post in (later, earlier):
        result = run_targeted_extractions(
            post=post,
            post_types={"job_listings"},
            config=_config(),
            calls={
                "job_listing_extraction": (
                    lambda *_args, response=responses[post.pk]: response
                )
            },
            max_calls=20,
        )
        assert result.organization_candidates_written == int(post == later)

    candidate = BrandDiscoveryCandidate.objects.get()
    assert candidate.first_observed_at == earlier.fetched_at
    assert candidate.last_observed_at == later.fetched_at
    assert candidate.source_identities == [
        f"post:{later.pk}",
        f"post:{earlier.pk}",
    ]


def test_failed_targeted_role_retries_and_then_converges():
    post = _post("retry-event", text="Attend our live workshop tomorrow.")
    responses = iter(
        [
            {"records": [{"attendance_mode": "invalid"}]},
            {
                "records": [
                    {
                        "brand_id": "anthropic",
                        "organization_name": "Anthropic",
                        "title": "Live workshop",
                        "attendance_mode": "online_live",
                        "source_status": "scheduled",
                    }
                ]
            },
        ]
    )

    def provider(*_args):
        return next(responses)

    first = run_targeted_extractions(
        post=post,
        post_types={"events"},
        config=_config(),
        calls={"event_extraction": provider},
        max_calls=20,
    )
    second = run_targeted_extractions(
        post=post,
        post_types={"events"},
        config=_config(),
        calls={"event_extraction": provider},
        max_calls=20,
    )

    assert first.failed_roles == ("event_extraction",)
    assert second.failed_roles == ()
    assert Event.objects.count() == 1
    state = TargetedExtractionState.objects.get()
    assert state.status == "succeeded"
    assert state.attempts == 2
    assert TargetedExtractionAttempt.objects.count() == 2


def test_changed_source_context_gets_a_new_attempt_without_duplicate_entity():
    post = _post("changed-context", text="Attend our live workshop.")
    calls = 0

    def provider(*_args):
        nonlocal calls
        calls += 1
        return {
            "records": [
                {
                    "brand_id": "anthropic",
                    "organization_name": "Anthropic",
                    "title": "Live workshop",
                    "attendance_mode": "online_live",
                }
            ]
        }

    first = run_targeted_extractions(
        post=post,
        post_types={"events"},
        config=_config(),
        calls={"event_extraction": provider},
        max_calls=20,
    )
    post.quoted_text = "Updated source context"
    post.save(update_fields=["quoted_text"])
    second = run_targeted_extractions(
        post=post,
        post_types={"events"},
        config=_config(),
        calls={"event_extraction": provider},
        max_calls=20,
    )

    assert first.calls_made == 1
    assert second.calls_made == 1
    assert calls == 2
    assert Event.objects.count() == 1
    assert TargetedExtractionAttempt.objects.count() == 2


def test_targeted_provider_adapter_uses_role_model_timeout_and_usage():
    captured = {}

    class FakeClient:
        _base_url = "https://api.deepseek.com/anthropic"

        def messages_create(self, **kwargs):
            captured.update(kwargs)
            return {
                "content": [{"type": "text", "text": '{"records":[]}'}],
                "usage": {"input_tokens": 12, "output_tokens": 3},
            }

    calls = build_targeted_extraction_calls(
        client=FakeClient(),
        roles={"job_listing_extraction": object()},
        timeout_seconds=17,
    )
    response = calls["job_listing_extraction"](
        "system", "user", "deepseek-v4-flash", 4000
    )

    assert captured == {
        "model": "deepseek-v4-flash",
        "max_tokens": 4000,
        "system": "system",
        "messages": [{"role": "user", "content": "user"}],
        "timeout": 17,
    }
    assert response == {
        "records": [],
        "usage": {"input_tokens": 12, "output_tokens": 3},
    }


def test_targeted_work_defers_before_transport_when_cycle_deadline_is_too_low():
    post = _post("deadline-event", text="Attend our live workshop.")
    provider_called = False

    def provider(*_args):
        nonlocal provider_called
        provider_called = True
        return {"records": []}

    class Deadline:
        def can_start(self, _seconds):
            return False

    result = run_targeted_extractions(
        post=post,
        post_types={"events"},
        config=_config(),
        calls={"event_extraction": provider},
        max_calls=20,
        deadline=Deadline(),
    )
    assert provider_called is False
    assert result.deferred_roles == ("event_extraction",)
    assert TargetedExtractionState.objects.count() == 0
