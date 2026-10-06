import pytest
from django.test import override_settings
from django.urls import reverse

from core.benchmark_metric_identity import configure_collection
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def secure_requests(settings):
    settings.SECURE_SSL_REDIRECT = False


def comparison():
    _, spec = setup_spec()
    subject = spec["mappings"][0]["subject_id"]
    spec["methodology"]["comparisons"] = {
        "fixture": {
            "title": "Fixture product",
            "launch_anchor": {
                "product_subject_id": subject,
                "announced_date": "2026-09-10",
                "precision": "date",
                "source_url": "https://example.org/launch",
                "event_kind": "announcement",
                "source_timezone": "unknown",
                "reviewed_by": "fixture",
            },
            "lines": [
                {
                    "key": "downloads",
                    "label": "HF downloads",
                    "source": "hf",
                    "subject_id": subject,
                    "metric_key": "downloads",
                    "mapping_identifiers": ["lab/Model"],
                    "aggregation": "single",
                    "baseline": "launch",
                }
            ],
        }
    }
    return configure_collection(spec)


def test_feature_is_disabled_by_default(client):
    contract = comparison()
    for name in ("benchmark_pulse", "benchmark_series"):
        assert (
            client.get(reverse(name, args=[contract.pk, "fixture"])).status_code == 404
        )


@override_settings(BENCHMARK_METRICS_ENABLED=True)
def test_public_page_real_template_and_read_only_series(client):
    contract = comparison()
    page = client.get(reverse("benchmark_pulse", args=[contract.pk, "fixture"]))
    assert page.status_code == 200
    assert b"benchmark-pulse.js" in page.content
    assert b"benchmark-pulse.css" in page.content
    endpoint = reverse("benchmark_series", args=[contract.pk, "fixture"])
    response = client.get(endpoint, {"end": "2026-09-12"})
    assert response.status_code == 200
    result = response.json()
    assert result["contract_id"] == str(contract.pk)
    assert result["lines"][0]["baseline"]["status"] == "baseline_missing"
    assert all(p["percent_change"] is None for p in result["lines"][0]["points"])
    assert client.post(endpoint).status_code == 405
    assert client.get(endpoint, {"end": "bad-date"}).status_code == 400
    assert (
        client.get(
            reverse("benchmark_series", args=[contract.pk, "missing"])
        ).status_code
        == 404
    )


@override_settings(BENCHMARK_METRICS_ENABLED=True)
def test_late_brand_posts_change_served_values_without_product_attribution(client):
    from datetime import UTC, datetime

    from core.benchmark_metric_history import import_history
    from core.measurement_taxonomy import configure_taxonomy, subject_id
    from core.models import Post, PostBrand
    from tests.test_benchmark_download_history import manifest

    product, spec = setup_spec()
    version = configure_taxonomy(
        {
            "reviewed_by": "fixture",
            "subjects": [
                {"kind": "product", "key": str(product.product_key)},
                {"kind": "brand", "key": "lab"},
            ],
        }
    )
    spec["taxonomy_version"] = str(version.pk)
    sid = str(subject_id("product", product.product_key))
    spec["methodology"]["comparisons"] = {
        "fixture": {
            "title": "Fixture",
            "launch_anchor": {
                "product_subject_id": sid,
                "announced_date": "2026-09-10",
                "precision": "date",
                "source_url": "https://example.org/launch",
                "event_kind": "announcement",
                "source_timezone": "unknown",
                "reviewed_by": "fixture",
            },
            "lines": [
                {
                    "key": "posts",
                    "label": "Brand posts",
                    "source": "x",
                    "metric_key": "post_volume",
                    "subject_id": str(subject_id("brand", "lab")),
                    "post_policy": "legacy_brand",
                    "baseline": "launch",
                },
                {
                    "key": "downloads",
                    "label": "HF",
                    "source": "hf",
                    "metric_key": "downloads",
                    "subject_id": sid,
                    "mapping_identifiers": ["lab/Model"],
                    "aggregation": "single",
                    "baseline": "launch",
                },
            ],
        }
    }
    contract = configure_collection(spec)
    import_history(manifest(contract), apply=True)
    for day in [10, 11]:
        post = Post.objects.create(
            tweet_id=str(day), created_at=datetime(2026, 9, day, tzinfo=UTC)
        )
        PostBrand.objects.create(post=post, brand_id="lab")
    endpoint = (
        reverse("benchmark_series", args=[contract.pk, "fixture"]) + "?end=2026-09-11"
    )
    before = client.get(endpoint)
    assert "no-store" in before.headers["Cache-Control"]
    assert before.json()["lines"][0]["points"][1]["percent_change"] == 0
    late = Post.objects.create(
        tweet_id="late", created_at=datetime(2026, 9, 11, tzinfo=UTC)
    )
    PostBrand.objects.create(post=late, brand_id="lab")
    after = client.get(endpoint).json()
    assert after["lines"][0]["points"][1]["percent_change"] == 100
    assert after["lines"][1]["points"][0]["raw_value"] == "6"
    assert after["lines"][1]["subject"]["kind"] == "product"
    assert after["lines"][0]["subject"]["kind"] == "brand"
