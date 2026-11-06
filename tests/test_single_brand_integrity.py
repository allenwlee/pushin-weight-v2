from datetime import UTC, date, datetime
from types import SimpleNamespace

from core import chart_engine
from core.chart_engine_view import single_brand_line


def test_rank_conflict_breaks_carry_until_next_observed_snapshot():
    line = single_brand_line(
        "arena",
        "rank",
        {0: 5, 4: 7},
        {2: {"coverage": "conflict"}},
        date(2026, 8, 13),
        0,
        5,
    )
    assert [p["coverage"] for p in line["points"]] == [
        "observed",
        "carried",
        "conflict",
        "missing",
        "observed",
    ]
    assert line["points"][2]["percent"] is None
    assert line["points"][3]["percent"] is None


def test_daily_reference_starts_after_release_day():
    values = {day: 100 if day == 0 else 10 for day in range(8)}
    line = single_brand_line("hf", "downloads", values, {}, date(2026, 8, 13), 0, 8)
    assert line["reference"]["start"] == "2026-08-14"
    assert line["reference"]["mean"] == 10
    assert line["points"][0]["raw"] == 100


def test_arena_reference_uses_first_positive_snapshot_without_losing_zero():
    line = single_brand_line("arena", "rank", {0: 0, 1: 5}, {}, date(2026, 8, 13), 0, 2)
    assert line["reference"]["start"] == "2026-08-14"
    assert line["points"][0]["raw"] == 0
    assert line["points"][0]["percent"] == -100


def test_partial_utc_days_excluded_from_brand_aggregation_window():
    start, end = chart_engine._complete_utc_window(
        datetime(2026, 8, 13, 12, tzinfo=UTC),
        datetime(2026, 8, 16, 12, tzinfo=UTC),
        datetime(2026, 8, 17, tzinfo=UTC),
    )
    assert start == datetime(2026, 8, 14, tzinfo=UTC)
    assert end == datetime(2026, 8, 16, tzinfo=UTC)


def test_exact_day_requires_explicit_matching_utc_bounds():
    row = {
        "temporal_status": "exact",
        "source_timezone": "UTC",
        "window_start_at": "2026-08-13T00:00:00+00:00",
        "window_end_at": "2026-08-14T00:00:00+00:00",
    }
    assert chart_engine._exact_utc_day(row, "2026-08-13")
    assert not chart_engine._exact_utc_day(
        dict(row, window_start_at="2026-08-13T01:00:00+00:00"), "2026-08-13"
    )
    assert not chart_engine._exact_utc_day(
        dict(row, source_timezone="unknown"), "2026-08-13"
    )


def test_mapped_series_drops_non_utc_window_and_wrong_metric_definition(monkeypatch):
    from core import benchmark_forecast_inputs

    mapping = SimpleNamespace(
        source_id="openrouter",
        pk="mapping",
        contract=object(),
        external_identifier="model",
    )
    metric = SimpleNamespace(
        mapping=mapping,
        selection=SimpleNamespace(metric_key="total_tokens", release="target"),
    )
    request = SimpleNamespace(
        start=datetime(2026, 8, 13, tzinfo=UTC),
        end=datetime(2026, 8, 16, tzinfo=UTC),
        cutoff=datetime(2026, 8, 17, tzinfo=UTC),
        history_mode="hindsight",
    )
    resolved = SimpleNamespace(request=request, metrics=[metric], comparison=None)
    monkeypatch.setattr(
        chart_engine, "_single_chart_definition", lambda *args: {"id": 1}
    )

    def row(day, start, end, definition):
        return {
            "metric": "total_tokens",
            "metric_definition_id": definition,
            "source_metadata": {},
            "period_label_date": day,
            "as_of_date": None,
            "as_of_at": None,
            "window_start_at": start,
            "window_end_at": end,
            "temporal_status": "exact",
            "source_timezone": "UTC",
            "dimensions": {},
            "value": 7,
            "unit": "tokens",
            "measurement_kind": "flow",
            "window_mode": "calendar",
            "run_id": "run",
            "value_id": 1,
            "observation_id": 1,
            "provider_as_of": "2026-08-17T00:00:00+00:00",
            "import_completed_at": "2026-08-17T00:00:00+00:00",
        }

    rows = [
        row("2026-08-13", "2026-08-13T00:00:00+00:00", "2026-08-14T00:00:00+00:00", 1),
        row("2026-08-14", "2026-08-14T01:00:00+00:00", "2026-08-15T01:00:00+00:00", 1),
        row("2026-08-15", "2026-08-15T00:00:00+00:00", "2026-08-16T00:00:00+00:00", 2),
    ]
    monkeypatch.setattr(
        benchmark_forecast_inputs,
        "forecast_inputs",
        lambda *args, **kwargs: {"values": rows},
    )
    result = chart_engine.metric_series(
        resolved, 0, source_use_override=True, single_template=True
    )
    assert [point["value"] for point in result["points"]] == [7, None, None]


def test_mapped_arena_excludes_other_leaderboard_categories(monkeypatch):
    from core import benchmark_forecast_inputs

    mapping = SimpleNamespace(
        source_id="arena", pk="mapping", contract=object(), external_identifier="model"
    )
    metric = SimpleNamespace(
        mapping=mapping, selection=SimpleNamespace(metric_key="rank", release="target")
    )
    request = SimpleNamespace(
        start=datetime(2026, 8, 13, tzinfo=UTC),
        end=datetime(2026, 8, 14, tzinfo=UTC),
        cutoff=datetime(2026, 8, 15, tzinfo=UTC),
        history_mode="hindsight",
    )
    resolved = SimpleNamespace(request=request, metrics=[metric], comparison=None)
    monkeypatch.setattr(
        chart_engine, "_single_chart_definition", lambda *args: {"id": 1}
    )
    monkeypatch.setattr(
        benchmark_forecast_inputs,
        "forecast_inputs",
        lambda *args, **kwargs: {
            "values": [
                {
                    "metric": "rank",
                    "metric_definition_id": 1,
                    "dimensions": {"config": "code", "category": "overall"},
                }
            ]
        },
    )
    result = chart_engine.metric_series(
        resolved, 0, source_use_override=True, single_template=True
    )
    assert result["points"][0]["value"] is None


def test_existing_reader_retains_archive_date_precedence(monkeypatch):
    from core import benchmark_forecast_inputs

    mapping = SimpleNamespace(
        source_id="openrouter",
        pk="mapping",
        contract=object(),
        external_identifier="model",
    )
    metric = SimpleNamespace(
        mapping=mapping,
        selection=SimpleNamespace(metric_key="total_tokens", release="target"),
    )
    request = SimpleNamespace(
        start=datetime(2026, 8, 13, tzinfo=UTC),
        end=datetime(2026, 8, 15, tzinfo=UTC),
        cutoff=datetime(2026, 8, 16, tzinfo=UTC),
        history_mode="hindsight",
    )
    resolved = SimpleNamespace(request=request, metrics=[metric], comparison=None)
    row = {
        "metric": "total_tokens",
        "source_metadata": {"archive_snapshot_date": "2026-08-14"},
        "period_label_date": "2026-08-13",
        "as_of_date": None,
        "as_of_at": None,
        "dimensions": {},
        "value": 7,
        "unit": "tokens",
        "measurement_kind": "flow",
        "window_mode": "calendar",
        "run_id": "run",
        "value_id": 1,
        "observation_id": 1,
        "provider_as_of": "2026-08-15T00:00:00+00:00",
        "import_completed_at": "2026-08-15T00:00:00+00:00",
    }
    monkeypatch.setattr(
        benchmark_forecast_inputs,
        "forecast_inputs",
        lambda *args, **kwargs: {"values": [row]},
    )
    result = chart_engine.metric_series(resolved, 0)
    assert [point["value"] for point in result["points"]] == [None, 7]


def test_rolling_hf_must_match_frozen_definition_and_30_day_window(monkeypatch):
    from core import benchmark_metric_identity
    from core.models import SourceMetric

    frozen = {
        "id": 1,
        "metric_key": "downloads",
        "unit": "downloads",
        "window_mode": "rolling",
        "window_amount": 30,
        "window_unit": "day",
    }
    mapping = SimpleNamespace(
        source_id="hf",
        contract=SimpleNamespace(
            source_configuration={"hf": {"definitions": [frozen]}}
        ),
    )
    obj = object()
    monkeypatch.setattr(
        SourceMetric.objects,
        "filter",
        lambda **kwargs: SimpleNamespace(first=lambda: obj),
    )
    monkeypatch.setattr(
        benchmark_metric_identity, "definition_snapshot", lambda value: dict(frozen)
    )
    assert chart_engine._single_chart_definition(mapping, "downloads") == frozen
    frozen["window_amount"] = "30.000"
    assert chart_engine._single_chart_definition(mapping, "downloads") == frozen
    frozen["window_amount"] = 7
    assert chart_engine._single_chart_definition(mapping, "downloads") is None
    frozen["window_amount"] = 30
    monkeypatch.setattr(
        benchmark_metric_identity,
        "definition_snapshot",
        lambda value: dict(frozen, unit="likes"),
    )
    assert chart_engine._single_chart_definition(mapping, "downloads") is None
