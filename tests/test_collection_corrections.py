"""Current attribution changes without rewriting original metric admission."""

from datetime import timedelta

import pytest

from core.collection_corrections import correct_attribution
from core.collection_reports import resource_statistics
from core.models import Actor, CollectionObservation
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
    assert correction.actor_id is None
    assert not Actor.objects.filter(actor_key="fixture:reviewer").exists()
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


@pytest.mark.parametrize("kind", ["human", "agent"])
def test_registered_correction_performer_preserves_original_label_and_history(kind):
    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    identity = Actor.objects.create(actor_kind=kind, actor_key="registered-reviewer")
    first = correct_attribution(
        observation,
        product=None,
        mapping=None,
        actor="Original operator wording",
        actor_identity=identity,
        reason="incorrect_product",
    )
    second = correct_attribution(
        observation,
        product=None,
        mapping=None,
        actor="Legacy repair label",
        reason="confirmed_unassigned",
    )
    first.refresh_from_db()
    assert first.actor == identity
    assert first.actor_identifier == "Original operator wording"
    assert second.actor_id is None
    assert second.predecessor_id == first.pk


def test_unsaved_actor_does_not_create_correction_or_register_inferred_identity():
    from core.models import CollectionCorrection

    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    with pytest.raises(ValueError, match="registered actor"):
        correct_attribution(
            observation,
            product=None,
            mapping=None,
            actor="Unproven name",
            actor_identity=Actor(actor_kind="human", actor_key="unregistered"),
            reason="incorrect_product",
        )
    assert not CollectionCorrection.objects.exists()
    assert not Actor.objects.filter(actor_key="unregistered").exists()
