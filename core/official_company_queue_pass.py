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
            "SELECT current_database(), system_identifier::text FROM pg_control_system()"
        )
        name, system_identifier = cursor.fetchone()
    return {"name": name, "system_identifier": system_identifier}


def _environment(manifest=None):
    value = os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
    if value not in {"production", "staging", "test"}:
        raise ValueError("explicit X_MONITOR_DEPLOYMENT_ENVIRONMENT is required")
    database = _database_identity()
    expected_targets = {
        "production": ("pushinweight_shadow", "7667808775691038771"),
        "staging": ("pushinweight_staging", "7673769124639031347"),
    }
    if value == "test":
        if not database["name"].startswith("test_pw_queue_pass_") or database[
            "system_identifier"
        ] not in {
            "7693527921830478235",  # Local shared PostgreSQL server on fuchitalee.
            "7673769124639031347",  # Staging PostgreSQL server.
        }:
            raise ValueError(
                "test environment requires an approved fixture-only database"
            )
    elif (database["name"], database["system_identifier"]) != expected_targets[value]:
        raise ValueError("deployment environment does not match database identity")
    if manifest is not None and manifest.get("lock_environment") != value:
        raise ValueError("manifest lock environment does not match the process")
    if manifest is not None and manifest.get("database") != database:
        raise ValueError("manifest database does not match connection")
    return value


def freeze_queue(*, path, total_limit):
    """Freeze all queued tiers in one repeatable-read snapshot before any call."""
    total_limit = Decimal(total_limit)
    if not total_limit.is_finite() or total_limit <= 0:
        raise ValueError("total limit must be positive and finite")
    if connection.in_atomic_block:
        raise ValueError("snapshot requires an outermost transaction")
    environment = _environment()
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
        baseline_attempts = {}
        for state_id, attempt_id in (
            OfficialCompanyAttempt.objects.filter(
                state_id__in=[s["id"] for s in states]
            )
            .values_list("state_id", "id")
            .iterator(chunk_size=500)
        ):
            baseline_attempts.setdefault(state_id, []).append(attempt_id)
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
                "baseline_attempt_ids": baseline_attempts.get(s["id"], []),
            }
            for s in states
        ]
    manifest = {
        "version": 1,
        "run_id": uuid.uuid4().hex,
        "database": database,
        "lock_environment": environment,
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
        or not isinstance(member.get("baseline_attempt_ids"), list)
        or any(not isinstance(pk, int) for pk in member["baseline_attempt_ids"])
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
    _environment(manifest)
    return manifest


def _report_snapshot(manifest):
    """Reconcile every frozen member against state and immutable attempt rows."""
    from collections import Counter

    from django.utils import timezone

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
    attempts = (
        OfficialCompanyAttempt.objects.filter(state_id__in=ids)
        .only(
            "id",
            "state_id",
            "evidence_hash",
            "actual_usd",
            "input_tokens",
            "output_tokens",
            "reserved_usd",
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
        baseline_ids = set(member["baseline_attempt_ids"])
        relevant = [
            a
            for a in by_state.get(member["state_id"], [])
            if a.evidence_hash == member["evidence_hash"]
            and (a.pk not in baseline_ids or a.pk == member["attempt_id"])
        ]
        unknown_ids = [
            a.pk
            for a in by_state.get(member["state_id"], [])
            if a.actual_usd is None and a.reserved_usd > 0
        ]
        if unknown_ids:
            row["unresolved_attempt_ids"] = unknown_ids
        if state is None or str(state.account_id) != member["account_key"]:
            row["disposition"] = "identity_unavailable"
        elif state.evidence_hash != member["evidence_hash"]:
            row["disposition"] = "changed_evidence"
        elif state.status in ("suppressed", "registered"):
            row["disposition"] = state.status
        elif relevant and relevant[-1].status == "owner_attested":
            row["disposition"] = "owner_settled"
        elif (
            relevant
            and relevant[-1].status == "completed"
            and relevant[-1].actual_usd is not None
        ):
            attempt = relevant[-1]
            row["attempt_id"] = attempt.pk
            row["disposition"] = "completed"
            row["outcome"] = (
                attempt.decision.get("outcome")
                if isinstance(attempt.decision, dict)
                else None
            )
            row["model"] = attempt.model
            row["input_tokens"] = attempt.input_tokens
            row["output_tokens"] = attempt.output_tokens
            row["actual_usd"] = str(attempt.actual_usd)
            row["run_attempt"] = (
                "queue-pass:" + manifest["run_id"] in attempt.budget_keys
            )
        elif unknown_ids or any(a.actual_usd is None for a in relevant):
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
            row["input_tokens"] = attempt.input_tokens
            row["output_tokens"] = attempt.output_tokens
            row["actual_usd"] = str(attempt.actual_usd)
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
        "cost_basis": "configured_usage_rates_or_evidenced_reconciliation",
        "reserved_usd": str(budget.reserved_usd if budget else 0),
        "members": rows,
    }


def report(manifest):
    """Reconcile states and attempts at a single database observation time."""
    if connection.in_atomic_block:
        raise ValueError("report requires an outermost transaction")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT transaction_timestamp()")
            observed = cursor.fetchone()[0]
        result = _report_snapshot(manifest)
        result["observed_at"] = observed.isoformat()
        return result


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

    _environment(manifest)
    if not reason or not reason.strip() or len(reason) > 500:
        raise ValueError("a bounded investigation reason is required")
    if yield_reason := _harvest_yield_reason(0):
        raise ValueError(yield_reason)
    with official_company_writer_lock(
        execution_mode="manual", entrypoint="queue-ack", run_id=manifest["run_id"]
    ) as lease:
        if not lease.acquired:
            raise ValueError("discovery lock busy")
        if yield_reason := _harvest_yield_reason(0):
            raise ValueError(yield_reason)
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


def reconcile_uncertain(
    manifest, *, attempt_id, actual_usd, evidence, reconciliation_path
):
    """Settle a known provider charge without inventing a model decision."""
    from django.utils import timezone

    from core.models import OfficialCompanyBudget
    from core.official_company_lock import official_company_writer_lock

    _environment(manifest)
    try:
        actual = Decimal(actual_usd)
    except (InvalidOperation, TypeError):
        raise ValueError("a verified actual cost is required") from None
    if (
        not actual.is_finite()
        or actual < 0
        or actual > Decimal("999999.9999999999")
        or actual != actual.quantize(Decimal("0.0000000001"))
    ):
        raise ValueError("actual cost is outside supported precision")
    if not evidence or not evidence.strip() or len(evidence) > 500:
        raise ValueError("a bounded provider evidence reference is required")
    if yield_reason := _harvest_yield_reason(0):
        raise ValueError(yield_reason)
    with official_company_writer_lock(
        execution_mode="manual", entrypoint="queue-reconcile", run_id=manifest["run_id"]
    ) as lease:
        if not lease.acquired:
            raise ValueError("discovery lock busy")
        if yield_reason := _harvest_yield_reason(0):
            raise ValueError(yield_reason)
        with transaction.atomic():
            attempt = (
                OfficialCompanyAttempt.objects.select_for_update()
                .filter(
                    pk=attempt_id,
                    budget_keys__contains=["queue-pass:" + manifest["run_id"]],
                    state_id__in=[m["state_id"] for m in manifest["members"]],
                )
                .first()
            )
            if attempt is None or attempt.status not in (
                "failed",
                "reserved",
                "completed",
            ):
                raise ValueError("attempt is not an unresolved call from this run")
            state = OfficialCompanyAccountState.objects.select_for_update().get(
                pk=attempt.state_id
            )
            if (
                state.claim_token == attempt.claim_token
                and state.claim_expires_at
                and state.claim_expires_at > timezone.now()
            ):
                raise ValueError("attempt claim is still active")
            entries = _acknowledgements(reconciliation_path, manifest)
            entry = {"actual_usd": str(actual), "evidence": evidence.strip()}
            previous = entries.get(str(attempt.pk))
            if previous is not None and previous != entry:
                raise ValueError(
                    "attempt already has different reconciliation evidence"
                )
            if attempt.actual_usd is not None:
                if previous == entry and attempt.actual_usd == actual:
                    return {
                        "reconciled_attempt": attempt.pk,
                        "already_reconciled": True,
                    }
                raise ValueError("attempt already has a recorded cost")
            budgets = [
                OfficialCompanyBudget.objects.select_for_update().get(pk=key)
                for key in sorted(attempt.budget_keys)
            ]
            if any(b.reserved_usd < attempt.reserved_usd for b in budgets):
                raise ValueError("budget reservation does not match attempt")
            entries[str(attempt.pk)] = entry
            _write_receipt(
                reconciliation_path,
                {"version": 1, "run_id": manifest["run_id"], "attempts": entries},
            )
            for budget in budgets:
                budget.reserved_usd -= attempt.reserved_usd
                budget.spent_usd += actual
                budget.save(update_fields=["reserved_usd", "spent_usd"])
            attempt.actual_usd = actual
            if attempt.status == "reserved":
                attempt.status = "failed"
                attempt.error_code = "reconciled_unknown_outcome"
                attempt.completed_at = timezone.now()
            attempt.save(
                update_fields=["actual_usd", "status", "error_code", "completed_at"]
            )
            if state.claim_token == attempt.claim_token:
                state.status = "review_needed"
                state.last_error = "reconciled_unknown_outcome"
                state.claim_token = ""
                state.claim_expires_at = None
                state.next_attempt_at = None
                state.save(
                    update_fields=[
                        "status",
                        "last_error",
                        "claim_token",
                        "claim_expires_at",
                        "next_attempt_at",
                        "updated_at",
                    ]
                )
            return {"reconciled_attempt": attempt.pk, "already_reconciled": False}


def _run_guard(manifest, acknowledgement_path):
    """Check all this run's attempts again while holding the discovery lock."""
    acknowledged = _acknowledgements(acknowledgement_path, manifest)
    attempts = OfficialCompanyAttempt.objects.filter(
        budget_keys__contains=["queue-pass:" + manifest["run_id"]]
    )
    if attempts.filter(actual_usd__isnull=True).exists():
        return "unresolved_run_attempt"
    if attempts.exclude(status="completed").exclude(pk__in=list(acknowledged)).exists():
        return "evaluation_failed"
    return None


def _near_scheduled_tick(timeout):
    import time

    elapsed = time.time() % 900
    return elapsed < 120 or 900 - elapsed <= timeout + 60


def _harvest_yield_reason(timeout):
    """Yield around scheduled ticks and while another harvest owns its lock."""
    from monitor.run_lock import _lock_keys

    if _near_scheduled_tick(timeout):
        return "scheduled_harvest_window"
    environment = (
        os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
        or os.environ.get("RENDER_GIT_BRANCH")
        or str(connection.settings_dict.get("NAME") or "default")
    )
    _, _, class_id, object_id = _lock_keys(environment)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM pg_locks
              WHERE locktype = 'advisory' AND granted AND objsubid = 2
                AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
                AND classid::bigint = %s AND objid::bigint = %s
            )
            """,
            [class_id, object_id],
        )
        return "harvest_active" if cursor.fetchone()[0] else None


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
    if (
        proof.get("run_id"),
        proof.get("model"),
        proof.get("credential_revision"),
        proof.get("input_usd_per_million"),
        proof.get("output_usd_per_million"),
    ) != (
        manifest["run_id"],
        cfg.model,
        revision,
        str(cfg.input_usd_per_million),
        str(cfg.output_usd_per_million),
    ):
        return False
    if (
        revision is not None
        and not OfficialCompanyProviderState.objects.filter(
            key="deepinfra-on-demand", credential_revision=revision, blocked_reason=""
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
            key="deepinfra-on-demand", credential_revision=revision, blocked_reason=""
        ).exists()
    ):
        return False
    proof = {
        "version": 1,
        "run_id": manifest["run_id"],
        "model": cfg.model,
        "credential_revision": revision,
        "input_usd_per_million": str(cfg.input_usd_per_million),
        "output_usd_per_million": str(cfg.output_usd_per_million),
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

    _environment(manifest)
    if not 1 <= limit <= 500 or not 1 <= seconds <= 3600:
        raise ValueError("invalid batch bound")
    if cfg.input_usd_per_million <= 0 or cfg.output_usd_per_million <= 0:
        raise ValueError("positive configured input and output prices are required")
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
    reason = "batch_finished"
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
        reason = _harvest_yield_reason(cfg.request_timeout_seconds)
        if reason:
            break
        with official_company_writer_lock(
            execution_mode="manual", entrypoint="queue-pass", run_id=manifest["run_id"]
        ) as lease:
            if not lease.acquired:
                reason = "discovery_busy"
                break
            reason = _harvest_yield_reason(cfg.request_timeout_seconds)
            if reason:
                break
            reason = _run_guard(manifest, acknowledgement_path)
            if reason:
                break
            verified = _proof_matches(receipt_path, manifest, cfg, call)
            current = report({**manifest, "members": [member]})["members"][0]
            if current["disposition"] != "pending":
                continue
            if time.monotonic() + cfg.request_timeout_seconds + 2 > deadline:
                reason = "batch_bound"
                break
            reason = _harvest_yield_reason(cfg.request_timeout_seconds)
            if reason:
                break
            made = evaluate_account(
                member["state_id"],
                cfg=cfg,
                call=call,
                budget_scope=batch_scope,
                expected_account_key=member["account_key"],
                expected_evidence_hash=member["evidence_hash"],
                run_budget=run_budget,
                provider_state_key="deepinfra-on-demand",
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
        "reason": reason or "batch_finished",
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "report": report(manifest),
    }
