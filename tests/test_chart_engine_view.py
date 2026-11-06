from decimal import Decimal

from core.chart_engine_view import prepare_line


def test_single_brand_gap_zero_reference_and_rank_carry():
    from datetime import date

    from core.chart_engine_view import single_brand_line

    values = {**{day: 10 for day in range(1, 8)}, 8: 0, 10: 15}
    line = single_brand_line("hf", "downloads", values, {}, date(2026, 8, 13), 1, 11)
    assert line["reference"]["mean"] == Decimal(10)
    assert line["points"][7]["raw"] == Decimal(0)
    assert line["points"][7]["percent"] == Decimal(-100)
    assert line["points"][8]["raw"] is None
    assert line["points"][9]["smooth_percent"] is None

    rank = single_brand_line(
        "arena", "rank", {2: 8, 5: 10}, {}, date(2026, 8, 13), 0, 7
    )
    assert rank["reference"]["basis"] == "first_observation"
    assert rank["points"][1]["percent"] is None
    assert rank["points"][3]["raw"] is None
    assert rank["points"][3]["source_date"] == "2026-08-15"
    assert rank["points"][3]["carried"] is True
    assert rank["points"][6]["percent"] is None


def test_public_single_brand_uses_rolling_downloads_and_includes_unavailable(
    monkeypatch,
):
    from datetime import UTC, date, datetime
    from types import SimpleNamespace

    from core import chart_engine

    product = SimpleNamespace(
        product_key="product-a",
        display_name="Model A",
        repo_id="org/model",
        brand_id="brand",
    )
    mapping = SimpleNamespace(source_id="hf", external_identifier="org/model")
    metric = SimpleNamespace(
        mapping=mapping, selection=SimpleNamespace(metric_key="downloads")
    )
    resolved = SimpleNamespace(
        target=SimpleNamespace(
            product=product,
            date=date(2026, 8, 13),
            anchor_source="caller",
            reviewed=False,
        ),
        metrics=(metric,),
    )
    captured = []
    monkeypatch.setattr(
        chart_engine,
        "validate_request",
        lambda request, **kwargs: captured.append(kwargs) or resolved,
    )
    monkeypatch.setattr(
        chart_engine,
        "_single_brand_discussion",
        lambda resolved: {"status": "stored_only", "daily": {}},
    )
    monkeypatch.setattr(chart_engine, "_unmapped_exact_values", lambda *args: {})
    monkeypatch.setattr(
        chart_engine,
        "metric_series",
        lambda *args, **kwargs: {
            "status": "available",
            "points": [
                {
                    "date": f"2026-08-{day:02}",
                    "value": 10,
                    "net_change": 500,
                    "evidence": {},
                }
                for day in range(14, 21)
            ],
        },
    )
    request = SimpleNamespace(
        comparison=None,
        history_mode="hindsight",
        start=datetime(2026, 8, 13, tzinfo=UTC),
        end=datetime(2026, 8, 22, tzinfo=UTC),
        cutoff=datetime(2026, 8, 23, tzinfo=UTC),
    )
    result = chart_engine.build_single_brand_chart(request, start_day=0, end_day=9)
    hf = next(line for line in result["lines"] if line["key"] == "hf:downloads")
    assert hf["points"][1]["raw"] == 10
    assert hf["reference"]["mean"] == Decimal(10)
    assert (
        next(line for line in result["lines"] if line["key"] == "opencode:tokens")[
            "status"
        ]
        == "mapping_unavailable"
    )
    assert captured == [{"source_use_override": True}]


def test_fixed_historical_week_and_trailing_smoothing_survive_crop():
    history = {day: Decimal(day + 10) for day in range(10)}
    line = prepare_line(
        {day: Decimal(day + 20) for day in range(10)},
        history,
        start=5,
        end=8,
        smoothing=True,
    )
    assert line[0]["day"] == 5
    assert line[0]["raw"] == Decimal(25)
    assert line[0]["value"] == (Decimal(24) / Decimal(14) - 1) * 100
    assert line[0]["reference"] == Decimal(14)


def test_gaps_and_nonpositive_or_incomplete_reference_are_not_invented():
    line = prepare_line(
        {0: 3, 1: None, 2: 4}, {day: 0 for day in range(7)}, start=0, end=3
    )
    assert all(point["value"] is None for point in line)
    assert prepare_line({0: 3}, {0: 1}, start=0, end=1)[0]["value"] is None
