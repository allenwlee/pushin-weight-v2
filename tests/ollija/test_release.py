from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.ollija.config import load_project_config
from scripts.ollija.git import GitObservation
from scripts.ollija.release import (
    GitPublisher,
    ReleaseError,
    inspect_refresh_readiness,
    require_release_readiness,
    verify_and_tag_candidate,
)
from scripts.ollija.render import RenderDeployment
from scripts.ollija.state import CandidateIdentity, Receipt, ReceiptStore
from scripts.ollija.verification import BrowserObservation, RouteObservation

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
            "target_resource_id": "local:fuchitalee",
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
            "local_refresh_receipt_id": local.receipt_id,
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


def _write_last_known_good(config) -> None:
    store = ReceiptStore(config.root / config.state.directory)
    receipt = Receipt.create(
        kind="last_known_good",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "service_set_id": "prior-set",
            "deployed_sha": PRIOR_SHA,
            "deployments": [],
        },
    )
    store.write_receipt(receipt)
    store.set_reference("pre_release_last_known_good", receipt.receipt_id)


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


def test_hosted_refresh_must_derive_from_the_current_local_refresh(
    tmp_path: Path,
) -> None:
    config = _configured(tmp_path)
    _write_ready_receipts(config)
    store = ReceiptStore(config.root / config.state.directory)
    receipts = store.iter_receipts()
    candidate = next(item for item in receipts if item.kind == "candidate")
    hosted = Receipt.create(
        kind="refresh",
        candidate=_candidate(),
        created_at=NOW,
        payload={
            "target_resource_id": "dpg-stage",
            "target_marker_status": "active",
            "raw_artifact_removed": True,
            "local_refresh_receipt_id": "f" * 64,
        },
    )
    store.write_receipt(hosted)
    store.set_reference("hosted_refresh", hosted.receipt_id)

    readiness = inspect_refresh_readiness(
        config,
        store,
        store.iter_receipts(),
        candidate,
        now=NOW,
    )

    assert readiness.state == "local_refreshed"
    assert readiness.error_code == "hosted_refresh_local_mismatch"


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


class _Render:
    def __init__(self, staging: RenderDeployment) -> None:
        self.staging = staging

    def require_resource(self, **kwargs) -> None:
        return None

    def current_deployment(self, resource_id: str) -> RenderDeployment:
        return self.staging

    def wait_for_exact_deployment(
        self,
        *,
        resource_id: str,
        candidate_sha: str,
        timeout_seconds: int,
        poll_interval_seconds: float,
    ) -> RenderDeployment:
        return replace(
            self.staging,
            resource_id=resource_id,
            deployment_id=f"dep-{resource_id}",
            commit_sha=candidate_sha,
        )


class _Publisher:
    def __init__(self) -> None:
        self.tags: list[tuple[str, str]] = []

    def tag_and_push(self, *, sha: str, tag: str) -> None:
        self.tags.append((sha, tag))


class _Browser:
    def observe_headline(self, *, url: str, selector: str, unavailable_text: str):
        return BrowserObservation(
            final_url=url,
            selector=selector,
            visible=True,
            text_fingerprint="f" * 64,
        )


def test_verification_revalidates_current_staging_before_tagging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _configured(tmp_path)
    for filename in ("config.yaml", "render.yaml"):
        shutil.copy2(REPO_ROOT / filename, tmp_path / filename)
    _write_ready_receipts(config)
    _write_last_known_good(config)
    git = replace(
        _git(),
        production_sha=SHA,
        staging_sha=SHA,
        branch_relationship="equal",
    )
    monkeypatch.setattr(
        "scripts.ollija.verification.probe_route",
        lambda base, path: RouteObservation(
            url=base + path,
            status_code=200,
            final_url=base + path,
        ),
    )
    publisher = _Publisher()

    receipt, _report = verify_and_tag_candidate(
        config=config,
        git=git,
        package_version="0.2.0b1",
        render=_Render(_stage()),
        publisher=publisher,
        browser_probe=_Browser(),
        now=NOW,
    )

    assert publisher.tags == [(SHA, "v0.2.0-beta.1")]
    assert receipt.payload["staging_deployment_id"] == "dep-stage"
    assert len(receipt.payload["approval_receipt_ids"]) == 2


def test_verification_does_not_tag_after_staging_replacement(
    tmp_path: Path,
) -> None:
    config = _configured(tmp_path)
    _write_ready_receipts(config)
    _write_last_known_good(config)
    git = replace(
        _git(),
        production_sha=SHA,
        staging_sha=SHA,
        branch_relationship="equal",
    )
    publisher = _Publisher()

    with pytest.raises(ReleaseError, match="replaced"):
        verify_and_tag_candidate(
            config=config,
            git=git,
            package_version="0.2.0b1",
            render=_Render(replace(_stage(), deployment_id="dep-replaced")),
            publisher=publisher,
            browser_probe=_Browser(),
            now=NOW,
        )

    assert publisher.tags == []


def test_existing_remote_tag_is_rejected_before_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = GitPublisher(tmp_path)
    monkeypatch.setattr(publisher, "_try", lambda *args: (1, ""))
    monkeypatch.setattr(
        publisher,
        "_run",
        lambda *args: f"{'c' * 40}\trefs/tags/v0.2.0-beta.1\n",
    )

    with pytest.raises(ReleaseError, match="already_exists"):
        publisher.assert_tag_absent("v0.2.0-beta.1")
