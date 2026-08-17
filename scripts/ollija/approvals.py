from __future__ import annotations

import re
from datetime import datetime

from .bridgewright import BridgewrightEvidence
from .state import CandidateIdentity, Receipt


class ApprovalError(ValueError):
    """Approval or evidence is not bound to the staged candidate."""


_OWNER = re.compile(r"[A-Za-z0-9._@-]{1,80}")


def owner_approval_receipt(
    *,
    candidate: CandidateIdentity,
    approval_kind: str,
    deployment_id: str,
    created_at: datetime,
) -> Receipt:
    if approval_kind not in {"desktop", "iphone"}:
        raise ApprovalError("owner_approval_kind_invalid")
    if not deployment_id:
        raise ApprovalError("staging_deployment_identity_missing")
    return Receipt.create(
        kind="approval",
        candidate=candidate,
        created_at=created_at,
        payload={
            "approval_kind": approval_kind,
            "approved": True,
            "deployment_id": deployment_id,
            "surface_fingerprint": candidate.surface_fingerprint,
            "authority": "owner_cli_action",
        },
    )


def bridgewright_evidence_receipt(
    *,
    candidate: CandidateIdentity,
    deployment_id: str,
    evidence: BridgewrightEvidence,
    created_at: datetime,
) -> Receipt:
    if evidence.status != "clean":
        raise ApprovalError("bridgewright_evidence_not_clean")
    return Receipt.create(
        kind="bridgewright_evidence",
        candidate=candidate,
        created_at=created_at,
        payload={
            "evidence_kind": "bridgewright",
            "deployment_id": deployment_id,
            "surface_fingerprint": candidate.surface_fingerprint,
            **evidence.to_payload(),
            "authority": "assessment_only",
        },
    )


def owner_override_receipt(
    *,
    candidate: CandidateIdentity,
    assessment_kind: str,
    deployment_id: str,
    owner: str,
    reason: str,
    created_at: datetime,
) -> Receipt:
    """Record an explicit, immutable exception without forging clean evidence."""

    if assessment_kind != "bridgewright":
        raise ApprovalError("owner_override_assessment_invalid")
    if not deployment_id:
        raise ApprovalError("staging_deployment_identity_missing")
    if not _OWNER.fullmatch(owner):
        raise ApprovalError("owner_override_identity_invalid")
    bounded_reason = reason.strip()
    if not bounded_reason or len(bounded_reason) > 500:
        raise ApprovalError("owner_override_reason_invalid")
    return Receipt.create(
        kind="owner_override",
        candidate=candidate,
        created_at=created_at,
        payload={
            "assessment_kind": assessment_kind,
            "overridden": True,
            "deployment_id": deployment_id,
            "surface_fingerprint": candidate.surface_fingerprint,
            "owner": owner,
            "reason": bounded_reason,
            "authority": "explicit_owner_override",
        },
    )
