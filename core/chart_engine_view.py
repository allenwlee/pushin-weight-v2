"""Convert stored daily values to stable, release-relative chart points."""

from decimal import Decimal


def prepare_line(
    values,
    reference_values,
    *,
    start,
    end,
    smoothing=False,
    normalized=True,
    reference_start=1,
):
    """Use one fixed seven-day historical reference, unaffected by view cropping."""
    reference = [
        reference_values.get(day) for day in range(reference_start, reference_start + 7)
    ]
    baseline = (
        sum(Decimal(str(v)) for v in reference) / 7
        if all(v is not None for v in reference)
        else None
    )
    if baseline is not None and baseline <= 0:
        baseline = None
    result = []
    for day in range(start, end):
        raw = values.get(day)
        trailing = [values.get(i) for i in range(day - 2, day + 1)]
        display = (
            (
                sum(Decimal(str(v)) for v in trailing) / 3
                if all(v is not None for v in trailing)
                else None
            )
            if smoothing
            else (Decimal(str(raw)) if raw is not None else None)
        )
        normalized_value = (
            (display / baseline - 1) * 100
            if display is not None and baseline is not None
            else None
        )
        result.append(
            {
                "day": day,
                "raw": Decimal(str(raw)) if raw is not None else None,
                "value": normalized_value if normalized else display,
                "reference": baseline,
            }
        )
    return result
