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


def test_seven_days_alone_never_authorizes_dropping_live_legacy_storage():
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
    assert not retirement_status(now=now + timedelta(days=6))["rollback_window_elapsed"]
    status = retirement_status(now=now + timedelta(days=7))
    assert status["rollback_window_elapsed"]
    assert status["legacy_consumers"] and status["restore_proof_required"]
    assert not status["ready"]
