from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

import environ

from .config import ConfigError, load_project_config
from .database import (
    DatabaseGuardError,
    PostgresRefreshBackend,
    RefreshError,
    RefreshPipeline,
    safety_policy_from_config,
)
from .git import mutation_preflight
from .hosted_database import HostedStagingBootstrap
from .preview import (
    PreviewError,
    build_preview_plan,
    port_is_available,
    start_preview,
    stop_preview,
    tailscale_dns_name,
)
from .redaction import UnsafeOutputError, redact_text
from .results import CommandError, CommandResult, EvidenceRef, NextAction
from .state import CandidateIdentity, Receipt, ReceiptStore
from .status import build_doctor_result, build_status_result, collect_status_facts

_COACHING = """common prompts:
  what's next?          ollija status
  check my setup        ollija doctor
  refresh review data   ollija refresh-local
  refresh hosted data   ollija refresh-staging
  start work            ollija start
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
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Emit the versioned structured result envelope.",
        )
    return parser


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
    surface = hashlib.sha256(completed.stdout.encode()).hexdigest()
    return CandidateIdentity(
        sha=sha,
        package_version=facts.package_version,
        release_tag=f"unreleased-{sha[:12]}",
        surface_fingerprint=surface,
    )


def _preflight_mutation(command: str, facts) -> CommandResult | None:
    decision = mutation_preflight(facts.authority, facts.git, operation="stage")
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
    backend = PostgresRefreshBackend(
        config=config,
        source_database_url=source_url,
    )
    report = RefreshPipeline(
        backend=backend,
        policy=safety_policy_from_config(config),
    ).run()
    candidate = _candidate_identity(config, facts)
    receipt = Receipt.create(
        kind="refresh",
        candidate=candidate,
        created_at=datetime.now(UTC),
        payload=report.to_receipt_payload(),
    )
    store = ReceiptStore(
        config.root / config.state.directory,
        retention_days=config.state.retention_days,
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
    report = HostedStagingBootstrap(
        config=config,
        target_database_url=target_url,
        target_resource_id=resource_id,
    ).run()
    candidate = _candidate_identity(config, facts)
    receipt = Receipt.create(
        kind="refresh",
        candidate=candidate,
        created_at=datetime.now(UTC),
        payload=report.to_receipt_payload(),
    )
    store = ReceiptStore(
        config.root / config.state.directory,
        retention_days=config.state.retention_days,
    )
    store.write_receipt(receipt)
    store.set_reference("hosted_refresh", receipt.receipt_id)
    return CommandResult(
        command="refresh-staging",
        status="ok",
        state=facts.lifecycle_state,
        summary="Hosted staging received the scrubbed, validated local snapshot.",
        evidence=(EvidenceRef("refresh", receipt.receipt_id, candidate.sha),),
        details=report.to_receipt_payload(),
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
        facts = collect_status_facts(config, cwd=working_directory)
        if args.command == "status":
            result = build_status_result(facts)
        elif args.command == "doctor":
            result = build_doctor_result(facts)
        elif args.command == "refresh-local":
            result = _refresh_local(config, facts)
        elif args.command == "refresh-staging":
            result = _refresh_staging(config, facts)
        elif args.command == "preview":
            result = _preview(config, facts)
        else:
            result = _preview_stop(config, facts)
        emit_result(result, json_output=args.json_output, stream=output)
    except (ConfigError, UnsafeOutputError) as exc:
        result = _config_failure(args.command, exc)
        emit_result(result, json_output=args.json_output, stream=output)
    except (DatabaseGuardError, PreviewError, RefreshError) as exc:
        result = _mutation_failure(args.command, redact_text(str(exc)))
        emit_result(result, json_output=args.json_output, stream=output)

    return {"ok": 0, "blocked": 2, "failed": 1}[result.status]
