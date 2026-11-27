from datetime import date, timedelta
from uuid import uuid4

import pytest

from core.event_dossiers import ClaimDecision, ProductReleaseInput
from core.models import Brand, Product
from core.release_chart_handoff import resolve_release
from tests.test_event_dossiers import claim, dossier, review

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def confirmed(*days, product=None):
    if product is None:
        brand = Brand.objects.create(nickname="chart-fixture")
        product = Product.objects.create(brand=brand, display_name="River")
    event = dossier("release-chart")
    evidence = [
        claim(event, key=f"river-{n}", effective_precision="day", effective_date=day)
        for n, day in enumerate(days)
    ]
    detail = ProductReleaseInput(
        observed_name="River",
        product_key=product.product_key,
        disclosure_state="announced",
        availability_state="available",
    )
    saved = review(
        event,
        evidence[0],
        review_state="confirmed",
        product_release=detail,
        claims=[
            ClaimDecision(row.pk, "accepted", "producer announcement")
            for row in evidence
        ],
    )
    return product, event, saved, evidence


def test_confirmed_release_resolves_and_pins_evidence():
    day = date(2026, 8, 14)
    product, event, saved, evidence = confirmed(day)
    first = resolve_release(str(event.pk))
    assert (
        first.product_key,
        first.date,
        first.source,
        first.dossier_id,
        first.review_id,
        first.claim_id,
    ) == (
        product.product_key,
        day,
        "dossier-reviewed",
        event.pk,
        saved.pk,
        evidence[0].pk,
    )
    assert first == resolve_release(event.pk)
    assert first.brand_id == product.brand_id
    with pytest.raises(ValueError):
        resolve_release(event.pk, cutoff=saved.recorded_at - timedelta(seconds=1))


def test_conflicting_accepted_dates_stay_pending():
    _, event, _, _ = confirmed(date(2026, 8, 14), date(2026, 8, 15))
    with pytest.raises(ValueError, match="conflict"):
        resolve_release(event.pk)


def test_unreviewed_context_does_not_displace_accepted_milestone_on_card():
    from core.event_dossiers import add_claim
    from core.pulse_readers import release_page

    day = date(2026, 8, 14)
    _, event, _, accepted = confirmed(day)
    for i in range(256):
        add_claim(accepted[0].event_dossier_source_id, claim_kind="release_context", scope_key=f"background-{i}",
                  assertion_text="Background context", source_excerpt="Background context", extraction_version="test-v1")
    assert release_page()["entries"][0]["timeline_date"] == resolve_release(event.pk).date == day


def test_older_identity_cannot_override_superseding_review():
    _, event, old, evidence = confirmed(date(2026, 8, 14))
    review(
        event, evidence[0], expected_current_review_id=old.pk, review_state="unresolved"
    )
    with pytest.raises(ValueError):
        resolve_release(event.pk)


def test_unqualified_and_unknown_release_stay_pending():
    with pytest.raises(ValueError):
        resolve_release(dossier("pending-chart-release").pk)
    with pytest.raises(ValueError):
        resolve_release(uuid4())


def test_old_release_link_uses_the_canonical_review_after_merge():
    from core.product_release_pipeline import merge_dossiers

    _, destination, _, evidence = confirmed(date(2026, 8, 14))
    old = dossier("river-duplicate")
    claim(old, key="duplicate-source")
    merge_dossiers(old.pk, destination.pk, actor="fixture", reason="same named release")
    result = resolve_release(old.pk)
    assert result == resolve_release(destination.pk)
    assert result.claim_id == evidence[0].pk


def test_current_negative_intake_takes_precedence_and_confirmed_correction_can_restore():
    from core.product_release_pipeline import record_intake_decision
    from core.pulse_readers import release_page
    from monitor.pulse_views import _card

    product, event, first, evidence = confirmed(date(2026, 8, 14))
    record_intake_decision(
        event.pk,
        claim_id=evidence[0].pk,
        outcome="non_release",
        actor="fixture",
        reason="new conflicting evidence",
    )
    with pytest.raises(ValueError, match="inactive"):
        resolve_release(event.pk)
    assert not _card(release_page()["entries"][0])["can_open_chart"]
    fixed = review(
        event,
        evidence[0],
        expected_current_review_id=first.pk,
        review_state="confirmed",
        product_release=ProductReleaseInput(
            observed_name=product.display_name,
            product_key=product.product_key,
            disclosure_state="announced",
        ),
    )
    assert resolve_release(event.pk).review_id == fixed.pk
    assert _card(release_page()["entries"][0])["can_open_chart"]



@pytest.mark.parametrize("same_post", [False, True])
def test_review_accepts_both_launch_and_later_access_update_without_moving_launch(same_post):
    from core.models import EventDossier, EventDossierClaim, Post
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_pipeline import merge_dossiers
    from core.pulse_readers import release_page
    from tests.test_pulse_finding_persistence import finding

    brand = Brand.objects.create(nickname="mixed-reviewed")
    product = Product.objects.create(brand=brand, display_name="River Alpha")
    post = Post.objects.create(tweet_id="mixed-review", text="River Alpha launched Nov 12. API access launched Nov 18.")
    events = []
    for idx, (subtype, day) in enumerate([("new_release", 12), ("availability_update", 18)]):
        source = post if same_post or idx == 0 else Post.objects.create(tweet_id="mixed-review-api", text=post.text)
        item = finding(name=product.display_name, key=str(idx + 1) * 64)
        item.update(brand_id=brand.pk, novelty=subtype)
        item["assertions"][0].update(claim_kind="announcement", effective_precision="day", effective_date=f"2026-11-{day}",
                                     source_excerpt=source.text, assertion_text=source.text)
        events.append(persist_classified_release_findings(
            source={"kind": "post", "id": source.pk}, revision_id="b" * 64,
            content_fingerprint="c" * 64, extraction_version="test", findings=[item]
        )["findings"][0]["dossier_id"])

    merge_dossiers(events[1], events[0], actor="test reviewer", reason="same product and edition")
    event = EventDossier.objects.get(pk=events[0])
    evidence = EventDossierClaim.objects.filter(event_dossier_source__event_dossier=event)
    decisions = [
        ClaimDecision(claim.pk, "accepted", "Confirmed source claim")
        for claim in evidence if claim.scope_key.startswith(("pulse-finding-v1:", "pulse-assertion-v1:"))
    ]
    review(event, evidence.first(), review_state="confirmed", product_release=ProductReleaseInput(
        observed_name=product.display_name, product_key=product.product_key, disclosure_state="announced"
    ), claims=decisions)
    assert resolve_release(event.pk).date == date(2026, 11, 12)
    assert release_page()["entries"][0]["timeline_date"] == date(2026, 11, 12)
