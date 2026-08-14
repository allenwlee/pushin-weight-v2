from __future__ import annotations

import json
import os
import re
import shutil
import socket
import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .adapters.base import AuthorityObservation
from .adapters.pushinweight import PushinWeightAdapter
from .config import ProjectConfig
from .git import (
    CommandRunner,
    GitObservation,
    SubprocessRunner,
    mutation_preflight,
    observe_git,
)
from .redaction import redact_text
from .release import deployment_set_id
from .render import RenderClient, RenderDeployment, RenderObservationError
from .results import CommandResult, EvidenceRef, NextAction
from .state import (
    CandidateIdentity,
    LiveAuthorities,
    ReceiptError,
    ReceiptStore,
    evaluate_lifecycle,
)


@dataclass(frozen=True, slots=True)
class CheckObservation:
    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class StatusFacts:
    authority: AuthorityObservation
    git: GitObservation
    lifecycle_state: str
    package_version: str
    checks: tuple[CheckObservation, ...]
    receipt_warnings: tuple[str, ...] = ()


_NEXT_ACTIONS = {
    "idle": NextAction("ollija start", "Select the clean commit as a candidate."),
    "candidate": NextAction("ollija stage", "Deploy this exact candidate to staging."),
    "staged": NextAction(
        "ollija approve desktop", "Review the staged candidate in desktop Chrome."
    ),
    "approved": NextAction("ollija release", "Promote the approved candidate."),
    "releasing": NextAction(
        "ollija verify-production", "Wait for and verify the production service set."
    ),
    "verified": NextAction("ollija status", "No release transition is pending."),
}


def _version_tuple(value: str) -> tuple[int, ...] | None:
    match = re.search(r"(?<!\d)(\d+(?:\.\d+){1,3})", value)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _json_path(body: object, path: str) -> object:
    value = body
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def _resolve_executable(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if "/" in value:
        path = Path(value).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(value)


def probe_tool(
    name: str,
    specification: Mapping[str, Any],
    runner: CommandRunner,
    *,
    cwd: Path,
) -> CheckObservation:
    executable = _resolve_executable(specification.get("executable"))
    if executable is None:
        return CheckObservation(name, "missing", "executable not found")

    version_args = specification.get("version_args", [])
    if not isinstance(version_args, list) or not all(
        isinstance(item, str) for item in version_args
    ):
        return CheckObservation(name, "incompatible", "invalid version probe")

    version = None
    if version_args:
        outcome = runner.run((executable, *version_args), cwd=cwd)
        if outcome.returncode != 0:
            return CheckObservation(name, "unreachable", "version probe failed")
        output = outcome.stdout or outcome.stderr
        json_path = specification.get("version_json_path")
        if isinstance(json_path, str):
            try:
                version = str(_json_path(json.loads(output), json_path))
            except (json.JSONDecodeError, KeyError, TypeError):
                return CheckObservation(name, "incompatible", "version output invalid")
        else:
            parsed = _version_tuple(output)
            version = ".".join(str(part) for part in parsed) if parsed else None

    minimum = specification.get("minimum_version")
    if isinstance(minimum, str):
        actual_version = _version_tuple(version or "")
        minimum_version = _version_tuple(minimum)
        if actual_version is None or minimum_version is None:
            return CheckObservation(name, "incompatible", "version unavailable")
        width = max(len(actual_version), len(minimum_version))
        actual_version += (0,) * (width - len(actual_version))
        minimum_version += (0,) * (width - len(minimum_version))
        if actual_version < minimum_version:
            return CheckObservation(
                name,
                "incompatible",
                f"version {version} is below required {minimum}",
            )

    probe_args = specification.get("probe_args", [])
    if probe_args:
        if not isinstance(probe_args, list) or not all(
            isinstance(item, str) for item in probe_args
        ):
            return CheckObservation(name, "incompatible", "invalid reachability probe")
        outcome = runner.run((executable, *probe_args), cwd=cwd)
        if outcome.returncode != 0:
            return CheckObservation(name, "unreachable", "authentication probe failed")
        expected_path = specification.get("probe_json_path")
        if isinstance(expected_path, str):
            try:
                actual = _json_path(json.loads(outcome.stdout), expected_path)
            except (json.JSONDecodeError, KeyError, TypeError):
                return CheckObservation(name, "unreachable", "probe output invalid")
            if actual != specification.get("probe_json_equals"):
                return CheckObservation(name, "unreachable", "probe state is not ready")

    detail = f"version {version}" if version else "available"
    return CheckObservation(name, "passed", detail)


def _read_package_version(config: ProjectConfig) -> str:
    source = config.versioning.get("source")
    field = config.versioning.get("field")
    if not isinstance(source, str) or not isinstance(field, str):
        return "unknown"
    try:
        value: object = tomllib.loads(
            (config.root / source).read_text(encoding="utf-8")
        )
        for part in field.split("."):
            if not isinstance(value, Mapping):
                return "unknown"
            value = value.get(part)
        return str(value) if value is not None else "unknown"
    except (OSError, tomllib.TOMLDecodeError):
        return "unknown"


def _local_database_check(
    config: ProjectConfig,
    runner: CommandRunner,
    *,
    cwd: Path,
) -> CheckObservation:
    local = config.environments.get("local", {})
    database_name = local.get("database_name") if isinstance(local, Mapping) else None
    production_names = config.database_safety.get("production_database_names", [])
    if not isinstance(database_name, str):
        return CheckObservation("local_database", "incompatible", "name not configured")
    if database_name in production_names:
        return CheckObservation(
            "local_database", "blocked", "configured name matches production"
        )

    psql = config.tooling.get("psql", {})
    executable = (
        _resolve_executable(psql.get("executable")) if isinstance(psql, Mapping) else None
    )
    if executable is None:
        return CheckObservation("local_database", "missing", "psql not found")
    outcome = runner.run(
        (executable, "--list", "--tuples-only", "--no-align"),
        cwd=cwd,
    )
    if outcome.returncode != 0:
        return CheckObservation("local_database", "unreachable", "catalog probe failed")
    names = {line.split("|", 1)[0].strip() for line in outcome.stdout.splitlines()}
    if database_name not in names:
        return CheckObservation(
            "local_database", "missing", f"{database_name} is not initialized"
        )
    return CheckObservation("local_database", "passed", database_name)


def _repository_hygiene_check(
    config: ProjectConfig, runner: CommandRunner
) -> CheckObservation:
    outcome = runner.run(
        ("git", "ls-files", ".env", "data/django_dev.db"),
        cwd=config.root,
    )
    if outcome.returncode != 0:
        return CheckObservation("repository_hygiene", "unreachable", "git probe failed")
    if outcome.stdout.strip():
        return CheckObservation(
            "repository_hygiene", "blocked", "runtime secrets or database are tracked"
        )
    return CheckObservation("repository_hygiene", "passed", "runtime files untracked")


def _tool_checks(
    config: ProjectConfig,
    runner: CommandRunner,
) -> tuple[CheckObservation, ...]:
    checks: list[CheckObservation] = []
    for name, specification in config.tooling.items():
        if not isinstance(specification, Mapping):
            checks.append(CheckObservation(str(name), "incompatible", "invalid config"))
            continue
        checks.append(probe_tool(str(name), specification, runner, cwd=config.root))
    checks.append(_local_database_check(config, runner, cwd=config.root))
    checks.append(_repository_hygiene_check(config, runner))
    return tuple(checks)


def _receipt_state(
    config: ProjectConfig,
    git: GitObservation,
    runner: CommandRunner,
) -> tuple[str, tuple[str, ...]]:
    store = ReceiptStore(
        config.root / config.state.directory,
        retention_days=config.state.retention_days,
    )
    if not store.root.exists():
        return "idle", ()

    try:
        receipts = store.iter_receipts()
        active_id = store.read_reference("active_candidate")
        candidate_receipt = next(
            (
                receipt
                for receipt in receipts
                if receipt.kind == "candidate" and receipt.receipt_id == active_id
            ),
            None,
        )
        active = candidate_receipt.candidate if candidate_receipt else None
        if active is not None and active.sha != git.head_sha:
            active = None
        live = LiveAuthorities(candidate=active)
        live_warnings: tuple[str, ...] = ()
        if active is not None and candidate_receipt is not None:
            required_approvals = tuple(
                item
                for item in candidate_receipt.payload.get("required_approvals", ())
                if isinstance(item, str)
            )
            required_evidence = tuple(
                item
                for item in candidate_receipt.payload.get("required_evidence", ())
                if isinstance(item, str)
            )
            live, live_warnings = _observe_live_authorities(
                config,
                runner,
                active=active,
                required_approvals=required_approvals,
                required_evidence=required_evidence,
            )
        evaluation = evaluate_lifecycle(receipts, live)
        warnings = live_warnings + tuple(
            f"stale receipt: {receipt_id}"
            for receipt_id in evaluation.stale_receipt_ids
        )
        return evaluation.state, warnings
    except ReceiptError as exc:
        return "idle", (redact_text(str(exc)),)


def _observe_live_authorities(
    config: ProjectConfig,
    runner: CommandRunner,
    *,
    active: CandidateIdentity,
    required_approvals: tuple[str, ...],
    required_evidence: tuple[str, ...],
) -> tuple[LiveAuthorities, tuple[str, ...]]:
    client = RenderClient(root=config.root, runner=runner)
    warnings: list[str] = []
    staging_id = None
    staging_sha = None
    staging_status = None
    staging = config.environments.get("staging")
    if isinstance(staging, Mapping):
        configured_id = staging.get("web_service_id")
        if isinstance(configured_id, str) and configured_id:
            try:
                observed = client.current_deployment(configured_id)
                staging_id = observed.deployment_id
                staging_sha = observed.commit_sha
                staging_status = observed.status
            except RenderObservationError:
                warnings.append("staging_render_state_unavailable")

    production_id = None
    production_sha = None
    production_status = None
    production = config.environments.get("production")
    services = production.get("deploy_services") if isinstance(production, Mapping) else None
    if isinstance(services, list) and services:
        deployments: list[RenderDeployment] = []
        try:
            for service in services:
                if not isinstance(service, Mapping) or not isinstance(
                    service.get("id"), str
                ):
                    raise RenderObservationError("production_service_set_invalid")
                deployments.append(client.current_deployment(str(service["id"])))
        except RenderObservationError:
            warnings.append("production_render_state_unavailable")
        if deployments and len(deployments) == len(services):
            production_id = deployment_set_id(deployments)
            shas = {item.commit_sha for item in deployments}
            statuses = {item.status for item in deployments}
            production_sha = next(iter(shas)) if len(shas) == 1 else "mixed"
            if statuses == {"live"}:
                production_status = "live"
            elif statuses & {
                "build_in_progress",
                "pre_deploy_in_progress",
                "update_in_progress",
            }:
                production_status = "update_in_progress"
            else:
                production_status = "failed"

    return (
        LiveAuthorities(
            candidate=active,
            staging_deployment_id=staging_id,
            staging_deployed_sha=staging_sha,
            staging_status=staging_status,
            production_deployment_id=production_id,
            production_deployed_sha=production_sha,
            production_status=production_status,
            required_approvals=required_approvals,
            required_evidence=required_evidence,
        ),
        tuple(warnings),
    )


def collect_status_facts(
    config: ProjectConfig,
    *,
    cwd: Path,
    runner: CommandRunner | None = None,
) -> StatusFacts:
    active_runner = runner or SubprocessRunner()
    git = observe_git(config, cwd=cwd, runner=active_runner)
    authority = PushinWeightAdapter(config).assess_authority(
        hostname=socket.gethostname(),
        repository_root=git.repository_root,
        repository_slug=git.repository_slug,
    )
    if not authority.mutation_allowed:
        return StatusFacts(
            authority=authority,
            git=git,
            lifecycle_state="idle",
            package_version=_read_package_version(config),
            checks=(),
        )

    lifecycle_state, receipt_warnings = _receipt_state(config, git, active_runner)
    return StatusFacts(
        authority=authority,
        git=git,
        lifecycle_state=lifecycle_state,
        package_version=_read_package_version(config),
        checks=_tool_checks(config, active_runner),
        receipt_warnings=receipt_warnings,
    )


def build_status_result(facts: StatusFacts) -> CommandResult:
    decision = mutation_preflight(facts.authority, facts.git, operation="stage")
    checks = [asdict(check) for check in facts.checks]
    warnings = list(facts.receipt_warnings)
    warnings.extend(
        f"{check.name}: {check.status} ({check.detail})"
        for check in facts.checks
        if check.status != "passed"
    )

    evidence = ()
    if facts.git.head_sha:
        evidence = (
            EvidenceRef("git_commit", facts.git.head_sha, facts.git.head_sha),
        )

    if not decision.allowed:
        authority_failure = any(
            reason in {"forbidden_host", "host_mismatch", "repository_root_mismatch"}
            for reason in decision.reason_codes
        )
        next_action = NextAction(
            "ssh fuchitalee" if authority_failure else "ollija doctor",
            "Return to the authoritative checkout."
            if authority_failure
            else "Resolve the repository safety checks before continuing.",
        )
        return CommandResult(
            command="status",
            status="blocked",
            state="blocked",
            summary="ollija cannot safely mutate from the current repository state.",
            next_action=next_action,
            evidence=evidence,
            warnings=tuple(warnings),
            details={
                "reason_codes": list(decision.reason_codes),
                "checks": checks,
                "git": _git_details(facts.git),
                "package_version": facts.package_version,
            },
        )

    return CommandResult(
        command="status",
        status="ok",
        state=facts.lifecycle_state,
        summary=f"ollija is {facts.lifecycle_state} at the current commit.",
        next_action=_NEXT_ACTIONS[facts.lifecycle_state],
        evidence=evidence,
        warnings=tuple(warnings),
        details={
            "checks": checks,
            "git": _git_details(facts.git),
            "package_version": facts.package_version,
        },
    )


def _git_details(git: GitObservation) -> dict[str, Any]:
    return {
        "head_sha": git.head_sha,
        "branch": git.branch,
        "detached": git.detached,
        "registered_worktree": git.registered_worktree,
        "dirty_paths": list(git.dirty_paths),
        "production_sha": git.production_sha,
        "staging_sha": git.staging_sha,
        "branch_relationship": git.branch_relationship,
        "remote_reachable": git.remote_reachable,
    }


def build_doctor_result(facts: StatusFacts) -> CommandResult:
    status_result = build_status_result(facts)
    failing = [check for check in facts.checks if check.status != "passed"]
    if status_result.status == "blocked" or failing:
        return CommandResult(
            command="doctor",
            status="blocked",
            state="blocked",
            summary="ollija doctor found checks that require attention.",
            next_action=NextAction(
                "ollija doctor", "Re-run after resolving the reported checks."
            ),
            evidence=status_result.evidence,
            warnings=status_result.warnings,
            details=status_result.details,
        )
    return CommandResult(
        command="doctor",
        status="ok",
        state=facts.lifecycle_state,
        summary="ollija doctor passed all required checks.",
        next_action=status_result.next_action,
        evidence=status_result.evidence,
        details=status_result.details,
    )
