from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

import environ

from .approvals import (
    ApprovalError,
    bridgewright_evidence_receipt,
    owner_approval_receipt,
)
from .bridgewright import BridgewrightError, collect_bridgewright_evidence
from .agents.registry import AgentDriverError, driver_for
from .config import ConfigError, load_project_config
from .database import (
    DatabaseGuardError,
    PostgresRefreshBackend,
    RefreshError,
    RefreshPipeline,
    safety_policy_from_config,
)
from .git import SubprocessRunner, mutation_preflight
from .hosted_database import HostedStagingRefresh
from .impact import assess_ui_impact
from .preview import (
    PreviewError,
    build_preview_plan,
    port_is_available,
    start_preview,
    stop_preview,
    tailscale_dns_name,
)
from .processes import ProcessControlError
from .redaction import UnsafeOutputError, redact_text
from .release import (
    GitPublisher,
    ReleaseError,
    inspect_refresh_readiness,
    promote_candidate,
    stage_candidate,
    verify_and_tag_candidate,
)
from .render import RenderClient, RenderObservationError
from .results import CommandError, CommandResult, EvidenceRef, NextAction
from .state import CandidateIdentity, Receipt, ReceiptError, ReceiptStore
from .status import build_doctor_result, build_status_result, collect_status_facts
from .task_control import (
    GoRequest,
    TaskControlError,
    build_task_status_result,
    go_task,
    stop_task,
    task_command_result,
    with_task_status,
)
from .tasks import TaskError
from .verification import CdpBrowserProbe, PlaywrightBrowserProbe, VerificationError
from .versioning import VersionError, parse_beta_version
from .workspaces import WorkspaceError

_COACHING = """common prompts:
  what's next?          ollija status
  check my setup        ollija doctor
  refresh review data   ollija refresh-local
  refresh hosted data   ollija refresh-staging
  start bounded work    ollija go --help
  stop bounded work     ollija stop <task>
  inspect bounded work  ollija task-status [task]
  freeze beta candidate ollija start
  show local preview    ollija preview
  stop local preview    ollija preview-stop
  stage this            ollija stage
  record phone approval ollija approve iphone
  release next beta     ollija release
  verify production     ollija verify-production
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ollija",
        description="PushinWeight staging and release coach.",
        epilog=_COACHING,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("status", "Read live authorities and recommend exactly one next action."),
        ("doctor", "Check the authoritative host, tools, auth, Git, and databases."),
        ("refresh-local", "Refresh a guarded local production-derived snapshot."),
        ("refresh-staging", "Copy the active scrubbed snapshot to hosted staging."),
        ("preview", "Start the local PostgreSQL preview on private tailnet HTTPS."),
        ("preview-stop", "Stop only the scoped ollija preview process."),
        ("start", "Freeze the clean beta commit as the active candidate."),
        ("assess-ui", "Record clean Bridgewright assessment evidence."),
        ("stage", "Deploy the frozen candidate to isolated hosted staging."),
        ("release", "Fast-forward production to the approved candidate."),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Emit the versioned structured result envelope.",
        )
    verification = subparsers.add_parser(
        "verify-production",
        help="Verify every production service and the visible headline, then tag.",
    )
    verification.add_argument(
        "--browser-storage-state",
        type=Path,
        help="Ignored Playwright storage-state file for the owner's Google session.",
    )
    verification.add_argument(
        "--browser-cdp-url",
        help="Chrome DevTools Protocol URL for an authenticated remote browser.",
    )
    verification.add_argument("--json", action="store_true", dest="json_output")
    approval = subparsers.add_parser(
        "approve",
        help="Record an explicit owner review against the staged deployment.",
    )
    approval.add_argument("approval_kind", choices=("desktop", "iphone"))
    approval.add_argument("--json", action="store_true", dest="json_output")
    go = subparsers.add_parser(
        "go", help="Explicitly arm one bounded task generation on fuchitalee."
    )
    go.add_argument("--task", required=True)
    go.add_argument("--parent-task")
    go.add_argument("--source", required=True, type=Path)
    go.add_argument("--agent", required=True, choices=("codex", "claude"))
    go.add_argument("--endpoint", required=True, choices=("commit", "production"))
    go.add_argument(
        "--verify-argv",
        action="append",
        default=[],
        help='Repeat a JSON argv array, e.g. \'["pytest","tests/ollija"]\'.',
    )
    go.add_argument("--no-test-reason")
    go.add_argument("--json", action="store_true", dest="json_output")
    stop = subparsers.add_parser(
        "stop", help="Durably cancel one task before stopping its process tree."
    )
    stop.add_argument("task")
    stop.add_argument("--json", action="store_true", dest="json_output")
    task_status = subparsers.add_parser(
        "task-status", help="Read durable task state without extending authority."
    )
    task_status.add_argument("task", nargs="?")
    task_status.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _verification_argv(values: list[str]) -> tuple[tuple[str, ...], ...]:
    commands: list[tuple[str, ...]] = []
    for value in values:
        try:
            body = json.loads(value)
        except json.JSONDecodeError as exc:
            raise TaskControlError("verification_argv_invalid") from exc
        if not isinstance(body, list) or not body or not all(
            isinstance(item, str) and item for item in body
        ):
            raise TaskControlError("verification_argv_invalid")
        commands.append(tuple(body))
    return tuple(commands)


def render_human(result: CommandResult) -> str:
    lines = [
        f"ollija {redact_text(result.command)}: {redact_text(result.status)}",
        redact_text(result.summary),
        f"State: {redact_text(result.state)}",
    ]
    for warning in result.warnings:
        lines.append(f"Warning: {redact_text(warning)}")
    for error in result.errors:
        lines.append(f"Error [{error.code}]: {redact_text(error.message)}")
    if result.next_action:
        lines.append(
            "Next: "
            f"{redact_text(result.next_action.command)} — "
            f"{redact_text(result.next_action.reason)}"
        )
    return "\n".join(lines)


def emit_result(
    result: CommandResult,
    *,
    json_output: bool,
    stream: TextIO,
) -> None:
    if json_output:
        stream.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
    else:
        stream.write(render_human(result) + "\n")


def _config_failure(command: str, exc: Exception) -> CommandResult:
    return CommandResult(
        command=command,
        status="failed",
        state="blocked",
        summary="ollija could not load the project contract.",
        errors=(
            CommandError(
                code="project_contract_invalid",
                message=redact_text(str(exc)),
            ),
        ),
    )


def _load_local_environment(root: Path) -> None:
    path = root / ".env"
    if path.is_file():
        environ.Env.read_env(str(path), overwrite=False)


def _mutation_failure(command: str, code: str) -> CommandResult:
    return CommandResult(
        command=command,
        status="failed",
        state="blocked",
        summary=f"ollija {command} stopped before changing the active environment.",
        errors=(CommandError(code=code, message=code),),
        next_action=NextAction("ollija doctor", "Resolve the reported safety check."),
    )


def _candidate_identity(config, facts) -> CandidateIdentity:
    sha = facts.git.head_sha
    if not sha:
        raise RefreshError("candidate_sha_unavailable")
    beta = parse_beta_version(facts.package_version)
    impact = assess_ui_impact(config, _changed_paths(config))
    return CandidateIdentity(
        sha=sha,
        package_version=facts.package_version,
        release_tag=beta.release_tag,
        surface_fingerprint=impact.surface_fingerprint,
    )


def _active_candidate_for_refresh(
    config,
    facts,
) -> tuple[ReceiptStore, tuple[Receipt, ...], Receipt]:
    store = ReceiptStore(
        config.state_root,
        retention_days=config.state.retention_days,
    )
    candidate_id = store.read_reference("active_candidate")
    if not candidate_id:
        raise RefreshError("active_candidate_missing")
    receipts = store.iter_receipts()
    candidate = next(
        (
            receipt
            for receipt in receipts
            if receipt.kind == "candidate" and receipt.receipt_id == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise RefreshError("active_candidate_receipt_missing")
    if candidate.candidate != _candidate_identity(config, facts):
        raise RefreshError("active_candidate_identity_mismatch")
    return store, receipts, candidate


def _changed_paths(config) -> tuple[str, ...]:
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            f"origin/{config.git.production_branch}...HEAD",
        ],
        cwd=config.root,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise RefreshError("candidate_surface_unknown")
    return tuple(sorted(set(completed.stdout.splitlines())))


def _start_candidate(config, facts) -> CommandResult:
    blocked = _preflight_mutation("start", facts)
    if blocked:
        return blocked
    beta = parse_beta_version(facts.package_version)
    GitPublisher(config.root).assert_tag_absent(beta.release_tag)
    impact = assess_ui_impact(config, _changed_paths(config))
    if not facts.git.head_sha:
        raise VersionError("candidate_sha_unavailable")
    candidate = CandidateIdentity(
        sha=facts.git.head_sha,
        package_version=beta.package_version,
        release_tag=beta.release_tag,
        surface_fingerprint=impact.surface_fingerprint,
    )
    receipt = Receipt.create(
        kind="candidate",
        candidate=candidate,
        created_at=datetime.now(UTC),
        payload={
            "ui_required": impact.ui_required,
            "matched_paths": list(impact.matched_paths),
            "changed_paths": list(impact.changed_paths),
            "required_approvals": list(impact.required_approvals),
            "required_evidence": list(impact.required_evidence),
        },
    )
    store = ReceiptStore(
        config.state_root,
        retention_days=config.state.retention_days,
    )
    store.write_receipt(receipt)
    store.set_reference("active_candidate", receipt.receipt_id)
    return CommandResult(
        command="start",
        status="ok",
        state="candidate",
        summary=f"Candidate {candidate.release_tag} is frozen at the current commit.",
        evidence=(EvidenceRef("candidate", receipt.receipt_id, candidate.sha),),
        details={
            "package_version": candidate.package_version,
            "release_tag": candidate.release_tag,
            "ui_required": impact.ui_required,
            "required_approvals": list(impact.required_approvals),
            "required_evidence": list(impact.required_evidence),
        },
        next_action=NextAction(
            "ollija refresh-local",
            "Refresh data evidence for this exact candidate before staging.",
        ),
    )


def _active_candidate_and_stage(config) -> tuple[ReceiptStore, Receipt, Receipt]:
    store = ReceiptStore(
        config.state_root,
        retention_days=config.state.retention_days,
    )
    candidate_id = store.read_reference("active_candidate")
    if not candidate_id:
        raise ApprovalError("active_candidate_missing")
    receipts = store.iter_receipts()
    candidate_receipt = next(
        (
            receipt
            for receipt in receipts
            if receipt.kind == "candidate" and receipt.receipt_id == candidate_id
        ),
        None,
    )
    if candidate_receipt is None:
        raise ApprovalError("active_candidate_receipt_missing")
    stages = [
        receipt
        for receipt in receipts
        if receipt.kind == "staging_deploy"
        and receipt.candidate == candidate_receipt.candidate
        and receipt.payload.get("status") == "live"
        and receipt.payload.get("deployed_sha") == candidate_receipt.candidate.sha
    ]
    if not stages:
        raise ApprovalError("live_staging_receipt_missing")
    return store, candidate_receipt, max(stages, key=lambda receipt: receipt.created_at)


def _assess_ui(config, facts) -> CommandResult:
    blocked = _preflight_mutation("assess-ui", facts)
    if blocked:
        return blocked
    store, candidate_receipt, stage = _active_candidate_and_stage(config)
    evidence = collect_bridgewright_evidence(config)
    receipt = bridgewright_evidence_receipt(
        candidate=candidate_receipt.candidate,
        deployment_id=str(stage.payload["deployment_id"]),
        evidence=evidence,
        created_at=datetime.now(UTC),
    )
    store.write_receipt(receipt)
    return CommandResult(
        command="assess-ui",
        status="ok",
        state="staged",
        summary="Bridgewright recorded clean assessment evidence without approval authority.",
        evidence=(
            EvidenceRef(
                "bridgewright_evidence",
                receipt.receipt_id,
                candidate_receipt.candidate.sha,
            ),
        ),
        next_action=NextAction(
            "ollija approve desktop",
            "The owner must inspect this exact staged deployment.",
        ),
    )


def _approve(config, facts, approval_kind: str) -> CommandResult:
    blocked = _preflight_mutation("approve", facts)
    if blocked:
        return blocked
    store, candidate_receipt, stage = _active_candidate_and_stage(config)
    receipt = owner_approval_receipt(
        candidate=candidate_receipt.candidate,
        approval_kind=approval_kind,
        deployment_id=str(stage.payload["deployment_id"]),
        created_at=datetime.now(UTC),
    )
    store.write_receipt(receipt)
    next_command = (
        "ollija approve iphone" if approval_kind == "desktop" else "ollija status"
    )
    return CommandResult(
        command=f"approve {approval_kind}",
        status="ok",
        state="staged",
        summary=f"Owner {approval_kind} approval is bound to the staged candidate.",
        evidence=(
            EvidenceRef("approval", receipt.receipt_id, candidate_receipt.candidate.sha),
        ),
        next_action=NextAction(
            next_command,
            "Complete the remaining candidate-bound review evidence.",
        ),
    )


def _preflight_mutation(command: str, facts) -> CommandResult | None:
    operation = "release" if command in {"release", "verify-production"} else "stage"
    decision = mutation_preflight(facts.authority, facts.git, operation=operation)
    failing_checks = [check for check in facts.checks if check.status != "passed"]
    if decision.allowed and not failing_checks:
        return None
    reasons = list(decision.reason_codes)
    reasons.extend(f"{check.name}_{check.status}" for check in failing_checks)
    return CommandResult(
        command=command,
        status="blocked",
        state="blocked",
        summary=f"ollija {command} refused an unsafe or incomplete preflight.",
        errors=tuple(
            CommandError(code=reason, message=reason) for reason in dict.fromkeys(reasons)
        ),
        next_action=NextAction("ollija doctor", "Resolve preflight before retrying."),
    )


def _refresh_local(config, facts) -> CommandResult:
    blocked = _preflight_mutation("refresh-local", facts)
    if blocked:
        return blocked
    source_url = os.environ.get("OLLIJA_PROD_READONLY_DATABASE_URL", "")
    if not source_url:
        return _mutation_failure(
            "refresh-local",
            "production_readonly_database_url_missing",
        )
    store, _receipts, candidate_receipt = _active_candidate_for_refresh(
        config,
        facts,
    )
    backend = PostgresRefreshBackend(
        config=config,
        source_database_url=source_url,
    )
    report = RefreshPipeline(
        backend=backend,
        policy=safety_policy_from_config(config),
    ).run()
    candidate = candidate_receipt.candidate
    receipt = Receipt.create(
        kind="refresh",
        candidate=candidate,
        created_at=datetime.now(UTC),
        payload=report.to_receipt_payload(),
    )
    store.write_receipt(receipt)
    store.set_reference("active_refresh", receipt.receipt_id)
    return CommandResult(
        command="refresh-local",
        status="ok",
        state=facts.lifecycle_state,
        summary="Local staging data was restored, scrubbed, validated, and activated.",
        evidence=(
            EvidenceRef("refresh", receipt.receipt_id, candidate.sha),
            EvidenceRef("git_commit", candidate.sha, candidate.sha),
        ),
        details=report.to_receipt_payload(),
        next_action=NextAction("ollija preview", "Review the active local snapshot."),
    )


def _preview(config, facts) -> CommandResult:
    blocked = _preflight_mutation("preview", facts)
    if blocked:
        return blocked
    backend = PostgresRefreshBackend(
        config=config,
        source_database_url="postgresql:///unused",
    )
    database = backend.discover_active_local_database()
    database_url = f"postgresql:///{database.database}"
    plan = build_preview_plan(
        config,
        database_url=database_url,
        database=database,
        policy=safety_policy_from_config(config),
        port_available=port_is_available,
        tailscale_dns_name=tailscale_dns_name(),
    )
    runtime = start_preview(config, plan)
    return CommandResult(
        command="preview",
        status="ok",
        state=facts.lifecycle_state,
        summary="Local preview is running on loopback and private tailnet HTTPS.",
        details=runtime.to_dict(),
        next_action=NextAction(
            runtime.private_url,
            "Open this private URL on desktop Chrome or the physical iPhone.",
        ),
    )


def _refresh_staging(config, facts) -> CommandResult:
    blocked = _preflight_mutation("refresh-staging", facts)
    if blocked:
        return blocked
    target_url = os.environ.get("OLLIJA_STAGING_DATABASE_URL", "")
    staging = config.environments.get("staging", {})
    resource_id = staging.get("database_resource_id")
    if not target_url:
        return _mutation_failure("refresh-staging", "staging_database_url_missing")
    if not isinstance(resource_id, str) or not resource_id:
        return _mutation_failure(
            "refresh-staging",
            "staging_database_resource_identity_missing",
        )
    store, receipts, candidate_receipt = _active_candidate_for_refresh(
        config,
        facts,
    )
    readiness = inspect_refresh_readiness(
        config,
        store,
        receipts,
        candidate_receipt,
        now=datetime.now(UTC),
    )
    if readiness.local is None:
        raise RefreshError(readiness.error_code or "local_refresh_missing")
    report = HostedStagingRefresh(
        config=config,
        target_database_url=target_url,
        target_resource_id=resource_id,
    ).run()
    local = readiness.local
    if (
        report.source_database != local.payload.get("target_database")
        or report.source_resource_id != local.payload.get("target_resource_id")
        or dict(report.row_counts) != local.payload.get("row_counts")
    ):
        raise RefreshError("hosted_refresh_local_source_mismatch")
    candidate = candidate_receipt.candidate
    payload = {
        **report.to_receipt_payload(),
        "local_refresh_receipt_id": local.receipt_id,
    }
    receipt = Receipt.create(
        kind="refresh",
        candidate=candidate,
        created_at=datetime.now(UTC),
        payload=payload,
    )
    store.write_receipt(receipt)
    store.set_reference("hosted_refresh", receipt.receipt_id)
    return CommandResult(
        command="refresh-staging",
        status="ok",
        state=facts.lifecycle_state,
        summary="Hosted staging received the scrubbed, validated local snapshot.",
        evidence=(EvidenceRef("refresh", receipt.receipt_id, candidate.sha),),
        details=payload,
        next_action=NextAction(
            "ollija stage",
            "Deploy the exact candidate against the active hosted snapshot.",
        ),
    )


def _preview_stop(config, facts) -> CommandResult:
    blocked = _preflight_mutation("preview-stop", facts)
    if blocked:
        return blocked
    runtime = stop_preview(config)
    return CommandResult(
        command="preview-stop",
        status="ok",
        state=facts.lifecycle_state,
        summary="The scoped local preview and its Tailscale Serve route were stopped.",
        details=runtime.to_dict(),
        next_action=NextAction("ollija status", "Continue from live workflow state."),
    )


def _stage(config, facts) -> CommandResult:
    blocked = _preflight_mutation("stage", facts)
    if blocked:
        return blocked
    receipt = stage_candidate(
        config=config,
        git=facts.git,
        package_version=facts.package_version,
        render=RenderClient(root=config.root),
        publisher=GitPublisher(config.root),
        now=datetime.now(UTC),
    )
    return CommandResult(
        command="stage",
        status="ok",
        state="staged",
        summary="The exact candidate is live on isolated hosted staging.",
        evidence=(
            EvidenceRef("staging_deploy", receipt.receipt_id, receipt.candidate.sha),
        ),
        details={
            "deployment_id": receipt.payload.get("deployment_id"),
            "deployed_sha": receipt.payload.get("deployed_sha"),
            "status": receipt.payload.get("status"),
        },
        next_action=NextAction(
            "ollija assess-ui",
            "Collect assessment evidence before owner desktop and iPhone review.",
        ),
    )


def _release(config, facts) -> CommandResult:
    blocked = _preflight_mutation("release", facts)
    if blocked:
        return blocked
    evidence, last_known_good = promote_candidate(
        config=config,
        git=facts.git,
        package_version=facts.package_version,
        render=RenderClient(root=config.root),
        publisher=GitPublisher(config.root),
        now=datetime.now(UTC),
    )
    return CommandResult(
        command="release",
        status="ok",
        state="releasing",
        summary="Production main now points to the exact approved candidate.",
        evidence=(
            EvidenceRef(
                "candidate",
                evidence.candidate.receipt_id,
                evidence.candidate.candidate.sha,
            ),
            EvidenceRef(
                "last_known_good",
                last_known_good.receipt_id,
                evidence.candidate.candidate.sha,
            ),
        ),
        details={
            "deployed_sha": evidence.candidate.candidate.sha,
            "release_tag": evidence.candidate.candidate.release_tag,
        },
        next_action=NextAction(
            "ollija verify-production",
            "Wait for every Render resource and verify the visible headline before tagging.",
        ),
    )


def _verify_production(
    config,
    facts,
    storage_state: Path | None,
    browser_cdp_url: str | None,
) -> CommandResult:
    blocked = _preflight_mutation("verify-production", facts)
    if blocked:
        return blocked
    configured_env = config.verification.get("browser_storage_state_env")
    environment_path = (
        os.environ.get(configured_env, "")
        if isinstance(configured_env, str) and configured_env
        else ""
    )
    selected = storage_state or (Path(environment_path) if environment_path else None)
    cdp_env_name = config.verification.get("browser_cdp_url_env")
    configured_cdp = (
        os.environ.get(cdp_env_name, "")
        if isinstance(cdp_env_name, str) and cdp_env_name
        else ""
    )
    selected_cdp = browser_cdp_url or configured_cdp or None
    if selected is not None and selected_cdp is not None:
        return _mutation_failure(
            "verify-production",
            "production_browser_probe_selection_ambiguous",
        )
    if selected is None and selected_cdp is None:
        return _mutation_failure(
            "verify-production",
            "production_browser_storage_state_missing",
        )
    browser_probe = (
        CdpBrowserProbe(selected_cdp)
        if selected_cdp is not None
        else PlaywrightBrowserProbe(selected)
    )
    receipt, report = verify_and_tag_candidate(
        config=config,
        git=facts.git,
        package_version=facts.package_version,
        render=RenderClient(root=config.root),
        publisher=GitPublisher(config.root),
        browser_probe=browser_probe,
        now=datetime.now(UTC),
    )
    return CommandResult(
        command="verify-production",
        status="ok",
        state="verified",
        summary="The approved beta is live, visibly serving a headline, and tagged.",
        evidence=(
            EvidenceRef("production_deploy", receipt.receipt_id, receipt.candidate.sha),
        ),
        details={
            "deployment_id": receipt.payload.get("deployment_id"),
            "deployed_sha": receipt.candidate.sha,
            "release_tag": receipt.candidate.release_tag,
            "headline_visible": report.browser.visible,
            "headline_model": report.headline_model,
        },
        next_action=NextAction(
            "ollija status",
            "Confirm the sealed release state and begin the next change from staging.",
        ),
    )


def main(
    argv: list[str] | None = None,
    *,
    cwd: Path | None = None,
    stream: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stream or sys.stdout
    working_directory = (cwd or Path.cwd()).resolve()
    try:
        config = load_project_config(working_directory)
        _load_local_environment(config.root)
        if args.command == "task-status":
            result = build_task_status_result(config, task_id=args.task)
        else:
            facts = collect_status_facts(config, cwd=working_directory)
        if args.command == "status":
            result = with_task_status(build_status_result(facts), config)
        elif args.command == "doctor":
            result = build_doctor_result(facts)
        elif args.command == "go":
            origin_host = os.environ.get("OLLIJA_ORIGIN_HOST") or socket.gethostname()
            origin_terminal = (
                os.environ.get("OLLIJA_ORIGIN_TERMINAL")
                or os.environ.get("TERM_PROGRAM")
                or os.environ.get("SSH_TTY")
                or "unknown"
            )
            snapshot = go_task(
                config,
                facts,
                GoRequest(
                    task_id=args.task,
                    parent_task_id=args.parent_task,
                    source_path=args.source.as_posix(),
                    agent_kind=args.agent,
                    endpoint=args.endpoint,
                    verification_argv=_verification_argv(args.verify_argv),
                    no_test_reason=args.no_test_reason,
                ),
                runner=SubprocessRunner(),
                driver=driver_for(args.agent),
                origin_host=origin_host,
                origin_terminal=origin_terminal,
                execution_host=socket.gethostname(),
            )
            result = task_command_result("go", snapshot)
        elif args.command == "stop":
            result = task_command_result(
                f"stop {args.task}", stop_task(config, facts, args.task)
            )
        elif args.command == "task-status":
            pass
        elif args.command == "refresh-local":
            result = _refresh_local(config, facts)
        elif args.command == "refresh-staging":
            result = _refresh_staging(config, facts)
        elif args.command == "start":
            result = _start_candidate(config, facts)
        elif args.command == "assess-ui":
            result = _assess_ui(config, facts)
        elif args.command == "approve":
            result = _approve(config, facts, args.approval_kind)
        elif args.command == "stage":
            result = _stage(config, facts)
        elif args.command == "release":
            result = _release(config, facts)
        elif args.command == "verify-production":
            result = _verify_production(
                config,
                facts,
                args.browser_storage_state,
                args.browser_cdp_url,
            )
        elif args.command == "preview":
            result = _preview(config, facts)
        else:
            result = _preview_stop(config, facts)
        emit_result(result, json_output=args.json_output, stream=output)
    except (ConfigError, UnsafeOutputError) as exc:
        result = _config_failure(args.command, exc)
        emit_result(result, json_output=args.json_output, stream=output)
    except (
        ApprovalError,
        BridgewrightError,
        DatabaseGuardError,
        PreviewError,
        ProcessControlError,
        RefreshError,
        ReceiptError,
        ReleaseError,
        RenderObservationError,
        AgentDriverError,
        TaskControlError,
        TaskError,
        VerificationError,
        VersionError,
        WorkspaceError,
    ) as exc:
        result = _mutation_failure(args.command, redact_text(str(exc)))
        emit_result(result, json_output=args.json_output, stream=output)

    return {"ok": 0, "blocked": 2, "failed": 1}[result.status]
