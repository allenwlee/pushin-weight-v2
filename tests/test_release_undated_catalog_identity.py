"""An original release can have a confirmed Product before it has a launch date."""

from datetime import timedelta

import pytest
from django.db import transaction

from core import models
from core.event_dossiers import ProductReleaseInput
from core.product_release_pipeline import record_intake_decision
from core.release_chart_handoff import (
    lock_catalog_release,
    resolve_catalog_release,
    resolve_release,
)
from tests.test_event_dossiers import claim, dossier, review

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def confirmed_undated():
    brand = models.Brand.objects.create(nickname="moonshot")
    product = models.Product.objects.create(brand=brand, display_name="Kimi K3.1 Pro")
    event = dossier("undated-kimi")
    evidence = claim(event, key="original-release", effective_precision="unknown")
    decision = review(
        event,
        evidence,
        review_state="confirmed",
        product_release=ProductReleaseInput(
            observed_name=product.display_name,
            product_key=product.product_key,
            disclosure_state="announced",
        ),
    )
    return event, evidence, decision, product


def test_undated_catalog_identity_is_pinned_and_never_supplies_a_chart_date():
    event, evidence, decision, product = confirmed_undated()
    catalog = resolve_catalog_release(event.pk)
    assert (catalog.dossier_id, catalog.product_key, catalog.brand_id) == (
        event.pk,
        product.product_key,
        product.brand_id,
    )
    assert not hasattr(catalog, "date")
    with transaction.atomic():
        assert lock_catalog_release(catalog) == catalog
    with pytest.raises(ValueError, match="no qualified day"):
        resolve_release(event.pk)
    with pytest.raises(ValueError, match="confirmed release review"):
        resolve_catalog_release(
            event.pk, cutoff=decision.recorded_at - timedelta(seconds=1)
        )
    record_intake_decision(
        event.pk,
        claim_id=evidence.pk,
        outcome="non_release",
        actor="test",
        reason="publisher correction",
    )
    with transaction.atomic(), pytest.raises(ValueError, match="inactive"):
        lock_catalog_release(catalog)


@pytest.mark.parametrize("flag", ["private", "disabled"])
def test_private_or_disabled_undated_product_has_no_catalog_release(flag):
    event, _, _, product = confirmed_undated()
    models.Product.objects.filter(pk=product.pk).update(**{flag: True})
    with pytest.raises(ValueError, match="public tracked Product"):
        resolve_catalog_release(event.pk)


def test_undated_catalog_identity_requires_qualified_product_and_review():
    event, evidence, decision, _ = confirmed_undated()
    review(
        event,
        evidence,
        expected_current_review_id=decision.pk,
        review_state="unresolved",
    )
    with pytest.raises(ValueError, match="confirmed release review"):
        resolve_catalog_release(event.pk)
    with pytest.raises(ValueError):
        resolve_catalog_release(dossier("unmatched-launch").pk)


def test_lock_checks_fingerprint_on_dated_release_too():
    from dataclasses import replace
    from datetime import date

    from tests.test_release_chart_handoff import confirmed

    _, event, _, _ = confirmed(date(2026, 8, 14))
    chart = resolve_release(event.pk)
    with transaction.atomic():
        assert lock_catalog_release(chart) == chart
        with pytest.raises(ValueError, match="changed"):
            lock_catalog_release(replace(chart, fingerprint="wrong"))


def test_saved_undated_p2_release_requires_its_exact_product_membership():
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    brand = models.Brand.objects.create(nickname="moonshot")
    name = "Kimi K3.1 Pro"
    product = models.Product.objects.create(brand=brand, display_name=name)
    text = "Moonshot released Kimi K3.1 Pro."
    post = models.Post.objects.create(tweet_id="undated-release-report", text=text)
    models.PostBrand.objects.create(post=post, brand=brand)
    models.PostBrandProduct.objects.create(
        post=post,
        brand=brand,
        product=product,
        observed_name=name,
        verification_policy_version="fixture",
        source_evidence={},
    )
    item = finding(name)
    item["brand_id"] = brand.pk
    item["assertions"][0].update(assertion_text=text, source_excerpt=text)
    row = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )["findings"][0]
    with pytest.raises(ValueError):
        resolve_catalog_release(row["dossier_id"])
    match = resolve_saved_release_finding(claim_id=row["anchor_claim_id"])
    assert match["product_key"] == str(product.product_key)
    with pytest.raises(ValueError):
        resolve_release(row["dossier_id"])
    identity = resolve_catalog_release(row["dossier_id"])
    assert identity.product_key == product.product_key and not hasattr(identity, "date")
    with transaction.atomic():
        assert lock_catalog_release(identity) == identity


def test_confirmed_review_cannot_promote_an_unresolved_finding_into_catalog_work():
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    brand = models.Brand.objects.create(nickname="unresolved")
    product = models.Product.objects.create(brand=brand, display_name="Model A")
    post = models.Post.objects.create(
        tweet_id="unresolved-release", text="Released Model A"
    )
    item = finding()
    item.update(novelty="unresolved", brand_id=brand.pk)
    row = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )["findings"][0]
    anchor = models.EventDossierClaim.objects.get(pk=row["anchor_claim_id"])
    event = models.EventDossier.objects.get(pk=row["dossier_id"])
    review(
        event,
        anchor,
        review_state="confirmed",
        product_release=ProductReleaseInput(
            observed_name=product.display_name,
            product_key=product.product_key,
            disclosure_state="announced",
        ),
    )
    with pytest.raises(ValueError, match="active eligible finding"):
        resolve_catalog_release(event.pk)


@pytest.mark.parametrize(
    "dated,measure", [(False, False), (False, True), (True, False)]
)
def test_scheduled_discovery_selects_recently_reviewed_models(
    dated, measure, settings, monkeypatch
):
    from django.utils import timezone

    from core import release_chart_collection as collection
    from core.product_vocabulary import product_type_id
    from tests.test_release_chart_handoff import confirmed

    if dated:
        product, event, _, _ = confirmed(timezone.now().date())
    else:
        event, _, _, product = confirmed_undated()
    models.Product.objects.filter(pk=product.pk).update(
        product_type_id=product_type_id("model-llm")
    )
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    settings.BENCHMARK_COLLECTION_ENABLED = measure
    checked = []
    monkeypatch.setattr(
        collection,
        "_discover_public_catalogs",
        lambda release, *_: checked.append((release.dossier_id, release.product_key)),
    )
    monkeypatch.setattr(
        "core.release_provider_identity.discover_verified_hf_model",
        lambda *a, **kw: False,
    )

    result = collection.collect_due_release_metrics(
        client=None, confirm_identities=True
    )

    assert checked == [(event.pk, product.product_key)]
    assert result["applied"] == result["linked_jobs"] == result["requests"] == 0


def test_recent_reviews_rotate_and_share_the_first_slot_with_pending_announcements():
    from django.utils import timezone

    from core.event_dossiers import add_claim
    from core.product_vocabulary import product_type_id
    from core.release_chart_collection import _recent_publisher_findings

    brand = models.Brand.objects.create(nickname="review-lab")
    product = models.Product.objects.create(
        brand=brand,
        display_name="Release model",
        product_type_id=product_type_id("model-llm"),
    )
    detail = ProductReleaseInput(
        observed_name=product.display_name,
        product_key=product.product_key,
        disclosure_state="announced",
    )
    reviewed = set()
    for i in range(7):
        event = dossier(f"reviewed-{i}")
        review(
            event,
            claim(event, key=f"review-claim-{i}"),
            review_state="confirmed",
            product_release=detail,
        )
        reviewed.add(event.pk)
    pending = dossier("unreviewed-launch")
    original = claim(pending, key="pending-original")
    add_claim(
        original.event_dossier_source_id,
        claim_kind="release_context",
        scope_key="pulse-novelty-v1:pending",
        assertion_text="new_release",
        source_excerpt="announced",
        extraction_version="test",
    )

    now = timezone.now()
    pages = [
        _recent_publisher_findings(
            now + timedelta(minutes=15 * i), include_confirmed=True
        )
        for i in range(2)
    ]
    assert all(pending.pk in page[:2] and 1 < len(page) <= 5 for page in pages)
    assert sum(page[0] == pending.pk for page in pages) == 1
    assert set().union(*pages) == reviewed | {pending.pk}
    assert (
        _recent_publisher_findings(now + timedelta(days=2), include_confirmed=True)
        == []
    )
