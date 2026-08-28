from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from scripts.staging_refresh.policy import (
    DatabaseInspection,
    PolicyError,
    authorize,
    expected_confirmation,
    load_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "staging_refresh.yaml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "operations" / "staging-data-refresh.md"


def _inspection(
    policy,
    *,
    source: bool,
    database: str | None = None,
    role: str | None = None,
) -> DatabaseInspection:
    endpoint = policy.source if source else policy.target
    return DatabaseInspection(
        database=database or endpoint.database,
        role=role or endpoint.role,
        server_version=180000,
        tls=True,
        default_transaction_read_only=source,
        has_write_privileges=False,
        can_create_database=not source,
        readable_tables=policy.relations.copied_tables if source else frozenset(),
        maintainable_tables=(
            policy.relations.excluded_tables if source else frozenset()
        ),
        readable_sequences=policy.relations.sequences if source else frozenset(),
        base_tables=policy.relations.classified_tables if source else frozenset(),
        views=policy.relations.views if source else frozenset(),
        sequences=policy.relations.sequences if source else frozenset(),
    )


def _environment(policy) -> dict[str, str]:
    return {
        "RENDER_SERVICE_ID": policy.service.id,
        "RENDER_SERVICE_NAME": policy.service.name,
        policy.enable_environment: "true",
        policy.source.environment: (
            f"postgresql://{policy.source.role}:secret@{policy.source.host}:5432/"
            f"{policy.source.database}?sslmode=require"
        ),
        policy.target.environment: (
            f"postgresql://{policy.target.role}:secret@{policy.target.host}:5432/"
            f"{policy.target.database}"
        ),
    }


def test_loads_the_tracked_exhaustive_policy() -> None:
    policy = load_policy(POLICY_PATH)

    assert policy.service.name == "pushinweight-staging-web"
    assert policy.source.role == "staging_refresh_reader"
    assert policy.source.database == "pushinweight_shadow"
    assert policy.target.database == "pushinweight_staging"
    assert policy.relations.copied_tables.isdisjoint(policy.relations.excluded_tables)
    assert "auth_user" in policy.relations.excluded_tables
    assert "posts" in policy.relations.copied_tables
    assert "trend_narrative_versions" in policy.relations.views


def test_migration_graph_tables_are_exhaustively_classified() -> None:
    from django.db.migrations.loader import MigrationLoader

    policy = load_policy(POLICY_PATH)
    state = MigrationLoader(None, ignore_no_migrations=True).project_state()
    migration_tables = {
        model.options.get("db_table") or f"{app_label}_{model_name}"
        for (app_label, model_name), model in state.models.items()
        if model.options.get("managed", True) and not model.options.get("proxy", False)
    }
    migration_tables.update(
        {
            "auth_group_permissions",
            "auth_user_groups",
            "auth_user_user_permissions",
            "django_migrations",
            "socialaccount_socialapp_sites",
        }
    )

    assert policy.relations.classified_tables == migration_tables


def test_per_brand_headline_graph_is_environment_local_state() -> None:
    policy = load_policy(POLICY_PATH)
    runtime_tables = {
        "trend_narrative_runs",
        "brand_trend_narratives",
        "trend_narrative_work_slots",
        "trend_narrative_provider_calls",
        "trend_narrative_visible_runs",
    }

    assert runtime_tables <= policy.relations.excluded_tables
    assert runtime_tables <= policy.scrub.truncate_tables
    assert {
        "trend_narrative_runs_id_seq",
        "brand_trend_narratives_id_seq",
        "trend_narrative_provider_calls_id_seq",
    } <= policy.relations.sequences
    assert policy.quiescence.harvest_environment == "staging"
    assert policy.quiescence.broker_environment == "CELERY_BROKER_URL"
    assert policy.quiescence.queue_name == "trend-narratives"
    assert policy.quiescence.queue_namespace_pattern == "trend-narratives*"
    assert policy.quiescence.unacked_index_key == "unacked_index"


def test_runbook_source_grants_cover_the_exhaustive_copy_policy() -> None:
    policy = load_policy(POLICY_PATH)
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    for relation in sorted(
        policy.relations.classified_tables | policy.relations.sequences
    ):
        assert relation in runbook
    assert "GRANT MAINTAIN ON" in runbook
    maintain_block = runbook.split("GRANT MAINTAIN ON", 1)[1].split(
        "TO staging_refresh_reader;", 1
    )[0]
    maintained_relations = frozenset(maintain_block.replace(",", " ").split())
    assert maintained_relations == policy.relations.excluded_tables
    assert "Do not add default privileges" in runbook
    assert "\\password staging_refresh_reader" in runbook


def test_policy_rejects_unknown_fields(tmp_path: Path) -> None:
    raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    raw["surprise"] = True
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(PolicyError, match="policy_unknown_fields:surprise"):
        load_policy(path)


def test_valid_staging_preflight_is_authorized() -> None:
    policy = load_policy(POLICY_PATH)

    result = authorize(
        policy,
        action="preflight",
        environ=_environment(policy),
        source=_inspection(policy, source=True),
        target=_inspection(policy, source=False),
    )

    assert result.source.database == "pushinweight_shadow"
    assert result.target.database == "pushinweight_staging"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("production_service", "service_identity_mismatch"),
        ("writable_source", "source_not_read_only"),
        ("source_database", "source_database_mismatch"),
        ("target_database", "target_database_mismatch"),
        ("production_target", "target_is_production"),
        ("excluded_readable", "source_excluded_table_readable:auth_user"),
        ("excluded_unlockable", "source_excluded_table_unlockable:auth_user"),
        (
            "unexpected_maintenance",
            "source_maintenance_privilege_unexpected:posts",
        ),
    ],
)
def test_guard_matrix_fails_closed(change: str, code: str) -> None:
    policy = load_policy(POLICY_PATH)
    environment = _environment(policy)
    source = _inspection(policy, source=True)
    target = _inspection(policy, source=False)

    if change == "production_service":
        environment["RENDER_SERVICE_ID"] = "srv-production"
    elif change == "writable_source":
        source = replace(source, default_transaction_read_only=False)
    elif change == "source_database":
        source = replace(source, database="other_source")
    elif change == "target_database":
        target = replace(target, database="other_target")
    elif change == "production_target":
        environment[policy.target.environment] = (
            f"postgresql://writer:secret@{policy.source.host}:5432/{policy.source.database}"
        )
    elif change == "excluded_readable":
        source = replace(source, readable_tables=source.readable_tables | {"auth_user"})
    elif change == "excluded_unlockable":
        source = replace(
            source, maintainable_tables=source.maintainable_tables - {"auth_user"}
        )
    elif change == "unexpected_maintenance":
        source = replace(
            source, maintainable_tables=source.maintainable_tables | {"posts"}
        )

    with pytest.raises(PolicyError, match=code):
        authorize(
            policy,
            action="preflight",
            environ=environment,
            source=source,
            target=target,
        )


def test_unknown_source_table_names_only_the_relation() -> None:
    policy = load_policy(POLICY_PATH)
    source = replace(
        _inspection(policy, source=True),
        base_tables=policy.relations.classified_tables | {"new_private_table"},
    )

    with pytest.raises(PolicyError) as exc_info:
        authorize(
            policy,
            action="preflight",
            environ=_environment(policy),
            source=source,
            target=_inspection(policy, source=False),
        )

    assert str(exc_info.value) == "source_unclassified_table:new_private_table"


@pytest.mark.parametrize("confirmation", ["yes", "refresh", "REFRESH production"])
def test_refresh_requires_the_exact_action_confirmation(confirmation: str) -> None:
    policy = load_policy(POLICY_PATH)

    with pytest.raises(PolicyError, match="confirmation_mismatch"):
        authorize(
            policy,
            action="refresh",
            environ=_environment(policy),
            source=_inspection(policy, source=True),
            target=_inspection(policy, source=False),
            confirmation=confirmation,
        )


def test_confirmation_cannot_be_replayed_for_another_action() -> None:
    policy = load_policy(POLICY_PATH)
    recovery = "pushinweight_staging_recovery_20260827t010203z"

    with pytest.raises(PolicyError, match="confirmation_mismatch"):
        authorize(
            policy,
            action="rollback",
            environ=_environment(policy),
            source=None,
            target=_inspection(policy, source=False),
            recovery=recovery,
            confirmation=expected_confirmation(policy, "prune", recovery=recovery),
        )


@pytest.mark.parametrize(
    "recovery",
    ["pushinweight_staging; DROP DATABASE x", "../recovery", "pushinweight_staging"],
)
def test_recovery_database_name_must_match_the_policy_grammar(recovery: str) -> None:
    policy = load_policy(POLICY_PATH)

    with pytest.raises(PolicyError, match="recovery_name_invalid"):
        expected_confirmation(policy, "rollback", recovery=recovery)
