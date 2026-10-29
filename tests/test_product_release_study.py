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
