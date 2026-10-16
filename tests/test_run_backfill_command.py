"""Any date range is input data; planning never calls providers or writes jobs."""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import CollectionJob, OriginalContentCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def planned(settings):
    settings.X_MONITOR_LIST_ID = 123


@pytest.mark.parametrize(
    "since,until",
    [("2026-07-01", "2026-08-01"), ("2026-09-17T03:00:00Z", "2026-09-17T05:00:00Z")],
)
def test_arbitrary_ranges_need_no_source_edits_or_paid_requests(planned, since, until):
    output = StringIO()
    call_command(
        "run_backfill",
        since=since,
        until=until,
        campaign_name="arbitrary-recovery",
        stdout=output,
    )
    frozen = json.loads(output.getvalue())
    assert frozen["campaign"] == "arbitrary-recovery"
    assert (
        frozen["windows"][0]["since"] == since
        and frozen["windows"][0]["until"] == until
    )
    assert len(frozen["windows"]) == 1
    definition = frozen["windows"][0]["collection_definition"]
    assert definition["scope"]["adapter"] == "x-backfill/v2"
    assert set(definition["scope"]["required_call_ids"]) == {
        "A", "B1", "B2", "B3", "C1", "C2", "C3",
    }
    assert definition["scope"]["since_epoch"] < definition["scope"]["until_epoch"]
    assert definition["scope"]["author_scope"]["historical_membership_reconstructed"] is False
    assert (
        not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()
    )


def test_multiple_windows_and_supplements_are_configuration(planned, tmp_path):
    path = tmp_path / "campaign.json"
    path.write_text(
        json.dumps(
            {
                "name": "two-windows",
                "windows": [
                    {"since": "2026-07-01", "until": "2026-07-02"},
                    {"since": "2026-09-01", "until": "2026-09-02"},
                ],
                "supplemental_queries": [
                    {"call_id": "B1", "query": "historical-alias"}
                ],
            }
        )
    )
    output = StringIO()
    call_command("run_backfill", windows=path, stdout=output)
    frozen = json.loads(output.getvalue())
    assert len(frozen["windows"]) == 2
    assert frozen["queries"][-1] == ["B1", "historical-alias"]
    assert not CollectionJob.objects.exists()


def test_saved_manifest_preserves_deadline_and_allowances(planned, tmp_path):
    first = StringIO()
    call_command("run_backfill", since="2026-07-01", until="2026-08-01", stdout=first)
    path = tmp_path / "saved.json"
    path.write_text(first.getvalue())
    second = StringIO()
    call_command("run_backfill", manifest=path, stdout=second)
    assert json.loads(second.getvalue()) == json.loads(first.getvalue())
    assert not CollectionJob.objects.exists()


def test_aggregate_execution_mode_does_not_change_saved_manifest(
    planned, tmp_path, monkeypatch
):
    import monitor.management.commands.run_backfill as command

    output = StringIO()
    call_command("run_backfill", since="2026-08-01", until="2026-08-02", stdout=output)
    frozen = json.loads(output.getvalue())
    saved = tmp_path / "saved.json"
    saved.write_text(output.getvalue())
    observed = []
    monkeypatch.setattr(
        command,
        "run",
        lambda manifest, cfg, **kwargs: observed.append((manifest, kwargs)),
    )
    call_command("run_backfill", manifest=saved, execute=True, evaluate_at_end=True)
    assert observed == [(frozen, {"evaluate_at_end": True})]
    assert json.loads(saved.read_text()) == frozen
    assert not CollectionJob.objects.exists()


@pytest.mark.parametrize(
    "since,until", [("2026-08-02", "2026-08-01"), ("invalid-date", "2026-08-01")]
)
def test_invalid_bounds_fail_before_any_job_or_provider(planned, since, until):
    with pytest.raises(CommandError):
        call_command("run_backfill", since=since, until=until, stdout=StringIO())
    assert (
        not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()
    )


def test_pending_rare_decisions_do_not_block_stored_post_enrichment(planned, monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import DataSource
    from scripts import backfill_campaign as campaign
    from x_monitor.config import load_config

    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "test-only-on-demand")
    DataSource.objects.get_or_create(id="x", defaults={"name": "X", "source_type": "social"})
    cfg = load_config(Path("config.yaml"))
    frozen = campaign.manifest(
        cfg, windows=[("2026-07-30", "2026-07-31")], campaign_name="pending-rare",
        deadline=timezone.now() + timedelta(hours=1),
    )
    phases = []

    def collect(job_id):
        # Enumeration finished, but a real job remains incomplete until Jev resolves.
        assert phases == []
        phases.append("collection")
        return {"collection_drained": True, "rare_gate_pending": 1}

    def enrich(*args, **kwargs):
        phases.append("enrichment")
        return {"status": "completed"}

    monkeypatch.setattr(campaign, "execute_job", collect)
    monkeypatch.setattr(campaign, "prepare_current_contract", lambda *args: None)
    monkeypatch.setattr(campaign, "execute_enrichment", enrich)
    monkeypatch.setattr(campaign, "policy_snapshot", lambda **kwargs: {})
    monkeypatch.setattr(campaign, "deferred_enrichment_work", lambda *args, **kwargs: {})
    monkeypatch.setattr(campaign, "advance_targeted", lambda *args, **kwargs: {"status": "completed"})
    result = campaign.execute_window(frozen["windows"][0], frozen=frozen, cfg=cfg, evaluate_at_end=True)
    assert phases == ["collection", "enrichment"]
    assert result["issues"] == [{"phase": "collection", "error_code": "rare_gate_pending"}]
    assert result["status"] == "attempted"
    assert CollectionJob.objects.get(pk=result["source_collection_job"]).state != "completed"
