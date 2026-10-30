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


def test_saved_campaign_can_select_a_new_exact_runtime_without_rewriting_instructions(
    planned, tmp_path, monkeypatch,
):
    import monitor.management.commands.run_backfill as command

    output = StringIO()
    call_command("run_backfill", since="2026-08-01", until="2026-08-02", stdout=output)
    frozen = json.loads(output.getvalue()) | {"revision": "a" * 40}
    saved = tmp_path / "saved.json"
    saved.write_text(json.dumps(frozen))
    original_bytes = saved.read_bytes()
    observed = []
    monkeypatch.setattr(command, "run", lambda manifest, cfg, **kw: observed.append((manifest, kw)))
    call_command(
        "run_backfill", manifest=saved, execute=True,
        runtime_revision="b" * 40, evaluate_at_end=True,
    )
    assert observed == [(frozen, {"evaluate_at_end": True, "runtime_revision": "b" * 40})]
    assert saved.read_bytes() == original_bytes
    assert not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()


@pytest.mark.parametrize("revision", ["main", "b" * 39, "b" * 41, "z" * 40])
def test_runtime_selection_requires_full_commit_sha_before_execution(planned, tmp_path, revision):
    saved = tmp_path / "saved.json"
    saved.write_text("{}")
    with pytest.raises(CommandError, match="full 40-character commit SHA"):
        call_command("run_backfill", manifest=saved, runtime_revision=revision, execute=True)
    assert not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()


def test_runtime_selection_requires_an_existing_manifest(planned):
    with pytest.raises(CommandError, match="requires --manifest"):
        call_command(
            "run_backfill", since="2026-08-01", until="2026-08-02",
            runtime_revision="b" * 40, execute=True,
        )
    assert not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()


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


@pytest.mark.parametrize("phase", ["legacy", "collect"])
def test_pending_rare_decisions_retain_legacy_deferral_but_block_collection_acceptance(planned, monkeypatch, phase):
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
    if phase == "collect":
        with pytest.raises(RuntimeError, match="collection_rare_gate_pending"):
            campaign.collect_window(frozen["windows"][0], frozen=frozen, cfg=cfg)
        assert phases == ["collection"]
        return
    result = campaign.execute_window(frozen["windows"][0], frozen=frozen, cfg=cfg, evaluate_at_end=True)
    assert phases == ["collection", "enrichment"]
    assert result["issues"] == [{"phase": "collection", "error_code": "rare_gate_pending"}]
    assert result["status"] == "attempted"
    assert CollectionJob.objects.get(pk=result["source_collection_job"]).state != "completed"


def test_explicit_campaign_all_routes_whole_range_to_phase_runner(planned, monkeypatch):
    import monitor.management.commands.run_backfill as command

    seen = []
    monkeypatch.setattr(command, "run_phases", lambda frozen, cfg, **kw: seen.append((frozen, kw)))
    monkeypatch.setattr(command, "run", lambda *a, **kw: pytest.fail("legacy runner selected"))
    call_command("run_backfill", since="2026-07-01", until="2026-07-03",
        campaign_name="explicit-phases", phase="all", execute=True,
        collection_concurrency=20, collection_starts_per_second=10, enrichment_concurrency=8)
    assert len(seen) == 1
    assert seen[0][0]["campaign"] == "explicit-phases"
    assert seen[0][1] == {"phase": "all", "enrichment_concurrency": 8,
        "collection_concurrency": 20, "collection_starts_per_second": 10, "evaluate_at_end": False}
    assert not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()


def test_phase_preferences_do_not_rewrite_saved_campaign(planned, tmp_path, monkeypatch):
    import monitor.management.commands.run_backfill as command

    output = StringIO()
    call_command("run_backfill", since="2026-07-01", until="2026-07-02", stdout=output)
    frozen = json.loads(output.getvalue())
    saved = tmp_path / "saved.json"
    saved.write_text(output.getvalue())
    seen = []
    monkeypatch.setattr(command, "run_phases", lambda value, cfg, **kw: seen.append((value, kw)))
    call_command("run_backfill", manifest=saved, phase="collect", execute=True, collection_concurrency=4)
    assert seen[0][0] == frozen
    assert seen[0][1]["collection_concurrency"] == 4
    assert json.loads(saved.read_text()) == frozen
    assert not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()


def test_window_spend_basis_is_planned_into_the_manifest_without_jobs(planned, tmp_path):
    path = tmp_path / "settled.json"
    path.write_text(json.dumps({"name": "settled-window", "windows": [
        {"since": "2026-07-01T00:00:00+00:00", "until": "2026-07-01T06:00:00+00:00", "spend_basis": "settled"},
        {"since": "2026-07-01T06:00:00+00:00", "until": "2026-07-01T12:00:00+00:00"},
    ]}))
    output = StringIO()
    call_command("run_backfill", windows=path, stdout=output)
    first, second = json.loads(output.getvalue())["windows"]
    assert first["spend_basis"] == "settled"
    assert "spend_basis" not in second
    assert not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()


def test_unknown_window_field_is_rejected_without_jobs(planned, tmp_path):
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps({"windows": [
        {"since": "2026-07-01T00:00:00+00:00", "until": "2026-07-01T06:00:00+00:00", "slice_seconds": 300},
    ]}))
    with pytest.raises(CommandError, match="unknown_window_field"):
        call_command("run_backfill", windows=path, stdout=StringIO())
    assert not CollectionJob.objects.exists() and not OriginalContentCall.objects.exists()
