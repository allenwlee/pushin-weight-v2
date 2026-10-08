from datetime import timedelta

import pytest
from django.utils import timezone

from core.benchmark_metric_store import persist_source
from tests.test_benchmark_download_persistence import configured, payload

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_operational_cutoff_excludes_late_import_and_later_revision():
    from core.benchmark_forecast_inputs import forecast_inputs

    contract = configured()
    first = persist_source(contract, "hf", "1" * 64, payload(10))
    cutoff = timezone.now()
    second = persist_source(contract, "hf", "2" * 64, payload(20))
    rows = forecast_inputs(
        contract, cutoff, use="isolated_review", isolated_review=True
    )
    assert {r["run_id"] for r in rows["values"]} == {str(first.pk)}
    assert str(second.pk) not in str(rows)
    assert rows["mode"] == "operational"
    assert all(r["first_local_observed_at"] for r in rows["values"])


def test_contract_review_after_cutoff_and_reconstruction_are_not_past_knowledge():
    from core.benchmark_forecast_inputs import forecast_inputs
    from core.models import MetricObservation

    contract = configured()
    run = persist_source(contract, "hf", "3" * 64, payload())
    MetricObservation.objects.filter(run=run).update(
        source_metadata={"history_basis": "reconstructed_current_relationships"}
    )
    assert (
        forecast_inputs(
            contract, timezone.now(), use="isolated_review", isolated_review=True
        )["values"]
        == []
    )
    assert (
        forecast_inputs(
            contract,
            timezone.now() - timedelta(days=1),
            use="isolated_review",
            isolated_review=True,
        )["values"]
        == []
    )
    research = forecast_inputs(
        contract,
        timezone.now(),
        mode="retrospective_research",
        use="isolated_review",
        isolated_review=True,
    )
    assert research["values"] and research["not_past_known_evidence"]
