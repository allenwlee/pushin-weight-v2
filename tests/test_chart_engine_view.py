from decimal import Decimal

from core.chart_engine_view import prepare_line


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
