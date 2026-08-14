from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.ollija.config import load_project_config
from scripts.ollija.database import (
    DatabaseFingerprint,
    DatabaseGuardError,
    guard_refresh_source,
    guard_refresh_target,
    safety_policy_from_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def policy():
    return safety_policy_from_config(load_project_config(REPO_ROOT))


@pytest.fixture
def source() -> DatabaseFingerprint:
    return DatabaseFingerprint(
        environment="production",
        host="production.internal",
        port=5432,
        database="pushinweight_shadow",
        role="ollija_dump",
        resource_id="dpg-d9koekqjobas73fvjqng-a",
        default_transaction_read_only=True,
    )


@pytest.fixture
def target() -> DatabaseFingerprint:
    return DatabaseFingerprint(
        environment="local",
        host="local_socket",
        port=5432,
        database="pushinweight_staging_shadow_20260814t120000z",
        role="fuchitalee",
        resource_id="local:fuchitalee",
        marker_environment="staging",
        marker_status="building",
    )


def test_source_requires_exact_production_identity_and_dedicated_read_only_role(
    policy, source
) -> None:
    guard_refresh_source(source, policy)

    cases = (
        (replace(source, resource_id=None), "source_resource_ambiguous"),
        (replace(source, role="pushinweight_shadow"), "source_role_not_dedicated"),
        (replace(source, default_transaction_read_only=False), "source_not_read_only"),
        (replace(source, database="unknown"), "source_database_unknown"),
    )
    for fingerprint, expected_code in cases:
        with pytest.raises(DatabaseGuardError, match=expected_code):
            guard_refresh_source(fingerprint, policy)


def test_target_rejects_production_identity_or_missing_positive_marker(
    policy, target
) -> None:
    guard_refresh_target(target, policy, allowed_statuses={"building"})

    cases = (
        (
            replace(
                target,
                database="pushinweight_shadow",
                resource_id="dpg-d9koekqjobas73fvjqng-a",
            ),
            "target_is_production",
        ),
        (replace(target, marker_environment=None), "target_marker_missing"),
        (replace(target, marker_status="active"), "target_marker_status_invalid"),
        (replace(target, database="personal_notes"), "target_name_invalid"),
    )
    for fingerprint, expected_code in cases:
        with pytest.raises(DatabaseGuardError, match=expected_code):
            guard_refresh_target(
                fingerprint,
                policy,
                allowed_statuses={"building"},
            )

