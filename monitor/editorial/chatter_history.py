"""Frozen evidence, query versions and queryable Chatter consideration history."""

import json
from datetime import timedelta
from typing import Annotated, Literal

from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from core.models import (
    EditorialStory,
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
    OriginalContentSource,
    SearchQuery,
)
from monitor.original_content import WORKFLOWS, citation_values, digest, safe_source_url

from .contracts import interval_start
from .evidence import post_evidence, safe_source_image

WORKFLOW = "chatter-discovery"
SCOPE = "chatter:v1"


class ClosedSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Counters(ClosedSnapshot):
    observed_at: AwareDatetime | None = None
    likes: int | None = Field(default=None, ge=0)
    replies: int | None = Field(default=None, ge=0)
    reposts: int | None = Field(default=None, ge=0)
    quotes: int | None = Field(default=None, ge=0)


class SourceSnapshot(ClosedSnapshot):
    id: str = Field(min_length=1, max_length=128)
    original_text: str = Field(min_length=1, max_length=6000)
    created_at: AwareDatetime | None
    observed_at: AwareDatetime
    verification_basis: Literal["saved_record", "provider_receipt"] = "saved_record"
    source_language: str = Field(default="", max_length=35)
    url: str = Field(min_length=1, max_length=4096)
    author_handle: str = Field(default="", max_length=128)
    author_id: str | None = Field(default=None, max_length=128)
    stored_quote: str = Field(default="", max_length=4000)
    local_parent: str = Field(default="", max_length=4000)
    quoted_author_handle: str = Field(default="", max_length=128)
    parent_author_handle: str = Field(default="", max_length=128)
    quoted_post_id: str = Field(default="", max_length=128)
    parent_post_id: str = Field(default="", max_length=128)
    is_quote: bool = False
    is_retweet: bool = False
    is_reply: bool = False
    excerpt_truncated: bool = False
    images: list[str] = Field(default_factory=list, max_length=8)
    brand_keys: list[str] = Field(default_factory=list, max_length=20)
    counters: Counters = Field(default_factory=Counters)

    @model_validator(mode="after")
    def validate_evidence(self):
        safe_source_url(self.url)
        if any(not safe_source_image(url) for url in self.images):
            raise ValueError("unapproved source image")
        if len(set(self.brand_keys)) != len(self.brand_keys):
            raise ValueError("duplicate source brand")
        return self


class XSource(SourceSnapshot):
    kind: Literal["x_post"]
    id: str = Field(pattern=r"^[0-9]{1,25}$")

    @model_validator(mode="after")
    def validate_identity(self):
        if self.url != f"https://x.com/i/status/{self.id}":
            raise ValueError("source URL does not match Post identity")
        return self


class DocumentSource(SourceSnapshot):
    kind: Literal["dossier_source"]
    dossier_source_id: int = Field(gt=0)
    images: list[str] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def validate_identity(self):
        if self.id != f"dossier-source:{self.dossier_source_id}":
            raise ValueError("source ID does not match dossier source")
        return self


class FrozenPacket(ClosedSnapshot):
    schema_version: Literal[1]
    sources: dict[str, Annotated[XSource | DocumentSource, Field(discriminator="kind")]] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_keys(self):
        if any(key != source.id for key, source in self.sources.items()):
            raise ValueError("source snapshot key mismatch")
        return self


def validated_packet(value):
    """JSON validation keeps strict scalar types while accepting ISO timestamps."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 240000:
            raise ValueError("source packet byte limit")
        return FrozenPacket.model_validate_json(encoded).model_dump(mode="json")
    except (ValueError, TypeError):
        # Validation errors may quote untrusted source/provider input.
        raise ValueError("invalid frozen source packet") from None


def project_post(post, *, receipt_at=None):
    evidence = post_evidence(post)
    fields = set(SourceSnapshot.model_fields) - {"observed_at", "counters"}
    source = {key: value for key, value in evidence.items() if key in fields}
    observed = receipt_at or timezone.now()
    measured = receipt_at or post.metrics_refreshed_at
    source.update(
        kind="x_post", observed_at=observed.isoformat(),
        verification_basis="provider_receipt" if receipt_at else "saved_record",
        counters={
            "observed_at": measured.isoformat() if measured else None,
            "likes": post.like_count, "replies": post.reply_count,
            "reposts": post.retweet_count, "quotes": post.quote_count,
        },
    )
    return validated_packet({"schema_version": 1, "sources": {post.pk: source}})["sources"][post.pk]


def locked_run(run_id, fence):
    run = OriginalContentRun.objects.select_for_update().get(pk=run_id)
    if (
        run.workflow_key != WORKFLOW or run.fence != fence
        or run.execution_state != "running" or run.lease_until is None
        or run.lease_until <= timezone.now()
    ):
        raise ValueError("stale Chatter source writer")
    return run


@transaction.atomic
def freeze_sources(run, sources, *, fence):
    if not isinstance(sources, list) or len(sources) > 200 or any(not isinstance(s, dict) for s in sources):
        raise ValueError("invalid frozen source list")
    current = locked_run(run.pk, fence)
    prior = validated_packet(current.snapshot or {"schema_version": 1, "sources": {}})
    incoming = {}
    for source in sources:
        key = source.get("id")
        if not isinstance(key, str) or (key in incoming and incoming[key] != source):
            raise ValueError("conflicting source identity")
        incoming[key] = source
    incoming = validated_packet({"schema_version": 1, "sources": incoming})["sources"]
    for key, source in incoming.items():
        if key in prior["sources"] and prior["sources"][key] != source:
            raise ValueError("frozen source is immutable")
    packet = validated_packet({"schema_version": 1, "sources": {**prior["sources"], **incoming}})
    current.snapshot = packet
    current.save(update_fields=["snapshot"])
    return packet


@transaction.atomic
def attach_sources(content, source_ids, *, fence, usage="consideration"):
    run = locked_run(content.run_id, fence)
    row = OriginalContent.objects.select_for_update().get(pk=content.pk)
    if row.run_id != run.pk:
        raise ValueError("stale consideration owner")
    if row.consideration_state is None or row.status != "prepared":
        raise ValueError("saved consideration sources are immutable")
    if usage not in {"consideration", "background"}:
        raise ValueError("invalid consideration usage")
    if (
        not isinstance(source_ids, list) or len(source_ids) > 200
        or any(type(key) is not str or not key or len(key) > 128 for key in source_ids)
    ):
        raise ValueError("invalid source list")
    packet = validated_packet(run.snapshot)
    ids = list(dict.fromkeys(source_ids))
    if not set(ids) <= packet["sources"].keys():
        raise ValueError("source is outside frozen packet")
    values = citation_values([packet["sources"][key] for key in ids])
    existing = list(row.consideration_sources.order_by("position"))
    by_source = {(source.post_id, source.dossier_source_id): source for source in existing}
    for value in values:
        saved = by_source.get((value["post_id"], value["dossier_source_id"]))
        if saved:
            if any(getattr(saved, key) != val for key, val in value.items() if key != "position"):
                raise ValueError("saved consideration source is immutable")
            if saved.usage == "background" and usage == "consideration":
                saved.usage = usage
                saved.save(update_fields=["usage"])
            continue
        value["position"] = len(existing)
        saved = OriginalContentSource.objects.create(content=row, usage=usage, **value)
        existing.append(saved)
        by_source[(saved.post_id, saved.dossier_source_id)] = saved
    return existing


def read_sources(content, *, usage=None):
    snapshot = OriginalContentRun.objects.values_list("snapshot", flat=True).get(pk=content.run_id)
    packet = validated_packet(snapshot)
    rows = content.consideration_sources.order_by("position")
    if usage is not None:
        if usage not in {"consideration", "background"}:
            raise ValueError("invalid consideration usage")
        rows = rows.filter(usage=usage)
    result = []
    for row in rows:
        key = row.post_id if row.post_id else f"dossier-source:{row.dossier_source_id}"
        source = packet["sources"].get(key)
        if source is None or digest(source) != row.source_hash:
            raise ValueError("consideration source snapshot mismatch")
        result.append(source)
    return result


@transaction.atomic
def save_query(text, *, development=None):
    if type(text) is not str or not text.strip() or len(text.encode()) > 4096:
        raise ValueError("invalid saved query")
    previous = None
    if development is not None:
        story = EditorialStory.objects.select_for_update().get(pk=development.pk)
        previous = story.search_queries.order_by("-pk").first()
        if previous and previous.query_text == text:
            return previous
    identity = "chatter:" + digest([str(development.pk) if development else None, previous.pk if previous else None, text])
    query, _ = SearchQuery.objects.get_or_create(
        query_id=identity,
        defaults={"query_text": text, "development": development, "previous_version": previous},
    )
    if query.query_text != text:
        raise ValueError("immutable query identity conflict")
    return query


def appearance_history(development, cutoff, *, periods=8):
    if type(periods) is not int or not 1 <= periods <= 96:
        raise ValueError("history period limit exceeded")
    slots = [interval_start(cutoff) - timedelta(minutes=15 * index) for index in range(periods)]
    runs = {run.interval: run for run in OriginalContentRun.objects.filter(
        workflow_key=WORKFLOW, scope_key=SCOPE, interval__in=slots, facts_as_of__lte=cutoff,
    ).annotate(discovery_observed=Exists(OriginalContentCall.objects.filter(
        run_id=OuterRef("pk"), workflow_key=WORKFLOW, stage="discovery",
        state="completed", completed_at__lte=cutoff,
    )))}
    appearances = {row.run_id: row for row in OriginalContent.objects.filter(
        development=development, run_id__in=[run.pk for run in runs.values()],
        attempted_at__lte=cutoff, discovery_call__completed_at__lte=cutoff,
        appearance_kind="semantic_shortlist", discovery_call__state="completed",
        discovery_call__run_id=F("run_id"), discovery_call__workflow_key=WORKFLOW,
    )}
    evidence, lower_bound, consecutive, known = [], 0, True, True
    for slot in slots:
        run = runs.get(slot)
        state = "unknown"
        candidate = None
        if run and run.discovery_state == "complete" and run.discovery_observed:
            candidate = appearances.get(run.pk)
            state = "fresh" if candidate else "not_rediscovered"
        if consecutive:
            if state == "fresh":
                lower_bound += 1
            else:
                consecutive = False
                known = state != "unknown"
        evidence.append({"interval": slot.isoformat(), "state": state,
                         "shortlist_position": candidate.shortlist_position if candidate else None})
    return {"consecutive_lower_bound": lower_bound, "continuity_known": known,
            "fresh_periods": sum(row["state"] == "fresh" for row in evidence),
            "unknown_periods": sum(row["state"] == "unknown" for row in evidence),
            "periods": evidence}


def competition_board(cutoff, *, limit=200):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("board limit exceeded")
    return list(history_query().filter(
        run__workflow_key=WORKFLOW, run__scope_key=SCOPE, run__discovery_state="complete",
        run__facts_as_of__lte=cutoff, run__facts_as_of__gt=cutoff - timedelta(hours=2),
        attempted_at__lte=cutoff,
        development__isnull=False, consideration_state__isnull=False,
        appearance_kind__in=["semantic_shortlist", "keyword_only", "release"],
    ).annotate(recent_rank=Window(
        expression=RowNumber(), partition_by=[F("development_id")],
        order_by=[F("run__facts_as_of").desc(), F("pk").desc()],
    )).filter(recent_rank=1).order_by("-run__facts_as_of", "pk")[:limit])


def history_query():
    """Keep run-sized packets out of repeated candidate metadata joins."""
    return OriginalContent.objects.select_related("run", "development").defer(
        "run__snapshot", "run__config_snapshot", "run__decisions", "run__outcome",
    )


def development_history(development, cutoff, *, limit=20):
    if type(limit) is not int or not 1 <= limit <= 40:
        raise ValueError("development history limit exceeded")
    return list(history_query().filter(
        Q(development=development) | Q(development__isnull=True, story_id=development.pk),
        workflow_key=WORKFLOWS["chatter"], run__facts_as_of__lte=cutoff, attempted_at__lte=cutoff,
    ).order_by("-attempted_at", "-pk")[:limit])


def uses_for_post(post_id, cutoff, *, limit=20):
    if type(post_id) is not str or not post_id or len(post_id) > 128:
        raise ValueError("invalid source lookup identity")
    if type(limit) is not int or not 1 <= limit <= 40:
        raise ValueError("source history limit exceeded")
    return list(history_query().filter(
        Q(consideration_sources__post_id=post_id)
        | Q(localized_texts__sources__post_id=post_id),
        workflow_key=WORKFLOWS["chatter"], run__facts_as_of__lte=cutoff, attempted_at__lte=cutoff,
    ).distinct().order_by("-attempted_at", "-pk")[:limit])
