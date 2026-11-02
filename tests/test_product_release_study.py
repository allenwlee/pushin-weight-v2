from copy import deepcopy
from datetime import timedelta

import pytest
from django.utils import timezone

from core import models
from core.product_release_study import apply_study, validate_assessment

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def packet():
    now = timezone.now()
    account = models.Account.objects.create(author_id="study-announcer")
    models.Post.objects.create(
        tweet_id="study-source",
        author=account,
        text="We announce Model Alto and Model Solo, available now.",
        created_at=now,
    )
    return {
        "schema": "product-release-study-v1",
        "actor": "session-review",
        "assessed_at": now.isoformat(),
        "cases": [
            {
                "case_id": "test",
                "identity": "lab/model-alto/1",
                "name": "Model Alto",
                "reason": "Separate product in the source announcement; publisher remains unverified.",
                "evidence": [
                    {
                        "post_id": "study-source",
                        "excerpt": "We announce Model Alto and Model Solo, available now.",
                        "kind": "announcement",
                        "effective_at": now.isoformat(),
                    }
                ],
                "significance": {
                    "product_kind": "general_model",
                    "lineage": "unknown",
                    "change": "unknown",
                    "reason": "No supported lineage yet",
                },
            }
        ],
    }


def test_study_persists_separate_products_and_reuses_evidence_on_repeat():
    value = packet()
    solo = deepcopy(value["cases"][0])
    solo.update(identity="lab/model-solo/1", name="Model Solo", case_id="test-solo")
    value["cases"].append(solo)
    result = apply_study(value)
    assert len({r["dossier_id"] for r in result["cases"]}) == 2
    assert {r["name"] for r in result["releases"]} == {"Model Alto", "Model Solo"}
    counts = [
        m.objects.count()
        for m in (
            models.EventDossier,
            models.EventDossierClaim,
            models.EventDossierReview,
        )
    ]
    repeated = apply_study(value)
    assert repeated == result
    assert counts == [
        m.objects.count()
        for m in (
            models.EventDossier,
            models.EventDossierClaim,
            models.EventDossierReview,
        )
    ]
    assert models.Post.objects.count() == 1


def test_study_rejects_invented_quote_atomically_and_unknown_fields():
    value = packet()
    value["cases"][0]["evidence"][0]["excerpt"] = "Invented release announcement"
    with pytest.raises(ValueError, match="does not occur"):
        apply_study(value)
    assert not models.EventDossier.objects.exists()
    value["cases"][0]["hidden_model_call"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        validate_assessment(value)


def test_study_confirmation_needs_controlled_announcer_and_retained_research():
    value = packet()
    case = value["cases"][0]
    case["state"] = "confirmed"
    with pytest.raises(ValueError, match="publisher verification"):
        apply_study(value)
    company = models.Company.objects.create(nickname="study-publisher")
    account = models.Account.objects.get(author_id="study-announcer")
    role = models.Role.objects.create(key="study-official")
    models.CompanyAccount.objects.create(
        company=company, account=account, role=role, ownership_confirmed=True
    )
    case["issuer_company_id"] = company.pk
    doc = {
        "url": "https://publisher.example/about",
        "text": "Publisher site identifies its organization and links the announcing account.",
        "observed_at": value["assessed_at"],
    }
    case["verification"] = {
        "post_id": "study-source",
        "entity": doc,
        "ownership": dict(doc, url="https://publisher.example/contact"),
    }
    result = apply_study(value)
    assert result["releases"][0]["state"] == "confirmed"
    proof = models.EventDossierClaim.objects.filter(
        claim_kind_reference__code="source_ownership"
    ).get()
    assert proof.source_archive.capture_kind == "release_study_assessment"
    models.CompanyAccount.objects.filter(company=company, account=account).update(
        ownership_confirmed=False
    )
    with pytest.raises(ValueError, match="verified publisher"):
        apply_study(value)


def test_confirmation_rejects_reshared_announcement_even_for_verified_account():
    value = packet()
    case = value["cases"][0]
    case["state"] = "confirmed"
    models.Post.objects.filter(pk="study-source").update(is_retweet=True)
    company = models.Company.objects.create(nickname="study-publisher")
    account = models.Account.objects.get(author_id="study-announcer")
    role = models.Role.objects.create(key="study-official")
    models.CompanyAccount.objects.create(company=company, account=account, role=role, ownership_confirmed=True)
    case["issuer_company_id"] = company.pk
    doc = {"url": "https://publisher.example/about", "text": "Publisher links the account.",
           "observed_at": value["assessed_at"]}
    case["verification"] = {"post_id": "study-source", "entity": doc, "ownership": doc}
    with pytest.raises(ValueError, match="verified publisher"):
        apply_study(value)


def test_discussion_packet_reports_source_count_and_rejects_stale_inputs():
    from core.discussion_windows import capture_window, discussion_packet

    packet()
    post = models.Post.objects.get(pk="study-source")
    brand = models.Brand.objects.create(nickname="packet-brand")
    models.PostBrand.objects.create(post=post, brand=brand)
    start = post.created_at - timedelta(minutes=1)
    snapshot, _ = capture_window(brand.pk, start, start + timedelta(minutes=15))
    result = discussion_packet(snapshot.pk)
    assert result["post_count"] == 1
    assert len(result["sources"]) == 1
    models.Post.objects.filter(pk=post.pk).update(lang="zh")
    with pytest.raises(ValueError, match="changed|stale"):
        discussion_packet(snapshot.pk)


def test_study_retains_day_precision_without_inventing_an_hour():
    value = packet()
    item = value["cases"][0]["evidence"][0]
    item["effective_date"] = item.pop("effective_at")[:10]
    result = apply_study(value)
    claims = result["releases"][0]["claims"]
    assert any(c["precision"] == "day" for c in claims)
    assert result["cases"][0]["dated_claims"]


def test_report_distinguishes_announcement_and_availability_comparisons():
    from core.discussion_windows import capture_window
    from core.product_release_report import release_rows, render_report

    value = packet()
    case = value["cases"][0]
    case["evidence"].append(dict(case["evidence"][0], kind="availability"))
    saved = apply_study(value)["cases"][0]
    post = models.Post.objects.get(pk="study-source")
    brand = models.Brand.objects.create(nickname="anchor-report")
    models.PostBrand.objects.create(post=post, brand=brand)
    snapshot, _ = capture_window(
        brand.pk, post.created_at, post.created_at + timedelta(days=7)
    )
    for claim_id in saved["dated_claims"]:
        models.EventDossierDiscussionWindow.objects.create(
            event_dossier_id=saved["dossier_id"],
            review_id=saved["review_id"],
            anchor_claim_id=claim_id,
            snapshot=snapshot,
            role="after",
        )
    rows = release_rows([saved["dossier_id"]])
    assert {w["anchor_kind"] for w in rows[0]["discussion"]} == {
        "announcement",
        "availability",
    }
    assert {w["anchor_claim_id"] for w in rows[0]["discussion"]} == set(
        saved["dated_claims"]
    )
    html = render_report(rows)
    assert "7d after announcement: 1 posts" in html
    assert "7d after availability: 1 posts" in html


def test_future_days_and_research_are_not_presented_as_observed():
    value = packet()
    evidence = value["cases"][0]["evidence"][0]
    evidence.pop("effective_at")
    evidence["effective_date"] = (timezone.now() + timedelta(days=1)).date().isoformat()
    with pytest.raises(ValueError, match="postdate"):
        validate_assessment(value)
    evidence.pop("effective_date")
    value["cases"][0]["research"] = [
        {
            "url": "https://publisher.example/release",
            "text": "Tomorrow's evidence is not known yet",
            "observed_at": (timezone.now() + timedelta(days=1)).isoformat(),
        }
    ]
    with pytest.raises(ValueError, match="cutoff"):
        validate_assessment(value)


def test_provisional_release_cannot_claim_availability_without_access_evidence():
    value = packet()
    value["cases"][0]["availability"] = "available"
    with pytest.raises(ValueError, match="Availability requires"):
        apply_study(value)


def test_report_does_not_attach_later_unreviewed_claims_to_saved_review():
    from core.event_dossiers import add_claim
    from core.product_release_report import release_rows

    result = apply_study(packet())
    event_id = result["cases"][0]["dossier_id"]
    source = models.EventDossierSource.objects.get(event_dossier_id=event_id)
    claim = add_claim(
        source.pk,
        claim_kind="availability",
        scope_key="later-api",
        assertion_text="A later access report",
        source_excerpt="A later access report",
        extraction_version="later-test",
    )
    row = release_rows([event_id])[0]
    assert str(claim.pk) not in {c["id"] for c in row["claims"]}
    assert row["availability"] == "unknown"
    assert row["review_id"] == result["cases"][0]["review_id"]


def test_untracked_publisher_is_retained_from_third_party_release_evidence():
    value = packet()
    models.Post.objects.filter(pk="study-source").update(
        text="Giotto announces Alto today."
    )
    case = value["cases"][0]
    case["evidence"][0]["excerpt"] = "Giotto announces Alto today."
    case["observed_publisher"] = {"post_id": "study-source", "name": "Giotto"}
    result = apply_study(value)
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier_id=result["cases"][0]["dossier_id"],
        scope_key="observed_publisher",
    )
    candidate = claim.reported_brand_discovery_candidate
    assert candidate.observed_name == "Giotto"
    assert candidate.verification_status == "pending"
    assert candidate.source_identities == ["post:study-source"]
    apply_study(value)
    assert models.BrandDiscoveryCandidate.objects.filter(pk=candidate.pk).count() == 1


def test_exclusive_source_can_merge_pending_container_with_publisher_context():
    value = packet()
    models.Post.objects.filter(pk="study-source").update(
        author_handle="new_lab", author_name="New Lab"
    )
    value["cases"][0]["evidence"][0]["exclusive_source"] = True
    result = apply_study(value)
    assert models.EventDossier.objects.filter(merged_into__isnull=True).count() == 1
    assert models.EventDossier.objects.filter(
        merged_into_id=result["cases"][0]["dossier_id"]
    ).exists()
    repeated = apply_study(value)
    assert repeated["cases"] == result["cases"]
