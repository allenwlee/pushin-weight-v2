"""Real public provider shapes remain compatible with the durable writer."""

import json
from pathlib import Path

import pytest

from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import digest
from tests.test_benchmark_download_persistence import provider_contract

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.mark.parametrize(
    "source,metrics",
    [
        ("hf", ["downloads", "downloads_all_time"]),
        ("openrouter", ["total_tokens"]),
        (
            "arena",
            [
                "rating",
                "rating_lower",
                "rating_upper",
                "rank",
                "vote_count",
                "variance",
            ],
        ),
    ],
)
def test_recorded_public_shapes_keep_values_and_provenance(source, metrics):
    contract = provider_contract(source, metrics) if source != "hf" else None
    if source == "hf":
        from core.benchmark_metric_identity import configure_collection
        from tests.test_benchmark_download_db_identity import setup_spec

        _, spec = setup_spec()
        contract = configure_collection(spec)
    fixture = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "benchmark_download_collector"
            / f"{source}-2026-10-06-selected.json"
        ).read_text()
    )
    assert digest(fixture["payload"]) == fixture["selection_sha256"]
    run = persist_source(contract, source, digest(fixture), fixture["payload"])
    # Fixture names deliberately differ from this test's mapping: evidence stays,
    # but a near name is not silently joined to the wrong product.
    assert run.status == "partial"
    assert run.observations.count() == len(fixture["payload"]["rows"])
    assert not run.observations.filter(mapping__isnull=False).exists()
    assert all(o.values.exists() for o in run.observations.all())
