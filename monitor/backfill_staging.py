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
    has_retry_review,
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
    PrefetchRateDeferred,
    _endpoint,
    _params,
    _recorded_provider,
    _request_provider_fields,
    _route_config,
    fetch_page,
)
from monitor.backfill_retry import (
    COOLDOWNS,
    PAGE_FAILURE_LIMIT,
    POLICIES,
    POLICY,
    transient,
)
from monitor.run_lock import backfill_yield_requested, harvest_writer_lock
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
from x_monitor.x_client import SEARCH_PATH, XClient

CATEGORY = "x_backfill_staging"


def validate_staging(scope):
    from monitor.backfill_database import identity, scope_relocated

    moved = scope_relocated(scope)
    dedicated = scope.get("response_storage") == "database"
    if dedicated:
        actual = identity()
        require(os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "backfill"
                and actual["name"] == actual["user"] == "xbackfiller"
                and scope.get("database_host") == actual["host"],
                "dedicated backfill database required")
    require(moved or dedicated or os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "staging",
            "direct ingestion requires staging environment")
    require(moved or dedicated or (scope.get("staging_host") == settings.DATABASES["default"].get("HOST")
            and bool(scope.get("staging_host"))), "staging database host changed")
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
                            retry_policy=self.retry.policy, transient_failures=0, retry_requests=0)

    def _save_retry(self):
        with fenced_run(self.claim) as (_, run):
            self.retry.save(run)

    def _routed_provider_fallback(self, request, status):
        provider = _recorded_provider(request)
        order = self.router.provider_order if self.router else ()
        return bool(status in {401, 429} and not request.cursor_before and provider in order
                    and order.index(provider) < len(order) - 1 and not self.router.force_twexapi)

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
        failures, not_before, group, last_failure = 0, None, None, None
        for request in requests:
            require(x_scope_ownership(request.scope_run) == x_scope_ownership(scope), "staging scope ancestry changed")
            if request.transport_outcome == 'unknown' and has_retry_review(request, self.claim.job_id):
                original_scope = copy(request.scope_run)
                original_scope.cursor = request.cursor_before
                require(request.error_code == 'operator_reconciled_interruption'
                        and (request.http_method == 'GET' or (request.http_method == 'POST' and _recorded_provider(request) == 'twexapi'))
                        and not request.accounting_complete
                        and request.request_config == _route_config(original_scope, _recorded_provider(request))
                        and request.endpoint_url == _endpoint(original_scope, _recorded_provider(request)),
                        'interrupted retry ancestry changed')
                if request.cursor_before == scope.cursor:
                    group = group or request.request_group or str(request.pk)
                continue
            if ((request.http_method == "GET" or (request.http_method == "POST" and _recorded_provider(request) == "twexapi")) and request.transport_outcome in {"received", "transport_error", "timeout"}
                    and (transient(request.error_code, request.http_status, policy=self.retry.policy)
                         or self._routed_provider_fallback(request, request.http_status))):
                original_scope = copy(request.scope_run)
                original_scope.cursor = request.cursor_before
                require(request.request_config == _route_config(original_scope, _recorded_provider(request))
                        and request.endpoint_url == _endpoint(original_scope, _recorded_provider(request)), "staging retry ancestry changed")
                if request.cursor_before == scope.cursor:
                    failures += 1
                    last_failure = max(last_failure or request.started_at, request.received_at or request.started_at)
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
            require(request.cursor_before == scope.cursor and request.request_config == _route_config(scope, _recorded_provider(request))
                    and request.endpoint_url == _endpoint(scope, _recorded_provider(request)), "staging cursor or query ancestry changed")
            # The successful receipt is durable but its page did not commit. Be
            # explicit about paid refetch and never claim identical search recall.
            with fenced_run(self.claim):
                request.body_lost = True
                request.save(update_fields=["body_lost"])
            self.metrics["lost_responses"] += 1
        if self.retry.policy == POLICY:
            require(failures < PAGE_FAILURE_LIMIT, "staging page retry allowance exhausted")
        elif failures >= PAGE_FAILURE_LIMIT:
            due = last_failure + timedelta(seconds=COOLDOWNS[-1])
            not_before = max(not_before or due, due)
        return not_before, group

    def _save(self, request, result):
        self._finish_route(request, result)
        body = None
        if result.body is not None:
            try:
                body = json.loads(result.body)
            except (ValueError, TypeError):
                pass
        raw = body.get("tweets", body.get("data", [])) if isinstance(body, dict) else []
        ids = [str(row.get("id") or row.get("tweet_id") or "") if isinstance(row, dict) else "" for row in raw] if isinstance(raw, list) else []
        response = {"path": result.response.get("path", SEARCH_PATH), "provider": result.response.get("provider", "twitterapi"),
                    "status_code": result.response.get("status_code"),
                    "raw_results": len(ids), "response_bytes": len(result.body or b"")}
        cursor = body.get("next_cursor") if isinstance(body, dict) else None
        retryable = (transient(result.error, response["status_code"], policy=self.retry.policy)
                     or self._routed_provider_fallback(request, response["status_code"]))
        retry_after = None
        if retryable:
            provider = _recorded_provider(request)
            order = self.router.provider_order if self.router else ()
            another_provider = (provider in order and order.index(provider) < len(order) - 1
                                and not request.cursor_before and not self.router.force_twexapi)
            if another_provider and response["status_code"] in {401, 429, 500, 502, 503, 504}:
                # Per-route cooldown is persisted independently of this scope.
                retry_after = result.received_at
            else:
                delay = max(random.uniform(5, 10), result.retry_after_seconds or 0)
                retry_after = result.received_at + timedelta(seconds=delay)
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
                                  rate_limited=response["status_code"] in ({401, 403, 429} if self.retry.policy == POLICIES[2] else {429}))
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
        if (not transient(result.error, result.response.get("status_code"), policy=self.retry.policy)
                and not self._routed_provider_fallback(request, result.response.get("status_code"))):
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
        self.router = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
        key = self.router.api_key
        futures = {}
        admission_open = True
        with ThreadPoolExecutor(max_workers=self.options.concurrency, thread_name_prefix="x-staging-http") as pool:
            try:
                while futures or admission_open:
                    rate_wait = 0
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
                            try:
                                route = self._select_route(scope)
                            except PrefetchRateDeferred as exc:
                                rate_wait = exc.seconds
                                break
                            provider = route.name if route else None
                            try:
                                with fenced_run(self.claim):
                                    self.budget.claim_api_request(30)
                                    attempt = CollectionAttempt.objects.get(pk=self.claim.attempt_id)
                                    request = begin_request(attempt, scope, endpoint_url=_endpoint(scope, provider), cursor=scope.cursor,
                                        method="POST" if provider == "twexapi" else "GET",
                                        request_config=_route_config(scope, provider), request_category=CATEGORY,
                                        request_group=group, request_revision=self.retry.policy,
                                        **_request_provider_fields(provider or self.router.default_credential_route))
                                self.metrics["retry_requests"] += int(group is not None)
                                future = pool.submit(fetch_page, route or key, _params(scope), max_bytes=max_bytes, timeout=30)
                                futures[future] = (scope, request, max_bytes)
                                if route:
                                    self.routes[request.pk] = route
                            except Exception:
                                if provider == "twexapi":
                                    self.router.circuit.release_fallback(datetime.now(UTC), self.router.twexapi_interval_s)
                                raise
                            self.next_start = time.monotonic() + 1 / self.options.starts_per_second
                            self.metrics["max_outstanding"] = max(self.metrics["max_outstanding"], sum(not f.done() for f in futures))
                            self.metrics["max_buffered"] = max(self.metrics["max_buffered"], len(futures))
                    if not futures:
                        if rate_wait:
                            wait_for_slot = min(rate_wait, 30)
                            if self.budget.can_start(wait_for_slot + 38):
                                time.sleep(wait_for_slot)  # Outside the writer lock and transaction.
                                continue
                            return
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
                    result = self._assess_route_result(request, future.result())
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
                        self._save(request, self._assess_route_result(request, future.result()))
                    except Exception as exc:  # noqa: BLE001 - account other started requests before raising
                        first_error = first_error or exc
                if first_error is not None:
                    raise first_error
