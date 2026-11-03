from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from core.models import Brand, Product

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_caller_supplied_anchor_is_not_a_reviewed_release():
    from core.chart_engine import ChartRequest, ReleaseAnchor, validate_request

    brand = Brand.objects.create(nickname="chart-lab")
    product = Product.objects.create(brand=brand, display_name="Model A")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(
            product_key=product.product_key, date=start.date(), source="caller"
        ),
        start=start,
        end=start + timedelta(days=1),
        cutoff=start + timedelta(days=2),
    )

    resolved = validate_request(request)

    assert resolved.target.product.pk == product.pk
    assert resolved.target.anchor_source == "caller"
    assert resolved.target.reviewed is False


def test_invalid_window_is_rejected_before_database_access():
    from core.chart_engine import ChartRequest, ReleaseAnchor, validate_request

    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product_key="missing", date=start.date(), source="caller"),
        start=start,
        end=start,
        cutoff=start + timedelta(days=1),
    )

    with pytest.raises(ValueError, match="window"):
        validate_request(request)


def test_rejected_release_claim_cannot_be_presented_as_reviewed():
    from django.db import transaction
    from django.utils import timezone

    from core.chart_engine import ChartRequest, ReleaseAnchor, validate_request
    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from tests.test_event_dossiers import claim, dossier

    product = Product.objects.create(display_name="Model B")
    event = dossier("chart-rejected-claim")
    evidence = claim(
        event,
        key="chart-rejected",
        effective_precision="day",
        effective_date=date(2026, 8, 1),
    )
    with transaction.atomic():
        review = complete_review(
            event.pk,
            expected_current_review_id=None,
            display_title="Model B",
            review_state="provisional",
            evidence_cutoff_at=timezone.now(),
            method_version="test-v1",
            actor="test",
            reason="review",
            claims=[ClaimDecision(evidence.pk, "rejected", "not a release")],
            product_release=ProductReleaseInput(
                observed_name="Model B", product_key=product.product_key
            ),
        )
    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(
            product.product_key, start.date(), "review", review.pk, evidence.pk
        ),
        start=start,
        end=start + timedelta(days=1),
        cutoff=start + timedelta(days=2),
    )

    with pytest.raises(ValueError, match="claim"):
        validate_request(request)


def test_accepted_release_claim_resolves_its_existing_review():
    from django.db import transaction
    from django.utils import timezone

    from core.chart_engine import ChartRequest, ReleaseAnchor, validate_request
    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from tests.test_event_dossiers import claim, dossier

    product = Product.objects.create(display_name="Model C")
    event = dossier("chart-accepted-claim")
    anchor_date = date(2026, 8, 1)
    evidence = claim(
        event,
        key="chart-accepted",
        effective_precision="day",
        effective_date=anchor_date,
    )
    with transaction.atomic():
        review = complete_review(
            event.pk,
            expected_current_review_id=None,
            display_title="Model C",
            review_state="provisional",
            evidence_cutoff_at=timezone.now(),
            method_version="test-v1",
            actor="test",
            reason="review",
            claims=[ClaimDecision(evidence.pk, "accepted", "source evidence")],
            product_release=ProductReleaseInput(
                observed_name="Model C", product_key=product.product_key
            ),
        )
    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(
            product.product_key, anchor_date, "review", review.pk, evidence.pk
        ),
        start=start,
        end=start + timedelta(days=1),
        cutoff=timezone.now(),
    )

    result = validate_request(request)

    assert result.target.reviewed is True
    assert result.target.claim_id == evidence.pk

    historical_request = ChartRequest(
        target=request.target,
        start=request.start,
        end=request.end,
        cutoff=datetime(2026, 8, 3, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="cutoff"):
        validate_request(historical_request)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"start": datetime(2026, 8, 1)}, "timezone"),  # noqa: DTZ001
        ({"start": datetime(2026, 8, 1, tzinfo=timezone(timedelta(hours=9)))}, "UTC"),
        ({"history_mode": "guessed"}, "history mode"),
        ({"classifications": (("invented", "anything"),)}, "classification"),
        ({"classifications": (("sentiment", "invented"),)}, "classification"),
        ({"comparison_start": datetime(2026, 8, 1, tzinfo=UTC)}, "comparison"),
    ],
)
def test_invalid_request_shapes_are_rejected(override, message):
    from core.chart_engine import ChartRequest, ReleaseAnchor, validate_request

    start = datetime(2026, 8, 1, tzinfo=UTC)
    values = {
        "target": ReleaseAnchor("missing", start.date(), "caller"),
        "start": start,
        "end": start + timedelta(days=1),
        "cutoff": start + timedelta(days=2),
    }
    values.update(override)
    with pytest.raises(ValueError, match=message):
        validate_request(ChartRequest(**values))


def test_reviewed_metric_mapping_is_resolved_for_the_selected_product():
    from core.benchmark_metric_identity import configure_collection
    from core.chart_engine import (
        ChartRequest,
        MetricSelection,
        ReleaseAnchor,
        validate_request,
    )
    from tests.test_benchmark_download_db_identity import setup_spec

    product, spec = setup_spec()
    contract = configure_collection(spec)
    mapping = contract.mappings.get(source_id="hf")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product.product_key, start.date(), "caller"),
        start=start,
        end=start + timedelta(days=1),
        cutoff=start + timedelta(days=2),
        metrics=(
            MetricSelection(product.product_key, contract.pk, mapping.pk, "downloads"),
        ),
    )

    result = validate_request(request)

    assert result.metrics[0].mapping.pk == mapping.pk
    assert result.metrics[0].unavailable_reason is None

    other = Product.objects.create(display_name="Different product")
    mismatch = ChartRequest(
        target=ReleaseAnchor(other.product_key, start.date(), "caller"),
        start=request.start,
        end=request.end,
        cutoff=request.cutoff,
        metrics=request.metrics,
    )
    assert (
        validate_request(mismatch).metrics[0].unavailable_reason
        == "mapping_product_mismatch"
    )

    source = mapping.source
    source.metadata["use_policy"]["internal_analysis"] = {"status": "prohibited"}
    source.save(update_fields=["metadata"])
    assert (
        validate_request(request).metrics[0].unavailable_reason
        == "source_use_not_permitted"
    )
