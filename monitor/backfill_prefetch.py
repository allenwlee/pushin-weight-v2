"""Bounded parallel HTTP; all accounting, replay and Post writes stay serial.

Workers receive immutable request parameters and never use the ORM. Returned
bytes are archived by the controller before the shared ingestion path sees them.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

from django.db.models import Sum

from core.collection_capture import begin_request, finish_request, read_document
from core.collection_state import fenced_run, x_scope_ownership
from core.measurement_taxonomy import require
from core.models import CollectionAttempt, CollectionRequest, CollectionScopeRun
from monitor.backfill_resources import BackfillBudgetExhausted
from monitor.run_lock import backfill_yield_requested, harvest_writer_lock
from x_monitor.apify import (
    SEARCH_PATH,
    TWITTERAPI_BASE,
    TwitterApiClient,
    _search_results,
    search_page_from_response,
)
from x_monitor.twitterapi_credentials import (
    TwitterApiCredentialPurpose,
    require_twitterapi_api_key,
)


@dataclass(frozen=True)
class PrefetchOptions:
    concurrency: int = 1
    starts_per_second: float = 10

    @classmethod
    def parse(cls, value=None):
        value = {} if value is None else value
        require(isinstance(value, dict) and set(value) <= {"concurrency", "starts_per_second"},
                "invalid collection execution options")
        selected = cls(**value)
        require(type(selected.concurrency) is int and 1 <= selected.concurrency <= 20,
                "collection concurrency must be 1–20")
        rate = selected.starts_per_second
        require(type(rate) in {int, float} and math.isfinite(rate) and 0 < rate <= 20,
                "collection request-start rate must be greater than zero and at most20")
        return selected


@dataclass
class CapturedPage:
    request: CollectionRequest
    response: dict
    replayed: bool
    body: dict | None = None

    def pages(self):
        # Lazy parsing lets CycleRunner retain its existing invalid-page handling.
        yield search_page_from_response(
            self.body if self.body is not None else read_document(self.request.archive),
            received_at=self.request.received_at,
        )


@dataclass(frozen=True)
class TransportResult:
    body: bytes | None
    response: dict
    error: str | None
    received_at: datetime
    seconds: float
    retry_after_seconds: int | None = None


def fetch_page(api_key, params, *, max_bytes, timeout):
    """One physical call, using the same client and status mapping as harvesting."""
    bodies, receipts = [], []
    client = TwitterApiClient(api_key=api_key, max_retries=0, timeout_s=timeout,
                              max_response_bytes=max_bytes, after_response=receipts.append)
    start = time.monotonic()
    error = None
    delay = None
    try:
        _search_results(client._get(SEARCH_PATH, params, raw_sink=bodies.append))
    except Exception as exc:  # noqa: BLE001 - return every worker failure for durable accounting
        # Never retain provider text, headers or credentials in operator reports.
        error = type(exc).__name__
        delay = getattr(exc, "retry_after_seconds", None)
    return TransportResult(
        body=bodies[0] if bodies else None,
        response=receipts[0] if receipts else {}, error=error,
        received_at=datetime.now(UTC), seconds=time.monotonic() - start,
        retry_after_seconds=delay,
    )


def _params(scope):
    owner = x_scope_ownership(scope)
    query = TwitterApiClient._effective_search_query(
        owner["query"], since=None, since_time=owner["since_epoch"], until_time=owner["until_epoch"],
    )
    params = {"query": query, "queryType": "Latest", "limit": 20}
    if scope.cursor:
        params["cursor"] = scope.cursor
    return params


def _request_identity(scope):
    return hashlib.sha256(json.dumps(_params(scope), sort_keys=True).encode()).hexdigest()


def _endpoint(scope):
    return TWITTERAPI_BASE + SEARCH_PATH + "?" + urlencode(_params(scope))


class Prefetcher:
    def __init__(self, claim, job, budget, options):
        self.claim, self.job, self.budget, self.options = claim, job, budget, options
        self.next_start = 0.0
        self.metrics = {"mode": "prefetch", "concurrency": options.concurrency,
                        "starts_per_second": options.starts_per_second, "captured_pages": 0,
                        "replayed_pages": 0, "http_seconds_sum": 0.0, "max_outstanding": 0}

    def _pending(self, scope):
        consumed = {str(e["prefetch_request_id"]) for e in scope.envelopes if e.get("prefetch_request_id")}
        # Legacy continuation copies scopes/envelopes into a new run. Keep each
        # request on the original run; validate exact immutable job/scope ancestry.
        requests = CollectionRequest.objects.filter(
            attempt__run__job_id=self.claim.job_id, scope_run__scope_key=scope.scope_key,
            request_category="x_backfill_prefetch",
        ).exclude(pk__in=consumed).select_related(
            "archive", "scope_run__run", "scope_run__job_target__search_query"
        ).order_by("started_at", "pk")
        pending = []
        for request in requests:
            require(x_scope_ownership(request.scope_run) == x_scope_ownership(scope),
                    "prefetch scope ancestry changed")
            if request.transport_outcome in {"pending", "unknown", "timeout", "transport_error"}:
                raise ValueError("prefetch physical request outcome unknown; reconcile before retry")
            require(request.archive_id is not None, "prefetch response archive missing")
            try:
                body = read_document(request.archive)
            except ValueError:
                body = None  # Retain/account malformed paid evidence before failing replay.
            raw = body.get("tweets", body.get("data", [])) if isinstance(body, dict) else []
            response = {
                "path": SEARCH_PATH, "status_code": request.http_status,
                "raw_results": len(raw) if isinstance(raw, list) else 0,
                "response_bytes": request.response_bytes or 0,
            }
            self.budget.record_captured_response(request, response)
            if request.http_status != 200:
                continue  # An accounted HTTP error is not a reusable search page.
            require(request.cursor_before == scope.cursor and request.request_config == _request_identity(scope)
                    and request.endpoint_url == _endpoint(scope),
                    "prefetch cursor or query ancestry changed")
            pending.append(CapturedPage(request, response, True))
        require(len(pending) <= 1, "duplicate unconsumed prefetch page")
        return pending[0] if pending else None

    def _save(self, request, result):
        outcome = "received" if result.body is not None else "transport_error"
        cursor = None
        if result.body is not None:
            try:
                body = json.loads(result.body)
                cursor = body.get("next_cursor") if isinstance(body, dict) else None
                cursor = cursor if isinstance(cursor, str) else None
            except (ValueError, TypeError):
                pass
        # Paid responses remain evidence even if ownership expired during HTTP.
        request = finish_request(request, outcome=outcome, body=result.body,
                                 http_status=result.response.get("status_code"), cursor=cursor,
                                 error_code=result.error, now=result.received_at)
        if result.response:
            self.budget.record_captured_response(request, result.response)
        self.metrics["captured_pages"] += int(result.body is not None)
        self.metrics["http_seconds_sum"] += result.seconds
        return CapturedPage(request, result.response, False)

    def pages(self, deferred_scopes):
        key = require_twitterapi_api_key(TwitterApiCredentialPurpose.ON_DEMAND)
        with ThreadPoolExecutor(max_workers=self.options.concurrency,
                                thread_name_prefix="x-backfill-http") as pool:
            while self.budget.can_start(38):
                scopes = list(CollectionScopeRun.objects.filter(
                    run_id=self.claim.run_id, scope_kind="x_query", enumeration_complete=False,
                ).exclude(outcome="blocked").exclude(scope_key__in=deferred_scopes)
                    .select_related("run", "job_target__search_query")
                    .order_by("id")[:self.options.concurrency])
                if not scopes:
                    return
                saved = [(scope, self._pending(scope)) for scope in scopes]
                pending = [(scope, capture) for scope, capture in saved if capture is not None]
                if pending:
                    for scope, capture in pending:
                        self.metrics["replayed_pages"] += 1
                        yield scope, capture
                    continue
                if not self.budget.remaining_api_requests:
                    return
                with fenced_run(self.claim) as (_, run):
                    bytes_left = self.job.budgets["bytes"] - run.report.get("response_bytes", 0)
                    items_left = self.job.budgets["items"] - run.selected_count
                    spent = self.job.runs.aggregate(n=Sum("request_count"))["n"] or 0
                    starts_left = self.job.scope["maximum_api_requests"] - self.job.scope["prior_api_requests"] - spent
                count = min(len(scopes), self.budget.remaining_api_requests,
                            max(0, items_left // 20), max(0, starts_left))
                if count <= 0 or bytes_left <= 0:
                    return
                max_bytes = min(1024 * 1024, bytes_left // count)
                if max_bytes <= 0:
                    return
                futures, captures = {}, []
                admission_error = None
                yielded = False
                try:
                    for scope in scopes[:count]:
                        # Observe completed errors before admitting more paid work.
                        if any(f.done() and f.result().error for f in futures):
                            break
                        delay = self.next_start - time.monotonic()
                        if delay > 0:
                            time.sleep(min(delay, self.budget.remaining_seconds))
                        with harvest_writer_lock(execution_mode="backfill",
                                entrypoint="management.backfill.prefetch") as lease:
                            if not lease.acquired:
                                yielded = True
                                break
                            if any(f.done() and f.result().error for f in futures):
                                break
                            if backfill_yield_requested():
                                yielded = True
                                break
                            with fenced_run(self.claim):
                                self.budget.claim_api_request(30)
                                attempt = CollectionAttempt.objects.get(pk=self.claim.attempt_id)
                                request = begin_request(attempt, scope, endpoint_url=_endpoint(scope),
                                    cursor=scope.cursor, request_config=_request_identity(scope),
                                    request_category="x_backfill_prefetch")
                            futures[pool.submit(fetch_page, key, _params(scope), max_bytes=max_bytes,
                                                 timeout=30)] = (scope, request)
                            self.next_start = time.monotonic() + 1 / self.options.starts_per_second
                            self.metrics["max_outstanding"] = max(self.metrics["max_outstanding"],
                                                                   sum(not f.done() for f in futures))
                except BackfillBudgetExhausted as exc:
                    if "yielding to queued live harvest" in str(exc):
                        yielded = True
                    else:
                        admission_error = exc
                except Exception as exc:  # noqa: BLE001 - archive outstanding responses before raising
                    admission_error = exc
                # Never drop an already-started response because another scope
                # failed, live queued, or the controller lost its lease.
                save_error = None
                transport_error = None
                for future in as_completed(futures):
                    scope, request = futures[future]
                    result = future.result()
                    try:
                        capture = self._save(request, result)
                        captures.append((scope, capture))
                    except Exception as exc:  # noqa: BLE001 - one capture failure cannot discard other responses
                        save_error = save_error or exc
                    if result.error:
                        status = result.response.get("status_code")
                        if status in {401, 402, 403, 429}:
                            from monitor.backfill_collection import (
                                BackfillProviderSafetyError,
                            )
                            transport_error = BackfillProviderSafetyError(status,
                                retry_after_seconds=result.retry_after_seconds)
                        else:
                            transport_error = transport_error or RuntimeError("prefetch transport or response failed")
                if save_error or admission_error or transport_error:
                    raise save_error or admission_error or transport_error
                if yielded or not captures:
                    return
                for scope, capture in sorted(captures, key=lambda pair: pair[0].pk):
                    yield scope, capture
