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


# Final assessments in the two shapes the runners return: run's campaign report
# and run_phases' compact per-window rows.
VERIFIED_WINDOW = {
    "status": "verified", "source_collection_job": "job-1",
    "window": {"index": 1, "since": "2026-07-01", "until": "2026-07-02"},
}
FAILED_WINDOW = {
    "status": "failed", "error_code": "classification_incomplete", "source_collection_job": "job-2",
    "window": {"index": 2, "since": "2026-07-02", "until": "2026-07-03"},
}
VERIFIED_REPORT = {"status": "verified", "windows_attempted": 1, "windows_verified": 1,
                   "windows": [VERIFIED_WINDOW]}
UNVERIFIED_REPORT = {"status": "incomplete", "windows_attempted": 2, "windows_verified": 1,
                     "windows": [VERIFIED_WINDOW, FAILED_WINDOW]}
PHASE_ROWS = [
    {"phase": "collection", "status": "verified", "source_collection_job": "job-1"},
    {"phase": "collection", "status": "verified", "source_collection_job": "job-2"},
    {"phase": "enrichment", "status": "verified", "source_collection_job": "job-1"},
    {"phase": "enrichment", "status": "failed", "error_code": "classification_incomplete",
     "source_collection_job": "job-2"},
]


def saved_campaign(tmp_path):
    """Saved instructions any phase accepts; the tests replace the runners."""
    from datetime import UTC, datetime, timedelta

    path = tmp_path / "saved.json"
    path.write_text(json.dumps({
        "campaign": "final-assessment", "direct_concurrency": 32, "windows": [],
        "deadline": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }))
    return path


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
    monkeypatch.setattr(
        command, "run",
        lambda manifest, cfg, **kw: observed.append((manifest, kw)) or VERIFIED_REPORT,
    )
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
        lambda manifest, cfg, **kwargs: observed.append((manifest, kwargs))
        or VERIFIED_REPORT,
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


@pytest.mark.parametrize("result,unverified", [
    (VERIFIED_REPORT, []),
    (UNVERIFIED_REPORT, [{"window": 2, "since": "2026-07-02", "until": "2026-07-03", "status": "failed",
                          "error_code": "classification_incomplete", "source_collection_job": "job-2"}]),
    ({"status": "incomplete", "windows": [VERIFIED_WINDOW]}, [{"status": "incomplete"}]),
    (PHASE_ROWS[:3], []),
    (PHASE_ROWS, [{"phase": "enrichment", "status": "failed", "error_code": "classification_incomplete",
                   "source_collection_job": "job-2"}]),
    (None, [{"status": "final_assessment_missing"}]),
])
def test_final_assessment_names_only_its_unverified_windows(result, unverified):
    from monitor.management.commands.run_backfill import unverified_windows

    assert unverified_windows(result) == unverified


def test_unverified_campaign_assessment_exits_3_after_its_receipts_are_saved(tmp_path, monkeypatch):
    import monitor.management.commands.run_backfill as command

    saved = []

    def run(frozen, cfg, **kw):
        # assess_campaign saves every window's receipt before returning its report.
        saved.extend(row["source_collection_job"] for row in UNVERIFIED_REPORT["windows"])
        return UNVERIFIED_REPORT

    monkeypatch.setattr(command, "run", run)
    with pytest.raises(CommandError, match="final assessment not verified") as failure:
        call_command("run_backfill", manifest=saved_campaign(tmp_path), execute=True, evaluate_at_end=True)
    assert failure.value.returncode == 3
    assert saved == ["job-1", "job-2"]
    message = str(failure.value)
    assert '"window": 2' in message and '"source_collection_job": "job-2"' in message
    assert "job-1" not in message and "CollectionRun.report['backfill_campaign']" in message


def test_unverified_phase_assessment_exits_3_after_verified_collection(tmp_path, monkeypatch):
    import monitor.management.commands.run_backfill as command

    seen = []
    monkeypatch.setattr(command, "run_phases", lambda frozen, cfg, **kw: seen.append(kw) or PHASE_ROWS)
    monkeypatch.setattr(command, "run", lambda *a, **kw: pytest.fail("legacy runner selected"))
    with pytest.raises(CommandError, match="final assessment not verified") as failure:
        call_command("run_backfill", manifest=saved_campaign(tmp_path), phase="all",
                     execute=True, evaluate_at_end=True)
    assert failure.value.returncode == 3
    assert len(seen) == 1 and seen[0]["phase"] == "all" and seen[0]["evaluate_at_end"] is True
    message = str(failure.value)
    assert '"phase": "enrichment"' in message and '"source_collection_job": "job-2"' in message
    assert "job-1" not in message and '"phase": "collection"' not in message


def test_unverified_final_assessment_is_a_failed_process_exit(tmp_path, monkeypatch):
    import monitor.management.commands.run_backfill as command

    monkeypatch.setattr(command, "run", lambda *a, **kw: UNVERIFIED_REPORT)
    stderr = StringIO()
    with pytest.raises(SystemExit) as exited:
        command.Command(stderr=stderr).run_from_argv([
            "manage.py", "run_backfill", "--manifest", str(saved_campaign(tmp_path)),
            "--execute", "--evaluate-at-end",
        ])
    assert exited.value.code == 3
    assert "final assessment not verified" in stderr.getvalue()


@pytest.mark.parametrize("runner,phase,result", [
    ("run", None, VERIFIED_REPORT),
    ("run_phases", "all", PHASE_ROWS[:3]),
])
def test_verified_final_assessment_exits_normally(tmp_path, monkeypatch, runner, phase, result):
    import monitor.management.commands.run_backfill as command

    seen = []
    monkeypatch.setattr(command, runner, lambda frozen, cfg, **kw: seen.append(kw) or result)
    call_command("run_backfill", manifest=saved_campaign(tmp_path), phase=phase,
                 execute=True, evaluate_at_end=True)
    assert len(seen) == 1 and seen[0]["evaluate_at_end"] is True


@pytest.mark.parametrize("runner,phase,result", [
    ("run", None, None),
    ("run", None, UNVERIFIED_REPORT),
    ("run_phases", "all", PHASE_ROWS),
    ("run_phases", "enrich", [{"phase": "enrichment", "status": "attempted"}]),
])
def test_without_evaluate_at_end_the_result_keeps_todays_exit(tmp_path, monkeypatch, runner, phase, result):
    import monitor.management.commands.run_backfill as command

    seen = []
    monkeypatch.setattr(command, runner, lambda frozen, cfg, **kw: seen.append(kw) or result)
    call_command("run_backfill", manifest=saved_campaign(tmp_path), phase=phase, execute=True)
    assert len(seen) == 1 and seen[0]["evaluate_at_end"] is False
