from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.ollija.config import load_project_config
from scripts.ollija.git import GitObservation
from scripts.ollija.release import ReleaseError, require_release_readiness
from scripts.ollija.render import RenderDeployment
from scripts.ollija.state import CandidateIdentity, Receipt, ReceiptStore

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
PRIOR_SHA = "b" * 40
NOW = datetime(2026, 8, 14, 5, 30, tzinfo=UTC)


def _configured(tmp_path: Path):
    source = load_project_config(REPO_ROOT)
    environments = {key: dict(value) for key, value in source.environments.items()}
    environments["staging"]["database_resource_id"] = "dpg-stage"
    environments["staging"]["web_service_id"] = "srv-stage"
    return replace(source, root=tmp_path, environments=environments)


def _candidate() -> CandidateIdentity:
    return CandidateIdentity(
        sha=SHA,
        package_version="0.2.0b1",
        release_tag="v0.2.0-beta.1",
        surface_fingerprint="surface-v1",
    )


def _write_ready_receipts(config) -> None:
    store = ReceiptStore(config.root / config.state.directory)
    candidate = Receipt.create(
        kind="candidate",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "required_approvals": ["desktop", "iphone"],
            "required_evidence": ["bridgewright"],
        },
    )
    local = Receipt.create(
        kind="refresh",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "target_marker_status": "active",
            "raw_artifact_removed": True,
            "database_affecting": True,
            "live_code_compatible": True,
            "recovery_posture": "prior_binding_retained",
        },
    )
    hosted = Receipt.create(
        kind="refresh",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "target_resource_id": "dpg-stage",
            "target_marker_status": "active",
            "raw_artifact_removed": True,
        },
    )
    stage = Receipt.create(
        kind="staging_deploy",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "deployment_id": "dep-stage",
            "deployed_sha": SHA,
            "status": "live",
        },
    )
    desktop = Receipt.create(
        kind="approval",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "approval_kind": "desktop",
            "approved": True,
            "deployment_id": "dep-stage",
            "surface_fingerprint": "surface-v1",
        },
    )
    iphone = Receipt.create(
        kind="approval",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "approval_kind": "iphone",
            "approved": True,
            "deployment_id": "dep-stage",
            "surface_fingerprint": "surface-v1",
        },
    )
    bridgewright = Receipt.create(
        kind="bridgewright_evidence",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "evidence_kind": "bridgewright",
            "status": "clean",
            "authority": "assessment_only",
            "deployment_id": "dep-stage",
            "surface_fingerprint": "surface-v1",
            "source_revision": "bridgewright-revision",
        },
    )
    for receipt in (
        candidate,
        local,
        hosted,
        stage,
        desktop,
        iphone,
        bridgewright,
    ):
        store.write_receipt(receipt)
    store.set_reference("active_candidate", candidate.receipt_id)
    store.set_reference("active_refresh", local.receipt_id)
    store.set_reference("hosted_refresh", hosted.receipt_id)
    store.set_reference("active_staging", stage.receipt_id)


def _git() -> GitObservation:
    return GitObservation(
        repository_root=REPO_ROOT,
        head_sha=SHA,
        branch="feat/release",
        detached=False,
        registered_worktree=True,
        dirty_paths=(),
        production_sha=PRIOR_SHA,
        staging_sha=SHA,
        branch_relationship="staging_ahead",
        remote_reachable=True,
    )


def _stage() -> RenderDeployment:
    return RenderDeployment(
        resource_id="srv-stage",
        deployment_id="dep-stage",
        commit_sha=SHA,
        status="live",
        created_at=NOW,
        finished_at=NOW,
    )


def test_release_readiness_requires_fresh_sha_bound_refresh_and_human_proof(
    tmp_path: Path,
) -> None:
    config = _configured(tmp_path)
    _write_ready_receipts(config)

    evidence = require_release_readiness(
        config=config,
        git=_git(),
        package_version="0.2.0b1",
        staging_live=_stage(),
        now=NOW,
    )

    assert {item.payload["approval_kind"] for item in evidence.approvals} == {
        "desktop",
        "iphone",
    }
    assert evidence.hosted_refresh.payload["target_resource_id"] == "dpg-stage"


def test_replaced_staging_deploy_blocks_release(tmp_path: Path) -> None:
    config = _configured(tmp_path)
    _write_ready_receipts(config)
    replaced = replace(_stage(), deployment_id="dep-replaced")

    with pytest.raises(ReleaseError, match="replaced"):
        require_release_readiness(
            config=config,
            git=_git(),
            package_version="0.2.0b1",
            staging_live=replaced,
            now=NOW,
        )
