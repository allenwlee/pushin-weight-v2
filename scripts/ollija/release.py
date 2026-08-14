from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import ProjectConfig
from .git import GitObservation
from .render import RenderClient, RenderDeployment
from .state import (
    LiveAuthorities,
    Receipt,
    ReceiptError,
    ReceiptStore,
    evaluate_lifecycle,
)
from .verification import BrowserProbe, ProductionVerification, verify_production


class ReleaseError(ValueError):
    """A stage or release mutation failed a candidate-bound safety gate."""


@dataclass(frozen=True, slots=True)
class ReleaseEvidence:
    candidate: Receipt
    local_refresh: Receipt
    hosted_refresh: Receipt
    staging_deploy: Receipt | None = None
    approvals: tuple[Receipt, ...] = ()
    bridgewright_evidence: tuple[Receipt, ...] = ()


def deployment_set_id(deployments: Sequence[RenderDeployment]) -> str:
    body = [
        {
            "resource_id": item.resource_id,
            "deployment_id": item.deployment_id,
            "commit_sha": item.commit_sha,
            "status": item.status,
        }
        for item in sorted(deployments, key=lambda value: value.resource_id)
    ]
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class GitPublisher:
    """Apply only exact, server-enforced fast-forward ref updates."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _run(self, *args: str, timeout: int = 60) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReleaseError("git_operation_unavailable") from exc
        if completed.returncode != 0:
            raise ReleaseError("git_operation_rejected")
        return completed.stdout

    def _try(self, *args: str, timeout: int = 60) -> tuple[int, str]:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReleaseError("git_operation_unavailable") from exc
        return completed.returncode, completed.stdout

    def push_exact(self, *, sha: str, branch: str) -> None:
        self._run(
            "push",
            "origin",
            f"{sha}:refs/heads/{branch}",
            timeout=120,
        )
        observed = self._run("ls-remote", "--heads", "origin", branch)
        fields = observed.split()
        if len(fields) != 2 or fields[0] != sha:
            raise ReleaseError("git_remote_ref_identity_mismatch")

    def tag_and_push(self, *, sha: str, tag: str) -> None:
        returncode, local = self._try(
            "rev-parse", "--verify", "--quiet", f"{tag}^{{}}"
        )
        local_target = local.strip()
        if returncode == 0:
            if local_target != sha:
                raise ReleaseError("release_tag_target_mismatch")
        elif returncode == 1:
            self._run(
                "tag",
                "--annotate",
                tag,
                sha,
                "--message",
                f"PushinWeight {tag}",
            )
        else:
            raise ReleaseError("release_tag_lookup_failed")

        remote = self._run(
            "ls-remote",
            "--tags",
            "origin",
            f"refs/tags/{tag}",
            f"refs/tags/{tag}^{{}}",
        )
        targets = {
            fields[1]: fields[0]
            for line in remote.splitlines()
            if len(fields := line.split()) == 2
        }
        dereferenced = targets.get(f"refs/tags/{tag}^{{}}")
        if dereferenced:
            if dereferenced != sha:
                raise ReleaseError("release_tag_target_mismatch")
            return
        if targets:
            raise ReleaseError("release_tag_remote_ambiguous")
        self._run("push", "origin", f"refs/tags/{tag}", timeout=120)


def _store(config: ProjectConfig) -> ReceiptStore:
    return ReceiptStore(
        config.root / config.state.directory,
        retention_days=config.state.retention_days,
    )


def _referenced_receipt(
    store: ReceiptStore,
    receipts: Sequence[Receipt],
    *,
    reference: str,
    kind: str,
) -> Receipt:
    receipt_id = store.read_reference(reference)
    if not receipt_id:
        raise ReleaseError(f"{reference}_missing")
    receipt = next(
        (
            item
            for item in receipts
            if item.kind == kind and item.receipt_id == receipt_id
        ),
        None,
    )
    if receipt is None:
        raise ReleaseError(f"{reference}_receipt_missing")
    return receipt


def _active_candidate(
    store: ReceiptStore,
    receipts: Sequence[Receipt],
    *,
    git: GitObservation,
    package_version: str,
) -> Receipt:
    candidate = _referenced_receipt(
        store,
        receipts,
        reference="active_candidate",
        kind="candidate",
    )
    if git.head_sha != candidate.candidate.sha:
        raise ReleaseError("candidate_head_sha_mismatch")
    if package_version != candidate.candidate.package_version:
        raise ReleaseError("candidate_package_version_mismatch")
    if git.dirty_paths:
        raise ReleaseError("candidate_tree_dirty")
    return candidate


def _require_refreshes(
    config: ProjectConfig,
    store: ReceiptStore,
    receipts: Sequence[Receipt],
    candidate: Receipt,
    *,
    now: datetime,
) -> tuple[Receipt, Receipt]:
    local = _referenced_receipt(
        store,
        receipts,
        reference="active_refresh",
        kind="refresh",
    )
    hosted = _referenced_receipt(
        store,
        receipts,
        reference="hosted_refresh",
        kind="refresh",
    )
    if local.candidate != candidate.candidate or hosted.candidate != candidate.candidate:
        raise ReleaseError("refresh_candidate_stale")
    max_age_seconds = config.verification.get("refresh_max_age_seconds", 86_400)
    if not isinstance(max_age_seconds, int) or max_age_seconds < 1:
        raise ReleaseError("refresh_age_policy_invalid")
    threshold = now.astimezone(UTC) - timedelta(seconds=max_age_seconds)
    if local.created_at < threshold or hosted.created_at < threshold:
        raise ReleaseError("refresh_evidence_expired")
    if local.payload.get("target_marker_status") != "active":
        raise ReleaseError("local_refresh_not_active")
    if local.payload.get("raw_artifact_removed") is not True:
        raise ReleaseError("local_refresh_artifact_retained")
    if local.payload.get("database_affecting") is True and (
        local.payload.get("live_code_compatible") is not True
        or not local.payload.get("recovery_posture")
    ):
        raise ReleaseError("database_recovery_posture_unproven")

    staging = config.environments.get("staging")
    resource_id = staging.get("database_resource_id") if isinstance(staging, Mapping) else None
    if not isinstance(resource_id, str) or not resource_id:
        raise ReleaseError("staging_database_resource_identity_missing")
    if hosted.payload.get("target_resource_id") != resource_id:
        raise ReleaseError("hosted_refresh_resource_mismatch")
    if hosted.payload.get("target_marker_status") != "active":
        raise ReleaseError("hosted_refresh_not_active")
    if hosted.payload.get("raw_artifact_removed") is not True:
        raise ReleaseError("hosted_refresh_artifact_retained")
    return local, hosted


def _staging_specification(config: ProjectConfig) -> tuple[str, str]:
    staging = config.environments.get("staging")
    if not isinstance(staging, Mapping):
        raise ReleaseError("staging_environment_invalid")
    service_id = staging.get("web_service_id")
    service_name = staging.get("web_service_name")
    if not isinstance(service_id, str) or not service_id:
        raise ReleaseError("staging_web_service_identity_missing")
    if not isinstance(service_name, str) or not service_name:
        raise ReleaseError("staging_web_service_name_missing")
    return service_id, service_name


def _timing(config: ProjectConfig) -> tuple[int, float]:
    timeout = config.verification.get("deploy_timeout_seconds", 1_800)
    interval = config.verification.get("poll_interval_seconds", 10)
    if not isinstance(timeout, int) or timeout < 1:
        raise ReleaseError("deploy_timeout_invalid")
    if not isinstance(interval, (int, float)) or interval <= 0:
        raise ReleaseError("deploy_poll_interval_invalid")
    return timeout, float(interval)


def stage_candidate(
    *,
    config: ProjectConfig,
    git: GitObservation,
    package_version: str,
    render: RenderClient,
    publisher: GitPublisher,
    now: datetime,
) -> Receipt:
    store = _store(config)
    receipts = store.iter_receipts()
    candidate = _active_candidate(
        store,
        receipts,
        git=git,
        package_version=package_version,
    )
    local_refresh, hosted_refresh = _require_refreshes(
        config,
        store,
        receipts,
        candidate,
        now=now,
    )
    service_id, service_name = _staging_specification(config)
    render.require_resource(
        resource_id=service_id,
        name=service_name,
        kind="web",
        branch=config.git.staging_branch,
        repository_slug=config.authority.repository_slug,
    )
    publisher.push_exact(
        sha=candidate.candidate.sha,
        branch=config.git.staging_branch,
    )
    timeout, interval = _timing(config)
    deployment = render.wait_for_exact_deployment(
        resource_id=service_id,
        candidate_sha=candidate.candidate.sha,
        timeout_seconds=timeout,
        poll_interval_seconds=interval,
    )
    receipt = Receipt.create(
        kind="staging_deploy",
        candidate=candidate.candidate,
        created_at=now,
        payload={
            **deployment.to_receipt_payload(),
            "environment": "staging",
            "local_refresh_receipt_id": local_refresh.receipt_id,
            "hosted_refresh_receipt_id": hosted_refresh.receipt_id,
        },
    )
    store.write_receipt(receipt)
    store.set_reference("active_staging", receipt.receipt_id)
    return receipt


def require_release_readiness(
    *,
    config: ProjectConfig,
    git: GitObservation,
    package_version: str,
    staging_live: RenderDeployment,
    now: datetime,
) -> ReleaseEvidence:
    store = _store(config)
    receipts = store.iter_receipts()
    candidate = _active_candidate(
        store,
        receipts,
        git=git,
        package_version=package_version,
    )
    if git.staging_sha != candidate.candidate.sha:
        raise ReleaseError("staging_branch_candidate_mismatch")
    if git.production_sha == candidate.candidate.sha:
        pass
    elif git.branch_relationship != "staging_ahead":
        raise ReleaseError("production_fast_forward_unproven")

    local_refresh, hosted_refresh = _require_refreshes(
        config,
        store,
        receipts,
        candidate,
        now=now,
    )
    stage = _referenced_receipt(
        store,
        receipts,
        reference="active_staging",
        kind="staging_deploy",
    )
    if stage.candidate != candidate.candidate:
        raise ReleaseError("staging_receipt_candidate_stale")
    if stage.payload.get("deployment_id") != staging_live.deployment_id:
        raise ReleaseError("staging_deployment_replaced")
    if staging_live.commit_sha != candidate.candidate.sha or staging_live.status != "live":
        raise ReleaseError("staging_deployment_not_exact_live_sha")

    required_approvals = tuple(candidate.payload.get("required_approvals", ()))
    required_evidence = tuple(candidate.payload.get("required_evidence", ()))
    if not all(isinstance(item, str) for item in required_approvals):
        raise ReleaseError("candidate_approval_policy_invalid")
    if not all(isinstance(item, str) for item in required_evidence):
        raise ReleaseError("candidate_evidence_policy_invalid")
    evaluation = evaluate_lifecycle(
        receipts,
        LiveAuthorities(
            candidate=candidate.candidate,
            staging_deployment_id=staging_live.deployment_id,
            staging_deployed_sha=staging_live.commit_sha,
            staging_status=staging_live.status,
            required_approvals=required_approvals,
            required_evidence=required_evidence,
        ),
    )
    if evaluation.state not in {"approved", "verified"}:
        raise ReleaseError("candidate_approvals_incomplete")
    approvals = tuple(
        item
        for item in receipts
        if item.kind == "approval"
        and item.candidate == candidate.candidate
        and item.payload.get("deployment_id") == staging_live.deployment_id
        and item.payload.get("approved") is True
    )
    evidence = tuple(
        item
        for item in receipts
        if item.kind == "bridgewright_evidence"
        and item.candidate == candidate.candidate
        and item.payload.get("deployment_id") == staging_live.deployment_id
        and item.payload.get("status") == "clean"
    )
    return ReleaseEvidence(
        candidate=candidate,
        local_refresh=local_refresh,
        hosted_refresh=hosted_refresh,
        staging_deploy=stage,
        approvals=approvals,
        bridgewright_evidence=evidence,
    )


def _production_specifications(
    config: ProjectConfig,
) -> tuple[tuple[str, str, str], ...]:
    production = config.environments.get("production")
    services = production.get("deploy_services") if isinstance(production, Mapping) else None
    if not isinstance(services, list) or not services:
        raise ReleaseError("production_service_set_invalid")
    result: list[tuple[str, str, str]] = []
    for item in services:
        if not isinstance(item, Mapping):
            raise ReleaseError("production_service_set_invalid")
        values = (item.get("id"), item.get("name"), item.get("kind"))
        if not all(isinstance(value, str) and value for value in values):
            raise ReleaseError("production_service_identity_invalid")
        result.append((str(values[0]), str(values[1]), str(values[2])))
    return tuple(result)


def observe_production_service_set(
    *,
    config: ProjectConfig,
    render: RenderClient,
    wait_for_sha: str | None = None,
) -> tuple[RenderDeployment, ...]:
    timeout, interval = _timing(config)
    deployments: list[RenderDeployment] = []
    for resource_id, name, kind in _production_specifications(config):
        render.require_resource(
            resource_id=resource_id,
            name=name,
            kind=kind,
            branch=config.git.production_branch,
            repository_slug=config.authority.repository_slug,
        )
        if wait_for_sha:
            deployment = render.wait_for_exact_deployment(
                resource_id=resource_id,
                candidate_sha=wait_for_sha,
                timeout_seconds=timeout,
                poll_interval_seconds=interval,
            )
        else:
            deployment = render.current_deployment(resource_id)
        deployments.append(deployment)
    return tuple(deployments)


def promote_candidate(
    *,
    config: ProjectConfig,
    git: GitObservation,
    package_version: str,
    render: RenderClient,
    publisher: GitPublisher,
    now: datetime,
) -> tuple[ReleaseEvidence, Receipt]:
    service_id, service_name = _staging_specification(config)
    render.require_resource(
        resource_id=service_id,
        name=service_name,
        kind="web",
        branch=config.git.staging_branch,
        repository_slug=config.authority.repository_slug,
    )
    staging_live = render.current_deployment(service_id)
    evidence = require_release_readiness(
        config=config,
        git=git,
        package_version=package_version,
        staging_live=staging_live,
        now=now,
    )
    current = observe_production_service_set(config=config, render=render)
    if any(item.status != "live" for item in current):
        raise ReleaseError("production_last_known_good_not_live")
    current_shas = {item.commit_sha for item in current}
    if len(current_shas) != 1:
        raise ReleaseError("production_last_known_good_mixed_sha")
    prior_sha = next(iter(current_shas))
    if git.production_sha and prior_sha != git.production_sha:
        raise ReleaseError("production_deploy_git_identity_mismatch")

    store = _store(config)
    last_known_good = Receipt.create(
        kind="last_known_good",
        candidate=evidence.candidate.candidate,
        created_at=now,
        payload={
            "service_set_id": deployment_set_id(current),
            "deployed_sha": prior_sha,
            "deployments": [item.to_receipt_payload() for item in current],
        },
    )
    store.write_receipt(last_known_good)
    store.set_reference("pre_release_last_known_good", last_known_good.receipt_id)
    publisher.push_exact(
        sha=evidence.candidate.candidate.sha,
        branch=config.git.production_branch,
    )
    return evidence, last_known_good


def verify_and_tag_candidate(
    *,
    config: ProjectConfig,
    git: GitObservation,
    package_version: str,
    render: RenderClient,
    publisher: GitPublisher,
    browser_probe: BrowserProbe,
    now: datetime,
) -> tuple[Receipt, ProductionVerification]:
    store = _store(config)
    receipts = store.iter_receipts()
    candidate = _active_candidate(
        store,
        receipts,
        git=git,
        package_version=package_version,
    )
    if git.production_sha != candidate.candidate.sha:
        raise ReleaseError("production_branch_candidate_mismatch")
    deployments = observe_production_service_set(
        config=config,
        render=render,
        wait_for_sha=candidate.candidate.sha,
    )
    verification = config.verification
    required_strings = {
        key: verification.get(key)
        for key in (
            "production_base_url",
            "health_path",
            "smoke_path",
            "headline_path",
            "headline_selector",
            "headline_unavailable_text",
        )
    }
    if not all(isinstance(value, str) and value for value in required_strings.values()):
        raise ReleaseError("production_verification_policy_invalid")
    report = verify_production(
        root=config.root,
        candidate_sha=candidate.candidate.sha,
        deployments=deployments,
        base_url=str(required_strings["production_base_url"]),
        health_path=str(required_strings["health_path"]),
        smoke_path=str(required_strings["smoke_path"]),
        headline_path=str(required_strings["headline_path"]),
        headline_selector=str(required_strings["headline_selector"]),
        headline_unavailable_text=str(required_strings["headline_unavailable_text"]),
        browser_probe=browser_probe,
    )
    publisher.tag_and_push(
        sha=candidate.candidate.sha,
        tag=candidate.candidate.release_tag,
    )
    stage = _referenced_receipt(
        store,
        receipts,
        reference="active_staging",
        kind="staging_deploy",
    )
    previous_id = store.read_reference("pre_release_last_known_good")
    approvals = [
        item.receipt_id
        for item in receipts
        if item.kind == "approval" and item.candidate == candidate.candidate
    ]
    bridgewright = [
        item.receipt_id
        for item in receipts
        if item.kind == "bridgewright_evidence"
        and item.candidate == candidate.candidate
    ]
    payload = {
        **report.to_receipt_payload(),
        "deployment_id": deployment_set_id(deployments),
        "deployed_sha": candidate.candidate.sha,
        "status": "live",
        "release_tag": candidate.candidate.release_tag,
        "release_tag_pushed": True,
        "staging_receipt_id": stage.receipt_id,
        "staging_deployment_id": stage.payload.get("deployment_id"),
        "approval_receipt_ids": sorted(approvals),
        "bridgewright_evidence_receipt_ids": sorted(bridgewright),
        "last_known_good_receipt_id": previous_id,
        "completed_at": now.astimezone(UTC).isoformat(),
    }
    receipt = Receipt.create(
        kind="production_deploy",
        candidate=candidate.candidate,
        created_at=now,
        payload=payload,
    )
    store.write_receipt(receipt)
    store.set_reference("active_production", receipt.receipt_id)
    store.set_reference("last_known_good", receipt.receipt_id)
    return receipt, report


def record_release_failure(
    *,
    config: ProjectConfig,
    candidate: Receipt,
    operation: str,
    code: str,
    now: datetime,
) -> Receipt:
    if operation not in {"stage", "release", "verify-production"}:
        raise ReceiptError("failure_operation_invalid")
    receipt = Receipt.create(
        kind="failure",
        candidate=candidate.candidate,
        created_at=now,
        payload={"operation": operation, "code": code},
    )
    _store(config).write_receipt(receipt)
    return receipt
