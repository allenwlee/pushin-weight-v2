from __future__ import annotations

import io
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ollija.changes import ChangeLedgerError
from scripts.ollija.cli import (
    _refresh_local,
    _refresh_staging,
    _start_candidate,
    build_parser,
    emit_result,
    render_human,
)
from scripts.ollija.results import CommandResult, EvidenceRef, NextAction
from scripts.ollija.state import CandidateIdentity, Receipt, ReceiptStore
from tests.ollija.change_ledger_helpers import LEDGER_TEXT

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


def _result() -> CommandResult:
    return CommandResult(
        command="status",
        status="ok",
        state="candidate",
        summary="Candidate is ready to stage.",
        next_action=NextAction("ollija stage", "Deploy this exact candidate."),
        evidence=(EvidenceRef("git_commit", SHA, SHA),),
    )


def test_human_and_json_output_recommend_the_same_action() -> None:
    result = _result()
    human = render_human(result)
    stream = io.StringIO()

    emit_result(result, json_output=True, stream=stream)
    machine = json.loads(stream.getvalue())

    assert "Next: ollija stage" in human
    assert machine["next_action"]["command"] == "ollija stage"


def test_bin_wrapper_resolves_repo_from_root_and_nested_directory() -> None:
    for cwd in (REPO_ROOT, REPO_ROOT / "tests" / "ollija"):
        completed = subprocess.run(
            [str(REPO_ROOT / "bin" / "ollija"), "--help"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0
        assert "what's next" in completed.stdout.lower()


def test_human_output_redacts_synthetic_error() -> None:
    unsafe = (
        "failed "
        + "postgresql://operator:"
        + "live-value"
        + "@example.invalid/db"
    )
    result = CommandResult(
        command="doctor",
        status="failed",
        state="blocked",
        summary=unsafe,
    )

    rendered = render_human(result)

    assert "live-value" not in rendered
    assert "[REDACTED" in rendered


def test_task_commands_are_discoverable_and_verification_is_structured() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "go",
            "--task",
            "task-1",
            "--source",
            "docs/plans/task.md",
            "--agent",
            "codex",
            "--endpoint",
            "commit",
            "--verify-argv",
            '["pytest","tests/ollija"]',
        ]
    )
    stopped = parser.parse_args(["stop", "task-1"])
    observed = parser.parse_args(["task-status", "task-1", "--json"])
    overridden = parser.parse_args(
        [
            "override",
            "bridgewright",
            "--owner",
            "allenwlee",
            "--reason",
            "adapter defect",
        ]
    )

    assert args.command == "go"
    assert args.verify_argv == ['["pytest","tests/ollija"]']
    assert stopped.command == "stop"
    assert observed.command == "task-status"
    assert observed.json_output is True
    assert overridden.assessment_kind == "bridgewright"


def test_start_candidate_refuses_ollija_change_without_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("scripts.ollija.cli._preflight_mutation", lambda *_args: None)
    monkeypatch.setattr(
        "scripts.ollija.cli._changed_paths",
        lambda _config: ("scripts/ollija/cli.py",),
    )
    monkeypatch.setattr(
        "scripts.ollija.cli.load_change_ledger_baseline",
        lambda *_args, **_kwargs: "",
    )

    with pytest.raises(ChangeLedgerError, match="ollija_change_ledger_missing"):
        _start_candidate(
            type(
                "Config",
                (),
                {
                    "root": tmp_path,
                    "git": SimpleNamespace(production_branch="main"),
                },
            )(),
            object(),
        )


def _workflow_only_candidate() -> Receipt:
    identity = CandidateIdentity(
        sha=SHA,
        package_version="0.2.0b1",
        release_tag="v0.2.0-beta.1",
        surface_fingerprint="surface",
    )
    return Receipt.create(
        kind="candidate",
        candidate=identity,
        created_at=datetime.now(UTC),
        payload={"data_refresh_required": False},
    )


def test_start_candidate_records_workflow_only_refresh_exemption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = tmp_path / "docs" / "ollija" / "CHANGES.md"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(LEDGER_TEXT, encoding="utf-8")
    changed_paths = ("scripts/ollija/cli.py", "docs/ollija/CHANGES.md")
    monkeypatch.setattr("scripts.ollija.cli._preflight_mutation", lambda *_args: None)
    monkeypatch.setattr(
        "scripts.ollija.cli._changed_paths",
        lambda _config: changed_paths,
    )
    monkeypatch.setattr(
        "scripts.ollija.cli.load_change_ledger_baseline",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(
        "scripts.ollija.cli.GitPublisher.assert_tag_absent",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "scripts.ollija.cli.assess_ui_impact",
        lambda *_args: SimpleNamespace(
            surface_fingerprint="surface",
            ui_required=False,
            matched_paths=(),
            changed_paths=changed_paths,
            required_approvals=("desktop",),
            required_evidence=(),
        ),
    )
    config = SimpleNamespace(
        root=tmp_path,
        git=SimpleNamespace(production_branch="main"),
        state_root=tmp_path / ".ollija" / "state",
        state=SimpleNamespace(retention_days=30),
    )
    facts = SimpleNamespace(
        package_version="0.2.0b1",
        git=SimpleNamespace(head_sha=SHA),
    )

    result = _start_candidate(config, facts)

    assert result.details["data_refresh_required"] is False
    assert result.next_action is not None
    assert result.next_action.command == "ollija stage"
    receipts = ReceiptStore(config.state_root).iter_receipts()
    assert receipts[-1].payload["data_refresh_required"] is False


@pytest.mark.parametrize("refresh", (_refresh_local, _refresh_staging))
def test_workflow_only_refresh_command_never_requires_database_credentials(
    refresh, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _workflow_only_candidate()
    monkeypatch.setattr("scripts.ollija.cli._preflight_mutation", lambda *_args: None)
    monkeypatch.setattr(
        "scripts.ollija.cli._active_candidate",
        lambda *_args: (object(), candidate),
    )
    monkeypatch.delenv("OLLIJA_PROD_READONLY_DATABASE_URL", raising=False)
    monkeypatch.delenv("OLLIJA_STAGING_DATABASE_URL", raising=False)

    result = refresh(SimpleNamespace(), SimpleNamespace())

    assert result.status == "ok"
    assert result.state == "ready_to_stage"
    assert result.next_action is not None
    assert result.next_action.command == "ollija stage"
