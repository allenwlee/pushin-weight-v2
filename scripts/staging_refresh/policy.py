from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

from . import POLICY_SCHEMA_VERSION


class PolicyError(ValueError):
    """A secret-free, operator-actionable refresh policy failure."""


@dataclass(frozen=True, slots=True)
class ServicePolicy:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class EndpointPolicy:
    environment: str
    resource_id: str
    host: str
    port: int
    database: str
    role: str
    minimum_server_version: int


@dataclass(frozen=True, slots=True)
class ProductionDenyPolicy:
    resource_ids: frozenset[str]
    hosts: frozenset[str]
    databases: frozenset[str]


@dataclass(frozen=True, slots=True)
class RelationsPolicy:
    copied_tables: frozenset[str]
    excluded_tables: frozenset[str]
    views: frozenset[str]
    sequences: frozenset[str]

    @property
    def classified_tables(self) -> frozenset[str]:
        return self.copied_tables | self.excluded_tables


@dataclass(frozen=True, slots=True)
class ScrubPolicy:
    truncate_tables: frozenset[str]
    retained_narrative_statuses: tuple[str, ...]
    site_domain: str
    site_name: str


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    exact_count_tables: tuple[str, ...]
    required_nonempty_tables: tuple[str, ...]
    latest_timestamp_table: str
    latest_timestamp_column: str
    maximum_latest_timestamp_lag_seconds: int
    required_columns: Mapping[str, frozenset[str]]
    translation_columns: Mapping[str, tuple[str, ...]]
    classification_tables: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoragePolicy:
    target_disk_bytes: int
    required_reserve_ratio: float
    local_free_space_multiplier: float


@dataclass(frozen=True, slots=True)
class QuiescencePolicy:
    harvest_environment: str
    broker_environment: str
    queue_name: str
    queue_namespace_pattern: str
    envelope_key: str
    unacked_key: str
    unacked_index_key: str
    worker_probe_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class LifecyclePolicy:
    marker_prefix: str
    shadow_prefix: str
    recovery_prefix: str
    retained_recoveries: int
    administration_statement_timeout_seconds: int
    cluster_lock_id: int
    deploy_lock_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class RefreshPolicy:
    path: Path
    service: ServicePolicy
    enable_environment: str
    source: EndpointPolicy
    target: EndpointPolicy
    production_deny: ProductionDenyPolicy
    relations: RelationsPolicy
    scrub: ScrubPolicy
    validation: ValidationPolicy
    storage: StoragePolicy
    quiescence: QuiescencePolicy
    lifecycle: LifecyclePolicy


@dataclass(frozen=True, slots=True)
class ConnectionIdentity:
    host: str
    port: int
    database: str
    role: str


@dataclass(frozen=True, slots=True)
class DatabaseInspection:
    database: str
    role: str
    server_version: int
    tls: bool
    default_transaction_read_only: bool
    has_write_privileges: bool
    can_create_database: bool
    readable_tables: frozenset[str]
    maintainable_tables: frozenset[str]
    readable_sequences: frozenset[str]
    base_tables: frozenset[str]
    views: frozenset[str]
    sequences: frozenset[str]


@dataclass(frozen=True, slots=True)
class Authorization:
    action: str
    source: ConnectionIdentity | None
    target: ConnectionIdentity
    recovery: str | None


_TOP_LEVEL = {
    "schema_version",
    "service",
    "source",
    "target",
    "production_deny",
    "relations",
    "scrub",
    "validation",
    "storage",
    "quiescence",
    "database_lifecycle",
}
_DATABASE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
_MUTATING_ACTIONS = frozenset({"refresh", "rollback", "prune"})


def _mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise PolicyError(f"policy_field_invalid:{key}")
    return value


def _strict(raw: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    missing = sorted(expected - set(raw))
    unknown = sorted(set(raw) - expected)
    if missing:
        raise PolicyError(f"policy_missing_fields:{field}:{','.join(missing)}")
    if unknown:
        prefix = (
            "policy_unknown_fields"
            if field == "root"
            else f"policy_unknown_fields:{field}"
        )
        raise PolicyError(f"{prefix}:{','.join(unknown)}")


def _line(raw: Mapping[str, Any], key: str, *, field: str) -> str:
    value = raw.get(key)
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise PolicyError(f"policy_field_invalid:{field}.{key}")
    return value.strip()


def _integer(raw: Mapping[str, Any], key: str, *, field: str, minimum: int = 0) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise PolicyError(f"policy_field_invalid:{field}.{key}")
    return value


def _number(raw: Mapping[str, Any], key: str, *, field: str, minimum: float) -> float:
    value = raw.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or float(value) < minimum
    ):
        raise PolicyError(f"policy_field_invalid:{field}.{key}")
    return float(value)


def _strings(
    raw: Mapping[str, Any],
    key: str,
    *,
    field: str,
    identifiers: bool = True,
) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise PolicyError(f"policy_field_invalid:{field}.{key}")
    result = tuple(value)
    if not all(
        isinstance(item, str)
        and item
        and "\n" not in item
        and "\r" not in item
        and (not identifiers or _DATABASE_NAME.fullmatch(item))
        for item in result
    ):
        raise PolicyError(f"policy_field_invalid:{field}.{key}")
    if len(set(result)) != len(result):
        raise PolicyError(f"policy_field_duplicate:{field}.{key}")
    return result


def _endpoint(raw: Mapping[str, Any], field: str) -> EndpointPolicy:
    expected = {
        "environment",
        "resource_id",
        "host",
        "port",
        "database",
        "role",
        "minimum_server_version",
    }
    _strict(raw, expected, field=field)
    endpoint = EndpointPolicy(
        environment=_line(raw, "environment", field=field),
        resource_id=_line(raw, "resource_id", field=field),
        host=_line(raw, "host", field=field).lower().rstrip("."),
        port=_integer(raw, "port", field=field, minimum=1),
        database=_line(raw, "database", field=field),
        role=_line(raw, "role", field=field),
        minimum_server_version=_integer(
            raw, "minimum_server_version", field=field, minimum=1
        ),
    )
    if not _DATABASE_NAME.fullmatch(endpoint.database):
        raise PolicyError(f"policy_field_invalid:{field}.database")
    return endpoint


def _identifier_mapping(
    raw: Mapping[str, Any], key: str, *, field: str
) -> dict[str, frozenset[str]]:
    value = raw.get(key)
    if not isinstance(value, Mapping) or not value:
        raise PolicyError(f"policy_field_invalid:{field}.{key}")
    result: dict[str, frozenset[str]] = {}
    for name, items in value.items():
        if not isinstance(name, str) or not _DATABASE_NAME.fullmatch(name):
            raise PolicyError(f"policy_field_invalid:{field}.{key}")
        if not isinstance(items, list) or not items:
            raise PolicyError(f"policy_field_invalid:{field}.{key}.{name}")
        identifiers = tuple(items)
        if not all(
            isinstance(item, str) and _DATABASE_NAME.fullmatch(item)
            for item in identifiers
        ):
            raise PolicyError(f"policy_field_invalid:{field}.{key}.{name}")
        if len(set(identifiers)) != len(identifiers):
            raise PolicyError(f"policy_field_duplicate:{field}.{key}.{name}")
        result[name] = frozenset(identifiers)
    return result


def load_policy(path: str | Path) -> RefreshPolicy:
    resolved = Path(path).expanduser().resolve()
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyError("policy_unreadable") from exc
    if not isinstance(raw, Mapping):
        raise PolicyError("policy_root_invalid")
    _strict(raw, _TOP_LEVEL, field="root")
    if raw.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise PolicyError("policy_schema_version_unsupported")

    service_raw = _mapping(raw, "service")
    _strict(service_raw, {"id", "name", "enable_environment"}, field="service")
    source = _endpoint(_mapping(raw, "source"), "source")
    target = _endpoint(_mapping(raw, "target"), "target")

    deny_raw = _mapping(raw, "production_deny")
    _strict(deny_raw, {"resource_ids", "hosts", "databases"}, field="production_deny")
    deny = ProductionDenyPolicy(
        resource_ids=frozenset(
            _strings(
                deny_raw,
                "resource_ids",
                field="production_deny",
                identifiers=False,
            )
        ),
        hosts=frozenset(
            host.lower().rstrip(".")
            for host in _strings(
                deny_raw,
                "hosts",
                field="production_deny",
                identifiers=False,
            )
        ),
        databases=frozenset(_strings(deny_raw, "databases", field="production_deny")),
    )

    relations_raw = _mapping(raw, "relations")
    _strict(
        relations_raw,
        {"copied_tables", "excluded_tables", "views", "sequences"},
        field="relations",
    )
    relations = RelationsPolicy(
        copied_tables=frozenset(
            _strings(relations_raw, "copied_tables", field="relations")
        ),
        excluded_tables=frozenset(
            _strings(relations_raw, "excluded_tables", field="relations")
        ),
        views=frozenset(_strings(relations_raw, "views", field="relations")),
        sequences=frozenset(_strings(relations_raw, "sequences", field="relations")),
    )
    if relations.copied_tables & relations.excluded_tables:
        raise PolicyError("policy_relation_classification_overlap")

    scrub_raw = _mapping(raw, "scrub")
    _strict(
        scrub_raw,
        {"truncate_tables", "retained_narrative_statuses", "site_domain", "site_name"},
        field="scrub",
    )
    scrub = ScrubPolicy(
        truncate_tables=frozenset(
            _strings(scrub_raw, "truncate_tables", field="scrub")
        ),
        retained_narrative_statuses=_strings(
            scrub_raw, "retained_narrative_statuses", field="scrub"
        ),
        site_domain=_line(scrub_raw, "site_domain", field="scrub"),
        site_name=_line(scrub_raw, "site_name", field="scrub"),
    )
    if scrub.truncate_tables != relations.excluded_tables:
        raise PolicyError("policy_scrub_classification_mismatch")

    validation_raw = _mapping(raw, "validation")
    validation_fields = {
        "exact_count_tables",
        "required_nonempty_tables",
        "latest_timestamp_table",
        "latest_timestamp_column",
        "maximum_latest_timestamp_lag_seconds",
        "required_columns",
        "translation_columns",
        "classification_tables",
    }
    _strict(validation_raw, validation_fields, field="validation")
    validation = ValidationPolicy(
        exact_count_tables=_strings(
            validation_raw, "exact_count_tables", field="validation"
        ),
        required_nonempty_tables=_strings(
            validation_raw, "required_nonempty_tables", field="validation"
        ),
        latest_timestamp_table=_line(
            validation_raw, "latest_timestamp_table", field="validation"
        ),
        latest_timestamp_column=_line(
            validation_raw, "latest_timestamp_column", field="validation"
        ),
        maximum_latest_timestamp_lag_seconds=_integer(
            validation_raw,
            "maximum_latest_timestamp_lag_seconds",
            field="validation",
        ),
        required_columns=_identifier_mapping(
            validation_raw, "required_columns", field="validation"
        ),
        translation_columns={
            table: tuple(columns)
            for table, columns in _identifier_mapping(
                validation_raw, "translation_columns", field="validation"
            ).items()
        },
        classification_tables=_strings(
            validation_raw, "classification_tables", field="validation"
        ),
    )
    validated_tables = (
        set(validation.exact_count_tables)
        | set(validation.required_nonempty_tables)
        | {validation.latest_timestamp_table}
    )
    if not validated_tables <= relations.copied_tables:
        raise PolicyError("policy_validation_table_not_copied")
    configured_validation_tables = (
        set(validation.required_columns)
        | set(validation.translation_columns)
        | set(validation.classification_tables)
    )
    if not configured_validation_tables <= relations.copied_tables:
        raise PolicyError("policy_validation_table_not_copied")

    storage_raw = _mapping(raw, "storage")
    _strict(
        storage_raw,
        {"target_disk_bytes", "required_reserve_ratio", "local_free_space_multiplier"},
        field="storage",
    )
    storage = StoragePolicy(
        target_disk_bytes=_integer(
            storage_raw, "target_disk_bytes", field="storage", minimum=1
        ),
        required_reserve_ratio=_number(
            storage_raw, "required_reserve_ratio", field="storage", minimum=0.01
        ),
        local_free_space_multiplier=_number(
            storage_raw, "local_free_space_multiplier", field="storage", minimum=1.0
        ),
    )
    if storage.required_reserve_ratio >= 1:
        raise PolicyError("policy_field_invalid:storage.required_reserve_ratio")

    quiescence_raw = _mapping(raw, "quiescence")
    _strict(
        quiescence_raw,
        {
            "harvest_environment",
            "broker_environment",
            "queue_name",
            "queue_namespace_pattern",
            "envelope_key",
            "unacked_key",
            "unacked_index_key",
            "worker_probe_timeout_seconds",
        },
        field="quiescence",
    )
    quiescence = QuiescencePolicy(
        harvest_environment=_line(
            quiescence_raw, "harvest_environment", field="quiescence"
        ),
        broker_environment=_line(
            quiescence_raw, "broker_environment", field="quiescence"
        ),
        queue_name=_line(quiescence_raw, "queue_name", field="quiescence"),
        queue_namespace_pattern=_line(
            quiescence_raw, "queue_namespace_pattern", field="quiescence"
        ),
        envelope_key=_line(quiescence_raw, "envelope_key", field="quiescence"),
        unacked_key=_line(quiescence_raw, "unacked_key", field="quiescence"),
        unacked_index_key=_line(
            quiescence_raw, "unacked_index_key", field="quiescence"
        ),
        worker_probe_timeout_seconds=_integer(
            quiescence_raw,
            "worker_probe_timeout_seconds",
            field="quiescence",
            minimum=1,
        ),
    )
    if quiescence.harvest_environment != "staging":
        raise PolicyError("policy_harvest_environment_invalid")

    lifecycle_raw = _mapping(raw, "database_lifecycle")
    lifecycle_fields = {
        "marker_prefix",
        "shadow_prefix",
        "recovery_prefix",
        "retained_recoveries",
        "administration_statement_timeout_seconds",
        "cluster_lock_id",
        "deploy_lock_timeout_seconds",
    }
    _strict(lifecycle_raw, lifecycle_fields, field="database_lifecycle")
    lifecycle = LifecyclePolicy(
        marker_prefix=_line(lifecycle_raw, "marker_prefix", field="database_lifecycle"),
        shadow_prefix=_line(lifecycle_raw, "shadow_prefix", field="database_lifecycle"),
        recovery_prefix=_line(
            lifecycle_raw, "recovery_prefix", field="database_lifecycle"
        ),
        retained_recoveries=_integer(
            lifecycle_raw, "retained_recoveries", field="database_lifecycle", minimum=1
        ),
        administration_statement_timeout_seconds=_integer(
            lifecycle_raw,
            "administration_statement_timeout_seconds",
            field="database_lifecycle",
            minimum=1,
        ),
        cluster_lock_id=_integer(
            lifecycle_raw, "cluster_lock_id", field="database_lifecycle", minimum=1
        ),
        deploy_lock_timeout_seconds=_integer(
            lifecycle_raw,
            "deploy_lock_timeout_seconds",
            field="database_lifecycle",
            minimum=1,
        ),
    )
    if not lifecycle.recovery_prefix.startswith(f"{target.database}_recovery_"):
        raise PolicyError("policy_recovery_prefix_invalid")
    if not lifecycle.shadow_prefix.startswith(f"{target.database}_shadow_"):
        raise PolicyError("policy_shadow_prefix_invalid")

    return RefreshPolicy(
        path=resolved,
        service=ServicePolicy(
            id=_line(service_raw, "id", field="service"),
            name=_line(service_raw, "name", field="service"),
        ),
        enable_environment=_line(service_raw, "enable_environment", field="service"),
        source=source,
        target=target,
        production_deny=deny,
        relations=relations,
        scrub=scrub,
        validation=validation,
        storage=storage,
        quiescence=quiescence,
        lifecycle=lifecycle,
    )


def _parse_connection(value: str | None, *, label: str) -> ConnectionIdentity:
    if not value:
        raise PolicyError(f"{label}_url_missing")
    try:
        parsed = urlsplit(value)
        port = parsed.port or 5432
    except ValueError as exc:
        raise PolicyError(f"{label}_url_invalid") from exc
    path_parts = parsed.path.removeprefix("/").split("/")
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or parsed.username is None
        or len(path_parts) != 1
        or not path_parts[0]
        or parsed.fragment
    ):
        raise PolicyError(f"{label}_url_invalid")
    identity = ConnectionIdentity(
        host=parsed.hostname.lower().rstrip("."),
        port=port,
        database=unquote(path_parts[0]),
        role=unquote(parsed.username),
    )
    if not _DATABASE_NAME.fullmatch(identity.database):
        raise PolicyError(f"{label}_database_name_invalid")
    return identity


def _guard_endpoint(
    actual: ConnectionIdentity,
    expected: EndpointPolicy,
    *,
    label: str,
) -> None:
    for field in ("host", "port", "database", "role"):
        if getattr(actual, field) != getattr(expected, field):
            raise PolicyError(f"{label}_{field}_mismatch")


def _validate_recovery(policy: RefreshPolicy, recovery: str | None) -> str:
    pattern = re.compile(
        rf"{re.escape(policy.lifecycle.recovery_prefix)}[0-9]{{8}}t[0-9]{{6}}z\Z"
    )
    if not recovery or not pattern.fullmatch(recovery):
        raise PolicyError("recovery_name_invalid")
    return recovery


def expected_confirmation(
    policy: RefreshPolicy,
    action: str,
    *,
    recovery: str | None = None,
) -> str:
    if action == "refresh":
        return (
            f"REFRESH production/{policy.source.database} -> "
            f"staging/{policy.target.database}"
        )
    if action == "rollback":
        recovery = _validate_recovery(policy, recovery)
        return f"ROLLBACK staging/{recovery} -> staging/{policy.target.database}"
    if action == "prune":
        recovery = _validate_recovery(policy, recovery)
        return f"PRUNE staging/{recovery}"
    raise PolicyError("action_invalid")


def guard_environment(
    policy: RefreshPolicy,
    *,
    action: str,
    environ: Mapping[str, str],
    confirmation: str | None = None,
    recovery: str | None = None,
) -> Authorization:
    if action not in {"preflight", "refresh", "verify", "rollback", "prune"}:
        raise PolicyError("action_invalid")
    if (
        environ.get("RENDER_SERVICE_ID") != policy.service.id
        or environ.get("RENDER_SERVICE_NAME") != policy.service.name
    ):
        raise PolicyError("service_identity_mismatch")
    if (
        action in _MUTATING_ACTIONS
        and environ.get(policy.enable_environment, "").lower() != "true"
    ):
        raise PolicyError("refresh_not_enabled")

    target = _parse_connection(environ.get(policy.target.environment), label="target")
    if (
        target.host in policy.production_deny.hosts
        or target.database in policy.production_deny.databases
        or policy.target.resource_id in policy.production_deny.resource_ids
    ):
        raise PolicyError("target_is_production")
    _guard_endpoint(target, policy.target, label="target")

    source: ConnectionIdentity | None = None
    if action in {"preflight", "refresh"}:
        source = _parse_connection(
            environ.get(policy.source.environment), label="source"
        )
        _guard_endpoint(source, policy.source, label="source")

    checked_recovery: str | None = None
    if action in {"rollback", "prune"}:
        checked_recovery = _validate_recovery(policy, recovery)
    if action in _MUTATING_ACTIONS:
        expected = expected_confirmation(policy, action, recovery=checked_recovery)
        if confirmation != expected:
            raise PolicyError("confirmation_mismatch")

    return Authorization(
        action=action, source=source, target=target, recovery=checked_recovery
    )


def _guard_source_inspection(policy: RefreshPolicy, source: DatabaseInspection) -> None:
    if source.database != policy.source.database:
        raise PolicyError("source_database_mismatch")
    if source.role != policy.source.role:
        raise PolicyError("source_role_mismatch")
    if source.server_version < policy.source.minimum_server_version:
        raise PolicyError("source_server_version_unsupported")
    if not source.tls:
        raise PolicyError("source_tls_required")
    if not source.default_transaction_read_only or source.has_write_privileges:
        raise PolicyError("source_not_read_only")

    unknown = source.base_tables - policy.relations.classified_tables
    if unknown:
        raise PolicyError(f"source_unclassified_table:{min(unknown)}")
    missing = policy.relations.classified_tables - source.base_tables
    if missing:
        raise PolicyError(f"source_classified_table_missing:{min(missing)}")
    unknown_views = source.views - policy.relations.views
    if unknown_views:
        raise PolicyError(f"source_unclassified_view:{min(unknown_views)}")
    if source.views != policy.relations.views:
        raise PolicyError("source_view_policy_mismatch")
    if source.sequences != policy.relations.sequences:
        raise PolicyError("source_sequence_policy_mismatch")

    excluded_readable = source.readable_tables & policy.relations.excluded_tables
    if excluded_readable:
        raise PolicyError(f"source_excluded_table_readable:{min(excluded_readable)}")
    unreadable = policy.relations.copied_tables - source.readable_tables
    if unreadable:
        raise PolicyError(f"source_required_table_unreadable:{min(unreadable)}")
    unexpected_maintenance = (
        source.maintainable_tables - policy.relations.excluded_tables
    )
    if unexpected_maintenance:
        raise PolicyError(
            f"source_maintenance_privilege_unexpected:{min(unexpected_maintenance)}"
        )
    unlockable = policy.relations.excluded_tables - source.maintainable_tables
    if unlockable:
        raise PolicyError(f"source_excluded_table_unlockable:{min(unlockable)}")
    if source.readable_sequences != policy.relations.sequences:
        raise PolicyError("source_sequence_privileges_invalid")


def _guard_target_inspection(policy: RefreshPolicy, target: DatabaseInspection) -> None:
    if target.database != policy.target.database:
        raise PolicyError("target_database_mismatch")
    if target.role != policy.target.role:
        raise PolicyError("target_role_mismatch")
    if target.server_version < policy.target.minimum_server_version:
        raise PolicyError("target_server_version_unsupported")
    if not target.can_create_database:
        raise PolicyError("target_createdb_required")


def authorize(
    policy: RefreshPolicy,
    *,
    action: str,
    environ: Mapping[str, str],
    source: DatabaseInspection | None,
    target: DatabaseInspection,
    confirmation: str | None = None,
    recovery: str | None = None,
) -> Authorization:
    authorization = guard_environment(
        policy,
        action=action,
        environ=environ,
        confirmation=confirmation,
        recovery=recovery,
    )
    if action in {"preflight", "refresh"}:
        if source is None:
            raise PolicyError("source_inspection_missing")
        _guard_source_inspection(policy, source)
    _guard_target_inspection(policy, target)
    return authorization
