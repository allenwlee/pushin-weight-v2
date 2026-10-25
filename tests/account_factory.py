"""Explicit X provider classification references for current-schema fixtures."""

from core.models import DataSource
from core.source_vocabulary import reference_id


def x_verification_id(code):
    if code is None:
        return None
    DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"}
    )
    return reference_id("account_verification_types", "x", code)
