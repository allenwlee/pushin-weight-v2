"""Frozen, operator-owned official-company queue snapshots."""

import json
import os
import tempfile
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import connection, transaction

from core.models import OfficialCompanyAccountState, OfficialCompanyAttempt
from core.official_company_accounts import digest


def _encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _timestamp(value):
    return value.isoformat() if value else None


def _database_identity():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
        )
        name, host, port = cursor.fetchone()
    return {"name": name, "host": host, "port": port}


def freeze_queue(*, path, total_limit):
    """Freeze all queued tiers in one repeatable-read snapshot before any call."""
    total_limit = Decimal(total_limit)
    if not total_limit.is_finite() or total_limit <= 0:
        raise ValueError("total limit must be positive and finite")
    if connection.in_atomic_block:
        raise ValueError("snapshot requires an outermost transaction")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SELECT transaction_timestamp()")
            cutoff = cursor.fetchone()[0]
        database = _database_identity()
        states = list(
            OfficialCompanyAccountState.objects.filter(
                status__in=("pending", "retry_due", "claimed"),
                candidate_priority__in=(1, 2, 3),
            )
            .order_by("candidate_priority", "pk")
            .values(
                "id",
                "account_id",
                "evidence_hash",
                "status",
                "candidate_priority",
                "next_attempt_at",
                "claim_token",
                "claim_expires_at",
            )
        )
        tokens = [s["claim_token"] for s in states if s["claim_token"]]
        attempt_ids = dict(
            OfficialCompanyAttempt.objects.filter(claim_token__in=tokens).values_list(
                "claim_token", "id"
            )
        )
        members = [
            {
                "state_id": s["id"],
                "account_key": str(s["account_id"]),
                "evidence_hash": s["evidence_hash"],
                "starting_status": s["status"],
                "priority": s["candidate_priority"],
                "next_attempt_at": _timestamp(s["next_attempt_at"]),
                "claim_token": s["claim_token"],
                "claim_expires_at": _timestamp(s["claim_expires_at"]),
                "attempt_id": attempt_ids.get(s["claim_token"]),
            }
            for s in states
        ]
    manifest = {
        "version": 1,
        "run_id": uuid.uuid4().hex,
        "database": database,
        "cutoff": cutoff.isoformat(),
        "total_limit_usd": str(total_limit),
        "count": len(members),
        "members": members,
    }
    manifest["sha256"] = digest(manifest)
    path = Path(path)
    fd, temp_path = tempfile.mkstemp(prefix=".queue-pass-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(_encoded(manifest) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Linking, unlike replace, refuses to overwrite an existing manifest.
        os.link(temp_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temp_path)
    return manifest


def read_manifest(path):
    manifest = json.loads(Path(path).read_text())
    if not isinstance(manifest, dict):
        raise ValueError("invalid manifest format")  # noqa: TRY004
    checksum = manifest.pop("sha256", None)
    if checksum != digest(manifest):
        raise ValueError("manifest checksum mismatch")
    manifest["sha256"] = checksum
    if (
        manifest.get("version") != 1
        or not isinstance(manifest.get("members"), list)
        or manifest.get("count") != len(manifest["members"])
    ):
        raise ValueError("invalid manifest format")
    try:
        run_id = uuid.UUID(hex=manifest["run_id"])
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError("invalid run ID") from None
    if run_id.hex != manifest["run_id"]:
        raise ValueError("invalid run ID")
    if any(
        not isinstance(member, dict)
        or not isinstance(member.get("state_id"), int)
        or not isinstance(member.get("account_key"), str)
        or not isinstance(member.get("evidence_hash"), str)
        or member.get("priority") not in (1, 2, 3)
        or member.get("starting_status") not in ("pending", "retry_due", "claimed")
        or not {"claim_token", "claim_expires_at", "attempt_id", "next_attempt_at"}
        <= member.keys()
        for member in manifest["members"]
    ):
        raise ValueError("invalid manifest member")
    ids = [m["state_id"] for m in manifest["members"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate state IDs")
    try:
        limit = Decimal(manifest["total_limit_usd"])
    except (KeyError, InvalidOperation):
        raise ValueError("invalid total limit") from None
    if not limit.is_finite() or limit <= 0:
        raise ValueError("invalid total limit")
    from django.utils.dateparse import parse_datetime

    try:
        cutoff = parse_datetime(manifest["cutoff"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("invalid cutoff") from None
    if cutoff is None or cutoff.utcoffset() is None:
        raise ValueError("invalid cutoff")
    if manifest.get("database") != _database_identity():
        raise ValueError("manifest database does not match connection")
    return manifest


def report(manifest):
    """Reconcile every frozen member against state and immutable attempt rows."""
    from collections import Counter

    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    from core.models import OfficialCompanyBudget

    members = manifest["members"]
    ids = [m["state_id"] for m in members]
    states = {
        s.pk: s
        for s in OfficialCompanyAccountState.objects.filter(pk__in=ids).only(
            "id",
            "account_id",
            "evidence_hash",
            "status",
            "claim_expires_at",
            "next_attempt_at",
        )
    }
    cutoff = parse_datetime(manifest["cutoff"])
    attempt_ids = [m["attempt_id"] for m in members if m["attempt_id"]]
    from django.db.models import Q

    attempts = (
        OfficialCompanyAttempt.objects.filter(state_id__in=ids)
        .filter(Q(created_at__gte=cutoff) | Q(pk__in=attempt_ids))
        .only(
            "id",
            "state_id",
            "evidence_hash",
            "actual_usd",
            "status",
            "decision",
            "model",
            "budget_keys",
            "created_at",
        )
        .order_by("created_at", "pk")
    )
    by_state = {}
    for attempt in attempts.iterator(chunk_size=500):
        by_state.setdefault(attempt.state_id, []).append(attempt)
    now = timezone.now()
    rows = []
    for member in members:
        state = states.get(member["state_id"])
        row = {"state_id": member["state_id"], "starting_priority": member["priority"]}
        relevant = [
            a
            for a in by_state.get(member["state_id"], [])
            if a.evidence_hash == member["evidence_hash"]
        ]
        if state is None or str(state.account_id) != member["account_key"]:
            row["disposition"] = "identity_unavailable"
        elif state.evidence_hash != member["evidence_hash"]:
            row["disposition"] = "changed_evidence"
        elif state.status in ("suppressed", "registered"):
            row["disposition"] = state.status
        elif any(a.actual_usd is None for a in relevant):
            active = (
                state.status == "claimed"
                and state.claim_expires_at
                and state.claim_expires_at > now
            )
            row["disposition"] = "in_flight" if active else "unknown_call"
        elif relevant:
            attempt = relevant[-1]
            row["attempt_id"] = attempt.pk
            row["disposition"] = (
                "completed" if attempt.status == "completed" else "failed"
            )
            row["outcome"] = (
                attempt.decision.get("outcome")
                if isinstance(attempt.decision, dict)
                else None
            )
            row["model"] = attempt.model
            row["run_attempt"] = (
                "queue-pass:" + manifest["run_id"] in attempt.budget_keys
            )
        elif (
            state.status == "claimed"
            and state.claim_expires_at
            and state.claim_expires_at > now
        ):
            row["disposition"] = "in_flight"
        elif state.next_attempt_at and state.next_attempt_at > now:
            row["disposition"] = "waiting_retry"
        elif state.status not in ("pending", "retry_due", "claimed"):
            row["disposition"] = "settled_or_review"
        else:
            row["disposition"] = "pending"
        rows.append(row)
    budget = OfficialCompanyBudget.objects.filter(
        pk="queue-pass:" + manifest["run_id"]
    ).first()
    by_priority = {
        str(priority): dict(
            Counter(
                row["disposition"]
                for row in rows
                if row["starting_priority"] == priority
            )
        )
        for priority in (1, 2, 3)
    }
    outcomes_by_priority = {
        str(priority): dict(
            Counter(
                row["outcome"]
                for row in rows
                if row["starting_priority"] == priority
                and row["disposition"] == "completed"
                and row.get("outcome")
            )
        )
        for priority in (1, 2, 3)
    }
    queue_key = "queue-pass:" + manifest["run_id"]
    own_attempts = [
        attempt
        for state_attempts in by_state.values()
        for attempt in state_attempts
        if queue_key in attempt.budget_keys
    ]
    return {
        "run_id": manifest["run_id"],
        "cutoff": manifest["cutoff"],
        "count": len(rows),
        "counts": dict(Counter(r["disposition"] for r in rows)),
        "counts_by_starting_priority": by_priority,
        "outcomes_by_starting_priority": outcomes_by_priority,
        "recorded_attempts": len(own_attempts),
        "attempts_with_unknown_cost": sum(a.actual_usd is None for a in own_attempts),
        "actual_usd": str(budget.spent_usd if budget else 0),
        "reserved_usd": str(budget.reserved_usd if budget else 0),
        "members": rows,
    }


def _acknowledgements(path, manifest):
    try:
        receipt = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}
    if not isinstance(receipt, dict):
        raise ValueError("invalid failure acknowledgement")  # noqa: TRY004
    checksum = receipt.pop("sha256", None)
    if (
        checksum != digest(receipt)
        or receipt.get("run_id") != manifest["run_id"]
        or receipt.get("version") != 1
    ):
        raise ValueError("invalid failure acknowledgement")
    entries = receipt.get("attempts")
    if not isinstance(entries, dict):
        raise ValueError("invalid failure acknowledgement")  # noqa: TRY004
    return entries


def _write_receipt(path, value):
    value = dict(value)
    value["sha256"] = digest(value)
    path = Path(path)
    fd, temp_path = tempfile.mkstemp(prefix=".queue-receipt-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(_encoded(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def acknowledge_failure(manifest, *, attempt_id, reason, acknowledgement_path):
    """Record an investigated known-cost failure without retrying it."""
    from core.official_company_lock import official_company_writer_lock

    if not reason or not reason.strip() or len(reason) > 500:
        raise ValueError("a bounded investigation reason is required")
    with official_company_writer_lock(
        execution_mode="manual", entrypoint="queue-ack", run_id=manifest["run_id"]
    ) as lease:
        if not lease.acquired:
            raise ValueError("discovery lock busy")
        attempt = OfficialCompanyAttempt.objects.filter(
            pk=attempt_id,
            status="failed",
            actual_usd__isnull=False,
            budget_keys__contains=["queue-pass:" + manifest["run_id"]],
            state_id__in=[m["state_id"] for m in manifest["members"]],
        ).first()
        if attempt is None:
            raise ValueError("attempt is not a known-cost failure from this run")
        entries = _acknowledgements(acknowledgement_path, manifest)
        if str(attempt.pk) in entries and entries[str(attempt.pk)] != reason.strip():
            raise ValueError("failure was already acknowledged with a different reason")
        entries[str(attempt.pk)] = reason.strip()
        _write_receipt(
            acknowledgement_path,
            {"version": 1, "run_id": manifest["run_id"], "attempts": entries},
        )
        return {"acknowledged_attempt": attempt.pk}


def _run_guard(manifest, acknowledgement_path):
    """Check all this run's attempts again while holding the discovery lock."""
    acknowledged = _acknowledgements(acknowledgement_path, manifest)
    attempts = OfficialCompanyAttempt.objects.filter(
        budget_keys__contains=["queue-pass:" + manifest["run_id"]]
    ).values_list("id", "status", "actual_usd")
    for attempt_id, status, actual in attempts:
        if actual is None:
            return "unresolved_run_attempt"
        if status != "completed" and str(attempt_id) not in acknowledged:
            return "evaluation_failed"
    return None


def _proof_matches(path, manifest, cfg, call):
    from core.models import OfficialCompanyProviderState

    path = Path(path)
    try:
        proof = json.loads(path.read_text())
    except FileNotFoundError:
        return False
    if not isinstance(proof, dict):
        raise ValueError("invalid verification receipt")  # noqa: TRY004
    checksum = proof.pop("sha256", None)
    if checksum != digest(proof) or proof.get("version") != 1:
        raise ValueError("invalid verification receipt")
    revision = getattr(call, "credential_revision", None)
    if not isinstance(revision, str):
        revision = None
    if (proof.get("run_id"), proof.get("model"), proof.get("credential_revision")) != (
        manifest["run_id"],
        cfg.model,
        revision,
    ):
        return False
    if (
        revision is not None
        and not OfficialCompanyProviderState.objects.filter(
            key="deepinfra", credential_revision=revision, blocked_reason=""
        ).exists()
    ):
        return False
    member = next(
        (m for m in manifest["members"] if m["state_id"] == proof.get("state_id")), None
    )
    if member is None:
        raise ValueError("verification receipt is outside the snapshot")
    row = report({**manifest, "members": [member]})["members"][0]
    return (
        row.get("attempt_id") == proof.get("attempt_id")
        and row["disposition"] == "completed"
        and row.get("run_attempt")
        and row.get("model") == cfg.model
        and row.get("outcome") in {"accepted", "rejected", "review_needed"}
    )


def _write_proof(path, manifest, cfg, call, row):
    from core.models import OfficialCompanyProviderState

    revision = getattr(call, "credential_revision", None)
    if not isinstance(revision, str):
        revision = None
    if (
        revision is not None
        and not OfficialCompanyProviderState.objects.filter(
            key="deepinfra", credential_revision=revision, blocked_reason=""
        ).exists()
    ):
        return False
    proof = {
        "version": 1,
        "run_id": manifest["run_id"],
        "model": cfg.model,
        "credential_revision": revision,
        "state_id": row["state_id"],
        "attempt_id": row["attempt_id"],
    }
    _write_receipt(path, proof)
    return True


def run_batch(manifest, *, cfg, call, limit, seconds, receipt_path):
    """One bounded invocation. Never hold the discovery lock between calls."""
    import time

    from core.official_company_accounts import evaluate_account
    from core.official_company_lock import official_company_writer_lock

    if not 1 <= limit <= 500 or not 1 <= seconds <= 3600:
        raise ValueError("invalid batch bound")
    started = time.monotonic()
    deadline = started + seconds
    batch_scope = "queue-" + uuid.uuid4().hex
    run_budget = (
        "queue-pass:" + manifest["run_id"],
        Decimal(manifest["total_limit_usd"]),
    )
    acknowledgement_path = str(receipt_path) + ".acknowledged.json"
    initial_report = report(manifest)
    initial_stop = _run_guard(manifest, acknowledgement_path)
    if initial_stop:
        return {
            "evaluator_invocations": 0,
            "reason": initial_stop,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "report": initial_report,
        }
    calls = 0
    reason = "complete"
    members_by_id = {m["state_id"]: m for m in manifest["members"]}
    for row in initial_report["members"]:
        if row["disposition"] != "pending":
            continue
        if (
            calls >= limit
            or time.monotonic() + cfg.request_timeout_seconds + 2 > deadline
        ):
            reason = "batch_bound"
            break
        member = members_by_id[row["state_id"]]
        with official_company_writer_lock(
            execution_mode="manual", entrypoint="queue-pass", run_id=manifest["run_id"]
        ) as lease:
            if not lease.acquired:
                reason = "discovery_busy"
                break
            reason = _run_guard(manifest, acknowledgement_path)
            if reason:
                break
            verified = _proof_matches(receipt_path, manifest, cfg, call)
            current = report({**manifest, "members": [member]})["members"][0]
            if current["disposition"] != "pending":
                continue
            made = evaluate_account(
                member["state_id"],
                cfg=cfg,
                call=call,
                budget_scope=batch_scope,
                expected_account_key=member["account_key"],
                expected_evidence_hash=member["evidence_hash"],
                run_budget=run_budget,
            )
            if not made:
                reason = "claim_or_budget_blocked"
                break
            calls += 1
            outcome = report({**manifest, "members": [member]})["members"][0]
            if outcome["disposition"] != "completed" or outcome.get("outcome") not in {
                "accepted",
                "rejected",
                "review_needed",
            }:
                reason = "evaluation_not_verified"
                break
            if not verified:
                reason = (
                    "verification_complete"
                    if _write_proof(receipt_path, manifest, cfg, call, outcome)
                    else "verification_invalidated"
                )
                break
        # Give scheduled discovery a chance to acquire the separate lock.
        if calls < limit and time.monotonic() + 5 < deadline:
            time.sleep(5)
    return {
        "evaluator_invocations": calls,
        "reason": reason or "complete",
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "report": report(manifest),
    }
