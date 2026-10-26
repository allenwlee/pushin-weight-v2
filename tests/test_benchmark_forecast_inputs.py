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


def test_typed_dataset_still_enforces_archive_restrictions_without_legacy_metadata():
    from core.benchmark_attribution import UseNotPermitted
    from core.benchmark_forecast_inputs import forecast_inputs
    from core.benchmark_metric_history import import_history
    from core.models import DataSource
    from tests.test_benchmark_download_history import manifest
    from tests.test_benchmark_use_policy import decision

    contract = configured()
    run = import_history(manifest(contract), apply=True)
    run.observations.update(source_metadata={})
    source = DataSource.objects.get(pk="hf")
    source.metadata["use_policy"]["datasets"]["cfahlgren1/hub-stats"][
        "public_forecasts"
    ] = decision("prohibited")
    source.save(update_fields=["metadata"])
    with pytest.raises(UseNotPermitted):
        forecast_inputs(contract, timezone.now(), use="public_forecasts")
    assert forecast_inputs(
        contract, timezone.now(), use="isolated_review", isolated_review=True,
    )["values"]


@pytest.mark.parametrize("source", ["openrouter", "arena"])
def test_forecast_coordinates_survive_retired_observation_documents(source):
    from core.benchmark_forecast_inputs import forecast_inputs
    from core.measurement_taxonomy import digest
    from core.models import CollectionObservation
    from tests.test_benchmark_download_persistence import provider_contract

    if source == "openrouter":
        contract = provider_contract(source, ["total_tokens"])
        payload = {
            "status": "ok", "meta": {"version": "v1"},
            "as_of": "2026-10-06T00:30:00Z",
            "rows": [{"date": "2026-10-05", "model_permaslug": "lab/model", "total_tokens": "100"}],
        }
        coordinates = {"date": "2026-10-05"}
    else:
        contract = provider_contract(source, ["rating", "rating_lower", "rating_upper", "rank"])
        payload = {
            "status": "ok", "config": "text_style_control",
            "coverage": "latest_publication_only",
            "rows": [{"model_name": "lab/model", "category": "overall",
                      "leaderboard_publish_date": "2026-09-25", "rating": 1400.0,
                      "rating_lower": 1390.0, "rating_upper": 1410.0, "rank": 10.0}],
        }
        coordinates = {"config": "text_style_control", "category": "overall"}
    run = persist_source(contract, source, digest([source, "forecast"]), payload)
    cutoff = timezone.now()
    before = forecast_inputs(contract, cutoff, use="isolated_review", isolated_review=True)
    assert before["values"] and all(row["dimensions"] == coordinates for row in before["values"])
    CollectionObservation.objects.filter(run=run).update(
        dimensions={}, source_metadata={}, listing={},
    )
    after = forecast_inputs(contract, cutoff, use="isolated_review", isolated_review=True)
    assert [row["dimensions"] for row in after["values"]] == [
        row["dimensions"] for row in before["values"]
    ]


@pytest.mark.parametrize(
    ("metadata", "reconstructed"),
    [
        ({"history_basis": "reconstructed_current_relationships"}, None),
        ({}, True),
    ],
    ids=["legacy-history", "typed-only-history"],
)
def test_contract_review_after_cutoff_and_reconstruction_are_not_past_knowledge(
    metadata, reconstructed
):
    from core.benchmark_forecast_inputs import forecast_inputs
    from core.models import CollectionObservation

    contract = configured()
    run = persist_source(contract, "hf", "3" * 64, payload())
    CollectionObservation.objects.filter(run=run).update(
        source_metadata=metadata, history_reconstructed=reconstructed
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
    if reconstructed:
        assert all(
            row["source_metadata"]["history_basis"]
            == "reconstructed_current_relationships"
            for row in research["values"]
        )
