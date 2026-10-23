"""Bounded streaming acquisition into staging, without full response archives.

The controller alone uses the ORM. Futures own at most one response per scope;
the shared page writer commits its Posts and cursor before that scope can refill.
Only known received responses can be retried after losing their in-memory body.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from django.conf import settings
from django.db.models import Sum

from core.collection_capture import begin_request, finish_request
from core.collection_state import fenced_run
from core.measurement_taxonomy import require
from core.models import CollectionAttempt, CollectionRequest, CollectionScopeRun
from monitor.backfill_prefetch import (
    CapturedPage,
    Prefetcher,
    _endpoint,
    _params,
    _request_identity,
    fetch_page,
)
from monitor.run_lock import backfill_yield_requested, harvest_writer_lock
from x_monitor.apify import SEARCH_PATH
from x_monitor.twitterapi_credentials import (
    TwitterApiCredentialPurpose,
    require_twitterapi_api_key,
)

CATEGORY = "x_backfill_staging"


def validate_staging(scope):
    require(os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "staging",
            "direct ingestion requires staging environment")
    require(scope.get("staging_host") == settings.DATABASES["default"].get("HOST")
            and bool(scope.get("staging_host")), "staging database host changed")


class StagingPrefetcher(Prefetcher):
    def __init__(self, claim, job, budget, options):
        super().__init__(claim, job, budget, options)
        validate_staging(job.scope)
        self.metrics.update(mode="staging", lost_responses=0, max_buffered=0)

    def _pending(self, scope):
        consumed = {str(e["prefetch_request_id"]) for e in scope.envelopes if e.get("prefetch_request_id")}
        requests = CollectionRequest.objects.filter(
            attempt__run__job_id=self.claim.job_id, scope_run__scope_key=scope.scope_key,
            request_category=CATEGORY,
        ).exclude(pk__in=consumed).select_related("scope_run", "attempt__run").order_by("started_at", "pk")
        for request in requests:
            require(request.scope_run.ownership == scope.ownership, "staging scope ancestry changed")
            require(request.transport_outcome == "received",
                    "staging physical request outcome unknown; reconcile before retry")
            original = request.attempt.run
            meta = original.report.get("staging_responses", {}).get(str(request.pk))
            require(meta is not None, "staging response accounting missing; reconcile before retry")
            if meta.get("body_lost") or request.http_status != 200:
                continue
            require(request.error_code is None, "invalid staging response requires reconciliation")
            require(request.cursor_before == scope.cursor and request.request_config == _request_identity(scope)
                    and request.endpoint_url == _endpoint(scope), "staging cursor or query ancestry changed")
            # The successful receipt is durable but its page did not commit. Be
            # explicit about paid refetch and never claim identical search recall.
            with fenced_run(self.claim):
                from core.models import CollectionRun
                original = CollectionRun.objects.select_for_update().get(pk=original.pk)
                receipts = original.report["staging_responses"]
                receipts[str(request.pk)]["body_lost"] = True
                original.save(update_fields=["report", "updated_at"])
            self.metrics["lost_responses"] += 1

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
        # Receipt, counters and lightweight metadata commit together. No body is
        # passed to finish_request, so no immutable evidence archive is created.
        with fenced_run(self.claim) as (_, run):
            request = finish_request(request, outcome="received" if result.body is not None else "transport_error",
                http_status=response["status_code"], cursor=cursor if isinstance(cursor, str) else None,
                error_code=result.error, response_bytes=response["response_bytes"], now=result.received_at)
            receipts = dict(run.report.get("staging_responses", {}))
            receipts[str(request.pk)] = {"raw_count": len(ids), "returned_ids": ids,
                "body_sha256": hashlib.sha256(result.body).hexdigest() if result.body is not None else None,
                "body_lost": False}
            run.report = {**run.report, "staging_responses": receipts}
            run.save(update_fields=["report", "updated_at"])
            self.budget.record_captured_response(request, response)
        self.metrics["captured_pages"] += int(result.body is not None)
        self.metrics["http_seconds_sum"] += result.seconds
        return CapturedPage(request, response, False, body=body)

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
                    # Completed responses count toward the cap until consumed.
                    # This bounds both HTTP concurrency and the in-memory backlog.
                    while admission_open and len(futures) < self.options.concurrency:
                        for future in futures:
                            if future.done():
                                self._check_error(future.result())
                        if not self.budget.can_start(38) or not self.budget.remaining_api_requests:
                            admission_open = False
                            break
                        busy = [value[0].pk for value in futures.values()]
                        scope = CollectionScopeRun.objects.filter(run_id=self.claim.run_id,
                            scope_kind="x_query", enumeration_complete=False).exclude(outcome="blocked").exclude(
                            scope_key__in=deferred_scopes).exclude(pk__in=busy).order_by("id").first()
                        if scope is None:
                            break
                        self._pending(scope)
                        with fenced_run(self.claim) as (_, run):
                            bytes_left = self.job.budgets["bytes"] - run.report.get("response_bytes", 0) - sum(v[2] for v in futures.values())
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
                                    request_config=_request_identity(scope), request_category=CATEGORY)
                            future = pool.submit(fetch_page, key, _params(scope), max_bytes=max_bytes, timeout=30)
                            futures[future] = (scope, request, max_bytes)
                            self.next_start = time.monotonic() + 1 / self.options.starts_per_second
                            self.metrics["max_outstanding"] = max(self.metrics["max_outstanding"], sum(not f.done() for f in futures))
                            self.metrics["max_buffered"] = max(self.metrics["max_buffered"], len(futures))
                    if not futures:
                        return
                    done, _ = wait(futures, return_when=FIRST_COMPLETED)
                    # Yield one page immediately, then refill. Other completed
                    # futures retain their reservation and cannot grow unbounded.
                    future = next(iter(done))
                    scope, request, _ = futures.pop(future)
                    result = future.result()
                    capture = self._save(request, result)
                    self._check_error(result)
                    yield scope, capture
            finally:
                # A consumer error, writer yield or provider failure must still
                # account all physical requests already started. Lost bodies are
                # explicitly identified on resume; ambiguous outcomes never retry.
                first_error = None
                for future, (_, request, _) in futures.items():
                    try:
                        self._save(request, future.result())
                    except Exception as exc:  # noqa: BLE001 - account other started requests before raising
                        first_error = first_error or exc
                if first_error is not None:
                    raise first_error
