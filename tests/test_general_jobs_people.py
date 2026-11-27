import json

import pytest

from core.models import (
    AffiliationType,
    JobListing,
    JobListingEvidence,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
)
from monitor.general_readers import general_feed
from tests.general_helpers import NOW, classified_post
from tests.person_factory import person_with_name

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
    person = person or person_with_name(
        "Alex Kim",
        date_of_birth="1990",
        date_of_birth_precision="year",
        sex="female",
    )
    type_code = overrides.pop("affiliation_type", "employment")
    claim = PersonBrandAffiliation.objects.create(
        **(
            {
                "person": person,
                "brand_id": "qwen",
                "affiliation_type_reference": AffiliationType.objects.get(code=type_code),
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


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("section,post_type", [("jobs", "job_listings"), ("moving", "personnel_changes")])
def test_recent_classified_lookup_matches_existing_pagination(monkeypatch, section, post_type):
    from monitor import general_readers

    for index in range(12):
        classified_post(f"ordered-{index:02d}", post_type, age=index // 3, brand="qwen")
    classified_post("different-brand", post_type, brand="mistral")

    def collect():
        result, cursor = [], None
        for _ in range(4):
            page = general_feed(section, brands=["qwen"], limit=3, cursor=cursor, as_of=NOW)
            result.extend(item["id"] for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                return result
        pytest.fail("Pagination did not finish within the expected four pages")

    actual = collect()
    monkeypatch.setattr(general_readers, "_recent_classified_candidates", lambda *args: None)
    assert actual == collect()
    assert actual == [f"ordered-{index:02d}" for index in range(12)]


@pytest.mark.django_db(transaction=True)
def test_jobs_skip_recent_history_scan_while_moving_retains_it(monkeypatch):
    from monitor import general_readers

    classified_post("jobs-direct", "job_listings")
    classified_post("moving-recent", "personnel_changes")
    calls = []
    original = general_readers._recent_classified_candidates

    def observed(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(general_readers, "_recent_classified_candidates", observed)
    assert general_feed("jobs", as_of=NOW)["items"][0]["id"] == "jobs-direct"
    assert calls == []
    assert general_feed("moving", as_of=NOW)["items"][0]["id"] == "moving-recent"
    assert len(calls) == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("section,post_type", [("jobs", "job_listings"), ("moving", "personnel_changes")])
def test_recent_classified_lookup_falls_back_for_sparse_brand(monkeypatch, section, post_type):
    from monitor import general_readers

    older = classified_post("sparse-classified", post_type, age=50, brand="qwen")
    for index in range(8):
        classified_post(f"new-other-{index}", post_type, age=index + 1, brand="mistral")
    monkeypatch.setattr(general_readers, "_RECENT_CLASSIFIED_SCAN_LIMIT", 5)
    page = general_feed(section, brands=["qwen"], as_of=NOW, limit=2)
    assert [item["id"] for item in page["items"]] == [older.pk]


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
