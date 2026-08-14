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
from scripts.ollija.hosted_database import guard_new_hosted_target

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
