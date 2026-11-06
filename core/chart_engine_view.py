"""Convert stored daily values to stable, release-relative chart points."""

from datetime import timedelta
from decimal import Decimal


def single_brand_line(source, metric, values, evidence, anchor, start, end):
    """Calculate a stable release-relative series, retaining missing observations."""
    values = {
        day: Decimal(str(value)) for day, value in values.items() if value is not None
    }
    observed = sorted(day for day in values if day >= 0)
    first = None
    basis = "complete_week"
    if source == "arena":
        basis = "first_observation"
        first = next((day for day in observed if values[day] > 0), None)
        baseline = values[first] if first is not None else None
    else:
        baseline = None
        for day in (day for day in observed if day >= 1):
            week = [values.get(index) for index in range(day, day + 7)]
            if all(value is not None for value in week) and sum(week) > 0:
                first = day
                baseline = sum(week) / 7
                break
    reference = None
    if first is not None:
        reference = {
            "basis": basis,
            "mean": baseline,
            "start": (anchor + timedelta(days=first)).isoformat(),
            "end": (
                anchor + timedelta(days=first + (6 if basis == "complete_week" else 0))
            ).isoformat(),
        }
    points = []
    rank_observed = sorted(values) if source == "arena" and metric == "rank" else []
    for day in range(start, end):
        raw = values.get(day)
        prior = [item for item in rank_observed if item <= day]
        carrying = bool(
            prior
            and rank_observed[0] < day < rank_observed[-1]
            and raw is None
            and not any(
                (evidence.get(index) or {}).get("coverage") not in {None, "missing"}
                for index in range(prior[-1] + 1, day + 1)
            )
        )
        source_day = prior[-1] if carrying else (day if raw is not None else None)
        display = values[source_day] if source_day is not None else None
        trailing = [values.get(index) for index in range(day - 2, day + 1)]
        average = (
            sum(trailing) / 3 if all(value is not None for value in trailing) else None
        )
        percent = (
            (display / baseline - 1) * 100 if display is not None and baseline else None
        )
        smooth = (
            (average / baseline - 1) * 100 if average is not None and baseline else None
        )
        if source == "arena":
            smooth = percent
        points.append(
            {
                "day": day,
                "date": (anchor + timedelta(days=day)).isoformat(),
                "raw": raw,
                "percent": percent,
                "smooth_percent": smooth,
                "coverage": "carried"
                if carrying
                else (
                    "observed"
                    if raw is not None
                    else (evidence.get(day) or {}).get("coverage", "missing")
                ),
                "source_date": (anchor + timedelta(days=source_day)).isoformat()
                if source_day is not None
                else None,
                "carried": carrying,
                "evidence": evidence.get(source_day),
            }
        )
    return {
        "reference": reference,
        "points": points,
        "observed_dates": sum(point["raw"] is not None for point in points),
    }


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
