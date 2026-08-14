from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .git import CommandRunner, SubprocessRunner


class RenderTopologyError(ValueError):
    """A Blueprint or live Render topology violates environment isolation."""


class RenderObservationError(ValueError):
    """Render could not prove a configured resource's exact deployment state."""


@dataclass(frozen=True, slots=True)
class StagingTopology:
    web_service_name: str
    database_name: str
    branch: str
    service_types: tuple[str, ...]
    environment_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RenderResource:
    resource_id: str
    name: str
    kind: str
    branch: str
    repository: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class RenderDeployment:
    resource_id: str
    deployment_id: str
    commit_sha: str
    status: str
    created_at: datetime
    finished_at: datetime | None

    def to_receipt_payload(self) -> dict[str, str | None]:
        return {
            "resource_id": self.resource_id,
            "deployment_id": self.deployment_id,
            "deployed_sha": self.commit_sha,
            "status": self.status,
            "created_at": self.created_at.astimezone(UTC).isoformat(),
            "finished_at": (
                self.finished_at.astimezone(UTC).isoformat()
                if self.finished_at
                else None
            ),
        }


_SERVICE_KINDS = {
    "web_service": "web",
    "background_worker": "worker",
    "cron_job": "cron",
}
_FAILED_DEPLOY_STATUSES = {
    "build_failed",
    "canceled",
    "pre_deploy_failed",
    "update_failed",
}


_FORBIDDEN_ENV_KEYS = {
    "ANTHROPIC_API_KEY",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "DEEPSEEK_API_KEY",
    "TWITTERAPI_IO_API_KEY",
    "X_MONITOR_HEADLINE_API_KEY",
    "X_MONITOR_LIST_ID",
}
_FALSE_CONTROLS = {
    "X_MONITOR_HEADLINE_SERVING_ENABLED",
    "X_MONITOR_HEADLINE_ENQUEUE_ENABLED",
    "X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED",
}


def _mapping(value: object, *, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RenderTopologyError(code)
    return value


def load_staging_topology(path: Path) -> StagingTopology:
    try:
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RenderTopologyError("staging_blueprint_invalid") from exc
    root = _mapping(body, code="staging_blueprint_invalid")
    services = root.get("services")
    databases = root.get("databases")
    if not isinstance(services, list) or len(services) != 1:
        raise RenderTopologyError("staging_service_count_invalid")
    if not isinstance(databases, list) or len(databases) != 1:
        raise RenderTopologyError("staging_database_count_invalid")
    service = _mapping(services[0], code="staging_service_invalid")
    database = _mapping(databases[0], code="staging_database_invalid")
    if service.get("type") != "web":
        raise RenderTopologyError("staging_recurring_service_forbidden")
    if service.get("branch") != "staging":
        raise RenderTopologyError("staging_branch_invalid")
    if service.get("name") != "pushinweight-staging-web":
        raise RenderTopologyError("staging_web_name_invalid")
    if database.get("name") != "pushinweight-staging-db":
        raise RenderTopologyError("staging_database_name_invalid")

    env_vars = service.get("envVars")
    if not isinstance(env_vars, list):
        raise RenderTopologyError("staging_environment_invalid")
    keyed: dict[str, Mapping[str, Any]] = {}
    for raw in env_vars:
        entry = _mapping(raw, code="staging_environment_invalid")
        if "fromGroup" in entry:
            raise RenderTopologyError("staging_environment_group_forbidden")
        key = entry.get("key")
        if isinstance(key, str):
            keyed[key] = entry
    forbidden = sorted(_FORBIDDEN_ENV_KEYS & keyed.keys())
    if forbidden:
        raise RenderTopologyError(
            "staging_provider_environment_forbidden:" + ",".join(forbidden)
        )
    for key in _FALSE_CONTROLS:
        if keyed.get(key, {}).get("value") != "False":
            raise RenderTopologyError(f"staging_control_not_disabled:{key}")
    for key in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "OLLIJA_STAGING_ALLOWED_EMAILS",
    ):
        if keyed.get(key, {}).get("sync") is not False:
            raise RenderTopologyError(f"staging_secret_not_prompted:{key}")
    database_reference = keyed.get("DATABASE_URL", {}).get("fromDatabase")
    if not isinstance(database_reference, Mapping) or (
        database_reference.get("name") != "pushinweight-staging-db"
    ):
        raise RenderTopologyError("staging_database_binding_invalid")

    return StagingTopology(
        web_service_name=str(service["name"]),
        database_name=str(database["name"]),
        branch=str(service["branch"]),
        service_types=(str(service["type"]),),
        environment_keys=tuple(sorted(keyed)),
    )


def assert_blueprints_are_disjoint(
    staging_path: Path,
    production_path: Path,
) -> None:
    staging = _mapping(
        yaml.safe_load(staging_path.read_text(encoding="utf-8")),
        code="staging_blueprint_invalid",
    )
    production = _mapping(
        yaml.safe_load(production_path.read_text(encoding="utf-8")),
        code="production_blueprint_invalid",
    )

    def names(body: Mapping[str, Any]) -> set[str]:
        result: set[str] = set()
        for section in ("services", "databases"):
            values = body.get(section, [])
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, Mapping) and isinstance(value.get("name"), str):
                        result.add(str(value["name"]))
        return result

    overlap = names(staging) & names(production)
    if overlap:
        raise RenderTopologyError(
            "blueprint_resource_overlap:" + ",".join(sorted(overlap))
        )


def _parse_time(value: object, *, required: bool = True) -> datetime | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise RenderObservationError("render_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RenderObservationError("render_timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise RenderObservationError("render_timestamp_invalid")
    return parsed.astimezone(UTC)


def parse_render_resources(output: str) -> tuple[RenderResource, ...]:
    try:
        body = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RenderObservationError("render_inventory_invalid") from exc
    if not isinstance(body, list):
        raise RenderObservationError("render_inventory_invalid")
    resources: list[RenderResource] = []
    for wrapper in body:
        if not isinstance(wrapper, Mapping):
            continue
        service = wrapper.get("service")
        if not isinstance(service, Mapping):
            continue
        resource_id = service.get("id")
        name = service.get("name")
        kind = _SERVICE_KINDS.get(str(service.get("type")))
        branch = service.get("branch")
        repository = service.get("repo")
        if not all(
            isinstance(value, str) and value
            for value in (resource_id, name, kind, branch, repository)
        ):
            raise RenderObservationError("render_service_identity_invalid")
        details = service.get("serviceDetails")
        url = details.get("url") if isinstance(details, Mapping) else None
        resources.append(
            RenderResource(
                resource_id=str(resource_id),
                name=str(name),
                kind=str(kind),
                branch=str(branch),
                repository=str(repository),
                url=str(url) if isinstance(url, str) and url else None,
            )
        )
    return tuple(resources)


def parse_render_deployments(
    output: str,
    *,
    resource_id: str,
) -> tuple[RenderDeployment, ...]:
    try:
        body = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RenderObservationError("render_deployments_invalid") from exc
    if not isinstance(body, list):
        raise RenderObservationError("render_deployments_invalid")
    deployments: list[RenderDeployment] = []
    for raw in body:
        if not isinstance(raw, Mapping):
            raise RenderObservationError("render_deployment_invalid")
        commit = raw.get("commit")
        if not isinstance(commit, Mapping):
            raise RenderObservationError("render_deployment_commit_missing")
        deployment_id = raw.get("id")
        commit_sha = commit.get("id")
        status = raw.get("status")
        if not all(
            isinstance(value, str) and value
            for value in (deployment_id, commit_sha, status)
        ):
            raise RenderObservationError("render_deployment_identity_invalid")
        deployments.append(
            RenderDeployment(
                resource_id=resource_id,
                deployment_id=str(deployment_id),
                commit_sha=str(commit_sha),
                status=str(status),
                created_at=_parse_time(raw.get("createdAt")),  # type: ignore[arg-type]
                finished_at=_parse_time(raw.get("finishedAt"), required=False),
            )
        )
    return tuple(sorted(deployments, key=lambda item: item.created_at, reverse=True))


class RenderClient:
    """Small read-only Render observer used around Git-triggered deploys."""

    def __init__(
        self,
        *,
        root: Path,
        runner: CommandRunner | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.root = root
        self.runner = runner or SubprocessRunner()
        self.sleep = sleep

    def resources(self) -> tuple[RenderResource, ...]:
        result = self.runner.run(
            ("render", "services", "--output", "json"),
            cwd=self.root,
            timeout=30,
        )
        if result.returncode != 0:
            raise RenderObservationError("render_inventory_unavailable")
        return parse_render_resources(result.stdout)

    def require_resource(
        self,
        *,
        resource_id: str,
        name: str,
        kind: str,
        branch: str,
        repository_slug: str,
    ) -> RenderResource:
        matches = [
            resource for resource in self.resources() if resource.resource_id == resource_id
        ]
        if len(matches) != 1:
            raise RenderObservationError("render_resource_identity_missing")
        resource = matches[0]
        expected_repo_suffix = f"/{repository_slug}"
        if resource.name != name:
            raise RenderObservationError("render_resource_name_mismatch")
        if resource.kind != kind:
            raise RenderObservationError("render_resource_kind_mismatch")
        if resource.branch != branch:
            raise RenderObservationError("render_resource_branch_mismatch")
        if not resource.repository.removesuffix(".git").endswith(expected_repo_suffix):
            raise RenderObservationError("render_resource_repository_mismatch")
        return resource

    def deployments(self, resource_id: str) -> tuple[RenderDeployment, ...]:
        result = self.runner.run(
            ("render", "deploys", "list", resource_id, "--output", "json"),
            cwd=self.root,
            timeout=30,
        )
        if result.returncode != 0:
            raise RenderObservationError("render_deployments_unavailable")
        return parse_render_deployments(result.stdout, resource_id=resource_id)

    def current_deployment(self, resource_id: str) -> RenderDeployment:
        deployments = self.deployments(resource_id)
        if deployments:
            return deployments[0]
        raise RenderObservationError("render_deployment_missing")

    def wait_for_exact_deployment(
        self,
        *,
        resource_id: str,
        candidate_sha: str,
        timeout_seconds: int,
        poll_interval_seconds: float,
    ) -> RenderDeployment:
        deadline = time.monotonic() + timeout_seconds
        while True:
            deployments = self.deployments(resource_id)
            exact = next(
                (item for item in deployments if item.commit_sha == candidate_sha),
                None,
            )
            if exact is not None and exact.status == "live":
                return exact
            if exact is not None and exact.status in _FAILED_DEPLOY_STATUSES:
                raise RenderObservationError(
                    f"render_deployment_failed:{resource_id}:{exact.status}"
                )
            if time.monotonic() >= deadline:
                raise RenderObservationError(
                    f"render_deployment_timeout:{resource_id}"
                )
            self.sleep(poll_interval_seconds)
