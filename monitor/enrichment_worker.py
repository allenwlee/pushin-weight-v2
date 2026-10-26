"""Continuous scheduling around CycleRunner's one enrichment implementation."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any

from django.db import connections, transaction

from monitor.enrichment_budget import config_fingerprint, reserve_request
from monitor.run_lock import _lock_keys
from scripts.database_lock import (
    DatabaseLockError,
    acquire_enrichment_coordination_lock,
)
from x_monitor.attribution import LLMCallBudgetExhausted


@dataclass
class ProcessLease:
    connection: Any
    keys: tuple[int, int]
    backend_pid: int
    coordination_connection: Any = None

    def assert_held(self):
        # Use the original driver connection. Never reconnect after loss.
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                if cursor.fetchone()[0] != self.backend_pid:
                    raise DatabaseLockError("enrichment_process_lock_lost")
            if self.coordination_connection is not None:
                with self.coordination_connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
        except Exception as exc:
            raise LLMCallBudgetExhausted("enrichment_process_lock_lost") from exc


@contextmanager
def process_slot(config, *, environment: str | None = None):
    database = connections["default"]
    if database.vendor != "postgresql":
        raise DatabaseLockError("enrichment_requires_postgresql")
    environment = (
        environment
        or os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
        or str(database.settings_dict["NAME"])
    )
    url = os.environ.get("DATABASE_URL")
    coordination = (
        acquire_enrichment_coordination_lock(url, environment=environment, shared=True)
        if url
        else nullcontext(None)
    )
    # An independent connection makes the lock survive ordinary ORM cleanup,
    # and lets provider threads check it without borrowing a Django connection.
    with coordination as admin:
        connection = database.get_new_connection(database.get_connection_params())
        connection.autocommit = True
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
                selected = None
                for slot in range(1, config.max_worker_processes + 1):
                    keys = _lock_keys(environment, f"enrichment-writer:slot:{slot}")[:2]
                    cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", keys)
                    if cursor.fetchone()[0]:
                        selected = keys
                        break
            if selected is None:
                yield None
                return
            try:
                yield ProcessLease(connection, selected, pid, admin)
            finally:
                if not connection.closed:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s, %s)", selected)


class DispatchGuard:
    def __init__(self, *, cfg, lease, scope="scheduled", stop_event=None):
        self.cfg = cfg
        self.lease = lease
        self.scope = scope
        self.stop_event = stop_event or threading.Event()
        self.fingerprint = config_fingerprint(cfg)
        self.calls = 0
        self.prepaid = 0
        self.error_code = ""
        self._lock = threading.Lock()
        self.deadline = (
            time.monotonic() + cfg.harvest.enrichment.claim_safe_envelope_seconds
        )

    def __call__(self, request):
        with self._lock:
            try:
                if self.stop_event.is_set():
                    raise LLMCallBudgetExhausted("enrichment_stopping")
                self.lease.assert_held()
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise LLMCallBudgetExhausted("enrichment_batch_deadline")
                request["timeout"] = min(
                    float(
                        request.get(
                            "timeout",
                            self.cfg.harvest.enrichment.request_timeout_seconds,
                        )
                    ),
                    remaining,
                )
                prepaid = request.pop("_enrichment_budget_prepaid", False)
                if prepaid:
                    if self.prepaid <= 0:
                        raise LLMCallBudgetExhausted(
                            "enrichment_pair_reservation_missing"
                        )
                    self.prepaid -= 1
                    return
                if self.calls >= self.cfg.harvest.enrichment.max_calls_per_batch:
                    raise LLMCallBudgetExhausted("enrichment_batch_budget_exhausted")
                window_id = self.cfg.harvest.enrichment.budget_window_id
                if window_id:
                    reserve_request(
                        window_id=window_id,
                        fingerprint=self.fingerprint,
                        request=request,
                        scope=self.scope,
                    )
                elif self.cfg.harvest.enrichment.mode == "worker":
                    raise LLMCallBudgetExhausted("enrichment_budget_missing")
                self.calls += 1
            except LLMCallBudgetExhausted as exc:
                self.error_code = str(exc)
                raise

    def reserve_pair(self, requests, attempts_per_role):
        """Debit both roles and retry envelopes atomically, before dispatch."""
        with self._lock:
            try:
                if self.stop_event.is_set():
                    raise LLMCallBudgetExhausted("enrichment_stopping")
                self.lease.assert_held()
                if time.monotonic() >= self.deadline:
                    raise LLMCallBudgetExhausted("enrichment_batch_deadline")
                if not isinstance(requests, list) or len(requests) != 2:
                    raise LLMCallBudgetExhausted("enrichment_pair_bounds_missing")
                required = 2 * attempts_per_role
                if (
                    self.calls + required
                    > self.cfg.harvest.enrichment.max_calls_per_batch
                ):
                    raise LLMCallBudgetExhausted("enrichment_batch_budget_exhausted")
                window_id = self.cfg.harvest.enrichment.budget_window_id
                if window_id:
                    with transaction.atomic():
                        for request in requests:
                            for _ in range(attempts_per_role):
                                reserve_request(
                                    window_id=window_id,
                                    fingerprint=self.fingerprint,
                                    request=request,
                                    scope=self.scope,
                                )
                elif self.cfg.harvest.enrichment.mode == "worker":
                    raise LLMCallBudgetExhausted("enrichment_budget_missing")
                self.calls += required
                self.prepaid += required
            except LLMCallBudgetExhausted as exc:
                self.error_code = str(exc)
                raise


def process_enrichment_batch(
    runner, kept_posts, *, stop_event=None, scope="scheduled", **kwargs
):
    """One bounded batch; never invokes collection, metrics or cursor work."""
    config = runner.cfg.harvest.enrichment
    with process_slot(config) as lease:
        if lease is None:
            return {
                "n_enrichment_claimed": 0,
                "enrichment_deferred_reason": "process_slots_busy",
            }
        guard = DispatchGuard(
            cfg=runner.cfg, lease=lease, scope=scope, stop_event=stop_event
        )
        previous_calls = runner._targeted_extraction_calls
        if kwargs.get("fair_queue"):
            from core.targeted_extraction import build_targeted_extraction_calls
            from monitor.cycle import _BoundedClassifierClient
            from x_monitor.reattribute import build_relevancy_client_from_env

            client = build_relevancy_client_from_env(
                runner.cfg,
                **(
                    {"deepinfra_key_env": "DEEPINFRA_ON_DEMAND"}
                    if scope == "pilot"
                    else {}
                ),
            )
            guarded_client = (
                _BoundedClassifierClient(
                    client,
                    maximum_calls=config.max_calls_per_batch,
                    pause_seconds=0,
                    before_dispatch=guard,
                )
                if client
                else None
            )
            runner._targeted_extraction_calls = build_targeted_extraction_calls(
                client=guarded_client,
                roles=runner.cfg.targeted_extraction.roles,
                timeout_seconds=runner.cfg.targeted_extraction.request_timeout_seconds,
            )
        try:
            result = runner._process_enrichment_claim_batch(
                kept_posts, dispatch_guard=guard, **kwargs
            )
            if kwargs.get("fair_queue") and runner.cfg.discovery.rare_types.enabled:
                from django.utils import timezone

                from core.models import RareTypeSearchHit
                from core.rare_type_search import reconcile_classified_hits

                post_ids = {
                    row["post_id"] for row in result.get("enrichment_state_facts", [])
                }
                hit_ids = set(
                    RareTypeSearchHit.objects.filter(post_id__in=post_ids).values_list(
                        "pk", flat=True
                    )
                )
                result["rare_hits_reconciled"] = reconcile_classified_hits(
                    now=timezone.now(), limit=len(hit_ids), hit_ids=hit_ids
                )
            result.update(
                reserved_dispatches=guard.calls,
                provider_requests=runner._llm_call_count
                + result.get("n_targeted_extraction_calls", 0),
                enrichment_stop_reason=guard.error_code,
            )
            lease.assert_held()
            return result
        finally:
            runner._targeted_extraction_calls = previous_calls
            from core.models import PostEnrichmentState

            if kwargs.get("run_id"):
                PostEnrichmentState.objects.filter(
                    claim_run_id=str(kwargs["run_id"])[:128]
                ).update(
                    claim_owner="",
                    claim_run_id="",
                    claimed_at=None,
                    claim_expires_at=None,
                )
