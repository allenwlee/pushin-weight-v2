from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class RenderTopologyError(ValueError):
    """A Blueprint or live Render topology violates environment isolation."""


@dataclass(frozen=True, slots=True)
class StagingTopology:
    web_service_name: str
    database_name: str
    branch: str
    service_types: tuple[str, ...]
    environment_keys: tuple[str, ...]


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
