"""Physical retirement stays blocked throughout compatible staging delivery."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import OriginalContentRun
from monitor.original_content_cutover import retirement_status

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_retirement_has_no_clock_without_an_observed_cutover():
    status = retirement_status()
    assert status["cutover_at"] is None and not status["ready"]


def test_retirement_has_no_wait_but_preserves_actual_legacy_dependencies():
    now = timezone.now()
    OriginalContentRun.objects.create(
        source_cycle_id="storage-cutover:verified",
        workflow_key="editorial-dispatch",
        scope_key="migration:original-content:cutover",
        facts_as_of=now,
        packet_schema_version=1,
        snapshot={},
        outcome={"cutover_at": now.isoformat()},
    )
    status = retirement_status(now=now)
    assert "rollback_window_elapsed" not in status
    assert "earliest_retirement_at" not in status
    assert status == retirement_status(now=now + timedelta(days=7))
    assert status["legacy_consumers"] and status["restore_proof_required"]
    assert not status["ready"]
