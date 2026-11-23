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
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from urllib.parse import urlencode

from django.db.models import Sum

from core.collection_capture import begin_request, finish_request, read_document
from core.collection_state import fenced_run, x_scope_ownership
from core.measurement_taxonomy import require
from core.models import (
    CollectionAttempt,
    CollectionRequest,
    CollectionScopeRequestUse,
    CollectionScopeRun,
)
from monitor.backfill_resources import BackfillBudgetExhausted
from monitor.run_lock import backfill_yield_requested, harvest_writer_lock
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
from x_monitor.x_client import (
    SEARCH_PATH,
    TWITTERAPI_BASE,
    XClient,
    _search_results,
    search_page_from_response,
    twexapi_search_page,
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
        body = self.body if self.body is not None else read_document(self.request.archive)
        if self.request.endpoint_url.startswith("https://api.twexapi.io/"):
            page = twexapi_search_page(body, received_at=self.request.received_at)
            if page.next_cursor:
                page = replace(page, next_cursor="twexapi:" + page.next_cursor)
            yield page
        else:
            page = search_page_from_response(body, received_at=self.request.received_at)
            provider = _recorded_provider(self.request)
            if page.next_cursor and provider and provider.startswith("twitterapi:"):
                page = replace(page, next_cursor=provider + ":" + page.next_cursor)
            yield page


@dataclass(frozen=True)
class TransportResult:
    body: bytes | None
    response: dict
    error: str | None
    received_at: datetime
    seconds: float
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class PrefetchRoute:
    """One physical request; no credential is included in logs or receipts."""
    name: str
    key: str = field(repr=False)


class PrefetchRateDeferred(BackfillBudgetExhausted):
    def __init__(self, seconds):
        self.seconds = seconds
        super().__init__("TwexAPI pacing slot is not yet available")


def _route_config(scope, provider=None):
    require(provider in {None, "twitterapi:scheduled", "twitterapi:on_demand", "twexapi"},
            "unknown recorded search provider")
    identity = _request_identity(scope)
    return identity + ":" + provider if provider else identity


def _recorded_provider(request):
    value = request.request_config or ""
    return value[65:] if len(value) > 65 and value[64] == ":" else None


def fetch_page(api_key, params, *, max_bytes, timeout):
    """One physical call, using the same client and status mapping as harvesting."""
    bodies, receipts = [], []
    route = api_key if isinstance(api_key, PrefetchRoute) else None
    key = route.key if route else api_key
    client = XClient(api_key=key, max_retries=0, timeout_s=timeout,
                              max_response_bytes=max_bytes, after_response=receipts.append)
    start = time.monotonic()
    error = None
    delay = None
    try:
        if route and route.name == "twexapi":
            payload = {"searchTerms": [params["query"]], "sortBy": "Latest"}
            if params.get("cursor"):
                payload["next_cursor"] = params["cursor"]
            response = client._bounded_request("POST", "https://api.twexapi.io/twitter/advanced_search/page", timeout,
                payload=payload, headers={"Authorization": "Bearer " + key}, max_bytes=max_bytes)
            bodies.append(response.content)
            receipts.append({"provider": "twexapi", "path": "/twitter/advanced_search/page",
                             "status_code": response.status_code, "response_bytes": len(response.content),
                             "raw_results": 0, "has_next_page": False})
            if response.status_code >= 400:
                exc = RuntimeError(f"provider_http_{response.status_code}")
                retry = str(response.headers.get("Retry-After", ""))
                if response.status_code == 429 and retry.isdigit():
                    exc.retry_after_seconds = int(retry)
                raise exc
            body = response.json()
            if not isinstance(body, dict) or body.get("code") != 200:
                raise ValueError("invalid TwexAPI response")
            items = _search_results(body)
            receipts[-1]["raw_results"] = len(items)
            receipts[-1]["has_next_page"] = bool(body.get("has_next_page"))
            if not items and body.get("has_next_page") and not body.get("next_cursor"):
                raise ValueError("empty page has invalid continuation")
        else:
            body = client._get(SEARCH_PATH, params, raw_sink=bodies.append)
            items = _search_results(body)
            if not items and body.get("has_next_page") and not body.get("next_cursor"):
                raise ValueError("empty page has invalid continuation")
    except Exception as exc:  # noqa: BLE001 - return every worker failure for durable accounting
        # Never retain provider text, headers or credentials in operator reports.
        error = type(exc).__name__
        delay = getattr(exc, "retry_after_seconds", None)
    if route and receipts and route.name.startswith("twitterapi:"):
        receipts[0].update(provider="twitterapi", credential_purpose=route.name)
    return TransportResult(
        body=bodies[0] if bodies else None,
        response=receipts[0] if receipts else {}, error=error,
        received_at=datetime.now(UTC), seconds=time.monotonic() - start,
        retry_after_seconds=delay,
    )


def _params(scope):
    owner = x_scope_ownership(scope)
    query = XClient._effective_search_query(
        owner["query"], since=None, since_time=owner["since_epoch"], until_time=owner["until_epoch"],
    )
    params = {"query": query, "queryType": "Latest", "limit": 20}
    if scope.cursor:
        cursor = scope.cursor
        if cursor.startswith("twexapi:"):
            cursor = cursor.removeprefix("twexapi:")
        elif cursor.startswith("twitterapi:"):
            cursor = cursor.split(":", 2)[2]
        params["cursor"] = cursor
    return params


def _request_identity(scope):
    return hashlib.sha256(json.dumps(_params(scope), sort_keys=True).encode()).hexdigest()


def _endpoint(scope, provider=None):
    if provider == "twexapi":
        return "https://api.twexapi.io/twitter/advanced_search/page"
    return TWITTERAPI_BASE + SEARCH_PATH + "?" + urlencode(_params(scope))


class Prefetcher:
    def __init__(self, claim, job, budget, options):
        self.claim, self.job, self.budget, self.options = claim, job, budget, options
        self.router = None
        self.routes = {}
        self.next_start = 0.0
        self.metrics = {"mode": "prefetch", "concurrency": options.concurrency,
                        "starts_per_second": options.starts_per_second, "captured_pages": 0,
                        "replayed_pages": 0, "http_seconds_sum": 0.0, "max_outstanding": 0}

    def _select_route(self, scope):
        if not self.router or not (self.router.provider_circuits or self.router.twexapi_key):
            return None
        cursor = scope.cursor or ""
        if cursor.startswith("twexapi:"):
            name = "twexapi"
            circuit = self.router.twex_circuit
        elif cursor.startswith("twitterapi:"):
            name = ":".join(cursor.split(":", 2)[:2])
            circuit = self.router.provider_circuits.get(name)
        elif cursor:
            # Untagged historical cursors were obtained with the on-demand key.
            name = "twitterapi:on_demand"
            circuit = self.router.provider_circuits.get(name)
        else:
            name = self.router._choose_search_provider()
            circuit = self.router.twex_circuit if name == "twexapi" else self.router.provider_circuits[name]
            # The selector has already claimed any half-open probe.
            return self._make_route(name, circuit)
        if circuit is None or not circuit.primary_permitted(datetime.now(UTC)):
            raise BackfillBudgetExhausted("Provider cursor held while its circuit is unavailable")
        return self._make_route(name, circuit)

    def _make_route(self, name, circuit):
        if name == "twexapi":
            wait = self.router.circuit.acquire_fallback(datetime.now(UTC), 60)
            if wait:
                circuit.abandon_probe()
                raise PrefetchRateDeferred(wait)
            return PrefetchRoute(name, self.router.twexapi_key)
        return PrefetchRoute(name, self.router.provider_credentials[name])

    def _finish_route(self, request, result):
        route = self.routes.pop(request.pk, None)
        if route is None:
            return
        status = result.response.get("status_code")
        if route.name == "twexapi":
            delay = max(self.router.twexapi_interval_s, result.retry_after_seconds or 0)
            self.router.circuit.release_fallback(datetime.now(UTC), delay)
            circuit = self.router.twex_circuit
        else:
            circuit = self.router.provider_circuits[route.name]
        if status == 401 or (status is not None and status >= 500) or (result.error and status in (None, 200)):
            circuit.record_failure(datetime.now(UTC))
        elif not result.error and status == 200:
            circuit.record_success(datetime.now(UTC))

    def _assess_route_result(self, request, result):
        route = self.routes.get(request.pk)
        if (route is None or result.error or result.response.get("status_code") != 200
                or request.cursor_before):
            return result
        circuit = self.router.twex_circuit if route.name == "twexapi" else self.router.provider_circuits[route.name]
        count = result.response.get("raw_results", 0)
        expected = circuit.observe_query(_params(request.scope_run)["query"], nonempty=bool(count), now=datetime.now(UTC))
        if not count and (expected or circuit.is_probe()):
            return replace(result, error="XClientServerError")
        return result

    def _pending(self, scope):
        consumed = set(CollectionScopeRequestUse.objects.filter(
            scope_run__run__job_id=self.claim.job_id,
            scope_run__scope_kind="x_query",
            scope_run__scope_key=scope.scope_key,
        ).values_list("request_id", flat=True))
        # A continuation keeps the physical request on its original run. Uses
        # across the job's scopes distinguish an already-committed page from
        # a captured response that still needs replay.
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
            if request.http_status != 200 or request.error_code:
                continue  # An accounted HTTP error is not a reusable search page.
            provider = _recorded_provider(request)
            require(request.cursor_before == scope.cursor and request.request_config == _route_config(scope, provider)
                    and request.endpoint_url == _endpoint(scope, provider),
                    "prefetch cursor or query ancestry changed")
            pending.append(CapturedPage(request, response, True))
        require(len(pending) <= 1, "duplicate unconsumed prefetch page")
        return pending[0] if pending else None

    def _save(self, request, result):
        self._finish_route(request, result)
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
        self.router = XClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
        key = self.router.api_key
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
                    from monitor.backfill_collection import ensure_response_bytes

                    bytes_left = self.job.budgets["bytes"] - ensure_response_bytes(run)
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
                rate_wait = 0
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
                            route = self._select_route(scope)
                            provider = route.name if route else None
                            try:
                                with fenced_run(self.claim):
                                    self.budget.claim_api_request(30)
                                    attempt = CollectionAttempt.objects.get(pk=self.claim.attempt_id)
                                    request = begin_request(attempt, scope, endpoint_url=_endpoint(scope, provider),
                                        method="POST" if provider == "twexapi" else "GET",
                                        cursor=scope.cursor, request_config=_route_config(scope, provider),
                                        request_category="x_backfill_prefetch")
                                    request.body_lost = False
                                    request.selection_accounted = False
                                    request.save(update_fields=["body_lost", "selection_accounted"])
                                futures[pool.submit(fetch_page, route or key, _params(scope), max_bytes=max_bytes,
                                                     timeout=30)] = (scope, request)
                                if route:
                                    self.routes[request.pk] = route
                            except Exception:
                                if provider == "twexapi":
                                    self.router.circuit.release_fallback(datetime.now(UTC), self.router.twexapi_interval_s)
                                raise
                            self.next_start = time.monotonic() + 1 / self.options.starts_per_second
                            self.metrics["max_outstanding"] = max(self.metrics["max_outstanding"],
                                                                   sum(not f.done() for f in futures))
                except PrefetchRateDeferred as exc:
                    rate_wait = exc.seconds
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
                retry_first_page = False
                for future in as_completed(futures):
                    scope, request = futures[future]
                    result = self._assess_route_result(request, future.result())
                    try:
                        capture = self._save(request, result)
                        if not result.error:
                            captures.append((scope, capture))
                    except Exception as exc:  # noqa: BLE001 - one capture failure cannot discard other responses
                        save_error = save_error or exc
                    if result.error:
                        status = result.response.get("status_code")
                        if (self.router and not self.router.force_twexapi and _recorded_provider(request) and not scope.cursor
                                and (status in (200, 401) or (status is not None and status >= 500))):
                            retry_first_page = True
                            continue
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
                if yielded:
                    return
                if not captures:
                    if rate_wait:
                        wait = min(rate_wait, 30)
                        if not self.budget.can_start(wait + 38):
                            return
                        time.sleep(wait)  # No writer lock or database transaction is held.
                        continue
                    if retry_first_page:
                        continue
                    return
                for scope, capture in sorted(captures, key=lambda pair: pair[0].pk):
                    yield scope, capture
