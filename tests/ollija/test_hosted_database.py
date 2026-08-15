from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.ollija.config import load_project_config
from scripts.ollija.database import (
    DatabaseFingerprint,
    DatabaseGuardError,
    safety_policy_from_config,
)
from scripts.ollija.hosted_database import (
    build_hosted_refresh_plan,
    guard_new_hosted_target,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _new_target() -> DatabaseFingerprint:
    return DatabaseFingerprint(
        environment="staging",
        host="oregon-postgres.render.com",
        port=5432,
        database="pushinweight_staging",
        role="pushinweight_staging",
        resource_id="dpg-staging123",
    )


def test_new_hosted_target_requires_exact_resource_empty_schema_and_staging_name() -> None:
    policy = safety_policy_from_config(load_project_config(REPO_ROOT))
    target = _new_target()

    guard_new_hosted_target(
        target,
        expected_resource_id="dpg-staging123",
        policy=policy,
        public_tables=set(),
    )

    cases = (
        (
            replace(target, resource_id="dpg-d9koekqjobas73fvjqng-a"),
            "target_is_production",
            set(),
        ),
        (replace(target, resource_id=None), "resource_identity_mismatch", set()),
        (replace(target, database="personal"), "target_name_invalid", set()),
        (target, "hosted_target_not_empty", {"posts"}),
        (
            replace(
                target,
                marker_environment="staging",
                marker_status="building",
            ),
            "hosted_target_already_marked",
            set(),
        ),
    )
    for fingerprint, code, tables in cases:
        with pytest.raises(DatabaseGuardError, match=code):
            guard_new_hosted_target(
                fingerprint,
                expected_resource_id="dpg-staging123",
                policy=policy,
                public_tables=tables,
            )


def test_active_hosted_target_uses_a_shadow_and_retains_recovery() -> None:
    policy = safety_policy_from_config(load_project_config(REPO_ROOT))
    active = replace(
        _new_target(),
        marker_environment="staging",
        marker_status="active",
    )

    plan = build_hosted_refresh_plan(
        active,
        expected_resource_id="dpg-staging123",
        policy=policy,
        public_tables={
            "django_migrations",
            "django_site",
            "posts",
            "brands",
            "trend_narratives",
        },
        suffix="20260815t120000000000z",
    )

    assert plan.mode == "replace"
    assert plan.canonical_database == "pushinweight_staging"
    assert plan.load_database.startswith("pushinweight_staging_shadow_")
    assert plan.recovery_database is not None
    assert plan.recovery_database.startswith("pushinweight_staging_recovery_")
    assert len({
        plan.canonical_database,
        plan.load_database,
        plan.recovery_database,
    }) == 3


def test_repeat_refresh_rejects_an_unhealthy_active_target() -> None:
    policy = safety_policy_from_config(load_project_config(REPO_ROOT))
    active = replace(
        _new_target(),
        marker_environment="staging",
        marker_status="building",
    )

    with pytest.raises(DatabaseGuardError, match="hosted_target_status_invalid"):
        build_hosted_refresh_plan(
            active,
            expected_resource_id="dpg-staging123",
            policy=policy,
            public_tables={"posts", "brands", "trend_narratives"},
            suffix="20260815t120000000000z",
        )
