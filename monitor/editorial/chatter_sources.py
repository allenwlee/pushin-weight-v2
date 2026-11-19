"""Typed Chatter collection ownership and compact physical source receipts."""

import hashlib
import json
import re
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.collection_capture import (
    archive_document,
    begin_request,
    finish_request,
    read_document,
)
from core.collection_jobs import register_job, set_job_state
from core.collection_state import checkpoint_scope, claim_job, fenced_run, finish_run
from core.models import (
    CollectionAttempt,
    CollectionJob,
    CollectionObservation,
    CollectionRequest,
    CollectionRun,
    CollectionScopeRequestUse,
    DataSource,
    OriginalContentCall,
)
from monitor.original_content import digest
from scripts.harvest_cost.pricing import load_pricing, rates_to_dict
from x_monitor.provider_http import https_request
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
from x_monitor.x_client import XClient, _normalize_tweet

from .chatter_accounting import admit, money
from .chatter_history import (
    freeze_sources,
    locked_run,
    project_post,
    save_query,
    validated_packet,
)
from .persistence import BudgetHeld

SOURCE_FINALIZATION_HEADROOM = timedelta(minutes=3)


class CompactPost(BaseModel):
    """Only evidence used by ingestion/frozen sources; no account profile payload."""
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[0-9]{1,25}$")
    text: str = Field(max_length=6000)
    created_at: str | None
    lang: str | None
    author_id: str
    author_handle: str
    like_count: int | None = Field(ge=0)
    reply_count: int | None = Field(ge=0)
    retweet_count: int | None = Field(ge=0)
    quote_count: int | None = Field(ge=0)
    quoted_status_id: str | None
    quoted_text: str | None = Field(max_length=6000)
    quoted_author_handle: str | None
    quoted_author_id: str | None
    quoted_created_at: str | None
    quoted_media_urls: list[str] = Field(max_length=8)
    is_quote: bool | None
    is_retweet: bool | None
    is_reply: bool | None
    in_reply_to_id: str | None
    in_reply_to_username: str | None
    in_reply_to_user_id: str | None
    media_urls: list[str] = Field(max_length=8)
    mentioned_account_ids: list[str] = Field(default_factory=list, max_length=100)


class ProjectionGap(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ordinal: int = Field(ge=0)
    code: Literal["invalid_source_projection"] = "invalid_source_projection"


class CompactSourceReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1, 2]
    projection_kind: Literal["chatter-source-reply-v1"]
    tweets: list[CompactPost]
    gaps: list[ProjectionGap]
    has_next_page: bool | None
    next_cursor: str | None

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("integer projection version required")
        return value


def compact_source_reply(rows, decoded):
    from x_monitor.tweet_entities import mention_id

    from .evidence import safe_source_image

    selected, gaps = [], []
    fields = set(CompactPost.model_fields) - {"quoted_created_at", "quoted_author_id", "quoted_media_urls", "media_urls", "mentioned_account_ids"}
    for index, raw in enumerate(rows):
        try:
            normalized = _normalize_tweet(raw)
            item = {key: normalized.get(key) for key in fields}
            for normalized_key, provider_key in (("like_count", "likeCount"), ("reply_count", "replyCount"),
                    ("retweet_count", "retweetCount"), ("quote_count", "quoteCount")):
                measured = raw.get(provider_key)
                item[normalized_key] = measured if type(measured) is int and measured >= 0 else None
            item["mentioned_account_ids"] = list(dict.fromkeys(identity for entry in (normalized.get("entities") or {}).get("user_mentions", []) if (identity := mention_id(entry))))[:100]
            quote = raw.get("quoted_tweet") or {}
            item["quoted_created_at"] = quote.get("createdAt") or quote.get("created_at")
            item["quoted_author_id"] = str((quote.get("author") or {}).get("id") or "") or None
            item["quoted_media_urls"] = [entry["media_url_https"] for entry in (quote.get("extendedEntities") or {}).get("media", [])
                if isinstance(entry, dict) and safe_source_image(entry.get("media_url_https"))][:8]
            extended = normalized.get("extended_entities") or {}
            item["media_urls"] = [entry["media_url_https"] for entry in extended.get("media", [])
                if isinstance(entry, dict) and safe_source_image(entry.get("media_url_https"))][:8]
            selected.append(CompactPost.model_validate(item))
        except (ValueError, TypeError, AttributeError):
            gaps.append(ProjectionGap(ordinal=index))
    return CompactSourceReply(schema_version=2, projection_kind="chatter-source-reply-v1", tweets=selected, gaps=gaps,
        has_next_page=decoded.get("has_next_page"), next_cursor=decoded.get("next_cursor")).model_dump(mode="json")


def compact_post_wire(row):
    """Reconstitute only captured source fields for the existing normalizer."""
    value = {"id": row["id"], "text": row["text"], "createdAt": row["created_at"], "lang": row["lang"],
             "author": {"id": row["author_id"], "userName": row["author_handle"]},
             "extendedEntities": row.get("extended_entities"),
             "entities": {"user_mentions": [{"id_str": identity} for identity in row.get("mentioned_account_ids", [])]},
             "isQuote": row["is_quote"], "isRetweet": row["is_retweet"], "isReply": row["is_reply"],
             "inReplyToId": row["in_reply_to_id"], "inReplyToUserId": row["in_reply_to_user_id"],
             "inReplyToUsername": row["in_reply_to_username"]}
    for key, field in (("likeCount", "like_count"), ("replyCount", "reply_count"),
                       ("retweetCount", "retweet_count"), ("quoteCount", "quote_count")):
        if row[field] is not None:
            value[key] = row[field]
    if row["quoted_status_id"]:
        value["quoted_tweet"] = {"id": row["quoted_status_id"], "text": row["quoted_text"],
            "createdAt": row["quoted_created_at"],
            "author": {"id": row["quoted_author_id"], "userName": row["quoted_author_handle"]},
            "extendedEntities": {"media": [{"media_url_https": url} for url in row["quoted_media_urls"]]}}
    return value


def _validated_ranked_execution(run, execution, requests, purpose):
    """Check the same immutable receipts for dispatch admission and fenced reclaim."""
    from .chatter_trends import read_ranked_batch

    batch = read_ranked_batch(run.pk)
    now = timezone.now()
    definition = execution.job.definition
    options = definition.get("options") if isinstance(definition, dict) else None
    if (execution.content_run_id != run.pk or execution.job.operation != "chatter_search"
            or execution.job.source_id != "x" or execution.job.purpose != "content"
            or not isinstance(options, dict) or options.get("workflow_version") != "chatter-trends-sources-v1"
            or execution.completed_at is None and (
                execution.lease_expires_at is None or execution.lease_expires_at > now)
            or execution.attempts.exclude(credential_purpose=purpose).exists()
            or len({request.endpoint_url for request in requests}) != len(requests)):
        raise BudgetHeld("saved Chatter source execution requires reconciliation")
    for request in requests:
        if (request.attempt.run_id != execution.pk or request.transport_outcome != "received"
                or request.http_status != 200 or request.received_at is None
                or request.archive_id is None or request.body_lost or not request.selection_accounted
                or not request.response_sha256
                or request.scope_run.run_id != execution.pk
                or request.scope_run.content_call_id != batch["rank_call_id"]
                or request.archive.encoding != "selected-json-canonical-v1"
                or request.archive.capture_kind != "chatter_source_projection"
                or request.archive.byte_count != len(bytes(request.archive.body))):
            raise BudgetHeld("saved Chatter source requests require reconciliation")
        value = CompactSourceReply.model_validate(read_document(request.archive))
        if len(value.tweets) + len(value.gaps) != request.raw_count:
            raise BudgetHeld("saved Chatter source projection count changed")


def source_resume_is_safe(run):
    """Provider-free eligibility; an uncertain send or live source lease stays held."""
    from .chatter_trends import checkpoint

    try:
        if run.scope_key != "chatter:personalized-trends:v1":
            return False
        purpose = checkpoint(run).credential_purpose
        executions = list(CollectionRun.objects.filter(content_run=run).exclude(
            job__job_key__startswith="chatter-personalized-trends:").select_related("job"))
        if len(executions) > 1:
            return False
        for execution in executions:
            requests = list(CollectionRequest.objects.filter(attempt__run=execution).select_related(
                "archive", "attempt", "scope_run"))
            _validated_ranked_execution(run, execution, requests, purpose)
        return True
    except (ValueError, TypeError, KeyError, OriginalContentCall.DoesNotExist, CollectionRun.DoesNotExist):
        return False


class SourceSession:
    def __init__(
        self,
        run,
        cfg,
        *,
        purpose,
        client=None,
        transport=None,
        policy_reader=None,
        resume=False,
    ):
        if not isinstance(purpose, TwitterApiCredentialPurpose):
            raise TypeError(
                "Chatter source calls require an explicit credential purpose"
            )
        self.run, self.cfg = run, cfg
        self.started_monotonic = time.monotonic()
        self.purpose = purpose
        self.ranked_lane = run.scope_key == "chatter:personalized-trends:v1"
        self._transport = transport or https_request
        self.policy_reader = policy_reader
        self.rates = load_pricing(repo_root=settings.BASE_DIR)
        self.client = client or (XClient(api_key="") if self.ranked_lane else XClient.from_env(purpose))
        self.client.max_retries = 0
        self.client.timeout_s = cfg.chatter.source_timeout_seconds
        self.client.max_response_bytes = 2_000_000
        self.client.on_exchange_start, self.client.on_exchange_finish = (
            self.start,
            self.finish,
        )
        mode = (
            "recurring"
            if purpose == TwitterApiCredentialPurpose.SCHEDULED
            else "manual"
        )
        options = {
            "credential_purpose": purpose.value,
            "workflow_version": "chatter-trends-sources-v1" if self.ranked_lane else "chatter-v1",
            "pricing_sha256": digest(rates_to_dict(self.rates)),
        }
        source, _ = DataSource.objects.get_or_create(
            pk="x", defaults={"name": "X", "source_type": "social"}
        )
        job = register_job(
            job_key="chatter-search:"
            + digest(
                [
                    cfg.chatter.model_dump(mode="json"),
                    options,
                    run.pk if mode == "manual" else None,
                ]
            )[:40],
            source=source,
            purpose="content",
            operation="chatter_search",
            mode=mode,
            definition={"version": 2, "options": options},
            settings={
                "owner_kind": "source",
                "schedule_kind": "interval" if mode == "recurring" else "manual",
                "schedule_driver": "external_render_cron"
                if mode == "recurring"
                else "manual",
                "interval_seconds": (3600 if self.ranked_lane else 900) if mode == "recurring" else None,
                "max_requests": None if self.ranked_lane else cfg.chatter.source_request_limit,
                "max_bytes": 8_000_000,
                "max_seconds": 600,
                "max_items": None if self.ranked_lane else 200,
            },
        )
        self.last_receipt_at = None
        self.last_request = None
        self.metric_presence = {}
        if resume:
            self.claim = self._resume(job, purpose)
            return
        if CollectionRun.objects.filter(content_run=run).exclude(
            job__job_key__startswith="chatter-personalized-trends:"
        ).exists():
            raise BudgetHeld("Chatter source execution already recorded; do not resend")
        if job.state == "paused":
            set_job_state(job.pk, "ready")
        self.claim = claim_job(
            job.pk,
            invocation_id=f"chatter:{run.pk}",
            manual_authorized=True,
            typed=True,
        )
        CollectionRun.objects.filter(pk=self.claim.run_id).update(content_run=run)
        CollectionAttempt.objects.filter(pk=self.claim.attempt_id).update(
            credential_purpose=purpose.value
        )

    @transaction.atomic
    def _resume(self, job, purpose):
        current = locked_run(self.run.pk, self.run.fence)
        job = CollectionJob.objects.select_for_update().get(pk=job.pk)
        execution = CollectionRun.objects.select_for_update().get(content_run=current, job=job)
        requests = list(CollectionRequest.objects.filter(attempt__run=execution))
        if self.ranked_lane:
            return self._resume_ranked(current, execution, requests, job, purpose)
        call = OriginalContentCall.objects.get(run=current, stage="discovery")
        if (
            current.discovery_state != "failed"
            or current.outcome.get("phase") != "held"
            or current.outcome.get("discovery_recovery")
            or current.provider_calls.count() != 1
            or call.state != "completed"
            or current.brand_narratives.exists()
            or validated_packet(current.snapshot)["sources"]
            or execution.job_id != job.pk
            or execution.status != "failed"
            or execution.completed_at is None
            or execution.attempts.count() != 1
            or execution.attempts.exclude(credential_purpose=purpose.value).exists()
            or len(requests) != 1
            or requests[0].endpoint_url != "https://api.x.ai/v1/responses"
            or requests[0].transport_outcome != "received"
            or not 200 <= (requests[0].http_status or 0) < 300
            or requests[0].received_at is None
            or requests[0].scope_run.content_call_id != call.pk
        ):
            raise BudgetHeld("saved discovery cannot be resumed safely")
        # Preserve the failed attempt and physical receipt. Only the aggregate
        # execution reopens, through the collection engine's existing continuation.
        current.outcome = {
            **current.outcome,
            "phase": "discovering",
            "discovery_recovery": {
                "version": 1,
                "call_id": call.pk,
                "previous_outcome": current.outcome,
                "previous_completed_at": execution.completed_at.isoformat(),
                "resumed_at": timezone.now().isoformat(),
            },
        }
        current.discovery_state = "pending"
        current.fence += 1
        current.save(
            update_fields=["outcome", "discovery_state", "fence", "updated_at"]
        )
        execution.completed_at, execution.status, execution.execution_state = (
            None,
            "partial",
            "yielded",
        )
        execution.save(
            update_fields=["completed_at", "status", "execution_state", "updated_at"]
        )
        claim = claim_job(
            job.pk,
            invocation_id=f"chatter:{current.pk}:saved-discovery-v1",
            continue_from=execution.pk,
            manual_authorized=True,
            typed=True,
        )
        CollectionAttempt.objects.filter(pk=claim.attempt_id).update(
            credential_purpose=purpose.value
        )
        self.run.fence, self.run.outcome = current.fence, current.outcome
        self.last_request, self.last_receipt_at = requests[0], requests[0].received_at
        return claim

    def _resume_ranked(self, current, execution, requests, job, purpose):
        _validated_ranked_execution(current, execution, requests, purpose.value)
        execution.attempts.filter(outcome="running").update(
            outcome="interrupted", stop_reason="expired_lease")
        current.fence += 1
        current.save(update_fields=["fence", "updated_at"])
        execution.completed_at, execution.status, execution.execution_state = None, "partial", "yielded"
        execution.save(update_fields=["completed_at", "status", "execution_state", "updated_at"])
        claim = claim_job(job.pk, invocation_id=f"chatter:{current.pk}:source-recovery:{current.fence}",
                          continue_from=execution.pk, manual_authorized=True, typed=True)
        CollectionAttempt.objects.filter(pk=claim.attempt_id).update(credential_purpose=purpose.value)
        self.run.fence = current.fence
        if requests:
            self.last_request = max(requests, key=lambda row: row.received_at)
            self.last_receipt_at = self.last_request.received_at
        return claim

    def captured_requests(self):
        """Saved compact evidence for gathering to replay before new I/O."""
        return CollectionRequest.objects.filter(attempt__run_id=self.claim.run_id).select_related("archive", "attempt").order_by("started_at", "pk")

    def captured_reply(self, request):
        if (request.attempt.run_id != self.claim.run_id or request.archive is None
                or request.archive.encoding != "selected-json-canonical-v1"):
            raise ValueError("compact source capture ownership mismatch")
        value = CompactSourceReply.model_validate(read_document(request.archive)).model_dump(mode="json")
        if len(value["tweets"]) + len(value["gaps"]) != request.raw_count:
            raise ValueError("compact source projection count changed")
        for row in value["tweets"]:
            self.metric_presence[row["id"]] = {key: row[field] for key, field in (
                ("likes", "like_count"), ("replies", "reply_count"), ("reposts", "retweet_count"), ("quotes", "quote_count"))}
            media = row.pop("media_urls")
            row["extended_entities"] = {"media": [{"media_url_https": url} for url in media]}
        self.last_request, self.last_receipt_at = request, request.received_at
        return value

    def search_pages(self, query):
        """Replay exact captured requests through the shared paginator before new I/O."""
        from x_monitor.twitterapi_credentials import require_twitterapi_api_key

        original_get = self.client._get

        def get(path, params):
            endpoint = self.client.base_url + path + ("?" + urlencode(params) if params else "")
            saved = list(self.captured_requests().filter(endpoint_url=endpoint))
            if saved:
                if len(saved) != 1 or saved[0].transport_outcome != "received" or saved[0].http_status != 200:
                    raise BudgetHeld("saved source send requires reconciliation")
                reply = self.captured_reply(saved[0])
                if reply["gaps"]:
                    raise ValueError("saved source projection has gaps")
                return {"tweets": [compact_post_wire(row) for row in reply["tweets"]],
                        "has_next_page": reply["has_next_page"], "next_cursor": reply["next_cursor"]}
            if not self.client.api_key:
                self.client.api_key = require_twitterapi_api_key(self.purpose)
            return original_get(path, params)

        self.client._get = get
        try:
            for page in self.client.run_search_pages(query, max_results=None, max_pages=None):
                if self.last_receipt_at:
                    page = replace(page, received_at=self.last_receipt_at, items=[
                        {**item, "_api_received_at": self.last_receipt_at.isoformat()} for item in page.items])
                yield page
        finally:
            self.client._get = original_get

    def scope(self, name, query=None, *, tool=False, start=None, end=None):
        query_row = save_query(query) if query else None
        call = OriginalContentCall.objects.filter(
            run=self.run, stage="trends-ranking-v1" if self.ranked_lane else "discovery"
        ).first()
        ownership = {
            "query_id": query_row.pk if query_row else None,
            "content_call_id": call.pk if call else None,
        }
        scope = checkpoint_scope(
            self.claim,
            scope_kind="chatter_tool" if tool else "chatter_search",
            scope_key=name,
            ownership=ownership,
            typed=True,
            requested_start_at=start,
            requested_end_at=end,
        )
        if scope.search_query_id not in (
            None,
            ownership["query_id"],
        ) or scope.content_call_id not in (None, ownership["content_call_id"]):
            raise ValueError("Chatter scope identity changed")
        scope.search_query, scope.content_call = query_row, call
        scope.save(update_fields=["search_query", "content_call"])
        return scope

    def _check_finalization_headroom(self, run):
        if self.ranked_lane and (
            run.lease_until is None
            or run.lease_until <= timezone.now() + SOURCE_FINALIZATION_HEADROOM
        ):
            raise BudgetHeld("Chatter source finalization headroom reached")

    def start(self, path, params):
        if time.monotonic() - self.started_monotonic >= 600:
            raise BudgetHeld("Chatter source execution deadline exhausted")
        self._check_finalization_headroom(self.run)
        if self.ranked_lane:
            used = CollectionRequest.objects.filter(attempt__run_id=self.claim.run_id).aggregate(total=Sum(Coalesce("response_bytes", 2_000_000)))["total"] or 0
            remaining = 8_000_000 - used
            if remaining <= 0:
                raise BudgetHeld("Chatter source byte allowance exhausted")
            self.client.max_response_bytes = min(2_000_000, remaining)
            self.client.timeout_s = min(self.cfg.chatter.source_timeout_seconds, max(1, int(600 - (time.monotonic() - self.started_monotonic))))
        if self.policy_reader and not self.policy_reader().chatter.enabled:
            raise BudgetHeld("Chatter disabled before source dispatch")
        model = path == "https://api.x.ai/v1/responses"
        query = params.get("query") if not model else None
        bounds = {}
        if query:
            for operator, value in re.findall(
                r"\b(since_time|until_time):([0-9]+)\b", query
            ):
                bounds["start" if operator == "since_time" else "end"] = (
                    datetime.fromtimestamp(int(value), tz=UTC)
                )
            query = re.sub(r"\s+(?:since_time|until_time):[0-9]+\b", "", query).strip()
        scope = self.scope(
            ("responses:" if model else "twitterapi:") + digest([path, params])[:40],
            query,
            **bounds,
        )
        with transaction.atomic():
            current = locked_run(self.run.pk, self.run.fence)
            with fenced_run(self.claim):
                endpoint_url = path if model else self.client.base_url + path + ("?" + urlencode(params) if params else "")
                if self.ranked_lane and CollectionRequest.objects.filter(
                    attempt__run_id=self.claim.run_id, endpoint_url=endpoint_url
                ).exists():
                    raise BudgetHeld("saved source request already captured; replay required")
                if (
                    not self.ranked_lane
                    and CollectionRequest.objects.filter(
                        attempt__run_id=self.claim.run_id
                    ).count()
                    >= self.cfg.chatter.source_request_limit
                ):
                    raise BudgetHeld("Chatter source request limit exhausted")
                if model:
                    if not OriginalContentCall.objects.filter(
                        run=self.run, stage="discovery", state="sent"
                    ).exists():
                        raise BudgetHeld(
                            "model request must be reserved before transport"
                        )
                    amount = Decimal(0)
                else:
                    amount = admit(
                        self.cfg, self.cfg.chatter.source_request_reservation_usd
                    )
                attempt = CollectionAttempt.objects.select_for_update().get(pk=self.claim.attempt_id)
                self._check_finalization_headroom(current)
                if self.ranked_lane:
                    # Reserve this admitted physical send, not a fixed page quota.
                    attempt.reserved_requests = attempt.requests.count() + 1
                    attempt.save(update_fields=["reserved_requests"])
                request = begin_request(
                    attempt,
                    scope,
                    endpoint_url=endpoint_url,
                    method="POST" if model else "GET",
                    requested_start_at=scope.requested_start_at,
                    requested_end_at=scope.requested_end_at,
                    request_config=params.get("queryType")
                    if not model
                    else "chatter-semantic-v1",
                )
                request.reserved_usd = amount
                request.save(update_fields=["reserved_usd"])
        return request

    def finish(self, request, receipt):
        body = receipt.get("body")
        observed = timezone.now()
        status = receipt.get("status_code")
        outcome = receipt.get("outcome", "unknown")
        with transaction.atomic():
            saved = finish_request(
                request,
                outcome=outcome,
                http_status=status,
                response_bytes=len(body) if isinstance(body, bytes) else None,
                error_code=None
                if outcome == "received"
                else "source_transport_failure",
                now=observed,
            )
            model = saved.endpoint_url == "https://api.x.ai/v1/responses"
            rows = None
            try:
                decoded = json.loads(body) if isinstance(body, bytes) else {}
                if (
                    not model
                    and isinstance(decoded, dict)
                    and 200 <= (status or 0) < 300
                ):
                    candidate = decoded.get("tweets", decoded.get("data"))
                    if (
                        isinstance(candidate, list)
                        and not decoded.get("error")
                        and str(decoded.get("status", "")).lower()
                        not in {"error", "failed"}
                    ):
                        rows = candidate
            except (ValueError, TypeError):
                pass
            if model:
                saved.estimated_usd = Decimal(
                    0
                )  # The model ledger owns this physical request's entire bill.
            elif rows is not None:
                if self.ranked_lane:
                    projection = compact_source_reply(rows, decoded)
                    saved.archive = archive_document(
                        json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
                        encoding="selected-json-canonical-v1", capture_kind="chatter_source_projection",
                    )
                credits = max(
                    Decimal(str(self.rates.call_floor_credits)),
                    len(rows) * Decimal(str(self.rates.tweet_credits)),
                )
                saved.estimated_usd = money(
                    credits / Decimal(str(self.rates.credits_per_usd))
                )
                saved.raw_count, saved.response_sha256 = (
                    len(rows),
                    hashlib.sha256(body).digest(),
                )
                saved.body_lost, saved.selection_accounted = False, True
                for index, row in enumerate(rows):
                    identity = str(row.get("id") or "") if isinstance(row, dict) else ""
                    if not re.fullmatch(r"[0-9]{1,25}", identity):
                        identity = ""
                    if identity and identity not in self.metric_presence:
                        self.metric_presence[identity] = {
                            name: row.get(raw)
                            if type(row.get(raw)) is int and row[raw] >= 0
                            else None
                            for name, raw in (
                                ("likes", "likeCount"),
                                ("replies", "replyCount"),
                                ("reposts", "retweetCount"),
                                ("quotes", "quoteCount"),
                            )
                        }
                    CollectionObservation.objects.create(
                        run_id=self.claim.run_id,
                        request=saved,
                        receipt_ordinal=index,
                        source_identifier=identity,
                        source_identifier_is_null=not bool(identity),
                        source_subject_kind="post_appearance",
                        observation_kind="x_request_appearance",
                        processing_outcome="received",
                        observed_at=observed,
                        observation_key=digest([str(saved.pk), index]),
                    )
            saved.save()
            scope = saved.scope_run
            scope.raw_count = len(rows) if rows is not None else 0
            scope.execution_state = "completed" if outcome == "received" else "failed"
            scope.coverage_state = "partial" if rows is not None else "unavailable"
            scope.outcome = "observed" if rows is not None else "unknown"
            scope.save(
                update_fields=[
                    "raw_count",
                    "execution_state",
                    "coverage_state",
                    "outcome",
                ]
            )
        self.last_request, self.last_receipt_at = saved, observed

    def transport(self, endpoint, key, body, **kwargs):
        request = self.start(endpoint, {})
        try:
            status, raw = self._transport(endpoint, key, body, **kwargs)
        except Exception:
            self.finish(
                request, {"outcome": "unknown", "status_code": None, "body": None}
            )
            raise
        self.finish(
            request, {"outcome": "received", "status_code": status, "body": raw}
        )
        return status, raw

    def tools(self, reply):
        parent = self.last_request
        for activity in reply.get("search_activity", []):
            query = activity["arguments"].get("query")
            bounds = {
                key: datetime.fromisoformat(activity["arguments"][arg]).replace(
                    tzinfo=UTC
                )
                for key, arg in (("start", "from_date"), ("end", "to_date"))
                if activity["arguments"].get(arg)
            }
            scope = self.scope(
                f"tool:{activity['sequence']}:{activity['name']}",
                query,
                tool=True,
                **bounds,
            )
            scope.parent_scope = parent.scope_run
            scope.coverage_state, scope.outcome = "unavailable", "tool_results_hidden"
            scope.save(update_fields=["parent_scope", "coverage_state", "outcome"])
            CollectionScopeRequestUse.objects.get_or_create(
                scope_run=scope,
                request=parent,
                defaults={"ordinal": 0, "observed_at": self.last_receipt_at},
            )

    def source_items(self, items):
        """Restore captured quote clocks/identities before qualification and ingestion."""
        compact = {}
        if self.ranked_lane and self.last_request and self.last_request.archive_id:
            compact = {row["id"]: row for row in self.captured_reply(self.last_request)["tweets"]}
        return [{**item, **compact.get(str(item.get("id") or ""), {})} for item in items]

    def ingest(self, items, *, freeze=True):
        from monitor.cycle import persist_x_post

        snapshot = self.run.__class__.objects.get(pk=self.run.pk).snapshot
        existing = validated_packet(snapshot)["sources"] if snapshot else {}
        projected = []
        for item in self.source_items(items):
            quote_id = item.get("quoted_status_id")
            if self.ranked_lane and quote_id and item.get("quoted_text") and item.get("quoted_created_at"):
                quote, _ = persist_x_post({
                    "id": quote_id, "text": item["quoted_text"], "created_at": item["quoted_created_at"],
                    "author_id": item.get("quoted_author_id") or "",
                    "author_handle": item.get("quoted_author_handle") or "",
                    "extended_entities": {"media": [{"media_url_https": url} for url in item.get("quoted_media_urls", [])]},
                })
                if quote and quote.pk not in existing and quote.text and quote.created_at and quote.created_at < self.run.facts_as_of:
                    quote.refresh_from_db(fields=["native_author_id"])
                    source = project_post(quote, receipt_at=self.last_receipt_at)
                    source["images"] = item.get("quoted_media_urls", [])
                    source["counters"].update({name: None for name in ("likes", "replies", "reposts", "quotes")})
                    projected.append(source)
                    existing[quote.pk] = source

            identity = str(item.get("id") or "")
            if identity in existing or not re.fullmatch(r"[0-9]{1,25}", identity):
                continue
            # Shared typed ingestion gets source facts, without unused profile blocks.
            essential = {
                key: item[key]
                for key in (
                    "id",
                    "text",
                    "created_at",
                    "lang",
                    "author_id",
                    "author_handle",
                    "author_display_name",
                    "like_count",
                    "reply_count",
                    "retweet_count",
                    "quote_count",
                    "quoted_text",
                    "quoted_status_id",
                    "quoted_author_handle",
                    "is_quote",
                    "is_retweet",
                    "is_reply",
                    "in_reply_to_id",
                    "in_reply_to_username",
                    "entities",
                    "extended_entities",
                )
                if key in item
            }
            for metric, field in (
                ("likes", "like_count"),
                ("replies", "reply_count"),
                ("reposts", "retweet_count"),
                ("quotes", "quote_count"),
            ):
                measured = self.metric_presence.get(identity, {}).get(metric)
                if measured is None:
                    essential.pop(field, None)
                else:
                    essential[field] = measured
            post, _ = persist_x_post(essential)
            if (
                post is None
                or not post.text
                or post.created_at is None
                or post.created_at > self.run.facts_as_of
            ):
                continue
            if self.ranked_lane:
                post.refresh_from_db(fields=["native_author_id"])
            source = project_post(post, receipt_at=self.last_receipt_at)
            if self.ranked_lane:
                source["images"] = [entry["media_url_https"] for entry in (item.get("extended_entities") or {}).get("media", []) if entry.get("media_url_https")]
                if item.get("quoted_created_at") and source["quoted_post_id"] not in existing:
                    source["stored_quote"] = ""
            source["counters"].update(
                self.metric_presence.get(
                    identity,
                    {name: None for name in ("likes", "replies", "reposts", "quotes")},
                )
            )
            projected.append(source)
            existing[identity] = source
            CollectionObservation.objects.get_or_create(
                run_id=self.claim.run_id,
                scope_run=self.last_request.scope_run,
                resource_key=identity,
                defaults={
                    "post": post,
                    "source_identifier": identity,
                    "source_subject_kind": "post",
                    "observation_kind": "chatter_source",
                    "observed_at": self.last_receipt_at,
                    "observation_key": digest(
                        [
                            str(self.claim.run_id),
                            self.last_request.scope_run_id,
                            identity,
                        ]
                    ),
                    "payload_sha256": digest(source),
                },
            )
        if projected and freeze:
            freeze_sources(self.run, projected, fence=self.run.fence)
        return existing

    def close(self, *, success):
        requests = CollectionRequest.objects.filter(attempt__run_id=self.claim.run_id)
        complete = not requests.exclude(transport_outcome="received").exists()
        return finish_run(
            self.claim,
            status="success" if success else "failed",
            typed=True,
            request_count=requests.count(),
            selected_count=0,
            success_count=0,
            physical_accounting_complete=complete,
        )
