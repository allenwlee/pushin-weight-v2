"""Bounded identity processing on the existing harvest/enrichment schedule."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

from django.db import connection

from core.product_release_detection_queue import drain_posts
from monitor import pulse_control

logger = logging.getLogger(__name__)
_LOCK_KEY = 0x50554C53454944
_active_identity = ContextVar("pulse_identity_application", default=None)


def identity_control_selected():
    from pathlib import Path

    from x_monitor.config import load_config

    return load_config(Path("config.yaml")).llm.classifier_pipeline == "compressed8_pulse_v1"


def identity_application_active():
    return _active_identity.get() is not None


class _IdentityBoundary:
    status = "busy"

    def allowed(self):
        """Acknowledge only between committed identity units, with the lock held."""
        if connection.in_atomic_block:
            raise ValueError("Pulse identity acknowledgement requires a committed boundary")
        row = pulse_control.read_status()
        self.status = row["status"]
        if self.status == "unavailable":
            return False
        try:
            row = pulse_control.acknowledge(row["desired_revision"], boundary="between_identity_posts")
        except (pulse_control.PulseControlConflict, pulse_control.PulseControlUnavailable):
            self.status = "control_changed"
            return False
        self.status = row["status"]
        return self.status == "running"


@contextmanager
def identity_application():
    """Serialize saved-finding and captured-acquisition identity application.

    Nested saved-run follow-ups finish as part of the current identity unit;
    they must not acknowledge a stop while their outer transaction can write.
    Network collection and evidence capture never enter this boundary.
    """
    active = _active_identity.get()
    if active is not None:
        yield active
        return
    if connection.vendor != "postgresql":
        raise ValueError("Pulse identity processing requires PostgreSQL")
    if connection.in_atomic_block:
        raise ValueError("Acquire the Pulse identity lock before starting a transaction")
    boundary = _IdentityBoundary()
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
        acquired = cursor.fetchone()[0]
    if not acquired:
        yield boundary
        return
    token = _active_identity.set(boundary)
    try:
        boundary.allowed()
        yield boundary
    finally:
        try:
            boundary.allowed()
        finally:
            _active_identity.reset(token)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])


def report_error(*, code, stage, post_id=None, run_id=None):
    """Use the existing bounded file panel; lack of a file never blocks harvest."""
    try:
        pulse_control.record_diagnostic(
            stage=stage[:64], code=code[:64], message="Pulse processing needs investigation.",
            references={key: str(value)[:128] for key, value in (
                ("post_id", post_id), ("run_id", run_id),
            ) if value is not None},
        )
    except pulse_control.PulseControlUnavailable:
        logger.warning("Pulse diagnostic unavailable: %s", code)


def _drain_one_lineage_wakeup(*, max_seconds):
    """Resume one eligible local job, leaving budget-blocked work visible."""
    from core.models import CollectionJob
    from core.product_release_lineage_recovery import drain_lineage_wakeup

    job_id = (CollectionJob.objects.filter(operation="lineage_wakeup", state="ready", last_success__isnull=True)
              .order_by("updated_at", "pk").values_list("pk", flat=True).first())
    if job_id is None:
        return {"status": "idle"}
    return drain_lineage_wakeup(job_id, max_seconds=max_seconds)


def process_saved_findings(*, limit=50, max_seconds=20):
    """Process saved evidence without provider or datasource collection calls.

    One database lock serializes identity processors so an acknowledgement
    means no other processor is still writing identities. Stops are observed
    between posts. Classification and evidence publication do not use this lock.
    """
    result = {"status": "busy", "provider_calls": 0}
    started = monotonic()
    measurements = {"queries": 0, "database_ms": 0.0, "affected_rows": 0}

    def measure(execute, sql, params, many, context):
        start = monotonic()
        try:
            value = execute(sql, params, many, context)
            if sql.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
                measurements["affected_rows"] += max(0, context["cursor"].rowcount)
            return value
        finally:
            measurements["queries"] += 1
            measurements["database_ms"] += (monotonic() - start) * 1000

    with connection.execute_wrapper(measure):
        with identity_application() as boundary:
            if boundary.status == "running":
                if max_seconds >= 2 and boundary.allowed():
                    try:
                        result["lineage_wakeup"] = _drain_one_lineage_wakeup(
                            max_seconds=min(5, max_seconds / 2),
                        )
                        wakeup = result["lineage_wakeup"]
                        if wakeup.get("status") == "budget_blocked":
                            report_error(code="lineage_wakeup_budget_blocked", stage="identity")
                        if wakeup.get("invalid"):
                            report_error(code="lineage_wakeup_invalid_evidence", stage="identity")
                        if wakeup.get("non_x_pending"):
                            report_error(code="lineage_nonx_pending", stage="identity")
                    except Exception:
                        logger.exception("Lineage wakeup recovery failed")
                        report_error(code="lineage_wakeup_error", stage="identity")
                        result["lineage_wakeup"] = {"status": "error"}
                remaining = max_seconds - (monotonic() - started)
                if remaining > 0 and boundary.allowed():
                    result.update(drain_posts(
                        limit=limit, max_seconds=remaining, classified_only=True, before_post=boundary.allowed,
                    ))
                else:
                    result.update(failed=0, association_limited=0)
                if result["failed"]:
                    report_error(code="identity_processing_error", stage="identity")
                if result["association_limited"]:
                    report_error(code="association_candidate_limit", stage="identity")
        result["status"] = boundary.status
    result.update(measurements, elapsed_ms=round((monotonic() - started) * 1000, 3))
    return result
