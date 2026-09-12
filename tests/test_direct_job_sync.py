from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from core.job_sources.registry import SOURCES
from core.job_sources.runner import run_source
from core.job_sources.sync import sync_snapshot
from core.job_sources.types import SourceJob, SourceSnapshot
from core.models import Brand, JobListing, JobSourceState, JobSourceSyncRun

pytestmark = pytest.mark.django_db


def _snapshot(*ids: str, complete: bool = True) -> SourceSnapshot:
    return SourceSnapshot(
        source_key="qwen",
        jobs=tuple(
            SourceJob(
                source_listing_id=value,
                title=f"Role {value}",
                canonical_url=f"https://talent.quark.cn/job/{value}",
                application_url=f"https://talent.quark.cn/job/{value}",
                description_text=f"Description {value}",
                locations=("Hangzhou",),
            )
            for value in ids
        ),
        declared_total=len(ids),
        complete=complete,
        observed_at=timezone.now(),
    )


def test_direct_sync_is_idempotent_updates_and_reopens():
    Brand.objects.create(nickname="qwen", display_name="Qwen")
    first = sync_snapshot(_snapshot("one"))
    listing = JobListing.objects.get()
    first_seen = listing.first_seen_at

    second = sync_snapshot(_snapshot("one"))
    listing.refresh_from_db()
    assert first.created_count == 1
    assert second.unchanged_count == 1
    assert JobListing.objects.count() == 1
    assert listing.first_seen_at == first_seen
    assert listing.source_key == "qwen"
    assert listing.consecutive_missing_snapshots == 0

    sync_snapshot(_snapshot())
    listing.refresh_from_db()
    assert listing.status == "open"
    assert listing.consecutive_missing_snapshots == 1

    closed = sync_snapshot(_snapshot())
    listing.refresh_from_db()
    assert closed.closed_count == 1
    assert listing.status == "closed"

    reopened = sync_snapshot(_snapshot("one"))
    listing.refresh_from_db()
    assert reopened.reopened_count == 1
    assert listing.status == "open"
    assert listing.closed_at is None


def test_incomplete_snapshot_never_advances_missing_counter():
    Brand.objects.create(nickname="qwen", display_name="Qwen")
    sync_snapshot(_snapshot("one"))
    sync_snapshot(_snapshot(complete=False))
    listing = JobListing.objects.get()
    assert listing.status == "open"
    assert listing.consecutive_missing_snapshots == 0


def test_source_lease_blocks_overlap_and_can_be_reclaimed_after_expiry():
    state = JobSourceState.objects.create(
        source_key="qwen",
        lease_token="first",
        lease_expires_at=timezone.now() + timedelta(minutes=30),
    )
    assert state.lease_is_active()

    state.lease_expires_at = timezone.now() - timedelta(seconds=1)
    state.save(update_fields=["lease_expires_at"])
    state.refresh_from_db()
    assert not state.lease_is_active()


def test_sync_run_records_complete_snapshot_counts():
    Brand.objects.create(nickname="qwen", display_name="Qwen")
    result = sync_snapshot(_snapshot("one", "two"))
    run = JobSourceSyncRun.objects.get(pk=result.run_id)
    assert run.status == "succeeded"
    assert run.snapshot_complete is True
    assert run.declared_total == run.observed_total == 2
    assert run.created_count == 2


def test_zero_after_nonzero_success_is_diagnostic_only(monkeypatch):
    Brand.objects.create(nickname="qwen", display_name="Qwen")
    snapshots = iter([_snapshot("one"), _snapshot()])
    monkeypatch.setattr(
        "core.job_sources.runner.fetch_source", lambda _source: next(snapshots)
    )

    assert run_source(SOURCES["qwen"]).status == "succeeded"
    result = run_source(SOURCES["qwen"])

    listing = JobListing.objects.get()
    state = JobSourceState.objects.get(source_key="qwen")
    latest = JobSourceSyncRun.objects.order_by("-id").first()
    assert result.status == "partial"
    assert listing.status == "open"
    assert listing.consecutive_missing_snapshots == 0
    assert state.last_snapshot_count == 1
    assert latest.snapshot_complete is False
    assert latest.metadata["anomaly"] == "zero_after_nonzero_snapshot"


def test_closed_listing_missing_counter_is_capped():
    Brand.objects.create(nickname="qwen", display_name="Qwen")
    sync_snapshot(_snapshot("one"))
    sync_snapshot(_snapshot())
    sync_snapshot(_snapshot())
    sync_snapshot(_snapshot())

    listing = JobListing.objects.get()
    assert listing.status == "closed"
    assert listing.consecutive_missing_snapshots == 2


def test_active_lease_skip_records_a_finished_run():
    JobSourceState.objects.create(
        source_key="qwen",
        lease_token="first",
        lease_expires_at=timezone.now() + timedelta(minutes=30),
    )

    result = run_source(SOURCES["qwen"])

    run = JobSourceSyncRun.objects.get()
    assert result.status == "skipped"
    assert run.status == "skipped"
    assert run.finished_at is not None
    assert run.error_summary == "active source lease"


def test_lost_lease_fails_without_mutating_listings(monkeypatch):
    Brand.objects.create(nickname="qwen", display_name="Qwen")

    def steal_lease(_source):
        rival = JobSourceSyncRun.objects.create(source_key="qwen")
        JobSourceState.objects.filter(source_key="qwen").update(
            lease_token="rival-token",
            lease_expires_at=timezone.now() + timedelta(minutes=30),
            active_run=rival,
        )
        return _snapshot("one")

    monkeypatch.setattr("core.job_sources.runner.fetch_source", steal_lease)
    result = run_source(SOURCES["qwen"])

    assert result.status == "failed"
    assert "lease was lost" in result.error
    assert not JobListing.objects.exists()
    assert JobSourceSyncRun.objects.filter(status="failed").count() == 1


def test_duplicate_ids_fail_dry_run_without_database_writes(monkeypatch):
    duplicate = SourceSnapshot(
        "qwen",
        (_snapshot("one").jobs[0], _snapshot("one").jobs[0]),
        2,
        True,
        timezone.now(),
    )
    monkeypatch.setattr(
        "core.job_sources.runner.fetch_source", lambda _source: duplicate
    )

    result = run_source(SOURCES["qwen"], dry_run=True)

    assert result.status == "failed"
    assert "duplicate listing IDs" in result.error
    assert not JobSourceState.objects.exists()
    assert not JobSourceSyncRun.objects.exists()
