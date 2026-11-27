"""GDPx source registration: metric definitions, monetary form and use policy."""

import copy
from importlib import import_module
from types import SimpleNamespace

import pytest

from core.measurement_taxonomy import digest

# Captured from definition_rows() at HEAD 2659285e before GDPx was added.
EXISTING_ROWS_COUNT = 38
EXISTING_ROWS_DIGEST = "ecf3b0ff89592c27b05c3e1f55ca8411b09226187a37159f144eb6aaa2d070a8"

GDPX_METRICS = {
    # key: (wire field, unit, quantity form, value kind, metric type)
    "score": ("score", "percent", "score", "float", "benchmark_score"),
    "partial_score": ("partialScore", "percent", "score", "float", "benchmark_score"),
    "tasks": ("tasks", "tasks", "count", "integer", "task_count"),
    "tasks_scored": ("tasksScored", "tasks", "count", "integer", "task_count"),
    "tasks_with_partial": (
        "tasksWithPartial",
        "tasks",
        "count",
        "integer",
        "task_count",
    ),
    "cost_per_task": ("costPerTask", "usd", "monetary", "float", "cost_per_task"),
    "tasks_with_cost": ("tasksWithCost", "tasks", "count", "integer", "task_count"),
    "tokens_per_task": (
        "tokensPerTask",
        "output_tokens_per_task",
        "ratio",
        "float",
        "tokens_per_task",
    ),
    "tasks_with_tokens": (
        "tasksWithTokens",
        "tasks",
        "count",
        "integer",
        "task_count",
    ),
}


def gdpx_rows():
    from core.benchmark_metric_identity import definition_rows

    return {
        row["metric_key"]: row
        for row in definition_rows()
        if row["source_id"] == "gdpx"
    }


def test_gdpx_definitions_mirror_wire_fields_with_ktd4_forms():
    from core.benchmark_metric_identity import METRIC_TYPES, SOURCES

    rows = gdpx_rows()
    assert set(rows) == set(GDPX_METRICS)
    for key, (wire, unit, form, kind, metric_type) in GDPX_METRICS.items():
        row = rows[key]
        assert row["version"] == 1
        assert row["unit"] == unit
        assert row["quantity_form"] == form
        assert row["value_kind"] == kind
        assert row["metric_type_id"] == metric_type
        assert metric_type in METRIC_TYPES
        assert row["value_role"] == "value"
        assert row["required"] is (key == "score")
        assert row["measurement_kind"] == "state"
        assert row["window_mode"] == "none"
        assert row["window_unit"] is None
        assert row["source_timezone_reference_id"] is None
        assert row["definition_metadata"] == {
            "wire_field": wire,
            "adapter_version": SOURCES["gdpx"][3],
        }
    assert {row["unit"] for row in rows.values()} == {
        "percent",
        "usd",
        "output_tokens_per_task",
        "tasks",
    }


def test_gdpx_source_is_a_benchmark_with_an_adapter():
    from core.benchmark_metric_identity import SOURCES

    name, kind, url, adapter, normalizer = SOURCES["gdpx"]
    assert (name, kind, url) == ("GDPx", "benchmark", "https://gdpx.semianalysis.com")
    assert adapter == "gdpx-dataset-v1"
    assert normalizer == "exact-v1"


def test_existing_definition_rows_are_byte_identical():
    from core.benchmark_metric_identity import definition_rows

    existing = [row for row in definition_rows() if row["source_id"] != "gdpx"]
    assert len(existing) == EXISTING_ROWS_COUNT
    assert digest(existing) == EXISTING_ROWS_DIGEST


def test_metric_quantity_constraint_admits_monetary_only_as_a_new_form():
    from core.models import SourceMetric

    (constraint,) = [
        c for c in SourceMetric._meta.constraints if c.name == "ck_metric_quantity"
    ]
    ((lookup, forms),) = constraint.condition.children
    assert lookup == "quantity_form__in"
    assert forms == ["count", "score", "rank", "variance", "ratio", "monetary"]


def test_migration_only_widens_metric_quantity_constraint():
    from django.db import migrations

    migration = import_module("core.migrations.0246_metric_monetary_quantity")
    operations = migration.Migration.operations
    assert [type(op) for op in operations] == [
        migrations.RemoveConstraint,
        migrations.AddConstraint,
    ]
    assert {op.model_name for op in operations} == {"sourcemetric"}
    assert operations[0].name == "ck_metric_quantity"
    assert operations[1].constraint.name == "ck_metric_quantity"
    assert "monetary" in operations[1].constraint.condition.children[0][1]


def test_gdpx_attribution_credit_and_terms():
    from core.benchmark_attribution import DEFAULTS

    credit = DEFAULTS["gdpx"]
    assert credit["publisher"] == "GDPx by SemiAnalysis"
    assert credit["url"] == "https://gdpx.semianalysis.com"
    assert credit["terms_url"] == "https://gdpx.semianalysis.com/terms"


def test_comparison_attributions_credit_gdpx():
    from core.benchmark_attribution import comparison_attributions

    contract = SimpleNamespace(source_configuration={"gdpx": {}})
    lines = [
        {
            "source": "gdpx",
            "baseline": {},
            "points": [{"evidence": [{"source_as_of": "2026-11-25"}]}],
        }
    ]
    (credit,) = comparison_attributions(contract, lines)
    assert credit["publisher"] == "GDPx by SemiAnalysis"
    assert credit["terms_url"] == "https://gdpx.semianalysis.com/terms"
    assert credit["notice"] == "Source: GDPx by SemiAnalysis."


def test_gdpx_recorded_use_policy_is_valid_and_grants_collection():
    from core.benchmark_attribution import (
        GDPX_USE_POLICY,
        UseNotPermitted,
        enforce_use,
        validate_use_policy,
    )

    validate_use_policy(GDPX_USE_POLICY)
    assert set(GDPX_USE_POLICY) == {"collection", "retention"}
    for decision in GDPX_USE_POLICY.values():
        assert decision["status"] == "allowed"
        assert decision["reviewed_by"] == "owner"
        assert decision["reviewed_at"] == "2026-11-27"
        assert decision["access_route"] == "public website"
        assert decision["evidence_url"] == "https://gdpx.semianalysis.com/terms"
        assert decision["restrictions"]
    comparison = {"lines": [{"source": "gdpx"}], "attributions": []}
    granted = SimpleNamespace(
        source_configuration={"gdpx": {"use_policy": GDPX_USE_POLICY}}
    )
    for use in ("collection", "retention"):
        enforce_use(
            granted, comparison, use, current_policies={"gdpx": GDPX_USE_POLICY}
        )
    ungranted = SimpleNamespace(source_configuration={"gdpx": {}})
    with pytest.raises(UseNotPermitted):
        enforce_use(ungranted, comparison, "collection", current_policies={"gdpx": {}})


def test_gdpx_operation_defaults_are_daily_and_valid():
    from core.benchmark_metric_identity import SOURCE_OPERATION_DEFAULTS
    from core.benchmark_metric_operations import validate_operations

    settings = copy.deepcopy(SOURCE_OPERATION_DEFAULTS["gdpx"])
    validate_operations(settings)
    assert settings["poll_seconds"] == 86400
    assert settings["completed_day_lag"] == 0


def test_opencode_operation_defaults_are_unchanged():
    from core.benchmark_metric_identity import SOURCE_OPERATION_DEFAULTS

    assert SOURCE_OPERATION_DEFAULTS["opencode"] == {
        "poll_seconds": 3600,
        "freshness_seconds": 7200,
        "publication_freshness_seconds": 7200,
        "max_requests": 100,
        "max_seconds": 120,
        "max_bytes": 16 * 1024 * 1024,
        "completed_day_lag": 0,
        "recheck_days": 56,
    }
    assert set(SOURCE_OPERATION_DEFAULTS) == {"opencode", "gdpx"}


@pytest.mark.parametrize(
    ("config", "mappings", "statistics", "allowed"),
    [
        ({"gdpx"}, [], False, True),
        ({"gdpx"}, [], True, False),
        ({"arena"}, [], False, False),
        ({"gdpx", "arena"}, [], False, False),
        ({"hf"}, [], False, False),
        ({"openrouter"}, [], True, True),
        ({"openrouter", "arena"}, [], True, True),
        ({"hf"}, [{}], False, True),
        ({"gdpx"}, [{}], False, True),
        ({"hf"}, [{}] * 1001, False, False),
    ],
)
def test_mapping_budget_allows_empty_only_for_gdpx_or_statistics(
    config, mappings, statistics, allowed
):
    from core.benchmark_metric_identity import mapping_budget_allowed

    spec = {"mappings": mappings}
    settings = {source: {} for source in config}
    assert mapping_budget_allowed(spec, settings, statistics) is allowed


# PostgreSQL-backed scenarios. These need the shared test database wrapper:
# ~/.local/bin/pushinweight-test-db pytest tests/test_benchmark_gdpx_definitions.py


def gdpx_spec():
    from tests.test_benchmark_download_db_identity import setup_spec

    _, spec = setup_spec()
    spec["mappings"] = []
    spec["source_configuration"] = {"gdpx": {"metrics": sorted(GDPX_METRICS)}}
    return spec


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_register_gdpx_definitions_creates_units_and_forms():
    from core.benchmark_metric_identity import register_definitions
    from core.models import DataSource, MeasurementUnit, SourceMetric

    register_definitions(sources=("gdpx",))
    assert DataSource.objects.get(pk="gdpx").adapter_key == "gdpx-dataset-v1"
    assert DataSource.objects.get(pk="gdpx").metadata["attribution"]["publisher"] == (
        "GDPx by SemiAnalysis"
    )
    assert {"percent", "usd", "output_tokens_per_task", "tasks"} <= set(
        MeasurementUnit.objects.values_list("code", flat=True)
    )
    stored = {m.metric_key: m for m in SourceMetric.objects.filter(source_id="gdpx")}
    assert set(stored) == set(GDPX_METRICS)
    for key, (_, unit, form, kind, _) in GDPX_METRICS.items():
        assert stored[key].unit_reference_id == unit
        assert stored[key].quantity_form == form
        assert stored[key].value_kind == kind
        assert stored[key].required is (key == "score")
    # Re-registration is idempotent against the installed definitions.
    register_definitions(sources=("gdpx",))


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_database_accepts_monetary_and_rejects_unknown_quantity_forms():
    from django.db import IntegrityError, transaction

    from core.benchmark_metric_identity import register_definitions
    from core.models import MetricType, SourceMetric

    register_definitions(sources=("gdpx",))
    base = {
        "source_id": "gdpx",
        "metric_type": MetricType.objects.get(pk="cost_per_task"),
        "name": "Fixture",
        "unit_reference_id": "usd",
        "value_kind": "float",
        "measurement_kind": "state",
    }
    SourceMetric.objects.create(
        metric_key="fixture_cost", version=1, quantity_form="monetary", **base
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        SourceMetric.objects.create(
            metric_key="fixture_currency", version=1, quantity_form="currency", **base
        )


BEFORE_MONETARY = ("core", "0245_home_sentiment_recent_boundary")
AFTER_MONETARY = ("core", "0246_metric_monetary_quantity")


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("migration_rehearsal_schema", [BEFORE_MONETARY], indirect=True)
def test_metric_quantity_migration_applies_and_reverses_without_row_changes(
    migration_rehearsal_schema,
):
    from django.db import IntegrityError, connection, transaction
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    old = executor.loader.project_state([BEFORE_MONETARY]).apps
    old.get_model("core", "MeasurementUnit").objects.create(code="usd")
    source = old.get_model("core", "DataSource").objects.create(
        pk="gdpx", name="GDPx", source_type="benchmark"
    )
    kind = old.get_model("core", "MetricType").objects.create(pk="cost", name="Cost")
    base = {
        "source": source,
        "metric_type": kind,
        "name": "Fixture",
        "unit_reference_id": "usd",
        "value_kind": "float",
        "measurement_kind": "state",
        "version": 1,
    }
    metric = old.get_model("core", "SourceMetric")
    metric.objects.create(metric_key="fixture_ratio", quantity_form="ratio", **base)
    with pytest.raises(IntegrityError), transaction.atomic():
        metric.objects.create(metric_key="early", quantity_form="monetary", **base)

    def rows(apps):
        return sorted(
            apps.get_model("core", "SourceMetric").objects.values_list(
                "pk", "metric_key", "quantity_form"
            )
        )

    before = rows(old)
    executor.migrate([AFTER_MONETARY])
    new = MigrationExecutor(connection).loader.project_state([AFTER_MONETARY]).apps
    assert rows(new) == before
    executor = MigrationExecutor(connection)
    executor.migrate([BEFORE_MONETARY])
    assert rows(executor.loader.project_state([BEFORE_MONETARY]).apps) == before


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_enforce_source_collection_needs_recorded_gdpx_policy():
    from core.benchmark_attribution import (
        GDPX_USE_POLICY,
        UseNotPermitted,
        enforce_source_collection,
    )
    from core.benchmark_metric_identity import register_definitions
    from core.models import DataSource

    register_definitions(sources=("gdpx",))
    without = SimpleNamespace(source_configuration={"gdpx": {}})
    with pytest.raises(UseNotPermitted):
        enforce_source_collection(without, "gdpx")
    source = DataSource.objects.get(pk="gdpx")
    source.metadata["use_policy"] = copy.deepcopy(GDPX_USE_POLICY)
    source.save(update_fields=["metadata"])
    granted = SimpleNamespace(
        source_configuration={"gdpx": {"use_policy": copy.deepcopy(GDPX_USE_POLICY)}}
    )
    enforce_source_collection(granted, "gdpx")


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_gdpx_only_contract_needs_no_mappings_and_has_a_stable_hash():
    from core.benchmark_metric_identity import configure_collection

    spec = gdpx_spec()
    contract = configure_collection(copy.deepcopy(spec))
    assert contract.mappings.count() == 0
    settings = contract.source_configuration["gdpx"]
    assert settings["adapter_key"] == "gdpx-dataset-v1"
    assert settings["poll_seconds"] == 86400
    assert configure_collection(copy.deepcopy(spec)).pk == contract.pk


@pytest.mark.requires_postgres
@pytest.mark.django_db
@pytest.mark.parametrize(
    "configuration",
    [
        {"arena": {"metrics": ["rating"]}},
        {"gdpx": {"metrics": ["score"]}, "arena": {"metrics": ["rating"]}},
    ],
)
def test_empty_mappings_stay_rejected_outside_gdpx_only(configuration):
    from core.benchmark_metric_identity import prepare_collection

    spec = gdpx_spec()
    spec["source_configuration"] = configuration
    with pytest.raises(ValueError, match="mapping budget exceeded or empty"):
        prepare_collection(spec)
