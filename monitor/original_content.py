"""Shared storage boundary for authored output; no provider or queue calls."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from django.db import connection, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from core.models import (
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
    OriginalContentSelection,
    OriginalContentSource,
    OriginalContentText,
    Post,
)

WORKFLOWS = {"chatter": "social-brief", "pulse": "development-report"}
LOCALES = frozenset({"en", "zh-cn", "ja"})


def shared_storage():
    mode = os.environ.get("ORIGINAL_CONTENT_STORAGE", "legacy")
    if mode not in {"legacy", "shared"}:
        raise ValueError("invalid OriginalContent storage mode")
    return mode == "shared"


def mirror_storage():
    return (
        shared_storage()
        or os.environ.get("ORIGINAL_CONTENT_MIRROR", "false").lower() == "true"
    )


def budget_totals(scope, day):
    """Reservations are ceilings, not invoices; immutable carry-forward counts once."""
    calls = OriginalContentCall.objects.filter(budget_scope=scope, budget_day=day)
    result = calls.aggregate(
        reserved_usd=Sum("reserved_usd"),
        calls=Count("pk"),
        media_calls=Count("pk", filter=Q(kind="media")),
    )
    result["reserved_usd"] = result["reserved_usd"] or Decimal(0)
    for receipt in OriginalContentRun.objects.filter(
        workflow_key="reservation-carryforward", scope_key=f"budget:{scope}:{day}"
    ):
        result["reserved_usd"] += Decimal(receipt.outcome["external_reserved_usd"])
        result["calls"] += int(receipt.outcome["external_calls"])
        result["media_calls"] += int(receipt.outcome.get("external_media_calls", 0))
    return result


def digest(value):
    return sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def advisory_lock(key):
    """Short transaction lock, also usable before a row exists."""
    if not connection.in_atomic_block:
        raise RuntimeError("content lock requires a transaction")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            [int.from_bytes(sha256(key.encode()).digest()[:8], "big", signed=True)],
        )


def safe_source_url(value):
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or any(c.isspace() for c in value)
    ):
        raise ValueError("invalid source URL")
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("invalid source URL")
    return value


def citation_values(sources, *, legacy=False):
    """Resolve saved projections only; never invent an old hash from today's post."""
    values = []
    seen = set()
    for source in sources:
        key = str(source.get("post_id") or source.get("id") or "")
        key = key.removeprefix("x:")
        if not key or key in seen:
            if key in seen:
                continue
            raise ValueError("citation has no post identity")
        seen.add(key)
        projected = any(k in source for k in ("original_text", "text", "excerpt"))
        values.append(
            {
                "post_id": key,
                "position": len(values),
                "url_snapshot": safe_source_url(source.get("url")),
                "author_label_snapshot": source.get("author_handle")
                or source.get("author_label")
                or "",
                "source_hash": digest(source.get("_writing_projection", source))
                if projected or not legacy
                else None,
                "hash_basis": "legacy_packet"
                if legacy and projected
                else "legacy_unavailable"
                if legacy
                else "writing_packet",
            }
        )
    found = set(Post.objects.filter(pk__in=seen).values_list("pk", flat=True))
    if found != seen:
        raise ValueError("missing cited posts: " + ",".join(sorted(seen - found)))
    return values


def publish_content(content, texts, *, selected_scope=None, fence=None, legacy=False):
    """Save copy, citations and optional pointer atomically, with no partial approval."""
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=content.run_id)
        row = OriginalContent.objects.select_for_update().get(pk=content.pk)
        if fence is not None and (
            run.fence != fence
            or run.execution_state != "running"
            or run.lease_until is None
            or run.lease_until <= timezone.now()
        ):
            raise ValueError("stale content fence")
        if row.status != "prepared":
            raise ValueError("saved content is immutable")
        locales = [text["locale"] for text in texts]
        if (
            not locales
            or len(locales) != len(set(locales))
            or not set(locales) <= LOCALES
        ):
            raise ValueError("invalid content locales")
        if row.workflow_key in (None, "brand-window") and not {"en", "zh-cn"} <= set(
            locales
        ):
            raise ValueError("trend requires complete bilingual output")
        results = []
        for spec in texts:
            if not spec.get("headline") or not spec.get("byline"):
                raise ValueError("incomplete saved copy")
            values = citation_values(spec.get("sources", []), legacy=legacy)
            if row.workflow_key in WORKFLOWS.values() and not values:
                raise ValueError("editorial output requires citations")
            producer = spec.get("producing_call")
            if not legacy:
                if producer is None:
                    raise ValueError("missing producing call")
                producer = OriginalContentCall.objects.get(pk=producer.pk)
                if (
                    producer.run_id != row.run_id
                    or producer.workflow_key != row.workflow_key
                    or producer.state != "completed"
                    or producer.kind != "text"
                ):
                    raise ValueError("producing call does not match saved text")
            text = OriginalContentText.objects.create(
                narrative=row,
                locale=spec["locale"],
                headline=spec["headline"],
                secondary=spec["byline"],
                body=spec.get("body", ""),
                public_id=UUID(str(spec["public_id"]))
                if spec.get("public_id")
                else uuid4(),
                producing_call=producer,
                provenance=spec.get("provenance", {}),
            )
            OriginalContentSource.objects.bulk_create(
                [OriginalContentSource(text=text, **value) for value in values]
            )
            results.append(text)
        row.status = "approved"
        row.verified_at = row.verified_at or row.published_at or timezone.now()
        row.published_at = row.published_at or row.verified_at
        if row.workflow_key in (None, "brand-window"):
            for text in results:
                if text.locale in {"en", "zh-cn"}:
                    suffix = text.locale.replace("-", "_")
                    setattr(row, f"headline_{suffix}", text.headline)
                    setattr(row, f"secondary_{suffix}", text.secondary)
        row.save()
        if selected_scope:
            if (
                len(results) != 1
                or selected_scope != f"featured:{row.workflow_key}:{results[0].locale}"
            ):
                raise ValueError("invalid featured selection scope")
            advisory_lock("selection:" + selected_scope)
            pointer = (
                OriginalContentSelection.objects.select_for_update()
                .filter(scope_key=selected_scope)
                .first()
            )
            if pointer and pointer.facts_as_of > run.facts_as_of:
                raise ValueError("stale featured publication")
            OriginalContentSelection.objects.update_or_create(
                scope_key=selected_scope,
                defaults={
                    "text": results[0],
                    "run": None,
                    "window_days": None,
                    "facts_as_of": run.facts_as_of,
                    "activated_at": row.published_at,
                },
            )
        return results


def source_payload(text):
    return [
        {"url": row.url_snapshot, "label": row.author_label_snapshot or "Source"}
        for row in text.sources.all()
    ]
