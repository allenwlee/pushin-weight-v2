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


def chatter_pool(source_locale, editorial_group):
    """Canonical database identity; publication language is a separate choice."""
    locales = {"en": "en", "ja": "ja", "zh-cn": "zh-CN"}
    source = locales.get(source_locale.casefold()) if isinstance(source_locale, str) else None
    if source is None or editorial_group not in {"giant", "rest"}:
        raise ValueError("invalid Chatter pool")
    return source, editorial_group


def featured_scope(workflow, locale, *, source_locale=None, editorial_group=None):
    if source_locale is None and editorial_group is None:
        return f"featured:{workflow}:{locale}"
    if workflow != WORKFLOWS["chatter"]:
        raise ValueError("only Chatter supports source pools")
    source, group = chatter_pool(source_locale, editorial_group)
    return f"featured:{workflow}:{source.casefold()}:{group}:{locale}"


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
        dossier_id = source.get("dossier_source_id")
        if dossier_id is not None:
            if type(dossier_id) is not int or dossier_id < 1 or source.get("post_id"):
                raise ValueError("invalid dossier citation identity")
            post_id = None
            key = ("dossier", dossier_id)
        else:
            post_id = str(source.get("post_id") or source.get("id") or "").removeprefix("x:")
            key = ("post", post_id)
        if (not dossier_id and not post_id) or key in seen:
            if key in seen:
                continue
            raise ValueError("citation has no post identity")
        seen.add(key)
        projected = any(k in source for k in ("original_text", "text", "excerpt"))
        values.append(
            {
                "post_id": post_id,
                "dossier_source_id": dossier_id,
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
    posts = {key for kind, key in seen if kind == "post"}
    found = set(Post.objects.filter(pk__in=posts).values_list("pk", flat=True))
    if found != posts:
        raise ValueError("missing cited posts: " + ",".join(sorted(posts - found)))
    dossiers = {key for kind, key in seen if kind == "dossier"}
    if dossiers:
        from core.models import EventDossierSource

        found = set(EventDossierSource.objects.filter(
            pk__in=dossiers, collection_observation__isnull=False
        ).values_list("pk", flat=True))
        if found != dossiers:
            raise ValueError("dossier citation requires an existing document source")
    return values


def publish_content(content, texts, *, selected_scope=None, fence=None, legacy=False):
    """Save copy, citations and optional pointer atomically, with no partial approval."""
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=content.run_id)
        row = OriginalContent.objects.select_for_update().get(pk=content.pk)
        if row.run_id != run.pk:
            raise ValueError("stale content owner")
        if row.consideration_state is not None and (fence is None or legacy):
            raise ValueError("new Chatter publication requires a current fence and producing call")
        if fence is not None and (
            run.fence != fence
            or run.execution_state != "running"
            or run.lease_until is None
            or run.lease_until <= timezone.now()
        ):
            raise ValueError("stale content fence")
        append_locale = (
            row.workflow_key == WORKFLOWS["chatter"]
            and row.consideration_state == "selected"
            and row.development_id is not None
            and row.status == "approved"
        )
        if row.status != "prepared" and not append_locale:
            raise ValueError("saved content is immutable")
        if row.consideration_state is not None and row.consideration_state != "selected":
            raise ValueError("only selected consideration can publish")
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
            if row.consideration_state is not None:
                from monitor.editorial.chatter_history import read_sources

                expected = {
                    (source["post_id"], source["dossier_source_id"]): source
                    for source in citation_values(read_sources(row, usage="consideration"))
                }
                owners = {(source.post_id, source.dossier_source_id): source.snapshot_run_id
                          for source in row.consideration_sources.all()}
                for value in values:
                    source = expected.get((value["post_id"], value["dossier_source_id"]))
                    if source is None or any(
                        source[key] != val for key, val in value.items() if key != "position"
                    ):
                        raise ValueError("citation does not match a considered source")
                    value["snapshot_run_id"] = owners[(value["post_id"], value["dossier_source_id"])]
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
            existing = row.localized_texts.filter(locale=spec["locale"]).first()
            if existing is not None:
                source_fields = [
                    "post_id", "dossier_source_id", "position", "url_snapshot",
                    "author_label_snapshot", "source_hash", "hash_basis",
                ]
                if row.consideration_state is not None:
                    source_fields.append("snapshot_run_id")
                saved_sources = list(existing.sources.order_by("position").values(*source_fields))
                if not append_locale or (
                    existing.headline != spec["headline"]
                    or existing.secondary != spec["byline"]
                    or existing.body != spec.get("body", "")
                    or existing.producing_call_id != producer.pk
                    or existing.provenance != spec.get("provenance", {})
                    or saved_sources != values
                ):
                    raise ValueError("saved content is immutable")
                results.append(existing)
                continue
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
            expected_scope = featured_scope(
                row.workflow_key, results[0].locale,
                **({"source_locale": row.source_locale_id, "editorial_group": row.editorial_group}
                   if row.consideration_state is not None else {}),
            )
            if (
                len(results) != 1
                or selected_scope != expected_scope
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
        {
            "url": row.url_snapshot,
            "label": row.author_label_snapshot
            or ("X" if urlsplit(row.url_snapshot).hostname == "x.com" else "Source"),
        }
        for row in text.sources.all()
    ]
