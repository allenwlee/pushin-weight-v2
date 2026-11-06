"""Request-boundary checks that do not need a database."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from django.test import RequestFactory

from monitor import single_brand_chart


@pytest.fixture(autouse=True)
def clear_chart_throttle(monkeypatch):
    monkeypatch.setattr(single_brand_chart, "_LAST_BUILD_FINISHED", float("-inf"))
    monkeypatch.setattr(single_brand_chart, "_CHART_BUILD_INTERVAL_SECONDS", 0)


def test_selected_product_is_passed_to_engine(monkeypatch):
    product = SimpleNamespace(product_key=UUID("d5278b36-2098-4648-a791-b4b696de0b6c"))
    filter_products = Mock(return_value=SimpleNamespace(first=lambda: product))
    monkeypatch.setattr(
        single_brand_chart,
        "_public_products",
        lambda: SimpleNamespace(filter=filter_products),
    )
    build = Mock(
        return_value={
            "product": {"key": str(product.product_key)},
            "lines": [],
            "notes": [],
        }
    )
    monkeypatch.setattr(single_brand_chart, "_calculate_chart", build)
    request = RequestFactory().get(
        "/general/chart/",
        {"product": str(product.product_key), "release_date": "2026-08-13"},
    )
    response = single_brand_chart.chart(request)
    assert response.status_code == 200
    assert build.call_args.args[0].target.date == date(2026, 8, 13)
    assert build.call_args.args[0].target.product_key == product.product_key


def test_chart_cache_reuses_result_but_update_recalculates(monkeypatch):
    product = SimpleNamespace(product_key=UUID("c3e65963-4a62-48be-8aef-d0d197abbc45"))
    monkeypatch.setattr(
        single_brand_chart,
        "_public_products",
        lambda: SimpleNamespace(
            filter=lambda **kwargs: SimpleNamespace(first=lambda: product)
        ),
    )
    store = {}
    monkeypatch.setattr(single_brand_chart.cache, "get", lambda key: store.get(key))
    monkeypatch.setattr(
        single_brand_chart.cache,
        "set",
        lambda key, value, timeout: store.update({key: value}),
    )
    build = Mock(return_value={"product": {}, "lines": [], "notes": []})
    monkeypatch.setattr(single_brand_chart, "_calculate_chart", build)
    params = {"product": str(product.product_key), "release_date": "2026-08-13"}
    assert (
        single_brand_chart.chart(
            RequestFactory().get("/general/chart/", params)
        ).status_code
        == 200
    )
    assert (
        single_brand_chart.chart(
            RequestFactory().get("/general/chart/", params)
        ).status_code
        == 200
    )
    assert build.call_count == 1
    assert (
        single_brand_chart.chart(
            RequestFactory().get("/general/chart/", dict(params, refresh="1"))
        ).status_code
        == 200
    )
    assert build.call_count == 2


def test_cached_chart_translation_does_not_change_other_locales(monkeypatch):
    product = SimpleNamespace(product_key=UUID("bb7ca324-a8cb-4f09-a9d0-347c4caf9bc3"))
    monkeypatch.setattr(single_brand_chart, "_public_products", lambda: SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(first=lambda: product)))
    store = {}
    monkeypatch.setattr(single_brand_chart.cache, "get", lambda key: store.get(key))
    monkeypatch.setattr(single_brand_chart.cache, "set", lambda key, value, timeout: store.update({key: value}))
    monkeypatch.setattr(single_brand_chart, "_calculate_chart", lambda request: {"product": {}, "lines": [{"label": "Brand posts", "unit": "posts"}], "notes": []})
    params = {"product": str(product.product_key), "release_date": "2026-08-13"}
    ja = single_brand_chart.chart(RequestFactory().get("/general/chart/", dict(params, lang="ja")))
    en = single_brand_chart.chart(RequestFactory().get("/general/chart/", dict(params, lang="en")))
    import json
    assert json.loads(ja.content)["lines"][0]["label"] != "Brand posts"
    assert json.loads(en.content)["lines"][0]["label"] == "Brand posts"


def test_chart_rejects_concurrent_uncached_builds(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    product = SimpleNamespace(product_key=UUID("c3e65963-4a62-48be-8aef-d0d197abbc45"))
    monkeypatch.setattr(
        single_brand_chart,
        "_public_products",
        lambda: SimpleNamespace(
            filter=lambda **kwargs: SimpleNamespace(first=lambda: product)
        ),
    )
    monkeypatch.setattr(single_brand_chart.cache, "get", lambda key: None)
    monkeypatch.setattr(single_brand_chart.cache, "set", lambda *args, **kwargs: None)
    started, finish = Event(), Event()

    def build(_request):
        started.set()
        assert finish.wait(timeout=3)
        return {"product": {}, "lines": [], "notes": []}

    monkeypatch.setattr(single_brand_chart, "_calculate_chart", build)
    params = {"product": str(product.product_key), "release_date": "2026-08-13"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            single_brand_chart.chart, RequestFactory().get("/general/chart/", params)
        )
        try:
            assert started.wait(timeout=3)
            second = single_brand_chart.chart(
                RequestFactory().get("/general/chart/", params)
            )
            assert second.status_code == 429
            assert second["Retry-After"] == "0"
        finally:
            finish.set()
        assert first.result(timeout=3).status_code == 200


def test_chart_limits_repeated_uncached_requests(monkeypatch):
    product = SimpleNamespace(product_key=UUID("f71d6dc7-2dc1-408f-8e48-7f09c5163544"))
    monkeypatch.setattr(
        single_brand_chart,
        "_public_products",
        lambda: SimpleNamespace(
            filter=lambda **kwargs: SimpleNamespace(first=lambda: product)
        ),
    )
    monkeypatch.setattr(single_brand_chart.cache, "get", lambda key: None)
    monkeypatch.setattr(single_brand_chart.cache, "set", lambda *args, **kwargs: None)
    monkeypatch.setattr(single_brand_chart, "_CHART_BUILD_INTERVAL_SECONDS", 3)
    monkeypatch.setattr(single_brand_chart.clock, "monotonic", lambda: 100)
    build = Mock(return_value={"product": {}, "lines": [], "notes": []})
    monkeypatch.setattr(single_brand_chart, "_calculate_chart", build)
    params = {
        "product": str(product.product_key),
        "release_date": "2026-08-13",
        "refresh": "1",
    }
    assert (
        single_brand_chart.chart(
            RequestFactory().get("/general/chart/", params)
        ).status_code
        == 200
    )
    busy = single_brand_chart.chart(RequestFactory().get("/general/chart/", params))
    assert busy.status_code == 429
    assert busy["Retry-After"] == "3"
    assert build.call_count == 1


def test_compact_date_is_rejected_before_database(monkeypatch):
    access = Mock(side_effect=AssertionError("should not query the database"))
    monkeypatch.setattr(
        single_brand_chart, "_public_products", lambda: SimpleNamespace(filter=access)
    )
    request = RequestFactory().get(
        "/general/chart/",
        {"product": "d5278b36-2098-4648-a791-b4b696de0b6c", "release_date": "20260813"},
    )
    assert single_brand_chart.chart(request).status_code == 400


def test_single_product_chart_preserves_observed_zero_and_missing_metric(monkeypatch):
    from core import chart_engine

    anchor = date(2026, 8, 13)
    product = SimpleNamespace(
        product_key=UUID("d5278b36-2098-4648-a791-b4b696de0b6c"),
        display_name="Example",
        repo_id="lab/example",
        brand_id="lab",
    )
    mapping = SimpleNamespace(source_id="hf", external_identifier="lab/example")
    metric = SimpleNamespace(
        mapping=mapping, selection=SimpleNamespace(metric_key="downloads")
    )
    resolved = SimpleNamespace(
        target=SimpleNamespace(
            date=anchor, product=product, anchor_source="test", reviewed=False
        ),
        metrics=(metric,),
    )
    monkeypatch.setattr(
        chart_engine, "validate_request", lambda *args, **kwargs: resolved
    )
    monkeypatch.setattr(
        chart_engine,
        "_single_brand_discussion",
        lambda *args, **kwargs: {"daily": {}, "status": "stored_only"},
    )
    monkeypatch.setattr(chart_engine, "_unmapped_exact_values", lambda *args: {})
    points = [
        {"date": (anchor + timedelta(days=i)).isoformat(), "value": 10}
        for i in range(7)
    ]
    points.extend(
        [
            {"date": (anchor + timedelta(days=7)).isoformat(), "value": 0},
            {"date": (anchor + timedelta(days=8)).isoformat(), "value": None},
        ]
    )
    monkeypatch.setattr(
        chart_engine,
        "metric_series",
        lambda *args, **kwargs: {"status": "available", "points": points},
    )
    request = SimpleNamespace(
        comparison=None,
        history_mode="hindsight",
        start=datetime(2026, 8, 1, tzinfo=UTC),
        end=datetime(2026, 9, 1, tzinfo=UTC),
        cutoff=datetime(2026, 9, 2, tzinfo=UTC),
    )
    result = chart_engine.build_single_brand_chart(request)
    hf = next(line for line in result["lines"] if line["key"] == "hf:downloads")
    assert hf["points"][21]["raw"] == 0
    assert hf["points"][22]["raw"] is None
    assert (
        next(line for line in result["lines"] if line["key"] == "opencode:tokens")[
            "status"
        ]
        == "mapping_unavailable"
    )


def test_failed_mapped_read_does_not_show_partial_fallback(monkeypatch):
    from core import chart_engine

    anchor = date(2026, 8, 13)
    product = SimpleNamespace(
        product_key=UUID("d5278b36-2098-4648-a791-b4b696de0b6c"),
        display_name="Example",
        repo_id="lab/example",
        brand_id="lab",
    )
    mapping = SimpleNamespace(source_id="hf", external_identifier="lab/example")
    metric = SimpleNamespace(
        mapping=mapping, selection=SimpleNamespace(metric_key="downloads")
    )
    resolved = SimpleNamespace(
        target=SimpleNamespace(
            date=anchor, product=product, anchor_source="test", reviewed=False
        ),
        metrics=(metric,),
    )
    monkeypatch.setattr(
        chart_engine, "validate_request", lambda *args, **kwargs: resolved
    )
    monkeypatch.setattr(
        chart_engine, "_single_brand_discussion", lambda *args: {"daily": {}}
    )
    monkeypatch.setattr(
        chart_engine,
        "metric_series",
        lambda *args, **kwargs: {
            "status": "unavailable",
            "reason": "evidence_limit",
            "points": [],
        },
    )
    fallback = Mock(return_value={"2026-08-13": {"value": 7}})
    monkeypatch.setattr(chart_engine, "_unmapped_exact_values", fallback)
    request = SimpleNamespace(
        comparison=None,
        history_mode="hindsight",
        start=datetime(2026, 8, 1, tzinfo=UTC),
        end=datetime(2026, 9, 1, tzinfo=UTC),
        cutoff=datetime(2026, 9, 2, tzinfo=UTC),
    )
    result = chart_engine.build_single_brand_chart(request)
    hf = next(line for line in result["lines"] if line["key"] == "hf:downloads")
    assert hf["status"] == "evidence_limit"
    assert hf["observed_dates"] == 0
    fallback.assert_not_called()
