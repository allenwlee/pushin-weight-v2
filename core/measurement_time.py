"""Database-generated finite measurement intervals; NULL endpoints mean unknown."""

from django.contrib.postgres.fields import DateTimeRangeField
from django.db import models


def measurement_window(start_field: str, end_field: str) -> models.GeneratedField:
    """Use the versioned PostgreSQL boundary rule for a metric window column."""
    return models.GeneratedField(
        expression=models.Func(
            models.F(start_field),
            models.F(end_field),
            function="measurement_window_v1",
            output_field=DateTimeRangeField(),
        ),
        output_field=DateTimeRangeField(),
        db_persist=True,
        null=True,
        db_comment=(
            "Finite [start,end) measurement window: inclusive start, exclusive end. "
            "Generated from endpoints; NULL if either endpoint is unknown, never unbounded."
        ),
    )
