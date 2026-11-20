"""Versioned personnel claims retain their exact source and time evidence."""

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from core.geolocation_evidence import source_evidence
from core.models import (
    AccountProfileSnapshot,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
)
from core.targeted_extraction import (
    _persist_personnel,
    _persist_profile_personnel,
    _prompts,
)
from tests.test_targeted_extraction import _config, _post

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def modern_record(post):
    text = post.text
    source = f"post:{post.pk}:text"
    record = {
        "person_name": "Anna Wang",
        "organization_name": "Anthropic",
        "affiliation_type": "employment",
        "brand_id": "anthropic",
        "title_raw": "Engineer",
        "status": "current",
        "start_date": "2026-10",
        "start_date_precision": "month",
    }
    record["field_evidence"] = {
        "schema": "personnel-field-evidence/v1",
        "fields": {
            field: [{"source_key": source, "span": text, "basis": "explicit"}]
            for field in (
                "person_name",
                "organization_name",
                "affiliation_type",
                "brand_id",
                "title_raw",
                "status",
                "start_date",
            )
        },
    }
    return record


def test_modern_post_record_preserves_each_source_and_original_clocks():
    post = _post(
        "modern-person", text="Anna Wang joined Anthropic as Engineer in October 2026."
    )
    post.created_at = datetime(2026, 10, 3, tzinfo=UTC)
    post.save(update_fields=["created_at"])
    record = modern_record(post)
    assert _persist_personnel(post, [record], "personnel-change-extraction-v3")[:2] == (
        1,
        1,
    )
    assert _persist_personnel(post, [record], "personnel-change-extraction-v3")[:2] == (
        0,
        0,
    )
    evidence = PersonBrandAffiliationEvidence.objects.get()
    assert evidence.source_post == post and evidence.review_status == "pending"
    projection = source_evidence(evidence).extracted_claim_data["field_evidence"]
    assert projection["schema"] == "personnel-field-evidence/v1"
    assert projection["validation"] == "exact_span_verified_semantics_pending_review"
    assert (
        projection["fields"]["start_date"][0]["published_at"]
        == post.created_at.isoformat()
    )
    assert projection["fields"]["start_date"][0]["span"] == post.text
    assert PersonBrandAffiliation.objects.get().start_date_precision == "month"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "wrong_source",
        "wrong_span",
        "wrong_basis",
        "extra_field",
        "unknown_record_field",
        "missing_type",
    ],
)
def test_modern_record_rejects_invalid_or_unsupported_field_claims(mutation):
    post = _post(
        "invalid-" + mutation,
        text="Anna Wang joined Anthropic as Engineer in October 2026.",
    )
    record = modern_record(post)
    fields = record["field_evidence"]["fields"]
    if mutation == "missing":
        del fields["title_raw"]
    elif mutation == "wrong_source":
        fields["status"][0]["source_key"] = "post:another:text"
    elif mutation == "wrong_span":
        fields["status"][0]["span"] = "not in any source"
    elif mutation == "wrong_basis":
        fields["status"][0]["basis"] = "certain"
    elif mutation == "extra_field":
        fields["title_raw"][0]["extra"] = "unreviewed"
    elif mutation == "unknown_record_field":
        record["invented_field"] = "unsupported"
    else:
        del record["affiliation_type"]
    with pytest.raises(ValueError):
        _persist_personnel(post, [record], "personnel-change-extraction-v3")
    assert not PersonBrandAffiliation.objects.exists()
    assert not PersonBrandAffiliationEvidence.objects.exists()


@pytest.mark.parametrize(
    "field,value", [("title_raw", "CEO"), ("start_date", "2025-10")]
)
def test_explicit_values_cannot_exceed_their_cited_span(field, value):
    post = _post(
        "fabricated-" + field,
        text="Anna Wang joined Anthropic as Engineer in October 2026.",
    )
    record = modern_record(post)
    record[field] = value
    with pytest.raises(ValueError, match="not present"):
        _persist_personnel(post, [record], "personnel-change-extraction-v3")
    assert not PersonBrandAffiliation.objects.exists()


def test_profile_citation_uses_selected_snapshot_and_cannot_infer_date_from_capture():
    post = _post("modern-profile", text="Unrelated old post about Anthropic")
    snapshot = AccountProfileSnapshot.objects.create(
        account=post.author,
        profile_hash="f" * 64,
        first_observed_at=post.fetched_at,
        last_observed_at=post.fetched_at,
        first_source_kind="post",
        first_source_post=post,
        description="Engineer at Anthropic",
        display_name="Anna Wang",
        present_fields=["description", "display_name"],
    )
    fields = {
        "person_name": [
            {
                "source_key": f"profile:{snapshot.pk}:display_name",
                "span": "Anna Wang",
                "basis": "explicit",
            }
        ]
    }
    for field in ("organization_name", "brand_id", "affiliation_type"):
        fields[field] = [
            {
                "source_key": f"profile:{snapshot.pk}:description",
                "span": "Engineer at Anthropic",
                "basis": "explicit",
            }
        ]
    record = {
        "person_name": "Anna Wang",
        "organization_name": "Anthropic",
        "brand_id": "anthropic",
        "affiliation_type": "employment",
        "source_profile_snapshot_id": snapshot.pk,
        "source_quote": "Engineer at Anthropic",
        "field_evidence": {"schema": "personnel-field-evidence/v1", "fields": fields},
    }
    assert _persist_profile_personnel(
        post, [record], "profile-affiliation-extraction-v3"
    )[:2] == (1, 1)
    evidence = PersonBrandAffiliationEvidence.objects.get()
    assert evidence.source_profile_snapshot_id == snapshot.pk
    assert (
        source_evidence(evidence).extracted_claim_data["field_evidence"]["fields"][
            "organization_name"
        ][0]["observed_at"]
        == snapshot.first_observed_at.isoformat()
    )
    bad = deepcopy(record)
    bad.update(start_date="2026-10", start_date_precision="month")
    bad["field_evidence"]["fields"]["start_date"] = [
        {
            "source_key": f"profile:{snapshot.pk}:description",
            "span": "Engineer at Anthropic",
            "basis": "inferred",
        }
    ]
    with pytest.raises(ValueError, match="publication time"):
        _persist_profile_personnel(post, [bad], "profile-affiliation-extraction-v3")


def test_modern_prompt_includes_source_keys_while_legacy_contract_is_unchanged():
    post = _post("modern-prompt", text="Anna Wang joined Anthropic")
    system, payload = _prompts(
        "personnel_change_extraction", post, version="personnel-change-extraction-v3"
    )
    assert "personnel-field-evidence/v1" in system
    assert f"post:{post.pk}:text" in json.loads(payload)["field_evidence_sources"]
    legacy_system, legacy_payload = _prompts(
        "personnel_change_extraction", post, version="personnel-change-extraction-v2"
    )
    assert "personnel-field-evidence/v1" not in legacy_system
    assert "field_evidence_sources" not in json.loads(legacy_payload)


def test_real_targeted_caller_sends_and_persists_modern_source_contract():
    from core.targeted_extraction import run_targeted_extractions

    post = _post(
        "modern-caller", text="Anna Wang joined Anthropic as Engineer in October 2026."
    )
    post.created_at = datetime(2026, 10, 3, tzinfo=UTC)
    post.save(update_fields=["created_at"])
    record, requests = modern_record(post), []

    def fake_provider(system, user, model, max_tokens):
        requests.append((system, json.loads(user)))
        return {"records": [record]}

    config = _config()
    config.roles[
        "personnel_change_extraction"
    ].prompt_version = "personnel-change-extraction-v3"
    result = run_targeted_extractions(
        post=post,
        post_types={"personnel_changes"},
        config=config,
        calls={"personnel_change_extraction": fake_provider},
        max_calls=1,
    )
    assert result.calls_made == 1 and result.failed_roles == ()
    assert "personnel-field-evidence/v1" in requests[0][0]
    assert (
        requests[0][1]["field_evidence_sources"][f"post:{post.pk}:text"]["text"]
        == post.text
    )
    assert (
        source_evidence(
            PersonBrandAffiliationEvidence.objects.get()
        ).extracted_claim_data["field_evidence"]["schema"]
        == "personnel-field-evidence/v1"
    )


def test_relative_month_inference_is_bound_to_publication_time():
    post = _post(
        "modern-relative", text="Anna Wang is joining Anthropic next month as Engineer."
    )
    post.created_at = datetime(2026, 8, 15, tzinfo=UTC)
    post.save(update_fields=["created_at"])
    record = modern_record(post)
    record["start_date"] = "2026-09"
    record["field_evidence"]["fields"]["start_date"][0]["basis"] = "inferred"
    assert _persist_personnel(post, [record], "personnel-change-extraction-v3")[:2] == (
        1,
        1,
    )
    bad = deepcopy(record)
    bad["start_date"] = "2026-10"
    with pytest.raises(ValueError, match="differs from its source"):
        _persist_personnel(post, [bad], "personnel-change-extraction-v3")


def test_relative_month_without_safe_time_anchor_is_not_invented():
    post = _post(
        "modern-relative-boundary",
        text="Anna Wang is joining Anthropic next month as Engineer.",
    )
    post.created_at = datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
    post.save(update_fields=["created_at"])
    record = modern_record(post)
    record["start_date"] = "2026-09"
    record["field_evidence"]["fields"]["start_date"][0]["basis"] = "inferred"
    with pytest.raises(ValueError, match="time-zone boundary"):
        _persist_personnel(post, [record], "personnel-change-extraction-v3")
    assert not PersonBrandAffiliation.objects.exists()


def test_named_departure_month_infers_arrival_without_inventing_old_role():
    post = _post(
        "modern-named-move",
        text="I left Mistral in October to join Anthropic",
        brand_ids=("mistral", "anthropic"),
    )
    post.created_at = datetime(2026, 11, 4, tzinfo=UTC)
    post.save(update_fields=["created_at"])
    source = f"post:{post.pk}:text"

    def claim(org, status):
        record = {
            "person_name": "Anna Wang",
            "person_handle": "a_nnawang",
            "organization_name": org,
            "brand_id": org.lower(),
            "affiliation_type": "employment",
            "status": status,
        }
        record["field_evidence"] = {
            "schema": "personnel-field-evidence/v1",
            "fields": {
                field: [{"source_key": source, "span": post.text, "basis": basis}]
                for field, basis in {
                    "person_name": "inferred", "person_handle": "inferred",
                    "organization_name": "explicit", "brand_id": "inferred",
                    "affiliation_type": "inferred", "status": "inferred",
                }.items()
            },
        }
        return record

    old = claim("Mistral", "former")
    arrival = claim("Anthropic", "current")
    arrival.update(start_date="2026-10", start_date_precision="month")
    arrival["field_evidence"]["fields"]["start_date"] = [
        {"source_key": source, "span": post.text, "basis": "inferred"}
    ]
    bad = deepcopy(arrival)
    bad["start_date"] = "2025-10"
    with pytest.raises(ValueError, match="differs from its source"):
        _persist_personnel(post, [bad], "personnel-change-extraction-v3")
    bad = deepcopy(arrival)
    bad["organization_name"] = "Mistral"
    with pytest.raises(ValueError, match="supported relative month"):
        _persist_personnel(post, [bad], "personnel-change-extraction-v3")
    assert _persist_personnel(post, [old, arrival], "personnel-change-extraction-v3")[:2] == (2, 2)
    previous = PersonBrandAffiliation.objects.get(observed_organization_name="Mistral")
    assert previous.start_date is None and previous.title_raw in (None, "")
    evidence = PersonBrandAffiliationEvidence.objects.get(
        affiliation__observed_organization_name="Anthropic"
    )
    fields = source_evidence(evidence).extracted_claim_data["field_evidence"]["fields"]
    assert fields["organization_name"][0]["basis"] == "explicit"
    assert fields["start_date"][0]["basis"] == "inferred"
