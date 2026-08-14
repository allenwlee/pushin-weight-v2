from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.ollija.approvals import (
    ApprovalError,
    bridgewright_evidence_receipt,
    owner_approval_receipt,
)
from scripts.ollija.bridgewright import BridgewrightEvidence
from scripts.ollija.state import (
    CandidateIdentity,
    LiveAuthorities,
    Receipt,
    evaluate_lifecycle,
)

NOW = datetime(2026, 8, 14, 6, 0, tzinfo=UTC)
SHA = "a" * 40


def _candidate() -> CandidateIdentity:
    return CandidateIdentity(SHA, "0.2.0b1", "v0.2.0-beta.1", "surface-v1")


def _base_receipts(candidate: CandidateIdentity) -> list[Receipt]:
    return [
        Receipt.create(kind="candidate", candidate=candidate, created_at=NOW),
        Receipt.create(
            kind="staging_deploy",
            candidate=candidate,
            created_at=NOW,
            payload={
                "deployment_id": "dep-1",
                "deployed_sha": SHA,
                "status": "live",
            },
        ),
    ]


def _live(candidate: CandidateIdentity) -> LiveAuthorities:
    return LiveAuthorities(
        candidate=candidate,
        staging_deployment_id="dep-1",
        staging_deployed_sha=SHA,
        staging_status="live",
        required_approvals=("desktop", "iphone"),
        required_evidence=("bridgewright",),
    )


def test_ui_candidate_needs_owner_device_approvals_and_bridgewright_evidence() -> None:
    candidate = _candidate()
    receipts = _base_receipts(candidate)
    receipts.extend(
        [
            owner_approval_receipt(
                candidate=candidate,
                approval_kind=kind,
                deployment_id="dep-1",
                created_at=NOW,
            )
            for kind in ("desktop", "iphone")
        ]
    )
    assert evaluate_lifecycle(receipts, _live(candidate)).state == "staged"

    evidence = BridgewrightEvidence(
        status="clean",
        source_revision="b" * 40,
        version="0.1.0",
        capability_schema="bridgewright.capabilities/v1",
        skill_digest="c" * 64,
        manifest_path="/repo/bridgewright.yaml",
        evidence_id="d" * 64,
    )
    receipts.append(
        bridgewright_evidence_receipt(
            candidate=candidate,
            deployment_id="dep-1",
            evidence=evidence,
            created_at=NOW,
        )
    )

    assert evaluate_lifecycle(receipts, _live(candidate)).state == "approved"


def test_bridgewright_cannot_be_recorded_as_an_owner_approval() -> None:
    with pytest.raises(ApprovalError, match="kind_invalid"):
        owner_approval_receipt(
            candidate=_candidate(),
            approval_kind="bridgewright",
            deployment_id="dep-1",
            created_at=NOW,
        )
