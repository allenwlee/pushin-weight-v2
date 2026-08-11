from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_quarantined_dry_run_needs_no_historical_window_and_writes_nothing():
    from core.models import HarvestBacklogWindow

    stdout = StringIO()
    call_command("backfill", quarantined=True, dry_run=True, stdout=stdout)
    assert "Quarantined harvest intervals: 0" in stdout.getvalue()
    assert HarvestBacklogWindow.objects.count() == 0


def test_historical_backfill_still_requires_since():
    with pytest.raises(CommandError, match="--since is required"):
        call_command("backfill")
