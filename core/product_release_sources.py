"""Bounded adapters from canonical stored evidence; never contact a provider.

Collection windows use physical receipt time where retained and explicit
first-storage fallback otherwise. Reprocessing a cached reply is not collection.
Current saved enrichment is labelled as such; this is not a historical LLM replay.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Exists, OuterRef, Q

from core import models
from core.collection_capture import observation_object_documents
from core.product_release_intake import (
    SavedLabel,
    SourceRecord,
    TextEvidence,
    URLReference,
)
from core.product_release_replay import ReplayWindow


@dataclass(frozen=True)
class StoredSource:
    record: SourceRecord
    post_id: str | None
    observation_id: int | None
    published_at: datetime | None
    stored_at: datetime
    source_url: str | None
    clock_basis: str
    limitations: tuple[str, ...] = ()


def _entities_urls(entities, prefix):
    if not isinstance(entities, dict) or not isinstance(entities.get("urls"), list):
        return []
    return [
        URLReference(row[field], f"{prefix}.urls[{i}].{field}")
        for i, row in enumerate(entities["urls"])
        if isinstance(row, dict)
        for field in ("expanded_url", "unwound_url", "url")
        if isinstance(row.get(field), str) and row[field].strip()
    ]


def post_page(window: ReplayWindow, *, clock="publication", after="", limit=500):
    """Return the next PK-ordered page, including detector nonmatches."""
    if clock not in {"publication", "collection", "first_storage"}:
        raise ValueError("Unknown source clock")
    if not 1 <= limit <= 2000:
        raise ValueError("Page size must be 1..2000")
    qs = models.Post.objects.filter(pk__gt=after)
    physical = models.CollectionObservation.objects.filter(
        Q(post_id=OuterRef("pk"))
        | Q(
            source_identifier=OuterRef("pk"),
            source_identifier_is_null=False,
            observation_kind__in=["x_page_appearance", "x_request_appearance"],
        ),
        run__job__source_id="x",
    ).filter(
        Q(
            request__receipt_kind="physical",
            request__transport_outcome="received",
            request__received_at__gte=window.start,
            request__received_at__lt=window.end,
        )
        | Q(
            scope_run__request_uses__request__receipt_kind="physical",
            scope_run__request_uses__request__transport_outcome="received",
            scope_run__request_uses__request__received_at__gte=window.start,
            scope_run__request_uses__request__received_at__lt=window.end,
        )
    )
    if clock == "publication":
        qs = qs.filter(created_at__gte=window.start, created_at__lt=window.end)
    elif clock == "first_storage":
        qs = qs.filter(fetched_at__gte=window.start, fetched_at__lt=window.end)
    else:
        qs = qs.annotate(physical_in_window=Exists(physical)).filter(
            Q(physical_in_window=True)
            | Q(fetched_at__gte=window.start, fetched_at__lt=window.end)
        )
    posts = list(qs.order_by("pk")[:limit])
    return _post_sources(posts, clock=clock)


def stored_posts(post_ids):
    """Explicit bounded selection for assessed cases; no historical-clock claim."""
    if not 1 <= len(post_ids) <= 2000:
        raise ValueError("Select 1..2000 stored posts")
    posts = list(models.Post.objects.filter(pk__in=post_ids).order_by("pk"))
    if {post.pk for post in posts} != set(post_ids):
        raise ValueError("Selected source posts are missing")
    return _post_sources(posts, clock="explicit_selection")


def _post_sources(posts, *, clock):
    ids = [p.pk for p in posts]
    labels, extractions, syntheses = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    for row in models.PostBrandSignal.objects.filter(post_id__in=ids).values(
        "post_id", "brand_id", "post_type_id"
    ):
        labels[row["post_id"]].append(
            SavedLabel(
                row["post_type_id"],
                f"posts_brands_signals:{row['brand_id']}:{row['post_type_id']}",
            )
        )
    for row in models.PostBrandProductLabel.objects.filter(post_id__in=ids).values(
        "post_id", "brand_id", "product_label_id"
    ):
        labels[row["post_id"]].append(
            SavedLabel(
                row["product_label_id"],
                f"posts_brands_product_labels:{row['brand_id']}:{row['product_label_id']}",
            )
        )
    for row in models.EventDossierClaim.objects.filter(
        event_dossier_source__post_id__in=ids,
        claim_kind_reference__code="release_report",
    ).values("id", "assertion_text", "event_dossier_source__post_id"):
        extractions[row["event_dossier_source__post_id"]].append(
            TextEvidence(
                f"event_dossier_claims:{row['id']}",
                "release_extraction",
                row["assertion_text"],
            )
        )
    for row in models.PostSynthesisText.objects.filter(
        artifact__post_id__in=ids,
        artifact__is_current=True,
        artifact__state="succeeded",
    ).values("id", "text", "artifact__post_id"):
        syntheses[row["artifact__post_id"]].append(
            TextEvidence(f"post_synthesis_texts:{row['id']}", "commentary", row["text"])
        )
    result = []
    fields = {
        "text": "raw",
        "quoted_text": "quote",
        "text_en": "translation",
        "text_zh_cn": "translation",
        "commentary_en": "commentary",
        "commentary_zh_cn": "commentary",
    }
    for post in posts:
        texts = [
            TextEvidence(f"posts:{post.pk}.{field}", kind, getattr(post, field))
            for field, kind in fields.items()
            if getattr(post, field)
        ]
        texts.extend(
            sorted(extractions[post.pk] + syntheses[post.pk], key=lambda x: x.locator)
        )
        basis = (
            "physical_receipt"
            if clock == "collection" and post.physical_in_window
            else clock
        )
        if clock == "collection" and basis != "physical_receipt":
            basis = "first_storage_fallback"
        result.append(
            StoredSource(
                SourceRecord(
                    "post",
                    post.pk,
                    tuple(texts),
                    tuple(sorted(labels[post.pk], key=lambda x: x.locator)),
                    tuple(_entities_urls(post.entities, f"posts:{post.pk}.entities")),
                    bool(post.is_retweet),
                ),
                post.pk,
                None,
                post.created_at,
                post.fetched_at,
                post.tweet_url or f"https://x.com/i/status/{post.pk}",
                basis,
                ("current_saved_enrichment", "stored_population_only"),
            )
        )
    return result


def observation_page(window: ReplayWindow, *, clock="publication", after=0, limit=500):
    if (
        clock not in {"publication", "collection", "first_storage"}
        or not 1 <= limit <= 2000
    ):
        raise ValueError("Invalid observation page selection")
    qs = models.CollectionObservation.objects.filter(
        pk__gt=after, post__isnull=True
    ).exclude(run__job__source_id="x")
    if clock == "publication":
        # Date-only publication cannot be assigned to an arbitrary sub-day window.
        qs = qs.filter(published_at__gte=window.start, published_at__lt=window.end)
    elif clock == "collection":
        qs = qs.filter(
            Q(
                request__receipt_kind="physical",
                request__received_at__gte=window.start,
                request__received_at__lt=window.end,
            )
            | Q(
                request__isnull=True,
                observed_at__gte=window.start,
                observed_at__lt=window.end,
            )
        )
    else:
        qs = qs.filter(observed_at__gte=window.start, observed_at__lt=window.end)
    observations = list(
        qs.select_related(
            "request__archive",
            "legacy_archive",
            "resource_snapshot",
            "run__job__source",
        )
        .prefetch_related("inputs__input_request__archive")
        .order_by("pk")[:limit]
    )
    result = []
    for obs in observations:
        texts, urls, limitations, labels = [], [], [], []
        archives = {}
        request = obs.request
        if request and request.archive:
            archives[request.archive_id] = request.archive
        for item in obs.inputs.all():
            if item.input_request_id and item.input_request.archive_id:
                archives[item.input_request.archive_id] = item.input_request.archive
        if obs.legacy_archive_id:
            archives[obs.legacy_archive_id] = obs.legacy_archive
        # Canonical projectors select the observation's actual object from a
        # retained page and check its identity/hash. Never attach a whole list's
        # release text to each repository on that page.
        raw = {}
        if any(a.byte_count > 2_000_000 for a in archives.values()):
            limitations.append("body_over_2mb")
        else:
            try:
                raw, _, _ = observation_object_documents(obs)
            except (ValueError, TypeError, KeyError, UnicodeDecodeError):
                limitations.append("source_document_unavailable_or_invalid")
            if isinstance(raw, dict):
                for field in (
                    "body",
                    "description",
                    "content",
                    "model_card",
                    "readme",
                    "title",
                    "message",
                ):
                    if isinstance(raw.get(field), str) and raw[field].strip():
                        texts.append(
                            TextEvidence(
                                f"collection_observations:{obs.pk}.listing.{field}",
                                "raw",
                                raw[field],
                            )
                        )
                snapshot = getattr(obs, "resource_snapshot", None)
                if (
                    snapshot
                    and snapshot.resource_kind == "releases"
                    and raw.get("tag_name")
                    and raw.get("draft") is False
                ):
                    labels.append(
                        SavedLabel(
                            "product_release",
                            f"collection_resource_snapshots:{obs.pk}.resource_kind",
                        )
                    )
                    texts.append(
                        TextEvidence(
                            f"collection_observations:{obs.pk}.listing.tag_name",
                            "release_extraction",
                            raw["tag_name"],
                        )
                    )
        if request and request.endpoint_url:
            urls.append(
                URLReference(
                    request.endpoint_url,
                    f"collection_requests:{request.pk}.endpoint_url",
                )
            )
        if not texts:
            limitations.append("no_supported_release_text")
        basis = (
            "physical_receipt"
            if clock == "collection" and request and request.receipt_kind == "physical"
            else "observation_time"
            if clock != "publication"
            else clock
        )
        result.append(
            StoredSource(
                SourceRecord(
                    "observation",
                    str(obs.pk),
                    tuple(texts),
                    labels=tuple(labels),
                    urls=tuple(urls),
                ),
                None,
                obs.pk,
                obs.published_at,
                obs.observed_at,
                request.endpoint_url if request else None,
                basis,
                tuple(sorted(set(limitations + ["stored_population_only"]))),
            )
        )
    return result
