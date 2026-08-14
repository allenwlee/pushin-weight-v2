from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.ollija.config import load_project_config
from scripts.ollija.database import (
    DatabaseFingerprint,
    DatabaseSnapshot,
    DumpArtifact,
    MigrationReport,
    RefreshError,
    RefreshPipeline,
    ScrubReport,
    ValidationReport,
    safety_policy_from_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeRefreshBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.checksum_valid = True
        self.restore_error: Exception | None = None
        self.migration = MigrationReport(
            applied=("core.0001_initial",),
            database_affecting=False,
            candidate_compatible=True,
            live_code_compatible=True,
            recovery_posture="prior_local_binding_retained",
        )
        self.validation = ValidationReport(
            schema_valid=True,
            invariants_passed=True,
            row_counts={"posts": 120, "brands": 20, "trend_narratives": 4},
        )
        self.source = DatabaseSnapshot(
            fingerprint=DatabaseFingerprint(
                environment="production",
                host="production.internal",
                port=5432,
                database="pushinweight_shadow",
                role="ollija_dump",
                resource_id="dpg-d9koekqjobas73fvjqng-a",
                default_transaction_read_only=True,
            ),
            captured_at=datetime(2026, 8, 14, 3, 0, tzinfo=UTC),
            schema_identity="schema-123",
            migration_identity="migration-123",
            row_counts={"posts": 120, "brands": 20, "trend_narratives": 4},
        )
        self.target = DatabaseFingerprint(
            environment="local",
            host="local_socket",
            port=5432,
            database="pushinweight_staging_shadow_20260814t120000z",
            role="fuchitalee",
            resource_id="local:fuchitalee",
            marker_environment="staging",
            marker_status="building",
        )
        self.artifact = DumpArtifact(
            identifier="dump-123",
            local_path=Path("/private/ollija/raw.dump"),
            expected_checksum="a" * 64,
            actual_checksum="a" * 64,
            byte_size=1024,
        )

    def inspect_source(self) -> DatabaseSnapshot:
        self.calls.append("inspect_source")
        return self.source

    def create_dump(self, source: DatabaseSnapshot) -> DumpArtifact:
        self.calls.append("create_dump")
        return self.artifact

    def verify_dump(self, artifact: DumpArtifact) -> bool:
        self.calls.append("verify_dump")
        return self.checksum_valid

    def prepare_shadow(self, source: DatabaseSnapshot) -> DatabaseFingerprint:
        self.calls.append("prepare_shadow")
        return self.target

    def restore_dump(
        self, artifact: DumpArtifact, target: DatabaseFingerprint
    ) -> None:
        self.calls.append("restore_dump")
        if self.restore_error:
            raise self.restore_error

    def migrate(self, target: DatabaseFingerprint) -> MigrationReport:
        self.calls.append("migrate")
        return self.migration

    def scrub(self, target: DatabaseFingerprint) -> ScrubReport:
        self.calls.append("scrub")
        return ScrubReport(
            cleared_rows={"django_session": 5, "auth_user": 1, "call_state": 2},
            preserved_tables=("posts", "brands", "trend_narratives"),
        )

    def validate(
        self,
        target: DatabaseFingerprint,
        source: DatabaseSnapshot,
    ) -> ValidationReport:
        self.calls.append("validate")
        return self.validation

    def activate(
        self,
        target: DatabaseFingerprint,
        *,
        recovery_posture: str,
    ) -> DatabaseFingerprint:
        self.calls.append("activate")
        return replace(target, marker_status="active")

    def discard_shadow(self, target: DatabaseFingerprint) -> None:
        self.calls.append("discard_shadow")

    def cleanup_dump(self, artifact: DumpArtifact) -> None:
        self.calls.append("cleanup_dump")


@pytest.fixture
def pipeline_and_backend() -> tuple[RefreshPipeline, FakeRefreshBackend]:
    backend = FakeRefreshBackend()
    config = load_project_config(REPO_ROOT)
    pipeline = RefreshPipeline(
        backend=backend,
        policy=safety_policy_from_config(config),
        now=lambda: datetime(2026, 8, 14, 3, 5, tzinfo=UTC),
    )
    return pipeline, backend


def test_checksum_mismatch_fails_before_any_target_mutation(
    pipeline_and_backend,
) -> None:
    pipeline, backend = pipeline_and_backend
    backend.checksum_valid = False

    with pytest.raises(RefreshError, match="dump_checksum_mismatch"):
        pipeline.run()

    assert "prepare_shadow" not in backend.calls
    assert backend.calls[-1] == "cleanup_dump"


def test_interrupted_restore_never_activates_and_discards_shadow(
    pipeline_and_backend,
) -> None:
    pipeline, backend = pipeline_and_backend
    backend.restore_error = RuntimeError("connection closed")

    with pytest.raises(RefreshError, match="refresh_failed"):
        pipeline.run()

    assert "activate" not in backend.calls
    assert "discard_shadow" in backend.calls
    assert backend.calls[-1] == "cleanup_dump"


@pytest.mark.parametrize(
    ("migration", "validation", "error_code"),
    [
        (
            MigrationReport(
                applied=("core.0099_drop_required_data",),
                database_affecting=True,
                candidate_compatible=True,
                live_code_compatible=True,
                recovery_posture=None,
            ),
            ValidationReport(True, True, {"posts": 120}),
            "recovery_posture_missing",
        ),
        (
            MigrationReport(
                applied=("core.0099_change_schema",),
                database_affecting=True,
                candidate_compatible=True,
                live_code_compatible=False,
                recovery_posture="prior_local_binding_retained",
            ),
            ValidationReport(True, True, {"posts": 120}),
            "live_code_incompatible",
        ),
        (
            MigrationReport(
                applied=("core.0099_drop_required_data",),
                database_affecting=True,
                candidate_compatible=True,
                live_code_compatible=True,
                recovery_posture="prior_local_binding_retained",
            ),
            ValidationReport(True, False, {"posts": 0}),
            "refresh_invariant_failed",
        ),
    ],
)
def test_unsafe_migration_or_validation_cannot_activate(
    pipeline_and_backend,
    migration,
    validation,
    error_code,
) -> None:
    pipeline, backend = pipeline_and_backend
    backend.migration = migration
    backend.validation = validation

    with pytest.raises(RefreshError, match=error_code):
        pipeline.run()

    assert "activate" not in backend.calls
    assert "discard_shadow" in backend.calls


def test_success_scrubs_private_state_preserves_product_counts_and_emits_safe_metadata(
    pipeline_and_backend,
) -> None:
    pipeline, backend = pipeline_and_backend

    report = pipeline.run()
    payload = report.to_receipt_payload()

    assert report.target.marker_status == "active"
    assert report.row_counts == backend.source.row_counts
    assert report.scrubbed_rows["auth_user"] == 1
    assert report.preserved_tables == ("posts", "brands", "trend_narratives")
    assert report.raw_artifact_removed is True
    assert payload["dump_checksum"] == "a" * 64
    assert "local_path" not in payload
    assert "url" not in repr(payload).lower()
    assert "content" not in repr(payload).lower()
    assert backend.calls[-2:] == ["activate", "cleanup_dump"]

