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
        ({"end": datetime(2028, 8, 1, tzinfo=UTC)}, "window"),
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


def test_omitting_metric_selection_discovers_reviewed_product_metrics():
    from core.benchmark_metric_identity import configure_collection
    from core.chart_engine import ChartRequest, ReleaseAnchor, validate_request
    from tests.test_benchmark_download_db_identity import setup_spec

    product, spec = setup_spec()
    contract = configure_collection(spec)
    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product.product_key, start.date(), "caller"),
        start=start,
        end=start + timedelta(days=1),
        cutoff=start + timedelta(days=2),
    )

    metrics = validate_request(request).metrics

    assert {item.selection.metric_key for item in metrics} == {
        "downloads",
        "downloads_all_time",
    }
    assert all(item.mapping.contract_id == contract.pk for item in metrics)


def test_brand_discussion_uses_exact_half_open_window_without_saving_snapshots():
    from django.utils import timezone

    from core.chart_engine import (
        ChartRequest,
        ReleaseAnchor,
        brand_discussion,
        validate_request,
    )
    from core.models import DiscussionWindowSnapshot, Post, PostBrand

    brand = Brand.objects.create(nickname="chart-bounds")
    product = Product.objects.create(brand=brand, display_name="Model D")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    for minute in (0, 5, 15, 20):
        post = Post.objects.create(
            tweet_id=f"chart-bound-{minute}",
            created_at=start + timedelta(minutes=minute),
        )
        PostBrand.objects.create(post=post, brand=brand)
    request = ChartRequest(
        target=ReleaseAnchor(product.product_key, start.date(), "caller"),
        start=start + timedelta(minutes=5),
        end=start + timedelta(minutes=20),
        cutoff=timezone.now(),
        history_mode="hindsight",
    )
    before = DiscussionWindowSnapshot.objects.count()

    result = brand_discussion(validate_request(request))

    assert result["scope"] == "brand_discussion"
    assert result["post_count"] == 2
    assert result["classification"]["unclassified"] == 2
    assert DiscussionWindowSnapshot.objects.count() == before


def test_multiple_classification_filters_count_a_post_once():
    from django.utils import timezone

    from core.chart_engine import (
        ChartRequest,
        ReleaseAnchor,
        brand_discussion,
        validate_request,
    )
    from core.models import Post, PostBrand, PostBrandSignal
    from tests.test_classification_readers import current_state, seed_keys

    seed_keys()
    brand = Brand.objects.create(nickname="chart-filter")
    product = Product.objects.create(brand=brand, display_name="Model E")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    post = Post.objects.create(tweet_id="chart-filtered", created_at=start)
    PostBrand.objects.create(post=post, brand=brand)
    current_state(post, brand, outcome="classified", sentiment_id="positive")
    PostBrandSignal.objects.create(
        post=post, brand=brand, post_type_id="other", sentiment_id="positive"
    )
    request = ChartRequest(
        target=ReleaseAnchor(product.product_key, start.date(), "caller"),
        start=start,
        end=start + timedelta(days=1),
        cutoff=timezone.now(),
        history_mode="hindsight",
        classifications=(("post_type", "other"), ("sentiment", "positive")),
    )

    result = brand_discussion(validate_request(request))

    assert result["post_count"] == 1
    assert result["classification"]["classified"] == 1


def test_strict_past_brand_membership_does_not_claim_reconstructible_history():
    from core.chart_engine import (
        ChartRequest,
        ReleaseAnchor,
        brand_discussion,
        validate_request,
    )

    brand = Brand.objects.create(nickname="chart-history")
    product = Product.objects.create(brand=brand, display_name="Model F")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product.product_key, start.date(), "caller"),
        start=start,
        end=start + timedelta(days=1),
        cutoff=start + timedelta(days=2),
    )

    result = brand_discussion(validate_request(request))

    assert result["status"] == "historical_membership_unavailable"
    assert result["post_count"] is None


def test_hindsight_cannot_include_posts_published_after_cutoff():
    from core.chart_engine import (
        ChartRequest,
        ReleaseAnchor,
        brand_discussion,
        validate_request,
    )
    from core.models import Post, PostBrand

    brand = Brand.objects.create(nickname="chart-cutoff")
    product = Product.objects.create(brand=brand, display_name="Model G")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    for day in (0, 2):
        post = Post.objects.create(
            tweet_id=f"chart-cutoff-{day}", created_at=start + timedelta(days=day)
        )
        PostBrand.objects.create(post=post, brand=brand)
    request = ChartRequest(
        target=ReleaseAnchor(product.product_key, start.date(), "caller"),
        start=start,
        end=start + timedelta(days=4),
        cutoff=start + timedelta(days=1),
        history_mode="hindsight",
    )

    result = brand_discussion(validate_request(request))

    assert result["post_count"] == 1
    assert list(result["daily"]) == ["2026-08-01"]


def test_source_metric_preserves_historical_values_and_labels_hindsight():
    from core.benchmark_metric_series import metric_points
    from core.chart_engine import (
        ChartRequest,
        MetricSelection,
        ReleaseAnchor,
        metric_series,
        validate_request,
    )
    from tests.test_benchmark_release_response import response_contract, seed

    contract = response_contract()
    seed(contract)
    mapping = contract.mappings.get(source_id="hf")
    product_key = mapping.subject.product_id
    start = datetime(2026, 9, 10, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product_key, start.date(), "caller"),
        start=start,
        end=datetime(2026, 9, 20, tzinfo=UTC),
        cutoff=datetime(2026, 9, 21, tzinfo=UTC),
        history_mode="hindsight",
        metrics=(MetricSelection(product_key, contract.pk, mapping.pk, "downloads"),),
    )

    result = metric_series(validate_request(request), 0)

    assert result["source"] == "hf"
    assert result["history_mode"] == "hindsight"
    assert any(point["value"] is not None for point in result["points"])
    assert all(point["date"] < "2026-09-20" for point in result["points"])
    points = {point["date"]: point for point in result["points"]}
    assert points["2026-09-18"]["net_change"] == "-20"
    assert points["2026-09-19"]["coverage"] == "missing"
    assert points["2026-09-19"]["net_change"] is None
    line = contract.methodology["comparisons"]["response"]["lines"][1]
    expected, _, _ = metric_points(contract, line, sorted(points))
    assert {p["date"]: p["value"] for p in result["points"]} == {
        p["date"]: p["raw_value"] for p in expected
    }


def test_partial_opencode_day_is_not_reported_as_complete():
    from core.benchmark_metric_store import persist_source
    from core.chart_engine import (
        ChartRequest,
        MetricSelection,
        ReleaseAnchor,
        metric_series,
        validate_request,
    )
    from tests.test_benchmark_opencode import configured, endpoint, read

    contract = configured()
    persist_source(contract, "opencode", "f" * 64, read(endpoint()))
    mapping = contract.mappings.get(source_id="opencode")
    product_key = mapping.subject.product_id
    start = datetime(2026, 10, 6, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product_key, start.date(), "caller"),
        start=start,
        end=datetime(2026, 10, 8, tzinfo=UTC),
        cutoff=datetime(2026, 10, 9, tzinfo=UTC),
        history_mode="hindsight",
        metrics=(MetricSelection(product_key, contract.pk, mapping.pk, "tokens"),),
    )

    points = {
        point["date"]: point
        for point in metric_series(validate_request(request), 0)["points"]
    }

    assert points["2026-10-06"]["value"] == "9007199254740993123"
    assert points["2026-10-07"]["value"] is None
    assert points["2026-10-07"]["coverage"] == "partial_source"


def test_opencode_uses_source_revision_order_not_import_order():
    from core.benchmark_metric_store import persist_source
    from core.chart_engine import (
        ChartRequest,
        MetricSelection,
        ReleaseAnchor,
        metric_series,
        validate_request,
    )
    from tests.test_benchmark_opencode import configured, endpoint, read

    contract = configured()
    for key, tokens, stamp in [
        ("4", 40, "12:00:00"),
        ("5", 40, "12:30:00"),
        ("6", 10, "12:15:00"),
    ]:
        persist_source(
            contract,
            "opencode",
            key * 64,
            read(endpoint(tokens=tokens, updated=f"2026-10-07T{stamp}Z")),
        )
    mapping = contract.mappings.get(source_id="opencode")
    product_key = mapping.subject.product_id
    start = datetime(2026, 10, 6, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product_key, start.date(), "caller"),
        start=start,
        end=datetime(2026, 10, 8, tzinfo=UTC),
        cutoff=datetime(2026, 10, 9, tzinfo=UTC),
        history_mode="hindsight",
        metrics=(MetricSelection(product_key, contract.pk, mapping.pk, "tokens"),),
    )

    points = {
        point["date"]: point
        for point in metric_series(validate_request(request), 0)["points"]
    }

    assert points["2026-10-06"]["value"] == "40"


def test_openrouter_does_not_replace_newer_source_revision_with_later_import():
    from core.benchmark_metric_store import persist_source
    from core.chart_engine import (
        ChartRequest,
        MetricSelection,
        ReleaseAnchor,
        metric_series,
        validate_request,
    )
    from tests.test_benchmark_download_persistence import provider_contract

    contract = provider_contract("openrouter", ["total_tokens"])
    for key, tokens, as_of in [
        ("1", "40", "2026-10-07T12:00:00Z"),
        ("2", "10", "2026-10-06T12:00:00Z"),
    ]:
        persist_source(
            contract,
            "openrouter",
            key * 64,
            {
                "status": "ok",
                "meta": {"version": "v1"},
                "as_of": as_of,
                "rows": [
                    {
                        "date": "2026-10-05",
                        "model_permaslug": "lab/model",
                        "total_tokens": tokens,
                    }
                ],
            },
        )
    mapping = contract.mappings.get(source_id="openrouter")
    product_key = mapping.subject.product_id
    start = datetime(2026, 10, 5, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product_key, start.date(), "caller"),
        start=start,
        end=start + timedelta(days=1),
        cutoff=start + timedelta(days=5),
        history_mode="hindsight",
        metrics=(
            MetricSelection(product_key, contract.pk, mapping.pk, "total_tokens"),
        ),
    )

    assert metric_series(validate_request(request), 0)["points"][0]["value"] == "40"


@pytest.mark.parametrize(
    ("source", "key", "day", "expected"),
    [
        ("openrouter", "total_tokens", "2026-09-18", "40"),
        ("arena", "rating", "2026-09-18", 1390.0),
    ],
)
def test_supported_provider_series_keep_their_own_units_and_values(
    source, key, day, expected
):
    from core.chart_engine import (
        ChartRequest,
        MetricSelection,
        ReleaseAnchor,
        metric_series,
        validate_request,
    )
    from tests.test_benchmark_release_response import response_contract, seed

    contract = response_contract()
    seed(contract)
    mapping = contract.mappings.get(source_id=source)
    product_key = mapping.subject.product_id
    start = datetime(2026, 9, 10, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product_key, start.date(), "caller"),
        start=start,
        end=datetime(2026, 9, 20, tzinfo=UTC),
        cutoff=datetime(2026, 9, 21, tzinfo=UTC),
        history_mode="hindsight",
        metrics=(MetricSelection(product_key, contract.pk, mapping.pk, key),),
    )

    result = metric_series(validate_request(request), 0)
    point = next(point for point in result["points"] if point["date"] == day)

    assert point["value"] == expected
    assert point["unit"]


def test_github_product_repository_metric_is_not_confused_with_account_metrics():
    from core.chart_engine import (
        ChartRequest,
        MetricSelection,
        ReleaseAnchor,
        metric_series,
        validate_request,
    )
    from core.models import DataSource, TimeZone
    from core.source_metric_projection import configure_source_statistics
    from tests.test_benchmark_use_policy import decision
    from tests.test_source_metric_projection import configured, evidence, project

    TimeZone.objects.get_or_create(pk="UTC")
    _, raw, product, spec = configured("github", product_type="llm-model", mapped=True)
    source = DataSource.objects.get(pk="github")
    source.metadata["use_policy"]["internal_analysis"] = decision()
    source.save(update_fields=["metadata"])
    contract = configure_source_statistics(spec)
    project(contract, "github", [evidence("github", raw)])
    mapping = contract.mappings.get(source_id="github", subject__subject_kind="product")
    start = datetime(2026, 10, 12, tzinfo=UTC)
    request = ChartRequest(
        target=ReleaseAnchor(product.product_key, start.date(), "caller"),
        start=start,
        end=start + timedelta(days=1),
        cutoff=start + timedelta(days=2),
        history_mode="hindsight",
        metrics=(
            MetricSelection(product.product_key, contract.pk, mapping.pk, "stars"),
        ),
    )

    result = metric_series(validate_request(request), 0)

    assert result["points"][0]["value"] == "3"
    assert result["points"][0]["unit"] == "stars"


def test_internal_chart_returns_same_values_and_svg_without_writes():
    from core.chart_engine import ChartRequest, ReleaseAnchor, build_chart
    from core.models import Post, PostBrand

    brand = Brand.objects.create(nickname="chart-end-to-end")
    product = Product.objects.create(brand=brand, display_name="Chart model")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    for day in range(8):
        post = Post.objects.create(
            tweet_id=f"chart-output-{day}",
            created_at=start + timedelta(days=day, hours=1),
        )
        PostBrand.objects.create(post=post, brand=brand)
    request = ChartRequest(
        target=ReleaseAnchor(product.product_key, start.date(), "test"),
        start=start,
        end=start + timedelta(days=8),
        cutoff=start + timedelta(days=9),
        history_mode="hindsight",
    )
    before = Post.objects.count()
    result = build_chart(request, start_day=0, end_day=7)
    assert result["discussion"]["target"]["post_count"] == 8
    assert result["lines"][0]["points"][0]["value"] == 0
    assert "Chart model brand discussion" in result["svg"]
    assert Post.objects.count() == before


def test_internal_forecast_requires_permission_and_produces_separate_dotted_line(
    monkeypatch,
):
    from types import SimpleNamespace
    from uuid import uuid4

    import core.chart_engine as engine

    target_id, prior_id = uuid4(), uuid4()
    target_product = SimpleNamespace(product_key=target_id, display_name="New")
    prior_product = SimpleNamespace(product_key=prior_id, display_name="Old")
    target_date, prior_date = date(2026, 9, 10), date(2026, 8, 1)
    target = engine.ResolvedRelease(target_product, target_date, "test", False)
    prior = engine.ResolvedRelease(prior_product, prior_date, "test", False)
    start = datetime(2026, 9, 10, tzinfo=UTC)
    request = engine.ChartRequest(
        target=engine.ReleaseAnchor(target_id, target_date, "test"),
        start=start,
        end=start + timedelta(days=10),
        cutoff=start + timedelta(days=3),
        comparison=engine.ReleaseAnchor(prior_id, prior_date, "test"),
        comparison_start=datetime(2026, 8, 1, tzinfo=UTC),
        comparison_end=datetime(2026, 8, 11, tzinfo=UTC),
        history_mode="hindsight",
        comparable_collection_accounting=True,
    )
    mapping = SimpleNamespace(source_id="openrouter", contract=object())
    metrics = tuple(
        engine.ResolvedMetric(
            engine.MetricSelection(pid, uuid4(), uuid4(), "total_tokens", role), mapping
        )
        for pid, role in ((target_id, "target"), (prior_id, "comparison"))
    )
    resolved = engine.ResolvedRequest(request, target, prior, metrics)
    monkeypatch.setattr(engine, "validate_request", lambda _: resolved)
    monkeypatch.setattr(engine, "enforce_use", lambda *args: None)
    monkeypatch.setattr(
        engine,
        "brand_discussion",
        lambda _, comparison=False: {
            "status": "stored_only",
            "daily": {
                (prior_date if comparison else target_date).isoformat(): 10,
                **{
                    (
                        (prior_date if comparison else target_date) + timedelta(days=i)
                    ).isoformat(): 10
                    for i in range(1, 10)
                },
            },
            "warning": "Coverage may be incomplete",
        },
    )
    monkeypatch.setattr(
        engine,
        "metric_series",
        lambda _, i: {
            "points": [
                {
                    "date": (
                        (target_date if i == 0 else prior_date) + timedelta(days=d)
                    ).isoformat(),
                    "value": "20",
                }
                for d in range(10)
            ]
        },
    )
    result = engine.build_chart(request, end_day=9)
    assert result["preview"][0]["ratio"] == 1
    assert any(line.get("forecast") for line in result["lines"])
    assert "stroke-dasharray" in result["svg"]

    def deny(*args):
        raise engine.UseNotPermitted("forecast not approved")

    monkeypatch.setattr(engine, "enforce_use", deny)
    denied = engine.build_chart(request, end_day=9)
    assert denied["preview"][0]["status"] == "unavailable"
    assert not any(line.get("forecast") for line in denied["lines"])
