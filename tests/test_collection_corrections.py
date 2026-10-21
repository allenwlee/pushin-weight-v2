"""Current attribution changes without rewriting original metric admission."""

from datetime import timedelta

import pytest

from core.collection_corrections import correct_attribution
from core.collection_reports import resource_statistics
from core.models import CollectionObservation
from tests.test_source_metric_projection import configured, evidence, project

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_current_and_historical_reports_distinguish_corrected_and_recorded_product():
    contract, raw, product, _ = configured(mapped=True, product_type="llm-model")
    run = project(contract, "hf", [evidence("hf", raw)])
    observation = run.observations.get()
    before = CollectionObservation.objects.filter(pk=observation.pk).values().get()
    correction = correct_attribution(
        observation,
        product=None,
        mapping=None,
        actor="fixture:reviewer",
        reason="incorrect_product",
    )
    report = resource_statistics(
        contract_id=contract.pk, source="hf", identifier=observation.source_identifier
    )
    assert all(
        v["canonical_product_id"] is None and v["recorded_product_id"] == product.pk
        for v in report["values"]
    )
    assert all(
        v["attribution_correction_id"] == str(correction.pk) for v in report["values"]
    )
    historical = resource_statistics(
        contract_id=contract.pk,
        source="hf",
        identifier=observation.source_identifier,
        known_at=correction.recorded_at - timedelta(microseconds=1),
    )
    assert all(v["canonical_product_id"] == product.pk for v in historical["values"])
    assert (
        CollectionObservation.objects.filter(pk=observation.pk).values().get() == before
    )
