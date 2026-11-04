"""Typed Chatter collection ownership and compact physical source receipts."""

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.collection_capture import begin_request, finish_request
from core.collection_jobs import register_job, set_job_state
from core.collection_state import checkpoint_scope, claim_job, fenced_run, finish_run
from core.models import (
    CollectionAttempt,
    CollectionObservation,
    CollectionRun,
    CollectionScopeRequestUse,
    DataSource,
    OriginalContentCall,
)
from monitor.original_content import digest
from scripts.harvest_cost.pricing import load_pricing, rates_to_dict
from x_monitor.provider_http import https_request
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
from x_monitor.x_client import XClient

from .chatter_accounting import admit, money
from .chatter_history import (
    freeze_sources,
    locked_run,
    project_post,
    save_query,
    validated_packet,
)
from .persistence import BudgetHeld


class SourceSession:
    def __init__(
        self, run, cfg, *, purpose, client=None, transport=None, policy_reader=None
    ):
        if not isinstance(purpose, TwitterApiCredentialPurpose):
            raise TypeError(
                "Chatter source calls require an explicit credential purpose"
            )
        self.run, self.cfg = run, cfg
        self._transport = transport or https_request
        self.policy_reader = policy_reader
        self.rates = load_pricing(repo_root=settings.BASE_DIR)
        self.client = client or XClient.from_env(purpose)
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
            "workflow_version": "chatter-v1",
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
                "interval_seconds": 900 if mode == "recurring" else None,
                "max_requests": cfg.chatter.source_request_limit,
                "max_bytes": 8_000_000,
                "max_seconds": 600,
                "max_items": 200,
            },
        )
        if CollectionRun.objects.filter(content_run=run).exists():
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
        self.last_receipt_at = None
        self.last_request = None
        self.metric_presence = {}

    def scope(self, name, query=None, *, tool=False, start=None, end=None):
        query_row = save_query(query) if query else None
        call = OriginalContentCall.objects.filter(
            run=self.run, stage="discovery"
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

    def start(self, path, params):
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
            locked_run(self.run.pk, self.run.fence)
            with fenced_run(self.claim):
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
                request = begin_request(
                    CollectionAttempt.objects.get(pk=self.claim.attempt_id),
                    scope,
                    endpoint_url=path
                    if model
                    else self.client.base_url
                    + path
                    + ("?" + urlencode(params) if params else ""),
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

    def ingest(self, items):
        from monitor.cycle import persist_x_post

        snapshot = self.run.__class__.objects.get(pk=self.run.pk).snapshot
        existing = validated_packet(snapshot)["sources"] if snapshot else {}
        projected = []
        for item in items:
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
            source = project_post(post, receipt_at=self.last_receipt_at)
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
        if projected:
            freeze_sources(self.run, projected, fence=self.run.fence)
        return existing

    def close(self, *, success):
        requests = (
            CollectionRun.objects.get(pk=self.claim.run_id)
            .attempts.get(pk=self.claim.attempt_id)
            .requests
        )
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
