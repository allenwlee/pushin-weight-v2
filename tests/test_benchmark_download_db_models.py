"""Shared numeric schema: representation and time are independent dimensions."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core import models

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def measurement():
    source = models.DataSource.objects.create(
        id="arena", name="Arena", source_type="benchmark"
    )
    kind = models.MetricType.objects.create(id="benchmark_score", name="Score")
    definition = models.SourceMetric.objects.create(
        source=source,
        metric_type=kind,
        metric_key="rating",
        version=1,
        name="Rating",
        unit="arena_points",
        value_kind="float",
        quantity_form="score",
        measurement_kind="state",
    )
    taxonomy = models.TaxonomyVersion.objects.create(
        version_hash="a" * 64, snapshot={}, reviewed_by="test"
    )
    contract = models.MetricCollectionContract.objects.create(
        taxonomy_version=taxonomy,
        contract_hash="b" * 64,
        catalog_hash="c" * 64,
        mapping_hash="d" * 64,
        methodology_hash="e" * 64,
        catalog_snapshot={},
        source_configuration={},
        methodology={},
        reviewed_by="test",
    )
    run = models.MetricCollectionRun.objects.create(
        contract=contract,
        source=source,
        ingestion_key="f" * 64,
        lease_expires_at=timezone.now(),
    )
    observation = models.MetricObservation.objects.create(
        run=run,
        source_identifier="fixture",
        source_subject_kind="model",
        observation_key="1" * 64,
    )
    return source, definition, observation


def test_shared_benchmark_siblings_and_protected_definitions():
    source, definition, observation = measurement()
    models.DataSource.objects.create(
        id="artificial_analysis", name="AA", source_type="benchmark"
    )
    assert set(
        models.DataSource.objects.filter(source_type="benchmark").values_list(
            "pk", flat=True
        )
    ) == {"arena", "artificial_analysis"}
    value = models.MetricValue.objects.create(
        observation=observation,
        source_metric=definition,
        float_value=1474.4402781653991,
    )
    assert value.float_value == 1474.4402781653991
    from django.db.models.deletion import ProtectedError

    with pytest.raises(ProtectedError):
        definition.delete()


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"integer_value": Decimal(1), "float_value": 1},
        {"float_value": float("nan")},
        {"float_value": float("inf")},
        {"float_value": float("-inf")},
        {"integer_value": Decimal("NaN")},
    ],
)
def test_invalid_numeric_storage_is_rejected(values):
    _, definition, observation = measurement()
    with (
        pytest.raises((IntegrityError, ValueError, ValidationError)),
        transaction.atomic(),
    ):
        models.MetricValue.objects.create(
            observation=observation, source_metric=definition, **values
        )


def test_state_cannot_claim_rolling_flow_window():
    _, definition, _ = measurement()
    with pytest.raises(IntegrityError), transaction.atomic():
        models.SourceMetric.objects.filter(pk=definition.pk).update(
            window_mode="rolling",
            window_amount=30,
            window_unit="day",
            window_duration_basis="unknown",
        )


def test_raw_sql_cannot_insert_numeric_nan():
    from django.db import connection

    _, definition, observation = measurement()
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as c:
        c.execute(
            "INSERT INTO metric_values (observation_id,source_metric_id,integer_value,temporal_status,source_timezone) VALUES (%s,%s,'NaN','unknown','unknown')",
            [observation.pk, definition.pk],
        )
