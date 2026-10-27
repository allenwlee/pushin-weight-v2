"""Bounded streaming acquisition into staging, without full response archives.

The controller alone uses the ORM. Futures own at most one response per scope;
the shared page writer commits its Posts and cursor before that scope can refill.
Recorded transient GET failures may be retried without erasing unknown billing.
An interrupted send without a recorded outcome still requires reconciliation.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import copy
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db.models import Sum

from core.collection_capture import begin_request, finish_request
from core.collection_staging import (
    adopt_retry_state,
    adopt_staging_receipt,
    ensure_staging_bytes,
    write_staging_receipt,
)
from core.collection_state import fenced_run, x_scope_ownership
from core.measurement_taxonomy import require
from core.models import (
    Brand,
    CollectionAttempt,
    CollectionRequest,
    CollectionRun,
    CollectionScopeRequestUse,
    CollectionScopeRun,
)
from monitor.backfill_prefetch import (
    CapturedPage,
    Prefetcher,
    _endpoint,
    _params,
    _request_identity,
    fetch_page,
)
from monitor.backfill_retry import PAGE_FAILURE_LIMIT, POLICY, transient
from monitor.run_lock import backfill_yield_requested, harvest_writer_lock
from x_monitor.twitterapi_credentials import (
    TwitterApiCredentialPurpose,
    require_twitterapi_api_key,
)
from x_monitor.x_client import SEARCH_PATH

CATEGORY = "x_backfill_staging"


def validate_staging(scope):
    require(os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "staging",
            "direct ingestion requires staging environment")
    require(scope.get("staging_host") == settings.DATABASES["default"].get("HOST")
            and bool(scope.get("staging_host")), "staging database host changed")
    # The frozen Call A author roles can name brands outside the keyword set.
    # Check their foreign keys before HTTP admission, not after a paid response.
    needed = set(scope.get("brands", []))
    for context in scope.get("author_scope", {}).get("contexts", {}).values():
        needed.update(context.get("official_brands", []))
        needed.update(context.get("staff_brands", []))
    missing = needed - set(Brand.objects.filter(pk__in=needed).values_list("pk", flat=True))
    require(not missing, "staging brand references missing: " + ",".join(sorted(missing)))


class StagingPrefetcher(Prefetcher):
    def __init__(self, claim, job, budget, options):
        super().__init__(claim, job, budget, options)
        validate_staging(job.scope)
        with fenced_run(self.claim) as (_, run):
            previous = (CollectionRun.objects.select_for_update().get(pk=job.last_attempt_id)
                        if run.staging_retry_version is None and job.last_attempt_id
                        and job.last_attempt_id != run.pk else run)
            self.retry = adopt_retry_state(previous)
            self.retry.save(run)
            ensure_staging_bytes(run)
        self.retry_at = None
        self.metrics.update(mode="staging", lost_responses=0, max_buffered=0,
                            retry_policy=POLICY, transient_failures=0, retry_requests=0)

    def _save_retry(self):
        with fenced_run(self.claim) as (_, run):
            self.retry.save(run)

    def _pending(self, scope):
        consumed = CollectionScopeRequestUse.objects.filter(
            scope_run__run__job_id=self.claim.job_id, scope_run__scope_kind="x_query",
            scope_run__scope_key=scope.scope_key,
        ).values_list("request_id", flat=True)
        requests = CollectionRequest.objects.filter(
            attempt__run__job_id=self.claim.job_id, scope_run__scope_key=scope.scope_key,
            request_category=CATEGORY,
        ).exclude(pk__in=consumed).select_related(
            "scope_run__run", "scope_run__job_target__search_query", "attempt__run"
        ).order_by("started_at", "pk")
        failures, not_before, group = 0, None, None
        for request in requests:
            require(x_scope_ownership(request.scope_run) == x_scope_ownership(scope), "staging scope ancestry changed")
            if (request.http_method == "GET" and request.transport_outcome in {"received", "transport_error", "timeout"}
                    and transient(request.error_code, request.http_status)):
                original_scope = copy(request.scope_run)
                original_scope.cursor = request.cursor_before
                require(request.request_config == _request_identity(original_scope)
                        and request.endpoint_url == _endpoint(original_scope), "staging retry ancestry changed")
                if request.cursor_before == scope.cursor:
                    failures += 1
                    group = group or request.request_group or str(request.pk)
                    due = request.retry_after_at or request.started_at + timedelta(seconds=10)
                    not_before = max(not_before or due, due)
                continue
            require(request.transport_outcome == "received",
                    "staging physical request outcome unknown; reconcile before retry")
            with fenced_run(self.claim):
                request = adopt_staging_receipt(request)
            if request.body_lost or request.http_status != 200:
                continue
            require(request.error_code is None, "invalid staging response requires reconciliation")
            require(request.cursor_before == scope.cursor and request.request_config == _request_identity(scope)
                    and request.endpoint_url == _endpoint(scope), "staging cursor or query ancestry changed")
            # The successful receipt is durable but its page did not commit. Be
            # explicit about paid refetch and never claim identical search recall.
            with fenced_run(self.claim):
                request.body_lost = True
                request.save(update_fields=["body_lost"])
            self.metrics["lost_responses"] += 1
        require(failures < PAGE_FAILURE_LIMIT, "staging page retry allowance exhausted")
        return not_before, group

    def _save(self, request, result):
        body = None
        if result.body is not None:
            try:
                body = json.loads(result.body)
            except (ValueError, TypeError):
                pass
        raw = body.get("tweets", body.get("data", [])) if isinstance(body, dict) else []
        ids = [str(row.get("id", "")) if isinstance(row, dict) else "" for row in raw] if isinstance(raw, list) else []
        response = {"path": SEARCH_PATH, "status_code": result.response.get("status_code"),
                    "raw_results": len(ids), "response_bytes": len(result.body or b"")}
        cursor = body.get("next_cursor") if isinstance(body, dict) else None
        retryable = transient(result.error, response["status_code"])
        retry_after = None
        if retryable:
            retry_after = result.received_at + timedelta(seconds=max(
                random.uniform(5, 10), result.retry_after_seconds or 0))
        # Receipt, counters and lightweight metadata commit together. No body is
        # passed to finish_request, so no immutable evidence archive is created.
        with fenced_run(self.claim) as (_, run):
            request = finish_request(request, outcome="received" if result.body is not None else "transport_error",
                http_status=response["status_code"], cursor=cursor if isinstance(cursor, str) else None,
                error_code=result.error, response_bytes=response["response_bytes"] if result.body is not None else None,
                retry_after_at=retry_after, now=result.received_at)
            request = write_staging_receipt(request, {"raw_count": len(ids) if result.body is not None else None,
                "returned_ids": ids if result.body is not None else None,
                "body_sha256": hashlib.sha256(result.body).hexdigest() if result.body is not None else None,
                "body_lost": False})
            if retryable:
                self.retry.failed(result.received_at.timestamp(), retry_after=result.retry_after_seconds or 0,
                                  rate_limited=response["status_code"] == 429)
                self.metrics["transient_failures"] += 1
            elif not result.error:
                self.retry.succeeded()
            self.retry.save(run)
            if result.body is not None:
                self.budget.record_captured_response(request, response)
        self.metrics["captured_pages"] += int(result.body is not None)
        self.metrics["http_seconds_sum"] += result.seconds
        return CapturedPage(request, response, False, body=body)

    def _failed(self, request, result):
        self._save(request, result)
        if not transient(result.error, result.response.get("status_code")):
            self._check_error(result)

    @staticmethod
    def _check_error(result):
        if result.error:
            status = result.response.get("status_code")
            if status in {401, 402, 403, 429}:
                from monitor.backfill_collection import BackfillProviderSafetyError
                raise BackfillProviderSafetyError(status, retry_after_seconds=result.retry_after_seconds)
            raise RuntimeError("staging transport or response failed")

    def pages(self, deferred_scopes):
        key = require_twitterapi_api_key(TwitterApiCredentialPurpose.ON_DEMAND)
        futures = {}
        admission_open = True
        with ThreadPoolExecutor(max_workers=self.options.concurrency, thread_name_prefix="x-staging-http") as pool:
            try:
                while futures or admission_open:
                    # Account errors before any new admission. Successful
                    # responses remain bounded and are ingested while draining.
                    for future in list(futures):
                        if future.done() and future.result().error:
                            _, request, _ = futures.pop(future)
                            self._failed(request, future.result())
                    limit = self.retry.limit(self.options.concurrency, datetime.now(UTC).timestamp())
                    delayed = {}
                    # Completed responses count toward the cap until consumed.
                    # This bounds both HTTP concurrency and the in-memory backlog.
                    while admission_open and len(futures) < limit:
                        if any(f.done() and f.result().error for f in futures):
                            break
                        if not self.budget.can_start(38) or not self.budget.remaining_api_requests:
                            admission_open = False
                            break
                        busy = [value[0].pk for value in futures.values()]
                        scope = CollectionScopeRun.objects.filter(run_id=self.claim.run_id,
                            scope_kind="x_query", enumeration_complete=False).exclude(outcome="blocked").exclude(
                            scope_key__in=deferred_scopes).exclude(pk__in=[*busy, *delayed]).order_by("id").first()
                        if scope is None:
                            break
                        due, group = self._pending(scope)
                        if due and due > datetime.now(UTC):
                            delayed[scope.pk] = due
                            continue
                        with fenced_run(self.claim) as (_, run):
                            bytes_left = self.job.budgets["bytes"] - ensure_staging_bytes(run) - sum(v[2] for v in futures.values())
                            items_left = self.job.budgets["items"] - run.selected_count - 20 * len(futures)
                            spent = self.job.runs.aggregate(n=Sum("request_count"))["n"] or 0
                        if items_left < 20 or bytes_left <= 0 or spent + self.job.scope["prior_api_requests"] >= self.job.scope["maximum_api_requests"]:
                            admission_open = False
                            break
                        max_bytes = min(1024 * 1024, bytes_left // (self.options.concurrency - len(futures)))
                        if max_bytes <= 0:
                            admission_open = False
                            break
                        delay = self.next_start - time.monotonic()
                        if delay > 0:
                            time.sleep(min(delay, self.budget.remaining_seconds))
                        with harvest_writer_lock(execution_mode="backfill", entrypoint="management.backfill.staging") as lease:
                            if not lease.acquired or backfill_yield_requested():
                                admission_open = False
                                break
                            with fenced_run(self.claim):
                                self.budget.claim_api_request(30)
                                attempt = CollectionAttempt.objects.get(pk=self.claim.attempt_id)
                                request = begin_request(attempt, scope, endpoint_url=_endpoint(scope), cursor=scope.cursor,
                                    request_config=_request_identity(scope), request_category=CATEGORY,
                                    request_group=group, request_revision=POLICY)
                            self.metrics["retry_requests"] += int(group is not None)
                            future = pool.submit(fetch_page, key, _params(scope), max_bytes=max_bytes, timeout=30)
                            futures[future] = (scope, request, max_bytes)
                            self.next_start = time.monotonic() + 1 / self.options.starts_per_second
                            self.metrics["max_outstanding"] = max(self.metrics["max_outstanding"], sum(not f.done() for f in futures))
                            self.metrics["max_buffered"] = max(self.metrics["max_buffered"], len(futures))
                    if not futures:
                        if self.retry.phase == "open":
                            self.retry_at = datetime.fromtimestamp(self.retry.until, UTC)
                            self._save_retry()
                            return
                        if admission_open and delayed:
                            self.retry_at = min(delayed.values())
                            self._save_retry()
                            return
                        return
                    done, _ = wait(futures, return_when=FIRST_COMPLETED)
                    # Yield one page immediately, then refill. Other completed
                    # futures retain their reservation and cannot grow unbounded.
                    future = next(iter(done))
                    scope, request, _ = futures.pop(future)
                    result = future.result()
                    if result.error:
                        self._failed(request, result)
                        continue
                    capture = self._save(request, result)
                    yield scope, capture
            finally:
                # A consumer error, writer yield or provider failure must still
                # account all physical requests already started. Lost bodies are
                # explicitly identified on resume; unrecorded sends never retry.
                first_error = None
                for future, (_, request, _) in futures.items():
                    try:
                        self._save(request, future.result())
                    except Exception as exc:  # noqa: BLE001 - account other started requests before raising
                        first_error = first_error or exc
                if first_error is not None:
                    raise first_error
