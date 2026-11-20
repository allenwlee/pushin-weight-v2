"""Build an offline, reviewable history-search specification.

The default command only creates an offline plan. Collection requires an
explicit bounded run, an on-demand client, and durable request receipts.
"""

import hashlib
import hmac
import json
import math
import re
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from x_monitor.queries import assert_under_length_cap
from x_monitor.special_events_search import GENERAL_QUERY_CLAUSES, QUERY_VERSION
from x_monitor.twitterapi_credentials import (
    TwitterApiCredentialPurpose,
    get_twitterapi_api_key,
)
from x_monitor.x_client import TWEETS_BY_IDS_CHUNK, XClient

HISTORY_QUERY_VERSION = "save-person-job-history-v2"
MOVE_TERMS = (
    '"I joined"',
    '"I am joining"',
    '"I’m joining"',
    '"recently joined"',
    '"I left"',
    '"my last day"',
    '"starting at"',
    '"after three years at"',
    '"after 3 years at"',
    '"decided to leave"',
    "resigned",
    '"promoted to"',
    '"new role"',
    '"new team"',
    '"我加入"',
    '"我离开"',
    "入社",
    "退職",
)


class HistoryBudgetExhausted(ValueError):
    """An already-frozen request or byte allowance cannot admit another call."""


class CollectionRequestHistoryJournal:
    """Persist selected history pages through existing fenced request receipts.

    A caller must supply a live ``RunClaim`` and its already-owned X-query
    scope. This class stores normalized selected facts, not raw provider
    envelopes. Real provider dispatch requires a finite monetary allowance,
    a matching on-demand credential, and disabled internal retries.
    """

    category = "save_person_job_history_v1"

    def __init__(
        self,
        claim,
        scope,
        *,
        endpoint="search",
        max_spend_usd=None,
        max_request_usd=None,
    ):
        from core.models import CollectionScopeRun

        if endpoint not in {"search", "lookup"}:
            raise ValueError("Unknown history receipt endpoint")
        selected = CollectionScopeRun.objects.select_related("run__job").get(
            pk=scope.pk
        )
        if (
            selected.run_id != claim.run_id
            or selected.run.job_id != claim.job_id
            or selected.scope_kind != "x_query"
        ):
            raise ValueError(
                "History receipt scope does not belong to the claimed X run"
            )
        if (
            selected.run.job.source_id != "x"
            or selected.run.job.scope.get("credential_purpose") != "on-demand"
        ):
            raise ValueError("History receipt requires an on-demand X collection job")
        self.claim, self.scope = claim, selected
        self.endpoint = endpoint
        self.category = (
            "save_person_job_history_v1"
            if endpoint == "search"
            else "save_person_job_lookup_v1"
        )
        self._lookup_batches = None
        self._transport = None
        self._lookup_raw = None
        self._max_spend = self._currency(max_spend_usd)
        self._max_request = self._currency(max_request_usd)
        self._max_response_bytes = None
        self._request_timeout = None
        self._budget_pin = (
            hashlib.sha256(
                f"{self._max_spend}:{self._max_request}".encode()
            ).hexdigest()
            if self._max_spend is not None or self._max_request is not None
            else None
        )

    @staticmethod
    def _currency(value):
        if value is None:
            return None
        if isinstance(value, (bool, float)):
            raise TypeError("Dollar limits require exact decimal values")
        try:
            amount = Decimal(value)
            if (
                not amount.is_finite()
                or amount <= 0
                or amount > Decimal("999999.999999")
                or amount != amount.quantize(Decimal("0.000001"))
            ):
                raise ValueError("Dollar limits must be positive to six decimal places")
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("Invalid dollar limit") from exc
        return amount

    def bind_client(self, client):
        if (
            self._max_spend is None
            or self._max_request is None
            or self._max_request > self._max_spend
        ):
            raise ValueError(
                "A finite dollar ceiling and per-request maximum are required"
            )
        key = get_twitterapi_api_key(TwitterApiCredentialPurpose.ON_DEMAND)
        if not key or not hmac.compare_digest(client.api_key, key):
            raise ValueError("Client must use the on-demand credential")
        if client.max_retries != 0:
            raise ValueError(
                "History collection requires zero automatic client retries"
            )
        if type(client.max_response_bytes) is not int or client.max_response_bytes < 1:
            raise ValueError("A finite per-response byte cap is required")
        if (
            isinstance(client.timeout_s, bool)
            or not isinstance(client.timeout_s, (int, float))
            or not math.isfinite(client.timeout_s)
            or client.timeout_s <= 0
        ):
            raise ValueError("A finite positive request timeout is required")
        self._max_response_bytes = client.max_response_bytes
        self._request_timeout = client.timeout_s
        self._budget_pin = hashlib.sha256(
            json.dumps(
                [
                    str(self._max_spend),
                    str(self._max_request),
                    client.max_response_bytes,
                    client.timeout_s,
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        previous = client.after_response
        previous_exchange = client.on_exchange_finish

        def capture_exchange(exchange, metadata):
            if metadata.get("outcome") == "received":
                # Account for the physical response before interpreting its
                # body. Malformed JSON is still a received, potentially billed
                # exchange and must remain in the byte/request ledger.
                self.record_transport(
                    status_code=metadata["status_code"],
                    response_bytes=len(metadata["body"]),
                )
            if (
                self.endpoint == "lookup"
                and metadata.get("outcome") == "received"
                and metadata.get("status_code") == 200
            ):
                raw = json.loads(metadata["body"])
                tweets = raw.get("tweets") if isinstance(raw, dict) else None
                if not isinstance(tweets, list):
                    raise ValueError("Lookup response has no tweet list")
                versions = {}
                appearances = []
                for row in tweets:
                    if not isinstance(row, dict):
                        appearances.append(None)
                        continue
                    post_id = str(row.get("id") or "") or None
                    appearances.append(post_id)
                    if post_id is not None:
                        author = row.get("author") or {}
                        source = {
                            "id": post_id,
                            "text": row.get("text"),
                            "created_at": row.get("createdAt") or row.get("created_at"),
                            "author_id": str(author.get("id") or "")
                            if isinstance(author, dict)
                            else "",
                        }
                        versions.setdefault(post_id, []).append(source)
                conflicts = {
                    key: value
                    for key, value in versions.items()
                    if len(
                        {
                            json.dumps(row, sort_keys=True, ensure_ascii=False)
                            for row in value
                        }
                    )
                    > 1
                }
                self._lookup_raw = {
                    "returned_ids": appearances,
                    "conflicting_sources": conflicts,
                }
            if previous_exchange:
                previous_exchange(exchange, metadata)

        def capture(metadata):
            self.record_transport(
                status_code=metadata["status_code"],
                response_bytes=metadata["response_bytes"],
            )
            if previous:
                previous(metadata)

        return replace(
            client, after_response=capture, on_exchange_finish=capture_exchange
        )

    def _requests(self, identity):
        from core.models import CollectionRequest

        return (
            CollectionRequest.objects.filter(
                scope_run__run_id=self.claim.run_id,
                scope_run__scope_kind=self.scope.scope_kind,
                scope_run__scope_key=self.scope.scope_key,
                request_category=self.category,
                request_config=identity,
            )
            .select_related("archive", "attempt")
            .order_by("attempt__ordinal", "ordinal")
        )

    def validate_search(self, request, since_time, until_time):
        from core.collection_state import x_scope_ownership

        if self.endpoint != "search":
            raise ValueError("History scope is not a search receipt")
        ownership = x_scope_ownership(self.scope)
        if (
            ownership["query"] != request["query"]
            or ownership["since_epoch"] != since_time
            or ownership["until_epoch"] != until_time
        ):
            raise ValueError("History query differs from its frozen collection scope")

    def validate_lookup(self, post_ids, expected_authors, deadline):
        if self.endpoint != "lookup":
            raise ValueError("History scope is not a lookup receipt")
        frozen = self.scope.run.job.scope.get("save_person_job_lookup")
        expected = {
            "schema": "save-person-job-lookup/v1",
            "post_ids": post_ids,
            "expected_authors": expected_authors,
            "deadline": deadline.isoformat(),
        }
        if frozen != expected:
            raise ValueError(
                "Lookup IDs, authors or deadline differ from the frozen job"
            )
        ids = list(dict.fromkeys(post_ids))
        self._lookup_batches = [
            ids[i : i + TWEETS_BY_IDS_CHUNK]
            for i in range(0, len(ids), TWEETS_BY_IDS_CHUNK)
        ]

    def load(self, identity):
        from core.collection_capture import read_document

        result = []
        for request in self._requests(identity):
            if request.request_group != self._budget_pin:
                raise ValueError("Frozen history dollar budget changed")
            receipt = {
                "identity": identity,
                "cursor_before": request.cursor_before,
                "state": "pending",
            }
            if (
                request.transport_outcome == "received"
                and request.http_status == 200
                and request.archive_id
            ):
                receipt.update(state="received", page=read_document(request.archive))
            elif request.http_status == 429:
                receipt["state"] = "rate_limited"
            result.append(receipt)
        return result

    def reserve(self, identity, cursor):
        from core.collection_capture import begin_request
        from core.collection_state import fenced_run
        from core.models import CollectionAttempt, CollectionRequest

        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise ValueError("Invalid history receipt identity")
        endpoint = (
            "https://api.twitterapi.io/twitter/tweet/advanced_search"
            if self.endpoint == "search"
            else "https://api.twitterapi.io/twitter/tweets"
        )
        if self.endpoint == "lookup":
            if (
                self._lookup_batches is None
                or not isinstance(cursor, str)
                or not cursor.isdigit()
                or int(cursor) >= len(self._lookup_batches)
            ):
                raise ValueError("Lookup batch is not pinned to the frozen job")
            endpoint += "?" + urlencode(
                {"tweet_ids": ",".join(self._lookup_batches[int(cursor)])}
            )
        with fenced_run(self.claim):
            self._transport = None
            self._lookup_raw = None
            if (
                CollectionRequest.objects.filter(
                    scope_run__run_id=self.claim.run_id,
                    scope_run__scope_kind=self.scope.scope_kind,
                    scope_run__scope_key=self.scope.scope_key,
                    request_category=self.category,
                )
                .exclude(request_config=identity)
                .exists()
            ):
                raise ValueError("Frozen history request identity changed")
            if self._requests(identity).filter(cursor_before=cursor).exists():
                raise ValueError("History request cursor is already reserved")
            attempt = CollectionAttempt.objects.select_for_update().get(
                pk=self.claim.attempt_id
            )
            if attempt.credential_purpose not in (None, "on-demand"):
                raise ValueError("Collection attempt is not on-demand")
            if attempt.credential_purpose is None:
                attempt.credential_purpose = "on-demand"
                attempt.save(update_fields=["credential_purpose"])
            if self._max_response_bytes is not None:
                from django.utils import timezone as django_timezone

                if (
                    attempt.lease_expires_at - django_timezone.now()
                ).total_seconds() <= self._request_timeout:
                    raise HistoryBudgetExhausted(
                        "Insufficient collection lease time for the request"
                    )
                if (
                    attempt.reserved_bytes is None
                    or attempt.actual_response_bytes + self._max_response_bytes
                    > attempt.reserved_bytes
                ):
                    raise HistoryBudgetExhausted(
                        "History request exceeds the reserved byte budget"
                    )
                reservations = CollectionRequest.objects.filter(
                    attempt__run_id=self.claim.run_id, request_category=self.category
                )
                # CollectionRequest stores a frozen configuration identity,
                # not a dollar column. Every intent (including unknown sends)
                # consumes the same pinned per-request maximum. Refuse a
                # different pin rather than reprice older reservations.
                if reservations.exclude(request_group=self._budget_pin).exists():
                    raise ValueError("Frozen history dollar budget changed")
                reserved = reservations.count() * self._max_request
                if reserved + self._max_request > self._max_spend:
                    raise HistoryBudgetExhausted(
                        "History request exceeds the reserved dollar budget"
                    )
            request = begin_request(
                attempt,
                self.scope,
                endpoint_url=endpoint,
                cursor=cursor,
                request_category=self.category,
                request_config=identity,
                request_group=self._budget_pin,
            )
            return request.pk

    def record_transport(self, *, status_code, response_bytes):
        if (
            type(status_code) is not int
            or not 100 <= status_code <= 599
            or type(response_bytes) is not int
            or response_bytes < 0
            or self._max_response_bytes is not None
            and response_bytes > self._max_response_bytes
        ):
            raise ValueError("Actual transport status and byte count are required")
        self._transport = {"status_code": status_code, "response_bytes": response_bytes}

    def finish(self, token, page):
        from core.collection_capture import finish_request
        from core.collection_state import fenced_run
        from core.models import CollectionRequest

        transport = self._transport
        self._transport = None
        if transport is None or transport["status_code"] != 200:
            raise ValueError("Successful physical response metadata is required")
        body = json.dumps(
            page,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        with fenced_run(self.claim):
            request = CollectionRequest.objects.select_for_update().get(
                pk=token, scope_run=self.scope, request_category=self.category
            )
            finish_request(
                request,
                outcome="received",
                body=body,
                http_status=transport["status_code"],
                response_bytes=transport["response_bytes"],
                body_encoding="selected-json-canonical-v1",
            )

    def fail(self, token, error_type):
        from core.collection_capture import finish_request
        from core.collection_state import fenced_run
        from core.models import CollectionRequest

        transport = self._transport
        self._transport = None
        with fenced_run(self.claim):
            request = CollectionRequest.objects.select_for_update().get(
                pk=token, scope_run=self.scope, request_category=self.category
            )
            finish_request(
                request,
                outcome="received" if transport else "transport_error",
                http_status=transport["status_code"] if transport else None,
                response_bytes=transport["response_bytes"] if transport else None,
                error_code=error_type[:64],
            )
        return transport["status_code"] if transport else None


def _history_time(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Missing post publication time")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        result = parsedate_to_datetime(value)
    if result is None or result.utcoffset() is None:
        raise ValueError("Post publication time requires a timezone")
    return result


def _canonical_native_id(value):
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdigit()
        and int(value) > 0
        and str(int(value)) == value
    )


def collect_history_pages(
    *,
    request,
    since_time,
    until_time,
    client,
    journal,
    authorized=False,
    credential_purpose=None,
    max_requests=0,
    max_pages=0,
    max_posts=0,
    deadline=None,
    now=None,
):
    """Collect one frozen query with a caller-owned durable receipt journal.

    This is not wired to the preview command. ``journal`` must durably reserve
    a request before dispatch and durably save each page before returning from
    ``finish``. An unfinished reservation is an unknown paid outcome and is
    never automatically retried. A real XClient requires the existing
    CollectionRequest journal, an on-demand key, and explicit spend caps.
    """
    if (
        authorized is not True
        or credential_purpose is not TwitterApiCredentialPurpose.ON_DEMAND
    ):
        raise ValueError("Explicit on-demand authorization is required")
    live_client = isinstance(client, XClient)
    if live_client and not isinstance(journal, CollectionRequestHistoryJournal):
        raise TypeError("Live collection requires shared durable receipt integration")
    if not getattr(client, "api_key", None):
        raise ValueError("On-demand client credential is required")
    if any(
        type(value) is not int or value < 1
        for value in (max_requests, max_pages, max_posts)
    ):
        raise ValueError("Finite positive request, page and post bounds are required")
    if not isinstance(deadline, datetime) or deadline.utcoffset() is None:
        raise ValueError("A timezone-aware deadline is required")
    if (
        type(since_time) is not int
        or type(until_time) is not int
        or since_time >= until_time
    ):
        raise ValueError("Invalid frozen history window")
    if not isinstance(request, dict) or not _canonical_native_id(
        request.get("native_id")
    ):
        raise ValueError("A stable native X identity is required")
    handle, query = request.get("handle"), request.get("query")
    if not isinstance(handle, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
        raise ValueError("A valid author handle is required")
    if not isinstance(query, str) or not re.search(
        rf"(?<![\w])from:{re.escape(handle)}(?![\w])", query, re.IGNORECASE
    ):
        raise ValueError("Frozen query must name the selected author")
    expected_query = XClient._effective_search_query(
        query, since=None, since_time=since_time, until_time=until_time
    )
    operators = re.findall(r"(?<!\w)(?:since_time|until_time):\d+(?!\d)", query)
    if expected_query != query or sorted(operators) != sorted(
        [f"since_time:{since_time}", f"until_time:{until_time}"]
    ):
        raise ValueError("Query time operators must match the frozen window")
    assert_under_length_cap(query)
    if len(query.encode("utf-8")) > 512:
        raise ValueError("Complete request exceeds 512 UTF-8 bytes")
    identity = hashlib.sha256(
        json.dumps(
            [
                request,
                since_time,
                until_time,
                max_pages,
                max_posts,
                deadline.isoformat(),
            ],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    if isinstance(journal, CollectionRequestHistoryJournal):
        journal.validate_search(request, since_time, until_time)
    if live_client:
        client = journal.bind_client(client)
    saved = list(journal.load(identity))
    records, appearances, rejected, seen_ids, seen_cursors = [], [], [], {}, set()
    conflicted_ids = set()
    cursor = None
    drained = False
    made = 0

    def result(reason):
        return {
            "status": "complete" if reason == "complete" else "partial",
            "reason": reason,
            "cursor": cursor,
            "records": records,
            "appearances": appearances,
            "rejected": rejected,
            "requests_made": made,
        }

    def consume(receipt):
        nonlocal cursor, drained
        if (
            receipt.get("identity") != identity
            or receipt.get("cursor_before") != cursor
        ):
            raise ValueError("Receipt query or cursor ancestry changed")
        if receipt.get("state") == "rate_limited":
            return "rate_limited"
        if receipt.get("state") != "received":
            return "unknown_request_outcome"
        page = receipt["page"]
        for item in page["items"]:
            post_id = item.get("id") if isinstance(item, dict) else None
            reason = None
            if not _canonical_native_id(post_id):
                reason = "invalid_post_id"
            elif item.get("author_id") != request["native_id"]:
                reason = "wrong_author"
            elif not isinstance(item.get("text"), str) or not item["text"].strip():
                reason = "missing_source_text"
            else:
                try:
                    timestamp = _history_time(item.get("created_at")).timestamp()
                    if not since_time <= timestamp < until_time:
                        reason = "outside_window"
                except (TypeError, ValueError, OverflowError):
                    reason = "invalid_publication_time"
            appearances.append(
                {"id": post_id, "cursor_before": cursor, "reason": reason}
            )
            if reason:
                rejected.append({"item": item, "reason": reason})
                continue
            if post_id in conflicted_ids:
                rejected.append({"item": item, "reason": "conflicting_post_content"})
                continue
            previous = seen_ids.get(post_id)
            if previous is not None:
                if previous.get("text") != item.get("text"):
                    conflicted_ids.add(post_id)
                    records.remove(previous)
                    seen_ids.pop(post_id)
                    rejected.append(
                        {"item": item, "reason": "conflicting_post_content"}
                    )
                continue
            seen_ids[post_id] = item
            records.append(item)
        if page.get("clipped") or page.get("continuation_invalid"):
            return "invalid_or_clipped_page"
        next_cursor = page.get("next_cursor")
        if not page.get("has_more"):
            drained = True
            return None
        if not next_cursor or next_cursor == cursor or next_cursor in seen_cursors:
            return "repeated_or_missing_cursor"
        seen_cursors.add(next_cursor)
        cursor = next_cursor
        return None

    for receipt in saved:
        if drained:
            raise ValueError("Receipt follows a drained query")
        reason = consume(receipt)
        if reason:
            return result(reason)
    pages_seen = len(saved)
    while (
        not drained
        and pages_seen < max_pages
        and len(appearances) < max_posts
        and made < max_requests
    ):
        current = (now or (lambda: datetime.now(UTC)))()
        if current >= deadline or (
            live_client and (deadline - current).total_seconds() < client.timeout_s
        ):
            break
        try:
            token = journal.reserve(identity, cursor)
        except HistoryBudgetExhausted:
            return result("budget_exhausted")
        made += 1
        try:
            pages = iter(
                client.run_search_pages(
                    query,
                    max_results=min(20, max_posts - len(appearances)),
                    max_pages=1,
                    cursor=cursor,
                    since_time=since_time,
                    until_time=until_time,
                )
            )
            page = next(pages)
        except Exception as exc:  # noqa: BLE001 - unknown sends must stay reserved
            status = None
            if live_client:
                status = journal.fail(token, type(exc).__name__)
            response = result(
                "rate_limited" if status == 429 else "request_failed_or_unknown"
            )
            response["error_type"] = type(exc).__name__
            return response
        receipt_page = {
            "items": page.items,
            "has_more": page.has_more,
            "next_cursor": page.next_cursor,
            "clipped": page.clipped
            or len(page.items) > max_posts - len(appearances)
            or len(page.raw_post_ids) > len(page.items),
            "continuation_invalid": page.continuation_invalid,
            "raw_post_ids": list(page.raw_post_ids),
            "received_at": page.received_at.isoformat(),
        }
        journal.finish(token, receipt_page)
        reason = consume(
            {
                "identity": identity,
                "cursor_before": cursor,
                "state": "received",
                "page": receipt_page,
            }
        )
        pages_seen += 1
        if reason:
            return result(reason)
    return result(
        "complete"
        if drained and not rejected
        else "rejected_source_rows"
        if drained
        else "bound_reached"
    )


def lookup_history_posts(
    *,
    post_ids,
    expected_authors,
    client,
    journal,
    authorized=False,
    credential_purpose=None,
    max_requests=0,
    deadline=None,
    now=None,
):
    """Recover exact posts with frozen IDs and durable request receipts.

    Saved lookup pages must use the same reserve/finish durability contract as
    ``collect_history_pages``. Missing, foreign and unverified IDs are retained
    as unresolved rather than fabricated posts.
    """
    if (
        authorized is not True
        or credential_purpose is not TwitterApiCredentialPurpose.ON_DEMAND
    ):
        raise ValueError("Explicit on-demand authorization is required")
    live_client = isinstance(client, XClient)
    if live_client and not isinstance(journal, CollectionRequestHistoryJournal):
        raise TypeError("Live collection requires shared durable receipt integration")
    if not getattr(client, "api_key", None):
        raise ValueError("On-demand client credential is required")
    if type(max_requests) is not int or max_requests < 1:
        raise ValueError("A finite positive request bound is required")
    if not isinstance(deadline, datetime) or deadline.utcoffset() is None:
        raise ValueError("A timezone-aware deadline is required")
    if not isinstance(post_ids, list) or not all(
        _canonical_native_id(x) for x in post_ids
    ):
        raise ValueError("Post identities must be canonical decimal strings")
    if not isinstance(expected_authors, dict) or any(
        key not in post_ids or not _canonical_native_id(value)
        for key, value in expected_authors.items()
    ):
        raise ValueError("Expected authors must be canonical selected identities")
    if isinstance(journal, CollectionRequestHistoryJournal):
        journal.validate_lookup(post_ids, expected_authors, deadline)
    if live_client:
        client = journal.bind_client(client)
    unique_ids = list(dict.fromkeys(post_ids))
    identity = hashlib.sha256(
        json.dumps(
            ["lookup/v1", post_ids, expected_authors, deadline.isoformat()],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    batches = [
        unique_ids[i : i + TWEETS_BY_IDS_CHUNK]
        for i in range(0, len(unique_ids), TWEETS_BY_IDS_CHUNK)
    ]
    saved = list(journal.load(identity))
    if len(saved) > len(batches):
        raise ValueError("Unexpected extra lookup receipt")
    accepted, unresolved, appearances, provider_appearances = [], [], [], []
    made = 0
    raw_appearances_complete = True

    def result(reason):
        return {
            "status": "complete" if reason == "complete" else "partial",
            "reason": reason,
            "records": accepted,
            "unresolved": unresolved,
            "appearances": appearances,
            "provider_returned_ids": provider_appearances,
            "provider_appearances_complete": raw_appearances_complete,
            "duplicate_id_count": len(post_ids) - len(unique_ids),
            "requests_made": made,
            "batches_processed": len(saved),
        }

    def consume(receipt, batch_index):
        nonlocal raw_appearances_complete
        if receipt.get("identity") != identity or receipt.get("cursor_before") != str(
            batch_index
        ):
            raise ValueError("Lookup receipt ancestry changed")
        if receipt.get("state") == "rate_limited":
            return "rate_limited"
        if receipt.get("state") != "received":
            return "unknown_request_outcome"
        batch = batches[batch_index]
        mapping = receipt["page"].get("posts")
        if not isinstance(mapping, dict):
            raise TypeError("Invalid lookup receipt")
        raw = receipt["page"].get("raw_lookup")
        if raw is not None:
            raw_ids = raw.get("returned_ids")
            conflicts = raw.get("conflicting_sources")
            if not isinstance(raw_ids, list) or not isinstance(conflicts, dict):
                raise ValueError("Invalid lookup appearance receipt")
            provider_appearances.extend(raw_ids)
            for extra in raw_ids:
                if extra not in batch:
                    unresolved.append({"id": extra, "reason": "unrequested_post_id"})
        else:
            conflicts = {}
            raw_appearances_complete = False
        for extra in mapping.keys() - set(batch):
            unresolved.append(
                {"id": extra, "reason": "unrequested_post_id", "item": mapping[extra]}
            )
        for post_id in batch:
            item = mapping.get(post_id)
            reason = None
            if item is None:
                reason = "missing_or_unavailable"
            elif not isinstance(item, dict) or item.get("id") != post_id:
                reason = "post_identity_mismatch"
            elif post_id in conflicts:
                reason = "conflicting_post_content"
            elif post_id not in expected_authors:
                reason = "author_not_established"
            elif item.get("author_id") != expected_authors[post_id]:
                reason = "wrong_author"
            elif not isinstance(item.get("text"), str) or not item["text"].strip():
                reason = "missing_source_text"
            else:
                try:
                    _history_time(item.get("created_at"))
                except (TypeError, ValueError, OverflowError):
                    reason = "invalid_publication_time"
            appearances.append({"id": post_id, "batch": batch_index, "reason": reason})
            if reason:
                unresolved.append({"id": post_id, "reason": reason, "item": item})
                if post_id in conflicts:
                    unresolved[-1]["source_versions"] = conflicts[post_id]
            else:
                accepted.append(item)
        return None

    for i, receipt in enumerate(saved):
        reason = consume(receipt, i)
        if reason:
            return result(reason)
    while len(saved) < len(batches) and made < max_requests:
        current = (now or (lambda: datetime.now(UTC)))()
        if current >= deadline or (
            live_client and (deadline - current).total_seconds() < client.timeout_s
        ):
            break
        batch_index = len(saved)
        try:
            token = journal.reserve(identity, str(batch_index))
        except HistoryBudgetExhausted:
            return result("budget_exhausted")
        made += 1
        try:
            posts = client.get_posts_by_ids(batches[batch_index])
        except Exception as exc:  # noqa: BLE001 - never resend an uncertain request
            status = journal.fail(token, type(exc).__name__) if live_client else None
            response = result(
                "rate_limited" if status == 429 else "request_failed_or_unknown"
            )
            response["error_type"] = type(exc).__name__
            return response
        page = {
            "posts": posts,
            "raw_lookup": journal._lookup_raw if live_client else None,
        }
        journal.finish(token, page)
        receipt = {
            "identity": identity,
            "cursor_before": str(batch_index),
            "state": "received",
            "page": page,
        }
        saved.append(receipt)
        reason = consume(receipt, batch_index)
        if reason:
            return result(reason)
    reason = (
        "bound_reached"
        if len(saved) < len(batches)
        else "unresolved_posts"
        if unresolved
        else "complete"
    )
    return result(reason)


def _request(query, start, end):
    rendered = XClient._effective_search_query(
        query, since=None, since_time=start, until_time=end
    )
    assert_under_length_cap(rendered)
    if len(rendered.encode("utf-8")) > 512:
        raise ValueError("Complete request exceeds 512 UTF-8 bytes")
    return rendered


def build_history_plan(*, people, cutoff, post_ids=()):
    """Return exact requests and ID batches; collecting requires separate authority."""
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() is None:
        raise ValueError("A timezone-aware frozen cutoff is required")
    start = int(datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp())
    end = int(cutoff.timestamp())
    if end <= start:
        raise ValueError("Cutoff must follow the history start")
    queries = []
    held_people = []
    seen = set()
    for person in people:
        native_id, handle = person.get("native_id"), person.get("handle")
        if not isinstance(handle, str) or not re.fullmatch(
            r"[A-Za-z0-9_]{1,15}", handle
        ):
            raise ValueError("A valid X handle is required")
        if native_id is None:
            held_people.append(
                {"handle": handle, "reason": "Stable X identity is missing"}
            )
            continue
        if (
            not isinstance(native_id, str)
            or not native_id.isascii()
            or not native_id.isdigit()
            or int(native_id) <= 0
            or str(int(native_id)) != native_id
        ):
            raise ValueError("A stable native X identity is required")
        if native_id in seen:
            raise ValueError("Duplicate native X identity")
        seen.add(native_id)
        prefix = f"from:{handle} "
        for family, terms in (
            ("special_events_1_baseline", GENERAL_QUERY_CLAUSES),
            ("job_history", MOVE_TERMS),
        ):
            chunk = []
            for term in terms:
                candidate = [*chunk, term]
                try:
                    _request(prefix + "(" + " OR ".join(candidate) + ")", start, end)
                except ValueError:
                    if not chunk:
                        raise
                    queries.append(
                        {
                            "native_id": native_id,
                            "handle": handle,
                            "family": family,
                            "query": _request(
                                prefix + "(" + " OR ".join(chunk) + ")", start, end
                            ),
                        }
                    )
                    # Validate a single clause too; never silently omit an
                    # alternative that cannot fit with its author and window.
                    _request(prefix + "(" + term + ")", start, end)
                    chunk = [term]
                else:
                    chunk = candidate
            if chunk:
                queries.append(
                    {
                        "native_id": native_id,
                        "handle": handle,
                        "family": family,
                        "query": _request(
                            prefix + "(" + " OR ".join(chunk) + ")", start, end
                        ),
                    }
                )
    requested_ids = list(post_ids)
    ids = list(dict.fromkeys(requested_ids))
    if any(
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdigit()
        or int(value) <= 0
        or str(int(value)) != value
        for value in ids
    ):
        raise ValueError("Post identities must be decimal strings")
    batches = [
        ids[i : i + TWEETS_BY_IDS_CHUNK]
        for i in range(0, len(ids), TWEETS_BY_IDS_CHUNK)
    ]
    return {
        "schema": "save-person-job-history-plan/v1",
        "query_version": HISTORY_QUERY_VERSION,
        "baseline_version": QUERY_VERSION,
        "credential_purpose": "on_demand",
        "since_time": start,
        "until_time": end,
        "queries": queries,
        "held_people": held_people,
        "requested_post_ids": requested_ids,
        "duplicate_post_id_count": len(requested_ids) - len(ids),
        "lookup_batches": batches,
        "lookup_basis": "Cited IDs are candidates; target inventory has not been checked for missing posts.",
        "syntax_status": "not_live_verified",
        "dispatch_available": False,
        "limitation": "Saved plan only; collection requires separate authorization and finite bounds.",
    }
