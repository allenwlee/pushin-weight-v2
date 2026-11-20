"""One durable hourly official-X observation and its accepted gathering ranking.

The collection ledger owns the official receipt; OriginalContentCall owns the
ranker's bill. A completed ranking is a gathering checkpoint, never a story vote.
"""

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from core.collection_capture import begin_request, finish_request
from core.collection_jobs import register_job, set_job_state
from core.collection_state import checkpoint_scope, claim_job, finish_run
from core.models import (
    CollectionAttempt,
    CollectionRequest,
    CollectionRun,
    DataSource,
    OriginalContentCall,
    OriginalContentRun,
)
from core.official_company_credentials import (
    CREDENTIAL_KEY,
    OwnerTokenStore,
    credential_diagnostics,
)
from monitor.original_content import advisory_lock, digest, shared_storage

from .chatter_accounting import admit, call_once
from .chatter_history import WORKFLOW, locked_run, validated_packet
from .chatter_windows import WindowRanking
from .config import EditorialConfig, load_editorial_config
from .providers import json_call, request_fingerprint, request_payload
from .voices import load_bound_voices

TRENDS_SCOPE = "chatter:personalized-trends:v1"
ROLLING_LANE = "personalized-trends-v2"
CAPTURE_SCOPE = "chatter:personalized-trends:capture:v2"
DECISION_SCOPE = "chatter:personalized-trends:decision:v2"
RANKED_SCOPES = (TRENDS_SCOPE, DECISION_SCOPE)
ROLLING_SCOPES = (CAPTURE_SCOPE, DECISION_SCOPE)
WINDOW_RANK_STAGE = "trends-ranking-v2"
RANK_STAGE = "trends-ranking-v1"
OFFICIAL_ENDPOINT = "https://api.x.com/2/users/personalized_trends"
OFFICIAL_PARAMS = {"personalized_trend.fields": "category,post_count,trend_name,trending_since"}
MAX_RESPONSE_BYTES = 2_000_000


class ClosedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value


class Headline(ClosedDocument):
    headline_id: int = Field(ge=1)
    trend_name: str = Field(min_length=1, max_length=6000)
    post_count: Annotated[int, Field(ge=0)] | Annotated[str, Field(min_length=1, max_length=80)] | None = None
    category: str | None = None
    trending_since: str | None = None


class RankedStory(ClosedDocument):
    title: str = Field(min_length=1, max_length=6000)
    headline_ids: list[int] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=6000)


class Ranking(ClosedDocument):
    ranked_stories: list[RankedStory]


class RankingUsage(ClosedDocument):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: str | None = None
    provider_reported_cost_usd: str | None = None

    @field_validator("estimated_cost", "provider_reported_cost_usd")
    @classmethod
    def finite_cost(cls, value):
        from .chatter_accounting import money

        if value is not None:
            money(value)
        return value


class RankingDiagnostics(ClosedDocument):
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_profile: None
    timeout_seconds: int = Field(ge=1, le=300)
    http_status: int = Field(ge=200, le=299)
    usage: RankingUsage
    model_matches_config: Literal[True]
    finish_reason: Literal["stop"]
    provider_request_id: str | None = Field(default=None, max_length=200)
    service_tier: Literal["priority", "standard", "default", "flex"] | None = None
    elapsed_seconds: float = Field(ge=0)


class RankingReply(ClosedDocument):
    schema_version: Literal[1]
    data: Ranking
    usage: RankingUsage
    model: Literal["openai/gpt-6-sol"]
    diagnostics: RankingDiagnostics


class WindowReply(RankingReply):
    schema_version: Literal[2]
    data: WindowRanking


def validate_rank_reply(value, stage=RANK_STAGE):
    contract = WindowReply if stage == WINDOW_RANK_STAGE else RankingReply
    reply = contract.model_validate(value)
    if reply.usage != reply.diagnostics.usage:
        raise ValueError("ranking usage differs from receipt")
    # Do not add absent optional keys to the provider's compact saved reply.
    return reply.model_dump(mode="json", exclude_unset=True)


class Observation(ClosedDocument):
    request_id: UUID
    archive_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: AwareDatetime
    http_status: int = Field(ge=100, le=599)
    credential_revision: int | None = Field(default=None, ge=1)
    credential_refresh_requests: int = Field(default=0, ge=0)
    rate_remaining: str | None = Field(default=None, max_length=80)
    rate_reset: str | None = Field(default=None, max_length=80)
    retry_after: str | None = Field(default=None, max_length=80)
    headline_count: int | None = Field(default=None, ge=0)


class Checkpoint(ClosedDocument):
    schema_version: Literal[1] = 1
    lane: Literal["personalized-trends-v1"] = "personalized-trends-v1"
    slot: AwareDatetime
    source_cycle_id: str = Field(min_length=1, max_length=128)
    cycle_started_at: AwareDatetime
    cutoff: AwareDatetime
    credential_purpose: Literal["scheduled", "on-demand"]
    phase: Literal["queued", "observing", "observed", "ranking", "ranked", "empty", "held"] = "queued"
    observation: Observation | None = None
    rank_call_id: int | None = Field(default=None, ge=1)
    ranking_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    error_code: str = Field(default="", max_length=64, pattern=r"^[a-zA-Z0-9_:-]*$")
    deferred_until: AwareDatetime | None = None
    last_enqueue_at: AwareDatetime | None = None


class WindowPointer(ClosedDocument):
    run_id: int = Field(ge=1)
    request_id: UUID
    archive_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SelectedDevelopment(ClosedDocument):
    consideration_id: int = Field(ge=1)
    development_id: UUID
    episode_id: str
    title: str
    selected_at: AwareDatetime
    wordings: list[str]


class WindowCheckpoint(Checkpoint):
    schema_version: Literal[2] = 2
    lane: Literal["personalized-trends-v2"] = ROLLING_LANE
    terminal_at: AwareDatetime | None = None
    selected_developments: list[SelectedDevelopment] = Field(default_factory=list, max_length=200)
    freeze_at: AwareDatetime | None = None
    manifest: list[WindowPointer] = Field(default_factory=list, max_length=4)
    missing_slots: list[AwareDatetime] = Field(default_factory=list, max_length=4)
    previous_id: int | None = Field(default=None, ge=1)
    previous_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    committed_at: AwareDatetime | None = None


def _document(model, value):
    # JSON mode accepts ISO clocks while strict mode rejects coercions and extra keys.
    if "schema_version" in model.model_fields and (not isinstance(value, dict) or "schema_version" not in value):
        raise ValueError("versioned Chatter document required")
    return model.model_validate_json(json.dumps(value, allow_nan=False))


def checkpoint(run):
    state = _document(WindowCheckpoint if run.scope_key in ROLLING_SCOPES else Checkpoint, run.outcome["trends"])
    if (run.scope_key not in (*RANKED_SCOPES, CAPTURE_SCOPE) or run.workflow_key != WORKFLOW
            or state.slot != run.interval or state.cutoff != run.facts_as_of
            or state.cycle_started_at != run.cycle_started_at
            or state.source_cycle_id != run.source_cycle_id):
        raise ValueError("trends checkpoint ownership changed")
    if run.scope_key in ROLLING_SCOPES:
        if run.interval.second or run.interval.microsecond or run.interval.minute % (30 if run.scope_key == DECISION_SCOPE else 15):
            raise ValueError("unaligned_rolling_slot")
        if run.scope_key == DECISION_SCOPE and (
            state.cutoff != state.slot or state.observation is not None
            or state.freeze_at and not state.slot <= state.freeze_at <= state.slot + timedelta(minutes=5)
            or state.committed_at and (not state.freeze_at or not state.ranking_sha256)
        ):
            raise ValueError("invalid_decision_checkpoint")
        if run.scope_key == CAPTURE_SCOPE and (state.freeze_at or state.rank_call_id or state.manifest):
            raise ValueError("invalid_capture_checkpoint")
    validated_packet(run.snapshot)
    return state


def ranking_prefix():
    return (Path(settings.BASE_DIR) / "config/editorial_chatter_chain/trends-ranking.txt").read_text()


def workflow_version(lane="personalized-trends-v1"):
    from .chatter_discovery import prompts

    if lane == ROLLING_LANE:
        from .chatter_windows import PROMPT

        return digest([lane, OFFICIAL_ENDPOINT, OFFICIAL_PARAMS, PROMPT.read_text(), prompts()])
    return digest(["personalized-trends-v1", OFFICIAL_ENDPOINT, OFFICIAL_PARAMS, ranking_prefix(), prompts()])


def reserve_due_slot(source_cycle_id, started, *, cfg, purpose, scope=TRENDS_SCOPE):
    """Commit the interval owner before a broker notification can be attempted."""
    rolling = scope in ROLLING_SCOPES
    lane = ROLLING_LANE if rolling else "personalized-trends-v1"
    if scope not in (*RANKED_SCOPES, CAPTURE_SCOPE) or not cfg.chatter.enabled or cfg.chatter.discovery_lane != lane:
        raise ValueError("personalized trends lane is not enabled")
    now = timezone.now()
    if started.tzinfo is None or started > now + timedelta(minutes=1) or started < now - timedelta(days=8):
        raise ValueError("invalid Chatter cutoff")
    if not rolling and cfg.chatter.trial and purpose != "on-demand":
        raise ValueError("explicit validation requires the on-demand purpose")
    step = 15 if scope == CAPTURE_SCOPE else 30 if scope == DECISION_SCOPE else 60
    tick = started.astimezone(UTC)
    slot = tick.replace(minute=tick.minute // step * step, second=0, microsecond=0)
    cutoff = slot if scope == DECISION_SCOPE else started
    state = (WindowCheckpoint if rolling else Checkpoint)(slot=slot, source_cycle_id=str(source_cycle_id), cycle_started_at=started,
                       cutoff=cutoff, credential_purpose=purpose)
    voices = load_bound_voices(cfg)
    with transaction.atomic():
        advisory_lock(scope)
        existing = OriginalContentRun.objects.filter(scope_key=scope, interval=slot).first()
        if existing:
            validate_slot_authority(existing, cfg=cfg, purpose=purpose)
            return existing, False
        latest = OriginalContentRun.objects.filter(scope_key=scope).order_by("-interval").first()
        if latest and scope != DECISION_SCOPE:
            previous = checkpoint(latest)
            if previous.deferred_until and previous.deferred_until > now:
                return latest, False
            if previous.error_code == "official_authentication_failed" and previous.observation:
                credential = credential_diagnostics()
                if (credential["credential_status"] != "ready"
                        or credential["credential_revision"] == previous.observation.credential_revision):
                    return latest, False
        run = OriginalContentRun.objects.create(
            scope_key=scope, interval=slot, source_cycle_id=str(source_cycle_id),
            workflow_key=WORKFLOW, workflow_version=workflow_version(lane), facts_as_of=cutoff,
            cycle_started_at=started, packet_schema_version=1,
            snapshot={"schema_version": 1, "sources": {}},
            config_snapshot={"schema_version": 1, "editorial": cfg.model_dump(mode="json"),
                             "voices": {key: voice.model_dump(mode="json") for key, voice in voices.items()}},
            execution_state="preparing", discovery_state="pending",
            outcome={"phase": "queued", "trends": state.model_dump(mode="json")},
        )
    return run, True


def validate_slot_authority(run, *, cfg, purpose):
    """A reused slot retains its credential purpose and complete trial grant."""
    state = checkpoint(run)
    saved = EditorialConfig.model_validate(run.config_snapshot["editorial"])
    if state.credential_purpose != purpose or saved.chatter.trial != cfg.chatter.trial:
        raise ValueError("saved Chatter slot authority differs from requested purpose or trial")
    return state


def envelope_for(run):
    state = checkpoint(run)
    return {"schema_version": 1, "lane": state.lane, "run_id": run.pk,
            "source_cycle_id": state.source_cycle_id, "cycle_started_at": state.cycle_started_at.isoformat(),
            "cutoff": state.cutoff.isoformat(), "dry_run": False, "credential_purpose": state.credential_purpose}


def _save(run, state, **changes):
    updated = _document(type(state), {**state.model_dump(mode="json"), **changes})
    with transaction.atomic():
        current = locked_run(run.pk, run.fence)
        current.outcome = {**current.outcome, "phase": updated.phase, "trends": updated.model_dump(mode="json")}
        current.save(update_fields=["outcome", "updated_at"])
        run.outcome = current.outcome
    return updated


def _headlines(document):
    if not isinstance(document, dict) or not isinstance(document.get("data"), list) or document.get("errors"):
        raise ValueError("invalid_official_observation")
    rows = []
    for index, raw in enumerate(document["data"], 1):
        if not isinstance(raw, dict):
            raise TypeError("invalid_official_headline")
        rows.append(Headline.model_validate({"headline_id": index, **{
            key: raw.get(key) for key in ("trend_name", "post_count", "category", "trending_since")
        }}).model_dump(mode="json"))
    return rows


def validate_ranking(value, count):
    ranking = Ranking.model_validate(value)
    members = [identity for row in ranking.ranked_stories for identity in row.headline_ids]
    if Counter(members) != Counter(range(1, count + 1)):
        raise ValueError("ranking_headline_membership_mismatch")
    return ranking.model_dump(mode="json")


def ranking_request(headlines):
    rows = [Headline.model_validate(row) for row in headlines]
    if [row.headline_id for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("headline identity changed")
    return {"packet_version": "chatter-trends-ranking-v1", "user": ranking_prefix() + "HEADLINES:\n" +
            json.dumps([{"id": row.headline_id, "headline": row.trend_name} for row in rows], ensure_ascii=False, indent=2)}


def _saved_observation(run, state):
    receipt = state.observation
    if receipt is None:
        raise ValueError("official observation missing")
    request = CollectionRequest.objects.select_related("archive", "attempt__run").get(pk=receipt.request_id)
    body = bytes(request.archive.body) if request.archive is not None else None
    if (request.attempt.run.content_run_id != run.pk or request.endpoint_url != OFFICIAL_ENDPOINT
            or request.http_method != "GET" or request.request_config != state.lane
            or request.transport_outcome != "received" or request.http_status != receipt.http_status
            or request.received_at != receipt.observed_at or request.archive is None
            or request.archive.content_sha256 != receipt.archive_sha256
            or hashlib.sha256(body).hexdigest() != receipt.archive_sha256):
        raise ValueError("official receipt ownership changed")
    return request, json.loads(body) if receipt.http_status == 200 else None


def _official_job(run, state):
    source, _ = DataSource.objects.get_or_create(pk="x", defaults={"name": "X", "source_type": "social"})
    recurring = state.credential_purpose == "scheduled"
    identity = [state.lane, CREDENTIAL_KEY, state.credential_purpose,
                run.config_snapshot["editorial"]["chatter"], OFFICIAL_ENDPOINT, OFFICIAL_PARAMS,
                None if recurring else run.pk]
    return register_job(
        job_key="chatter-personalized-trends:" + digest(identity)[:40], source=source, purpose="content",
        operation="chatter_search", mode="recurring" if recurring else "manual", definition={"version": 2, "options": {
            "credential_purpose": state.credential_purpose, "workflow_version": state.lane,
            "pricing_sha256": digest(["official-x", "unpriced"]),
        }}, settings={"owner_kind": "source", "schedule_kind": "interval" if recurring else "manual",
                      "schedule_driver": "external_render_cron" if recurring else "manual",
                      "interval_seconds": (900 if state.lane == ROLLING_LANE else 3600) if recurring else None,
                      "max_requests": 1, "max_bytes": MAX_RESPONSE_BYTES, "max_seconds": 120, "max_items": 10000},
    )


def _rate_reset(headers, now):
    candidates = []
    for key in ("x-rate-limit-reset", "retry-after"):
        value = headers.get(key)
        if isinstance(value, str) and re.fullmatch(r"[0-9]{1,12}", value):
            try:
                candidates.append(datetime.fromtimestamp(int(value), UTC) if key == "x-rate-limit-reset"
                                  else now + timedelta(seconds=int(value)))
            except (ValueError, OverflowError, OSError):
                pass
        elif key == "retry-after" and value:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is not None:
                    candidates.append(date)
            except (ValueError, TypeError, OverflowError):
                pass
    return max([now + timedelta(hours=1), *candidates])


def _observe(run, state, *, token_store, official_get):
    # No request exists until local credential checks/rotation have succeeded.
    store = token_store or OwnerTokenStore.from_env()
    token = store.access_token()
    with transaction.atomic():
        locked_run(run.pk, run.fence)
        if CollectionRun.objects.filter(content_run=run, job__job_key__startswith="chatter-personalized-trends:").exists():
            raise ValueError("official_send_requires_reconciliation")
        job = _official_job(run, state)
        if job.state == "paused":
            set_job_state(job.pk, "ready")
        claim = claim_job(job.pk, invocation_id=f"chatter-trends:{run.pk}", manual_authorized=True, typed=True)
        CollectionRun.objects.filter(pk=claim.run_id).update(content_run=run)
        attempt = CollectionAttempt.objects.get(pk=claim.attempt_id)
        attempt.credential_purpose = state.credential_purpose
        attempt.save(update_fields=["credential_purpose"])
        scope = checkpoint_scope(claim, scope_key=state.lane, scope_kind="chatter_trends",
                                 ownership={"content_run_id": run.pk}, typed=True, requested_end_at=run.facts_as_of)
        request = begin_request(attempt, scope, endpoint_url=OFFICIAL_ENDPOINT, method="GET",
                                request_config=state.lane)
        # Hold a conservative source-call reservation; official-X has no
        # TwitterAPI price estimate or reported charge in this receipt.
        run_config = EditorialConfig.model_validate(run.config_snapshot["editorial"])
        request.reserved_usd = admit(run_config, run_config.chatter.source_request_reservation_usd)
        request.save(update_fields=["reserved_usd"])
        state = _save(run, state, phase="observing")
        store.check_access_expiry()
    try:
        response = (official_get or requests.get)(OFFICIAL_ENDPOINT, headers={"Authorization": "Bearer " + token},
            params=OFFICIAL_PARAMS, timeout=20, allow_redirects=False, stream=True)
        try:
            if hasattr(response, "iter_content"):
                chunks, length = [], 0
                for chunk in response.iter_content(65536):
                    length += len(chunk)
                    if length > MAX_RESPONSE_BYTES:
                        raise ValueError("official_response_exceeds_cap")
                    chunks.append(chunk)
                body = b"".join(chunks)
            else:
                body = response.content
            if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("invalid_official_response_body")
            headers = {key.lower(): str(value)[:80] for key, value in response.headers.items()
                       if key.lower() in {"x-rate-limit-remaining", "x-rate-limit-reset", "retry-after"}}
            status = response.status_code
        finally:
            if hasattr(response, "close"):
                response.close()
        # Token-bearing provider text must never be archived.
        for secret in store.redactions:
            if secret:
                body = body.replace(secret.encode(), b"[REDACTED]")
    except Exception:
        finish_request(request, outcome="unknown", error_code="official_transport_unknown")
        finish_run(claim, status="failed", typed=True, request_count=1, selected_count=0,
                   success_count=0, physical_accounting_complete=False)
        raise
    at = timezone.now()
    with transaction.atomic():
        locked_run(run.pk, run.fence)
        saved = finish_request(request, outcome="received", body=body, http_status=status, now=at)
        observation = Observation(request_id=saved.pk, archive_sha256=saved.archive.content_sha256,
            observed_at=at, http_status=status, credential_revision=store.revision,
            credential_refresh_requests=getattr(store, "refresh_attempts", 0),
            rate_remaining=headers.get("x-rate-limit-remaining"), rate_reset=headers.get("x-rate-limit-reset"),
            retry_after=headers.get("retry-after"))
        state = _save(run, state, phase="observed", observation=observation.model_dump(mode="json"),
                      deferred_until=_rate_reset(headers, at).isoformat() if status == 429 else None)
        finish_run(claim, status="success" if status == 200 else "failed", typed=True, request_count=1,
                   selected_count=0, success_count=0, physical_accounting_complete=True)
    return state


def read_ranked_batch(run_id):
    """Hash-checked U47 input: all groups plus ten leads with original members."""
    run = OriginalContentRun.objects.get(pk=run_id)
    state = checkpoint(run)
    if run.scope_key == DECISION_SCOPE:
        from .chatter_window_runs import read_window_batch

        return read_window_batch(run, state)
    _, document = _saved_observation(run, state)
    headlines = _headlines(document)
    if state.observation.http_status != 200 or state.observation.headline_count != len(headlines):
        raise ValueError("official batch changed")
    cfg = EditorialConfig.model_validate(run.config_snapshot["editorial"])
    body = request_payload(cfg.chatter.ranking, ranking_request(headlines))
    _, request_hash = request_fingerprint(body)
    call = OriginalContentCall.objects.get(pk=state.rank_call_id, run=run, stage=RANK_STAGE, state="completed")
    if (call.request_packet != body or call.request_hash != request_hash
            or call.response_hash != digest(call.response_payload)):
        raise ValueError("saved ranking identity changed")
    reply = validate_rank_reply(call.response_payload)
    if reply["diagnostics"]["request_sha256"] != call.request_hash:
        raise ValueError("ranking request receipt changed")
    ranking = validate_ranking(reply["data"], len(headlines))
    if digest(ranking) != state.ranking_sha256:
        raise ValueError("saved ranking checkpoint changed")
    members = {row["headline_id"]: row for row in headlines}
    return {"schema_version": 1, "run_id": run.pk, "request_id": str(state.observation.request_id),
            "batch_sha256": state.observation.archive_sha256, "rank_call_id": call.pk,
            "cutoff": state.cutoff.isoformat(), "observed_at": state.observation.observed_at.isoformat(),
            "headlines": headlines, **ranking, "leads": [
                {"rank": index, **row, "headlines": [members[identity] for identity in row["headline_ids"]]}
                for index, row in enumerate(ranking["ranked_stories"][:10], 1)]}


def discover_trends(run_id, *, cfg=None, transport=None, official_get=None, token_store=None):
    """Reconcile saved stages; any uncertain physical send is held, never retried."""
    current_cfg = cfg or load_editorial_config()
    if not current_cfg.chatter.enabled:
        return {"status": "disabled"}
    if not shared_storage():
        raise ValueError("Chatter workflow requires shared content storage")
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=run_id)
        try:
            state = checkpoint(run)
            cfg = EditorialConfig.model_validate(run.config_snapshot["editorial"])
        except (ValueError, KeyError):
            return {"status": "held", "run_id": run.pk, "error_code": "invalid_trends_checkpoint"}
        if run.workflow_version != workflow_version(state.lane):
            return {"status": "held", "run_id": run.pk, "error_code": "trends_prompt_changed"}
        if run.scope_key == CAPTURE_SCOPE and run.execution_state == "completed":
            return {"status": "captured", "run_id":run.pk}
        if state.phase == "ranked":
            try:
                read_ranked_batch(run.pk)
            except (ValueError, KeyError, OriginalContentCall.DoesNotExist, CollectionRequest.DoesNotExist):
                return {"status": "held", "run_id": run.pk, "error_code": "invalid_ranked_checkpoint"}
            return {"status": "ranked", "run_id": run.pk}
        if state.phase == "empty":
            _, document = _saved_observation(run, state)
            if _headlines(document) or state.observation.headline_count != 0:
                return {"status": "held", "run_id": run.pk, "error_code": "invalid_empty_checkpoint"}
            return {"status": "empty", "run_id": run.pk}
        if run.claim_owner and run.lease_until and run.lease_until > timezone.now():
            return {"status": "already_dispatched", "run_id": run.pk}
        run.fence += 1
        run.claim_owner = str(uuid4())
        run.lease_until = timezone.now() + timedelta(minutes=10)
        run.execution_state = "running"
        run.discovery_state = "pending"
        run.save(update_fields=["fence", "claim_owner", "lease_until", "execution_state", "discovery_state"])
    try:
        if state.observation is None:
            if state.phase == "held":
                return {"status": "held", "run_id": run.pk, "error_code": state.error_code}
            if timezone.now() >= state.slot + timedelta(minutes=15 if state.lane == ROLLING_LANE else 60):
                raise ValueError("official_observation_window_elapsed")
            state = _observe(run, state, token_store=token_store, official_get=official_get)
        _, document = _saved_observation(run, state)
        status = state.observation.http_status
        if status != 200:
            raise ValueError("official_authentication_failed" if status in (401, 403) else
                             "official_rate_limited" if status == 429 else "official_http_failure")
        headlines = _headlines(document)
        state = _save(run, state, observation={**state.observation.model_dump(mode="json"), "headline_count": len(headlines)})
        if run.scope_key == CAPTURE_SCOPE:
            OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(execution_state="completed", discovery_state="complete")
            return {"status":"captured", "run_id":run.pk}
        if not headlines:
            _save(run, state, phase="empty", error_code="")
            return {"status": "empty", "run_id": run.pk}
        request = ranking_request(headlines)
        expected = request_payload(cfg.chatter.ranking, request)
        _, request_hash = request_fingerprint(expected)
        prior = OriginalContentCall.objects.filter(run=run, stage=RANK_STAGE).first()
        if prior:
            if (prior.state != "completed" or prior.request_packet != expected
                    or prior.request_hash != request_hash
                    or prior.response_hash != digest(prior.response_payload)):
                raise ValueError("ranking_send_requires_reconciliation")
            reply = validate_rank_reply(prior.response_payload)
        else:
            state = _save(run, state, phase="ranking")
            reply = json_call(run, RANK_STAGE, cfg.chatter.ranking, request, cfg,
                              transport=transport, reservation=call_once)
        ranking = validate_ranking(reply["data"], len(headlines))
        call = OriginalContentCall.objects.get(run=run, stage=RANK_STAGE, state="completed")
        _save(run, state, phase="ranked", rank_call_id=call.pk, ranking_sha256=digest(ranking), error_code="")
        return {"status": "ranked", "run_id": run.pk}
    except Exception as exc:  # noqa: BLE001 - persist a safe hold without provider bodies
        code = getattr(exc, "code", None) or (str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        if not isinstance(code, str) or not re.fullmatch(r"[a-zA-Z0-9_:-]{1,64}", code):
            code = "trends_stage_failure"
        state = checkpoint(OriginalContentRun.objects.get(pk=run.pk))
        _save(run, state, phase="held", error_code=code, **({"terminal_at":timezone.now().isoformat()} if run.scope_key == CAPTURE_SCOPE else {}))
        OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(discovery_state="failed")
        return {"status": "held", "run_id": run.pk, "error_code": code}
    finally:
        OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(claim_owner="")
