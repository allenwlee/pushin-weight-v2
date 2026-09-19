from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.job_sources.registry import SOURCES
from core.job_sources.runner import SourceRunResult, run_source
from core.job_sources.types import SourceSnapshot
from core.models import JobListing, JobSourceState, JobSourceSyncRun


def test_named_sources_are_repeatable_and_json_is_machine_readable(monkeypatch):
    calls = []

    def fake_run(source, **options):
        calls.append((source.key, options))
        return SourceRunResult(source.key, "validated", 7)

    monkeypatch.setattr(
        "core.management.commands.sync_job_sources.run_source", fake_run
    )
    output = StringIO()
    call_command(
        "sync_job_sources",
        "--source",
        "qwen",
        "--source",
        "kimi",
        "--dry-run",
        "--json",
        stdout=output,
    )
    assert [key for key, _ in calls] == ["qwen", "kimi"]
    assert '"observed_total": 7' in output.getvalue()
    assert all(options["dry_run"] for _, options in calls)


def test_all_sources_are_attempted_before_the_command_reports_failure(monkeypatch):
    calls = []

    def fake_run(source, **_options):
        calls.append(source.key)
        if source.key == "minimax":
            return SourceRunResult(source.key, "failed", error="contract drift")
        return SourceRunResult(source.key, "succeeded", 1)

    monkeypatch.setattr(
        "core.management.commands.sync_job_sources.run_source", fake_run
    )
    with pytest.raises(CommandError, match="1 job source"):
        call_command("sync_job_sources", stdout=StringIO())
    assert calls == list(SOURCES)


def test_unexpected_source_exception_does_not_stop_later_sources(monkeypatch):
    calls = []

    def fake_run(source, **_options):
        calls.append(source.key)
        if source.key == "minimax":
            raise RuntimeError("unexpected adapter failure")
        return SourceRunResult(source.key, "succeeded", 1)

    monkeypatch.setattr(
        "core.management.commands.sync_job_sources.run_source", fake_run
    )
    with pytest.raises(CommandError, match="1 job source"):
        call_command("sync_job_sources", stdout=StringIO())
    assert calls == list(SOURCES)


@pytest.mark.django_db
def test_dry_run_fetches_but_creates_no_rows_or_lease(monkeypatch):
    snapshot = SourceSnapshot("qwen", (), 0, True, datetime.now(UTC))
    monkeypatch.setattr(
        "core.job_sources.runner.fetch_source", lambda _source: snapshot
    )
    result = run_source(SOURCES["qwen"], dry_run=True)
    assert result.status == "validated"
    assert not JobListing.objects.exists()
    assert not JobSourceSyncRun.objects.exists()
    assert not JobSourceState.objects.exists()
