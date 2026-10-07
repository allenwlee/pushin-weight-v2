"""A fixed, resumable rerun with immutable earlier decisions and spend receipts.

The existing discovery lock must be held for initialization and execution.
Inspection is read-only. Cohort membership never follows the moving review queue.
"""

import json
import time
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import (
    OfficialCompanyAccountState,
    OfficialCompanyAttempt,
    OfficialCompanyScan,
)
from core.official_company_accounts import (
    BLOCKCHAIN_POLICY_VERSION,
    POLICY_VERSION,
    digest,
    evaluate_account,
    official_organization_links,
)
from core.official_company_hf import VERSION as HF_POLICY_VERSION

COHORT_KEY = "official-company-requalification-20261007-v3"
POLICIES = {POLICY_VERSION, BLOCKCHAIN_POLICY_VERSION}


def initialize_cohort(manifest):
    rows = manifest["review"] + manifest["failed"]
    if not 1 <= len(rows) <= 2000:
        raise ValueError("cohort must contain 1..2000 accounts")
    frozen_at = parse_datetime(manifest["frozen_at"])
    if frozen_at is None or timezone.is_naive(frozen_at):
        raise ValueError("cohort requires a timezone-aware frozen timestamp")
    members = [{
        "state_id": int(row["id"]), "account_id": str(row["account_id"]),
        "evidence_hash": row["evidence_hash"],
        "baseline_outcome": row["decision"].get("outcome"),
    } for row in rows]
    if len({row["state_id"] for row in members}) != len(members):
        raise ValueError("duplicate cohort member")
    identity = digest({"members": members, "frozen_at": manifest["frozen_at"]})
    cursor = {
        "identity": identity, "policy_version": POLICY_VERSION,
        "members": members, "queued": [], "excluded": {},
    }
    with transaction.atomic():
        scan, created = OfficialCompanyScan.objects.get_or_create(
            key=COHORT_KEY, defaults={"started_at": frozen_at, "population": len(members),
                                     "cursor": json.dumps(cursor)},
        )
        existing = json.loads(scan.cursor)
        if existing["identity"] != identity or existing["policy_version"] != POLICY_VERSION:
            raise ValueError("cohort identity/policy mismatch")
    return created


def cohort_report(*, include_members=False):
    scan = OfficialCompanyScan.objects.filter(key=COHORT_KEY).first()
    if scan is None:
        return None
    cursor = json.loads(scan.cursor)
    members = {row["state_id"]: row for row in cursor["members"]}
    if len(members) > 2000 or cursor["policy_version"] != POLICY_VERSION:
        raise ValueError("unsupported cohort")
    states = {row["pk"]: row for row in OfficialCompanyAccountState.objects.filter(pk__in=members).values(
        "pk", "status", "decision", "evidence_hash", "last_error", "next_attempt_at",
    )}
    attempts = list(OfficialCompanyAttempt.objects.filter(
        state_id__in=members, policy_version__in=POLICIES, created_at__gte=scan.started_at,
    ).order_by("-created_at", "-pk").values(
        "pk", "state_id", "evidence_hash", "status", "decision", "actual_usd", "reserved_usd", "error_code",
    ))
    latest = {}
    spent = Decimal(0)
    reserved = Decimal(0)
    for attempt in attempts:
        if attempt["evidence_hash"] != members[attempt["state_id"]]["evidence_hash"]:
            continue
        latest.setdefault(attempt["state_id"], attempt)
        spent += attempt["actual_usd"] or 0
        if attempt["status"] == "reserved" or attempt["actual_usd"] is None:
            reserved += attempt["reserved_usd"]
    result = {
        "key": COHORT_KEY, "population": scan.population, "qualified": 0,
        "newly_qualified": 0, "model": 0, "agent": 0, "harness": 0,
        "uncertain": 0, "rejected": 0, "failed": 0, "retry_pending": 0,
        "pending": 0, "excluded": 0, "hf_verified": 0,
        "qualified_accounts": [], "spent_usd": str(spent), "reserved_usd": str(reserved),
    }
    if include_members:
        result["members"] = []
        result["frozen_at"] = scan.started_at
    for state_id, member in members.items():
        state = states.get(state_id, {})
        attempt = latest.get(state_id)
        record = {
            **member, "bucket": "pending", "decision": {}, "development_type": None,
            "hf_verified": False, "attempt_id": attempt["pk"] if attempt else None,
            "error_code": (attempt or {}).get("error_code") or state.get("last_error", ""),
            "next_attempt_at": state.get("next_attempt_at"),
        }
        if include_members:
            result["members"].append(record)
        proof = (state.get("decision") or {}).get("hf_verification") or {}
        observed_at = parse_datetime(proof.get("observed_at", ""))
        # Registration already required the private server signature. The web
        # reader need not possess that signing key. Preserve paid attempt failures
        # while recognizing an independent, newly registered HF verification.
        hf_verified = (
            state.get("status") == "registered"
            and state.get("evidence_hash") == member["evidence_hash"]
            and proof.get("version") == HF_POLICY_VERSION
            and proof.get("outcome") == "passed"
            and proof.get("evidence_hash") == member["evidence_hash"]
            and observed_at is not None and timezone.is_aware(observed_at)
            and observed_at >= scan.started_at
        )
        if hf_verified:
            result["hf_verified"] += 1
            record["hf_verified"] = True
            decision = state["decision"]
        else:
            decision = None
        excluded = str(state_id) in cursor["excluded"] or (
            state_id in cursor["queued"] and (
                state.get("status") in {"suppressed", "registered"}
                or state.get("last_error") == "already_tracked"
            )
        )
        if excluded and not hf_verified:
            result["excluded"] += 1
            record["bucket"] = "excluded"
            continue
        if hf_verified:
            pass
        elif state_id in cursor["queued"] and state.get("last_error") in {
            "attempt_limit", "evidence_envelope_exceeded",
        }:
            result["failed"] += 1
            record["bucket"] = "failed"
        elif attempt is None or attempt["status"] == "reserved":
            result["pending"] += 1
        elif attempt["status"] == "failed":
            record["bucket"] = "retry_pending" if state.get("status") == "retry_due" else "failed"
            result[record["bucket"]] += 1
        else:
            decision = attempt["decision"]
        if decision is not None:
            record["decision"] = decision
            if decision.get("outcome") == "accepted":
                kind = "model" if hf_verified else decision.get("development_type", "model")
                record["development_type"] = kind
                record["bucket"] = "newly_qualified" if member["baseline_outcome"] != "accepted" else "qualified"
                result["qualified"] += 1
                result[kind] += 1
                result["newly_qualified"] += int(member["baseline_outcome"] != "accepted")
                result["qualified_accounts"].append({
                    "account_id": member["account_id"], "development_type": kind,
                    "organization_name": decision["organization_name"],
                    "newly_qualified": member["baseline_outcome"] != "accepted",
                })
            else:
                record["bucket"] = "rejected" if decision.get("outcome") == "rejected" else "uncertain"
                result[record["bucket"]] += 1
    result["completed"] = scan.population - result["pending"] - result["retry_pending"]
    result["complete"] = result["completed"] == scan.population
    return result


def run_cohort_batch(*, cfg, call, limit, deadline):
    if not cfg.enabled or call is None or not 1 <= limit <= 500:
        raise ValueError("enabled bounded cohort execution required")
    with transaction.atomic():
        scan = OfficialCompanyScan.objects.select_for_update().get(key=COHORT_KEY)
        cursor = json.loads(scan.cursor)
        if cursor["policy_version"] != POLICY_VERSION:
            raise ValueError("cohort policy mismatch")
        queued = set(cursor["queued"])
        staged = 0
        for member in cursor["members"]:
            state_id = member["state_id"]
            if state_id in queued or str(state_id) in cursor["excluded"]:
                continue
            if staged >= limit or time.monotonic() + 2 > deadline:
                break
            staged += 1
            state = OfficialCompanyAccountState.objects.select_for_update().filter(pk=state_id).first()
            reason = ""
            if state is None or str(state.account_id) != member["account_id"]:
                reason = "identity_unavailable"
            elif state.status in {"registered", "suppressed"} or state.model == "owner-attestation":
                reason = "settled_or_suppressed"
            elif state.evidence_hash != member["evidence_hash"]:
                reason = "changed_evidence"
            elif state.status == "accepted" and (state.decision.get("hf_verification") or {}).get("outcome") == "passed":
                reason = "already_hf_settled"
            elif any(official_organization_links(state.account)):
                reason = "already_tracked"
            elif state.status == "claimed" and state.claim_expires_at and state.claim_expires_at > timezone.now():
                continue
            if reason:
                cursor["excluded"][str(state_id)] = reason
                continue
            if not OfficialCompanyAttempt.objects.filter(
                state=state, evidence_hash=state.evidence_hash, policy_version__in=POLICIES,
                created_at__gte=scan.started_at,
            ).exists():
                # Keep the old decision and immutable attempt rows. Only this
                # policy's bounded claim state restarts; evidence stays identical.
                state.status = "pending"
                state.attempts = 0
                state.last_error = ""
                state.next_attempt_at = None
                state.claim_token = ""
                state.claim_expires_at = None
                state.save(update_fields=["status", "attempts", "last_error", "next_attempt_at",
                                          "claim_token", "claim_expires_at", "updated_at"])
            queued.add(state_id)
        cursor["queued"] = sorted(queued)
        scan.cursor = json.dumps(cursor)
        scan.save(update_fields=["cursor", "updated_at"])
    ids = list(OfficialCompanyAccountState.objects.filter(
        pk__in=cursor["queued"], status__in=["pending", "retry_due", "claimed"],
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now()))
        .filter(~Q(status="claimed") | Q(claim_expires_at__isnull=True) | Q(claim_expires_at__lte=timezone.now()))
        .order_by("candidate_priority", "pk").values_list("pk", flat=True)[:limit])
    members = {row["state_id"]: row for row in cursor["members"]}
    attempted = 0
    for state_id in ids:
        if time.monotonic() + cfg.request_timeout_seconds + 2 > deadline:
            break
        current_hash = OfficialCompanyAccountState.objects.filter(pk=state_id).values_list("evidence_hash", flat=True).first()
        if current_hash != members[state_id]["evidence_hash"]:
            cursor["excluded"][str(state_id)] = "changed_evidence"
            OfficialCompanyScan.objects.filter(key=COHORT_KEY).update(cursor=json.dumps(cursor))
            continue
        attempted += int(evaluate_account(
            state_id, cfg=cfg, call=call, budget_scope=COHORT_KEY, initial=True,
        ))
    if cfg.hf_verification_enabled:
        from core.official_company_hf import verify_review_candidates

        verify_review_candidates(limit=1, deadline=deadline, state_ids=list(members))
    report = cohort_report()
    OfficialCompanyScan.objects.filter(key=COHORT_KEY).update(
        enumerated=report["completed"], complete=report["complete"], updated_at=timezone.now(),
    )
    return {"attempted": attempted, **report}
