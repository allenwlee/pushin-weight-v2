"""Career definitions reuse DataSource without activating collection."""

import pytest
from django.db import IntegrityError, transaction

from core.models import DataSource

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_career_site_source_type_starts_inert():
    source = DataSource.objects.create(
        id="career_qwen_test", name="Qwen careers",
        source_type="career_site", enabled=False,
    )
    assert source.source_type == "career_site"
    assert not source.enabled
    with pytest.raises(IntegrityError), transaction.atomic():
        DataSource.objects.filter(pk=source.pk).update(enabled=True)
