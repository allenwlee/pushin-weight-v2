from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.ollija.state import (
    CandidateIdentity,
    LiveAuthorities,
    Receipt,
    ReceiptError,
    ReceiptStore,
    evaluate_lifecycle,
)

SHA_A = "a" * 40
SHA_B = "b" * 40
NOW = datetime(2026, 8, 14, 4, 30, tzinfo=UTC)


def _candidate(sha: str = SHA_A, surface: str = "ui-v1") -> CandidateIdentity:
    return CandidateIdentity(
        sha=sha,
        package_version="0.2.0b1",
        release_tag="v0.2.0-beta.1",
        surface_fingerprint=surface,
    )


def _receipt(kind: str, candidate: CandidateIdentity, **payload: object) -> Receipt:
    return Receipt.create(
        kind=kind,
        candidate=candidate,
        created_at=NOW,
        payload=payload,
    )


def test_lifecycle_transitions_are_recomputed_from_live_authorities() -> None:
    candidate = _candidate()
    candidate_receipt = _receipt("candidate", candidate)
    staged = _receipt(
        "staging_deploy",
        candidate,
        deployment_id="dep-stage-1",
        deployed_sha=SHA_A,
        status="live",
    )
    desktop = _receipt(
        "approval",
        candidate,
        approval_kind="desktop",
        deployment_id="dep-stage-1",
        approved=True,
        surface_fingerprint="ui-v1",
    )
    iphone = _receipt(
        "approval",
        candidate,
        approval_kind="iphone",
        deployment_id="dep-stage-1",
        approved=True,
        surface_fingerprint="ui-v1",
    )
    production = _receipt(
        "production_deploy",
        candidate,
        deployment_id="dep-prod-1",
        deployed_sha=SHA_A,
        status="live",
        health_passed=True,
        smoke_passed=True,
    )

    base = LiveAuthorities(candidate=candidate)
    assert evaluate_lifecycle([], base).state == "idle"
    assert evaluate_lifecycle([candidate_receipt], base).state == "candidate"

    live_stage = replace(
        base,
        staging_deployment_id="dep-stage-1",
        staging_deployed_sha=SHA_A,
        staging_status="live",
        required_approvals=("desktop", "iphone"),
    )
    assert evaluate_lifecycle([candidate_receipt, staged], live_stage).state == "staged"
    assert (
        evaluate_lifecycle(
            [candidate_receipt, staged, desktop, iphone], live_stage
        ).state
        == "approved"
    )

    releasing = replace(
        live_stage,
        production_deployment_id="dep-prod-1",
        production_deployed_sha=SHA_A,
        production_status="update_in_progress",
    )
    assert (
        evaluate_lifecycle(
            [candidate_receipt, staged, desktop, iphone], releasing
        ).state
        == "releasing"
    )

    verified = replace(releasing, production_status="live")
    assert (
        evaluate_lifecycle(
            [candidate_receipt, staged, desktop, iphone], verified
        ).state
        == "releasing"
    )
    assert (
        evaluate_lifecycle(
            [candidate_receipt, staged, desktop, iphone, production], verified
        ).state
        == "verified"
    )


def test_candidate_change_stales_deployment_and_approval_receipts() -> None:
    old_candidate = _candidate()
    new_candidate = _candidate(SHA_B, "ui-v2")
    receipts = [
        _receipt("candidate", new_candidate),
        _receipt(
            "staging_deploy",
            old_candidate,
            deployment_id="dep-stage-1",
            deployed_sha=SHA_A,
            status="live",
        ),
        _receipt(
            "approval",
            old_candidate,
            approval_kind="desktop",
            deployment_id="dep-stage-1",
            approved=True,
            surface_fingerprint="ui-v1",
        ),
    ]
    live = LiveAuthorities(
        candidate=new_candidate,
        staging_deployment_id="dep-stage-1",
        staging_deployed_sha=SHA_A,
        staging_status="live",
        required_approvals=("desktop",),
    )

    evaluation = evaluate_lifecycle(receipts, live)

    assert evaluation.state == "candidate"
    assert set(evaluation.stale_receipt_ids) == {
        receipts[1].receipt_id,
        receipts[2].receipt_id,
    }


def test_receipts_are_immutable_and_tampering_is_detected(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / ".ollija" / "state")
    receipt = _receipt("candidate", _candidate())

    path = store.write_receipt(receipt)
    assert store.write_receipt(receipt) == path

    tampered = receipt.to_dict()
    tampered["payload"] = {"changed": True}
    path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ReceiptError, match="content hash"):
        store.load_receipt(receipt.kind, receipt.receipt_id)


def test_interrupted_reference_write_keeps_prior_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ReceiptStore(tmp_path / ".ollija" / "state")
    first = _receipt("candidate", _candidate())
    second = _receipt("candidate", _candidate(SHA_B, "ui-v2"))
    store.write_receipt(first)
    store.write_receipt(second)
    store.set_reference("active_candidate", first.receipt_id)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        store.set_reference("active_candidate", second.receipt_id)

    assert store.read_reference("active_candidate") == first.receipt_id


def test_state_permissions_and_expired_receipts_are_reported(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / ".ollija" / "state", retention_days=7)
    old = Receipt.create(
        kind="failure",
        candidate=_candidate(),
        created_at=NOW - timedelta(days=8),
        payload={"code": "simulated"},
    )
    path = store.write_receipt(old)

    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert any("expired superseded receipt" in item for item in store.warnings(NOW))

    store.root.chmod(0o755)
    path.chmod(0o644)
    warnings = store.warnings(NOW, active_receipt_ids={old.receipt_id})
    assert any("state directory permissions" in item for item in warnings)
    assert any("receipt permissions" in item for item in warnings)
    assert not any("expired superseded receipt" in item for item in warnings)


def test_unknown_receipt_schema_is_rejected(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / ".ollija" / "state")
    receipt = _receipt("refresh", _candidate(), checksum="abc123")
    path = store.write_receipt(receipt)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["schema_version"] = 99
    path.write_text(json.dumps(body), encoding="utf-8")

    with pytest.raises(ReceiptError, match="Unsupported receipt schema version 99"):
        store.load_receipt(receipt.kind, receipt.receipt_id)
