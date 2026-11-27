"""Bounded, read-only pages over saved release dossiers and their source links.

The feed is an inventory of discoveries. A review, canonical Product, provider
mapping, or dated claim is never required for inclusion.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID

from django.core import signing
from django.db.models import (
    BinaryField,
    Count,
    Exists,
    F,
    FilteredRelation,
    OuterRef,
    Q,
    Subquery,
    TextField,
    Value,
    Window,
)
from django.db.models.functions import Coalesce, NullIf, RowNumber, Substr
from django.utils import timezone

from core.collection_capture import read_document
from core.models import (
    Brand,
    BrandCompany,
    Company,
    CompanyLabel,
    EventDossier,
    EventDossierClaim,
    EventDossierIntakeDecision,
    EventDossierReview,
    EventDossierReviewClaim,
    EventDossierSource,
    PostBrandClassificationJudgment,
    Product,
    ProductGroupMembership,
    SourceSubjectMapping,
)
from core.product_release_findings import NOVELTIES

PAGE_SIZE = 25
MAX_PAGE_SIZE = 50
SOURCE_PREVIEW_SIZE = 3
DATE_PREVIEW_SIZE = 5
COMPANY_PREVIEW_SIZE = 4
CATEGORY_ANCHOR_LIMIT = 8
MAX_CATEGORY_PACKET_BYTES = 64 * 1024
CURRENT_CATEGORIES = frozenset(
    {"model-llm", "model-other", "agent", "harness", "other"}
)
_CURSOR_SALT = "pulse-pages-v1"
_DATE_KINDS = (
    "release_report",
    "announcement",
    "source_stated_release",
    "availability",
    "first_observed_usage",
    "rumor",
)
_FINDING_PACKET_FIELDS = frozenset({
    "schema", "source", "revision_id", "content_fingerprint", "extraction_version", "finding",
})


class PulseReadError(RuntimeError):
    """Stored dossier relationships cannot be safely displayed."""


def _limit(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_PAGE_SIZE
    ):
        raise ValueError("Invalid Pulse page size")
    return value


def _cursor(cursor, *, kind, event_id=None):
    if cursor is None:
        return None
    try:
        if not isinstance(cursor, str) or len(cursor) > 2048:
            raise ValueError
        value = signing.loads(cursor, salt=_CURSOR_SALT)
        if (
            not isinstance(value, dict)
            or set(value) - {"kind", "event_id", "ceiling", "after", "dated"}
            or ("dated" in value and (kind != "releases" or type(value["dated"]) is not bool))
            or value["kind"] != kind
            or value["event_id"] != event_id
        ):
            raise ValueError
        value["ceiling"] = datetime.fromisoformat(value["ceiling"])
        clock, identifier = value["after"]
        clock = datetime.fromisoformat(clock)
        identifier = UUID(identifier) if kind == "releases" else int(identifier)
        if timezone.is_naive(clock) or timezone.is_naive(value["ceiling"]):
            raise ValueError
        if clock > value["ceiling"]:
            raise ValueError
        value["after"] = (clock, identifier)
        return value
    except (
        signing.BadSignature,
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
    ) as error:
        raise ValueError("Invalid Pulse cursor") from error


def _next_cursor(*, kind, event_id, ceiling, clock, identifier, dated=None):
    return signing.dumps(
        {
            "kind": kind,
            "event_id": event_id,
            "ceiling": ceiling.isoformat(),
            "after": [clock.isoformat(), str(identifier)],
            **({"dated": dated} if dated is not None else {}),
        },
        salt=_CURSOR_SALT,
    )


def _url(value):
    """Links are saved source locations, never executable or credential URLs."""
    if not value or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            return value
    except ValueError:
        pass
    return None


def _count(queryset, group, field="pk", *, distinct=False):
    return Coalesce(
        Subquery(
            queryset.order_by()
            .values(group)
            .annotate(total=Count(field, distinct=distinct))
            .values("total")[:1]
        ),
        Value(0),
    )


def _review_before(dossier_id, cutoff):
    return EventDossierReview.objects.filter(
        event_dossier_id=dossier_id, recorded_at__lte=cutoff,
    ).order_by("-revision").values("pk")[:1]


def _review_dispositions(cutoff):
    return EventDossierReviewClaim.objects.filter(
        review_id=Subquery(_review_before(OuterRef("review__event_dossier_id"), cutoff)),
    )


def _events(cutoff):
    claims = EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier_id=OuterRef("pk"), recorded_at__lte=cutoff,
        event_dossier_source__linked_at__lte=cutoff,
    )
    # Legacy intake reports store the name directly. Classified findings also
    # contain release_report prose; only their finding anchor stores the name.
    reports = claims.filter(
        ~Q(extraction_version__startswith="pulse-classified-findings-")
        | Q(
            extraction_version__startswith="pulse-classified-findings-v1:",
            scope_key__startswith="pulse-finding-v1:",
        ),
        claim_kind_reference__code="release_report",
        source_archive__capture_kind="product_release_intake",
        source_archive__encoding="selected-json-canonical-v1",
    )
    # Only these explicit writer conventions name the released subject. HF
    # base-product claims also reference Products, but describe lineage.
    products = claims.filter(
        Q(
            scope_key__startswith="github_named_product:",
            extraction_version="github-named-product-v1",
        )
        | Q(
            scope_key__startswith="pulse-self-identity-v1:",
            extraction_version="pulse-product-identity-v1",
        ),
        reported_product__isnull=False,
        claim_kind_reference__code="release_context",
    )
    accepted_brand = _review_dispositions(cutoff).filter(
        claim_id=OuterRef("pk"),
        disposition="accepted",
    )
    brands = (
        claims.filter(reported_brand__isnull=False)
        .annotate(
            canonical_brand=FilteredRelation("reported_brand"),
            accepted_by_current_review=Exists(accepted_brand),
        )
        .filter(
            ~Exists(_review_before(OuterRef("event_dossier_source__event_dossier_id"), cutoff))
            | Q(accepted_by_current_review=True)
        )
    )
    sources = EventDossierSource.objects.filter(event_dossier_id=OuterRef("pk"), linked_at__lte=cutoff)
    intake = EventDossierIntakeDecision.objects.filter(
        event_dossier_id=OuterRef("pk"), recorded_at__lte=cutoff,
    ).order_by("-recorded_at", "-pk")
    return EventDossier.objects.annotate(
        snapshot_review=FilteredRelation("reviews", condition=Q(reviews__recorded_at__lte=cutoff))
    ).filter(Q(snapshot_review__isnull=True) | Q(snapshot_review__pk=Subquery(_review_before(OuterRef("pk"), cutoff)))).filter(
        event_kind_reference__code="product_release", merged_into__isnull=True
    ).annotate(
        has_pulse_finding=Exists(claims.filter(scope_key__startswith="pulse-finding-v1:",
            extraction_version__startswith="pulse-classified-findings-v1:")),
        report_names=_count(
            reports,
            "event_dossier_source__event_dossier_id",
            "assertion_text",
            distinct=True,
        ),
        report_name=Subquery(
            reports.order_by("id")
            .annotate(name=Substr("assertion_text", 1, 512))
            .values("name")[:1]
        ),
        claimed_products=_count(
            products,
            "event_dossier_source__event_dossier_id",
            "reported_product_id",
            distinct=True,
        ),
        claimed_product_id=Subquery(
            products.order_by("id").values("reported_product_id")[:1]
        ),
        claimed_brands=_count(
            brands,
            "event_dossier_source__event_dossier_id",
            "reported_brand_id",
            distinct=True,
        ),
        claimed_brand_id=Subquery(
            brands.order_by("id").values("canonical_brand__nickname")[:1]
        ),
        source_count=_count(sources, "event_dossier_id"),
        intake_outcome=Subquery(intake.values("outcome")[:1]),
        intake_recorded_at=Subquery(intake.values("recorded_at")[:1]),
        observed_name=Substr("snapshot_review__product_release__observed_name", 1, 512),
        canonical_issuer=FilteredRelation(
            "snapshot_review__product_release__release_issuer_company"
        ),
        issuer_company_id=F("canonical_issuer__nickname"),
    )


def _latest_release_manifest(post_id, *, cutoff=None):
    judgments = PostBrandClassificationJudgment.objects.filter(
        post_id=post_id,
        changes_json__release_output__schema="pulse-classified-release-output-v1",
        validation_state__in=("validated", "release_only"),
    )
    if cutoff is not None:
        judgments = judgments.filter(created_at__lte=cutoff)
    return judgments.order_by("-created_at", "-pk").values("changes_json__release_output__finding_keys")[:1]


def _source_query(event_ids, cutoff):
    accepted = _review_dispositions(cutoff).filter(
        claim__event_dossier_source_id=OuterRef("pk"),
        disposition="accepted",
    )
    return EventDossierSource.objects.filter(event_dossier_id__in=event_ids, linked_at__lte=cutoff).annotate(
        supports_current_review=Exists(accepted),
        post_label=Substr(
            Coalesce(
                NullIf("post__author_name", Value("")),
                NullIf("post__author_handle", Value("")),
                "post_id",
                output_field=TextField(),
            ),
            1,
            256,
        ),
        has_attached_finding=Exists(EventDossierClaim.objects.filter(
            event_dossier_source_id=OuterRef("pk"), scope_key__startswith="pulse-finding-v1:",
            extraction_version__startswith="pulse-classified-findings-v1:",
        )),
        post_classifier_error=F("post__enrichment_state__classification_error_code"),
        excerpt=Substr("post__text", 1, 320),
        last_release_keys=Subquery(_latest_release_manifest(OuterRef("post_id"), cutoff=cutoff)),
        post_url=Substr("post__tweet_url", 1, 2049),
        observation_url=Substr("collection_observation__run__source_url", 1, 2049),
        observation_label=Substr("collection_observation__source_identifier", 1, 256),
    )


_SOURCE_FIELDS = (
    "id",
    "event_dossier_id",
    "post_id",
    "collection_observation_id",
    "linked_at",
    "post_url",
    "post_label",
    "excerpt",
    "last_release_keys",
    "has_attached_finding",
    "post_classifier_error",
    "observation_label",
    "observation_url",
    "supports_current_review",
)


def _source(row):
    post_id = row["post_id"]
    url = row["post_url"] if post_id else row["observation_url"]
    if not url and post_id and str(post_id).isdigit():
        url = f"https://x.com/i/status/{post_id}"
    return {
        "id": row["id"],
        "post_id": post_id,
        "excerpt": row["excerpt"],
        "invalid_answer": (row["post_classifier_error"] or "").startswith("classification_compressed_invalid"),
        "has_attached_finding": row["has_attached_finding"],
        "last_finding_count": len(row["last_release_keys"]) if isinstance(row["last_release_keys"], list) else None,
        "observation_id": row["collection_observation_id"],
        "label": row["post_label"]
        or row["observation_label"]
        or str(post_id or row["collection_observation_id"]),
        "url": _url(url),
        "linked_at": row["linked_at"],
        "supports_current_review": row["supports_current_review"],
    }


def _source_previews(event_ids, cutoff):
    rows = (
        _source_query(event_ids, cutoff)
        .annotate(
            position=Window(
                RowNumber(),
                partition_by=[F("event_dossier_id")],
                order_by=[F("linked_at").asc(), F("pk").asc()],
            ),
        )
        .filter(position__lte=SOURCE_PREVIEW_SIZE)
        .order_by("event_dossier_id", "linked_at", "pk")
        .values(*_SOURCE_FIELDS)
    )
    result = {event_id: [] for event_id in event_ids}
    for row in rows:
        result[row["event_dossier_id"]].append(_source(row))
    return result


def _date_value(row):
    precision = row["effective_precision"]
    if precision == "datetime":
        return row["effective_at"].isoformat()
    if precision == "day":
        return row["effective_date"].isoformat()
    if precision == "month":
        return f"{row['effective_year']:04d}-{row['effective_month']:02d}"
    if precision == "year":
        return str(row["effective_year"])
    if precision == "range":
        return " / ".join(
            value.isoformat() if value else "…"
            for value in (row["not_before"], row["not_after"])
        )
    return None


def _dates(event_ids, cutoff):
    disposition = _review_dispositions(cutoff).filter(
        claim_id=OuterRef("pk"),
    ).values("disposition")[:1]
    rows = (
        EventDossierClaim.objects.filter(
            event_dossier_source__event_dossier_id__in=event_ids,
            claim_kind_reference__code__in=_DATE_KINDS,
            recorded_at__lte=cutoff, event_dossier_source__linked_at__lte=cutoff,
        )
        .exclude(effective_precision="unknown")
        .annotate(
            disposition=Subquery(disposition),
            locator=Substr("source_locator", 1, 2049),
            position=Window(
                RowNumber(),
                partition_by=[F("event_dossier_source__event_dossier_id")],
                order_by=[F("recorded_at").desc(), F("pk").desc()],
            ),
        )
        .filter(position__lte=DATE_PREVIEW_SIZE + 1)
        .order_by("event_dossier_source__event_dossier_id", "-recorded_at", "-pk")
        .values(
            "id",
            "event_dossier_source_id",
            "event_dossier_source__event_dossier_id",
            "claim_kind_reference__code",
            "effective_precision",
            "effective_at",
            "effective_date",
            "effective_year",
            "effective_month",
            "not_before",
            "not_after",
            "locator",
            "release_access_channel_reference__code",
            "disposition",
        )
    )
    result = {event_id: [] for event_id in event_ids}
    for row in rows:
        result[row["event_dossier_source__event_dossier_id"]].append(
            {
                "id": str(row["id"]),
                "kind": row["claim_kind_reference__code"],
                "precision": row["effective_precision"],
                "value": _date_value(row),
                "source_id": row["event_dossier_source_id"],
                "url": _url(row["locator"]),
                "access_channel": row["release_access_channel_reference__code"],
                "disposition": row["disposition"],
            }
        )
    return result


def _product_id(row):
    # A completed review's unresolved identity is intentional, including null.
    if row["snapshot_review__pk"] is not None:
        return row["snapshot_review__product_release__product__id"]
    if row.get("qualified_product_id") is not None:
        return row["qualified_product_id"]
    return row["claimed_product_id"] if row["claimed_products"] == 1 else None


def _reported_brand_id(row):
    return row["claimed_brand_id"] if row["claimed_brands"] == 1 else None


def _saved_category(row):
    """Read one bounded, source-bound classification packet without fetching it."""
    body = row["packet_body"]
    if (
        body is None
        or len(body) > MAX_CATEGORY_PACKET_BYTES
        or row["source_archive__byte_count"] != len(body)
        or row["source_archive__capture_kind"] != "product_release_intake"
        or row["source_archive__encoding"] != "selected-json-canonical-v1"
    ):
        raise ValueError("Invalid finding archive")
    packet = read_document(SimpleNamespace(
        body=body, content_sha256=row["source_archive__content_sha256"]
    ))
    # This encoding is the writer's sorted UTF-8 JSON. Round-tripping rejects
    # ambiguous duplicate keys and non-finite values accepted by json.loads.
    if json.dumps(
        packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode() != bytes(body):
        raise ValueError("Noncanonical finding packet")
    if not isinstance(packet, dict) or set(packet) != _FINDING_PACKET_FIELDS:
        raise ValueError("Invalid finding packet")
    finding, source = packet["finding"], packet["source"]
    if (
        packet["schema"] != "pulse-release-intake-v1"
        or not isinstance(finding, dict)
        or "category" not in finding
        or not isinstance(source, dict)
        or set(source) != {"kind", "id"}
        or not isinstance(packet["extraction_version"], str)
        or not packet["extraction_version"].strip()
    ):
        raise ValueError("Invalid finding packet shape")
    for value in (
        packet["revision_id"], packet["content_fingerprint"], finding.get("finding_key")
    ):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid finding revision")
    post_id = row["linked_post_id"]
    observation_id = row["event_dossier_source__collection_observation_id"]
    if post_id is not None and observation_id is None:
        source_matches = source["kind"] == "post" and source["id"] == post_id
    elif post_id is None and observation_id is not None:
        source_matches = (
            source["kind"] == "observation"
            and type(source["id"]) is int
            and source["id"] == observation_id
        )
    else:
        source_matches = False
    if (
        not source_matches
        or row["anchor_scope"] != f"pulse-finding-v1:{finding['finding_key']}"
        or row["anchor_version"] != f"pulse-classified-findings-v1:{packet['revision_id']}"
    ):
        raise ValueError("Finding archive identity mismatch")
    category = finding["category"]
    if category is not None and (
        not isinstance(category, str) or category not in CURRENT_CATEGORIES
    ):
        raise ValueError("Invalid finding category")
    return category


def _projected_categories(event_ids):
    """Read only source-linked category claims, never restricted archive bytes."""
    result = {event_id: {"categories": set(), "incomplete": False} for event_id in event_ids}
    anchors = (EventDossierClaim.objects.filter(
        Q(scope_key__startswith="pulse-finding-") | Q(extraction_version__startswith="pulse-classified-findings-"),
        event_dossier_source__event_dossier_id__in=event_ids,
        claim_kind_reference__code__in=("release_report", "release_signal"),
    ).exclude(scope_key__startswith="pulse-assertion-v1:").annotate(
        position=Window(RowNumber(), partition_by=[F("event_dossier_source__event_dossier_id")],
                        order_by=[F("recorded_at").desc(), F("pk").desc()]),
    ).filter(position__lte=CATEGORY_ANCHOR_LIMIT + 1).values(
        "event_dossier_source__event_dossier_id", "event_dossier_source_id", "position", "scope_key",
        "extraction_version", "source_archive_id", "source_archive__capture_kind", "source_archive__encoding"))
    rows = list(anchors)
    source_ids = {row["event_dossier_source_id"] for row in rows}
    category_scopes = {"pulse-category-v1:" + row["scope_key"].rsplit(":", 1)[-1] for row in rows}
    projections = EventDossierClaim.objects.filter(
        event_dossier_source_id__in=source_ids, scope_key__in=category_scopes,
        extraction_version__in={row["extraction_version"] for row in rows},
        source_archive_id__in={row["source_archive_id"] for row in rows if row["source_archive_id"]},
        claim_kind_reference__code="release_context",
    ).values("event_dossier_source_id", "scope_key", "extraction_version", "source_archive_id", "assertion_text")
    by_key = {}
    for item in projections:
        key = (item["event_dossier_source_id"], item["scope_key"], item["extraction_version"], item["source_archive_id"])
        by_key.setdefault(key, []).append(item["assertion_text"])
    for row in rows:
        state = result[row["event_dossier_source__event_dossier_id"]]
        scope, version = row["scope_key"], row["extraction_version"]
        if (row["position"] > CATEGORY_ANCHOR_LIMIT or not re.fullmatch(r"pulse-finding-v1:[0-9a-f]{64}", scope)
                or not re.fullmatch(r"pulse-classified-findings-v1:[0-9a-f]{64}", version)
                or not row["source_archive_id"] or row["source_archive__capture_kind"] != "product_release_intake"
                or row["source_archive__encoding"] != "selected-json-canonical-v1"):
            state["incomplete"] = True
            continue
        key = (row["event_dossier_source_id"], "pulse-category-v1:" + scope.rsplit(":", 1)[-1],
               version, row["source_archive_id"])
        values = by_key.get(key, [])
        if len(values) != 1 or values[0] not in CURRENT_CATEGORIES | {"unknown"}:
            state["incomplete"] = True
        elif values[0] != "unknown":
            state["categories"].add(values[0])
    return result


def _saved_categories(event_ids):
    from django.db import connection

    # Source archives are owner-only. Use the narrow projection when the
    # actual connection cannot read them (including staging's serving login).
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT has_column_privilege(current_user, 'collection_evidence_archives', 'body', 'SELECT')")
            if not cursor.fetchone()[0]:
                return _projected_categories(event_ids)
    result = {
        event_id: {"categories": set(), "incomplete": False}
        for event_id in event_ids
    }
    # Include identifiable anchors with malformed versions/archives so a valid
    # subset cannot quietly become the displayed category.
    rows = (
        EventDossierClaim.objects.filter(
            Q(scope_key__startswith="pulse-finding-")
            | Q(extraction_version__startswith="pulse-classified-findings-"),
            event_dossier_source__event_dossier_id__in=event_ids,
            claim_kind_reference__code__in=("release_report", "release_signal"),
        )
        .exclude(scope_key__startswith="pulse-assertion-v1:")
        .annotate(
            position=Window(
                RowNumber(),
                partition_by=[F("event_dossier_source__event_dossier_id")],
                order_by=[F("recorded_at").desc(), F("pk").desc()],
            ),
            packet_body=Substr(
                "source_archive__body", 1, MAX_CATEGORY_PACKET_BYTES + 1,
                output_field=BinaryField(),
            ),
            anchor_scope=Substr("scope_key", 1, 256),
            anchor_version=Substr("extraction_version", 1, 129),
            linked_post_id=Substr("event_dossier_source__post_id", 1, 513),
        )
        .filter(position__lte=CATEGORY_ANCHOR_LIMIT + 1)
        .values(
            "event_dossier_source__event_dossier_id", "position", "packet_body",
            "anchor_scope", "anchor_version", "linked_post_id",
            "event_dossier_source__collection_observation_id",
            "source_archive__byte_count", "source_archive__content_sha256",
            "source_archive__capture_kind", "source_archive__encoding",
        )
    )
    for row in rows:
        state = result[row["event_dossier_source__event_dossier_id"]]
        if row["position"] > CATEGORY_ANCHOR_LIMIT:
            state["incomplete"] = True
            continue
        try:
            category = _saved_category(row)
        except (ValueError, TypeError, RecursionError):
            state["incomplete"] = True
            continue
        if category is not None:
            state["categories"].add(category)
    return result


def _finding_novelties(event_ids, *, cutoff):
    """Resolve source-linked subtypes for this page without reading archive bodies."""
    from django.db.models.functions import Concat

    prefix = "pulse-finding-v1:"
    projection = EventDossierClaim.objects.filter(
        event_dossier_source_id=OuterRef("event_dossier_source_id"),
        source_archive_id=OuterRef("source_archive_id"),
        extraction_version=OuterRef("extraction_version"),
        scope_key=Concat(Value("pulse-novelty-v1:"), Substr(OuterRef("scope_key"), len(prefix) + 1)),
        claim_kind_reference__code="release_context", recorded_at__lte=cutoff,
    )
    anchors = EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier_id__in=event_ids,
        scope_key__startswith=prefix, extraction_version__startswith="pulse-classified-findings-v1:",
        claim_kind_reference__code__in=("release_report", "release_signal"),
        recorded_at__lte=cutoff, source_archive__capture_kind="product_release_intake",
        source_archive__encoding="selected-json-canonical-v1",
    )
    # Keep only the newest revision of each source's finding. A later empty
    # classifier answer can also withdraw it without producing another anchor.
    latest = anchors.filter(event_dossier_source_id=OuterRef("event_dossier_source_id"),
                            scope_key=OuterRef("scope_key")).order_by("-recorded_at", "-pk")
    accepted = _review_dispositions(cutoff).filter(claim_id=OuterRef("pk"), disposition="accepted")
    rows = (anchors.filter(pk=Subquery(latest.values("pk")[:1]))
            .filter(~Exists(_review_before(OuterRef("event_dossier_source__event_dossier_id"), cutoff)) | Exists(accepted))
            .annotate(subtype=Subquery(projection.values("assertion_text")[:1]),
                      keys=Subquery(_latest_release_manifest(OuterRef("event_dossier_source__post_id"), cutoff=cutoff)),
                      position=Window(RowNumber(), partition_by=[F("event_dossier_source__event_dossier_id")],
                                      order_by=[F("recorded_at").desc(), F("pk").desc()]))
            .filter(position__lte=CATEGORY_ANCHOR_LIMIT + 1)
            .values_list("event_dossier_source__event_dossier_id", "position", "subtype", "keys", "scope_key"))
    kinds, overflow = {}, set()
    for dossier, position, subtype, keys, scope in rows:
        if position > CATEGORY_ANCHOR_LIMIT:
            overflow.add(dossier)
        elif subtype in NOVELTIES and (keys is None or scope[len(prefix):] in keys):
            kinds.setdefault(dossier, set()).add(subtype)
    # A later access report on the same canonical launch is still an update
    # on its own source. It does not turn the launch into a second release.
    priority = ("new_release", "historical_release", "availability_update", "unresolved")
    return {dossier: next(item for item in priority if item in values)
            for dossier, values in kinds.items() if dossier not in overflow}


def _identities(rows, *, cutoff):
    product_ids = {_product_id(row) for row in rows} - {None}
    from core.product_preview_names import preview_redirects

    provisional = Product.objects.filter(pk__in=product_ids, repo_id__isnull=True).values_list(
        "pk", "brand_id", "display_name")
    redirects = preview_redirects(provisional, cutoff=cutoff, strict=True)
    product_ids.update(redirects.values())
    mappings = (
        SourceSubjectMapping.objects.filter(
            subject__subject_kind="product",
            subject__product_id=OuterRef("product_key"),
            source_subject_kind__in=("model", "repository"),
        )
        .exclude(reviewed_by="")
        .exclude(evidence_url="")
    )
    products = {
        row["id"]: row
        for row in Product.objects.filter(pk__in=product_ids)
        .annotate(
            # Alias the joins explicitly: an ordinary related-PK projection
            # may be optimized into the differently cased foreign-key value.
            canonical_brand=FilteredRelation("brand"),
            brand_key=F("canonical_brand__nickname"),
            name=Substr("display_name", 1, 512),
            catalog_mapping_present=Exists(mappings.filter(purpose="catalog")),
            metric_mapping_present=Exists(
                mappings.filter(purpose="metric").exclude(contract__reviewed_by="")
            ),
        )
        .values(
            "id",
            "product_key",
            "name",
            "product_type__code",
            "brand_key",
            "catalog_mapping_present",
            "metric_mapping_present",
        )
    }
    families = {product_id: [] for product_id in product_ids}
    for row in (
        ProductGroupMembership.objects.filter(
            product__id__in=product_ids,
            group__group_kind="family",
            membership_status="included",
            taxonomy_version_id=F("group__rule_taxonomy_version_id"),
        )
        .annotate(
            product_row_id=F("product__id"),
            position=Window(
                RowNumber(),
                partition_by=[F("product_id")],
                order_by=[F("group_id").asc()],
            ),
        )
        .filter(position__lte=2)
        .values("product_row_id", "group_id", "group__name")
    ):
        families[row["product_row_id"]].append(
            {"id": str(row["group_id"]), "name": row["group__name"]}
        )
    for product_id, product in products.items():
        matches = families[product_id]
        product["family"] = matches[0] if len(matches) == 1 else None
        product["family_conflict"] = len(matches) > 1

    for provisional_id, public_id in redirects.items():
        if public_id in products:
            products[provisional_id] = products[public_id]
    brand_ids = {row["brand_key"] for row in products.values()} - {None}
    brand_ids.update(_reported_brand_id(row) for row in rows)
    brand_ids.discard(None)
    brands = {
        row["nickname"]: {
            "id": row["nickname"], "name": row["name"] or row["nickname"]
        }
        for row in Brand.objects.filter(pk__in=brand_ids)
        .annotate(name=Substr("display_name", 1, 256))
        .values("nickname", "name")
    }
    owners = {brand_id: [] for brand_id in brand_ids}
    for row in (
        BrandCompany.objects.filter(brand_id__in=brand_ids)
        .annotate(
            canonical_brand=FilteredRelation("brand"),
            canonical_company=FilteredRelation("company"),
            brand_key=F("canonical_brand__nickname"),
            company_key=F("canonical_company__nickname"),
            position=Window(
                RowNumber(),
                partition_by=[F("brand_id")],
                order_by=[F("company_id").asc()],
            ),
        )
        .filter(position__lte=COMPANY_PREVIEW_SIZE + 1)
        .order_by("brand_id", "company_id")
        .values("brand_key", "company_key")
    ):
        owners[row["brand_key"]].append(row["company_key"])
    company_ids = {row["issuer_company_id"] for row in rows} - {None}
    company_ids.update(company_id for ids in owners.values() for company_id in ids)
    label = CompanyLabel.objects.filter(
        company_id=OuterRef("pk"), locale_id="und"
    ).values("label")[:1]
    companies = {
        row["nickname"]: {"id": row["nickname"], "name": row["name"]}
        for row in Company.objects.filter(pk__in=company_ids)
        .annotate(
            name=Substr(
                Coalesce(Subquery(label), F("nickname"), output_field=TextField()),
                1,
                256,
            ),
        )
        .values("nickname", "name")
    }
    return products, brands, owners, companies


def _timeline_page(*, ceiling, after, limit, dated=None):
    """Page IDs first, then load the expensive card details only for that page."""
    from django.db import connection

    # The SQL selector runs before LIMIT so a discarded revision cannot move a
    # launch onto another page. Its P2 scope follows release_chart_handoff:
    # current finding and manifest, exact Product/version, then its own assertions
    # or an independently verified history claim. Never select the archive body.
    with connection.cursor() as cursor:
        cursor.execute("""
          SELECT id, day, code, clock, qualified_product FROM (
            -- Only rows with an actual milestone enter the evidence query. All
            -- other discoveries can be paginated from the lightweight inventory.
            WITH inventory AS MATERIALIZED (
                SELECT d.id, d.created_at
                FROM event_dossiers d JOIN event_kinds kind ON kind.id = d.event_kind_id
                WHERE d.merged_into_id IS NULL AND kind.code = 'product_release' AND d.created_at <= %(ceiling)s
            ), with_date AS MATERIALIZED (
                SELECT DISTINCT s.event_dossier_id FROM event_dossier_claims c
                JOIN event_dossier_sources s ON s.id=c.event_dossier_source_id
                JOIN event_claim_kinds k ON k.id=c.claim_kind_id
                WHERE c.effective_precision IN ('day','datetime')
                  AND k.code IN ('source_stated_release','announcement','release_report')
                  AND c.recorded_at<=%(ceiling)s AND s.linked_at<=%(ceiling)s
            ), dossiers AS (
                SELECT d.id, r.id AS review_id, r.review_state, r.recorded_at AS reviewed_at,
                       EXISTS (SELECT 1 FROM event_dossier_review_claims a
                               JOIN event_dossier_claims c ON c.id=a.claim_id
                               WHERE a.review_id=r.id AND a.disposition='accepted'
                                 AND starts_with(c.scope_key,'pulse-finding-v1:')) AS approved_finding
                FROM with_date JOIN inventory d ON d.id=with_date.event_dossier_id
                LEFT JOIN LATERAL (
                    SELECT id, recorded_at, review_state FROM event_dossier_reviews
                    WHERE event_dossier_id = d.id AND recorded_at <= %(ceiling)s
                    ORDER BY revision DESC LIMIT 1
                ) r ON true
            ), dates AS MATERIALIZED (
                SELECT d.*, chosen.day, chosen.code, chosen.qualified_product FROM dossiers d
                LEFT JOIN LATERAL (
                    WITH evidence AS MATERIALIZED (
                        SELECT c.id, s.id AS source, s.post_id, c.source_archive_id AS archive,
                               c.scope_key AS scope, c.extraction_version AS revision, c.recorded_at,
                               c.reported_product_id AS product, c.reported_brand_id AS brand, k.code,
                               c.effective_at, COALESCE(c.effective_date, (c.effective_at AT TIME ZONE 'UTC')::date) AS day,
                               CASE WHEN c.scope_key ~ '^pulse-novelty-v1:' THEN left(c.assertion_text,32) END AS subtype
                        FROM event_dossier_sources s JOIN event_dossier_claims c ON c.event_dossier_source_id = s.id
                        JOIN event_claim_kinds k ON k.id = c.claim_kind_id
                        WHERE s.event_dossier_id = d.id AND c.recorded_at <= %(ceiling)s AND s.linked_at <= %(ceiling)s
                          AND (d.review_id IS NULL
                               OR (d.approved_finding AND c.scope_key ~ '^pulse-(finding|novelty)-v1:')
                               OR EXISTS (SELECT 1 FROM event_dossier_review_claims a
                                          WHERE a.review_id=d.review_id AND a.claim_id=c.id
                                            AND a.disposition='accepted' AND k.code IN
                                                ('source_stated_release','announcement','release_report')))
                        LIMIT CASE WHEN d.review_id IS NULL THEN 257 ELSE 513 END
                    ), anchors AS (
                        -- A source can revise a finding or withdraw it in its latest manifest.
                        SELECT DISTINCT ON (source, scope) e.*, split_part(scope, ':', 2) AS key
                        FROM evidence e
                        WHERE e.archive IS NOT NULL AND scope ~ '^pulse-finding-v1:[0-9a-f]{64}$'
                          AND revision ~ '^pulse-classified-findings-v1:[0-9a-f]{64}$'
                        ORDER BY source, scope, recorded_at DESC, e.id DESC
                    ), projected AS MATERIALIZED (
                        -- Older packets without a projected subtype cannot qualify through
                        -- P2 on the web login. Skip their archive and judgment lookups.
                        SELECT a.id, a.source, a.archive, a.revision, a.brand, a.post_id, a.key, n.subtype
                        FROM anchors a LEFT JOIN evidence n ON n.source=a.source AND n.archive=a.archive
                            AND n.revision=a.revision AND n.code='release_context' AND n.scope='pulse-novelty-v1:' || a.key
                        WHERE d.approved_finding OR n.id IS NOT NULL
                    ), active AS (
                        SELECT a.* FROM projected a JOIN collection_evidence_archives archive ON archive.id=a.archive
                            AND archive.capture_kind='product_release_intake' AND archive.encoding='selected-json-canonical-v1'
                        LEFT JOIN LATERAL (
                            SELECT j.changes_json->'release_output'->'finding_keys' AS keys
                            FROM posts_brands_classification_judgments j
                            WHERE j.post_id = a.post_id AND j.validation_state IN ('validated','release_only')
                              AND j.changes_json->'release_output'->>'schema' = 'pulse-classified-release-output-v1'
                              AND j.created_at <= %(ceiling)s
                            ORDER BY j.created_at DESC, j.id DESC LIMIT 1
                        ) manifest ON true
                        WHERE manifest.keys IS NULL OR manifest.keys ? a.key
                    ), members AS (
                        -- Resolve the same source+archive-bound Product and version as P2.
                        SELECT a.*, m.product, split_part(m.scope,':',3) AS version, p.product_key, p.brand_id,
                            (m.scope ~ '^pulse-event-member-v1:[0-9a-f]{64}:[0-9a-f]{64}$'
                             AND i.product = m.product AND (a.brand IS NULL OR a.brand = p.brand_id)
                             AND NOT b.is_sentinel AND NOT coalesce(p.private,false) AND NOT coalesce(p.disabled,false)
                             AND count(*) OVER (PARTITION BY a.id) = 1) AS valid
                        FROM active a LEFT JOIN evidence m ON m.source = a.source AND m.archive = a.archive
                            AND m.revision = 'pulse-event-identity-v1' AND m.product IS NOT NULL
                            AND starts_with(m.scope, 'pulse-event-member-v1:' || a.key || ':')
                        LEFT JOIN LATERAL (
                            SELECT DISTINCT i.product, true AS present FROM evidence i
                            WHERE i.source = a.source AND i.archive = a.archive
                              AND i.revision = 'pulse-product-identity-v1' AND i.scope = 'pulse-self-identity-v1:' || a.key
                        ) i ON true
                        LEFT JOIN products p ON p.id = m.product LEFT JOIN brands b ON b.nickname = p.brand_id
                        WHERE a.subtype IN ('new_release','historical_release','availability_update')
                          AND (i.present OR m.id IS NOT NULL)
                    ), exact AS (
                        SELECT min(product) AS product FROM members
                        HAVING bool_and(coalesce(valid,false)) AND count(DISTINCT (product,version)) = 1
                    ), approved AS (
                        SELECT a.* FROM active a JOIN event_dossier_review_claims rc
                            ON rc.claim_id=a.id AND rc.review_id=d.review_id AND rc.disposition='accepted'
                    ), accepted AS (
                        SELECT e.* FROM evidence e JOIN event_dossier_review_claims rc
                            ON rc.claim_id=e.id AND rc.review_id=d.review_id AND rc.disposition='accepted'
                        WHERE e.code IN ('source_stated_release','announcement','release_report')
                    ), reviewed_launch_dates AS (
                        -- Remove access-only sources. For a mixed source, remove
                        -- only dated assertions from its exact accepted update packet.
                        SELECT a.* FROM accepted a WHERE NOT EXISTS (
                            SELECT 1 FROM approved u WHERE u.subtype='availability_update' AND u.source=a.source
                              AND ((u.archive=a.archive AND u.revision=a.revision
                                    AND a.scope ~ '^pulse-(assertion|finding)-v1:'
                                    AND split_part(a.scope,':',2)=u.key)
                                   OR NOT EXISTS (SELECT 1 FROM approved other WHERE other.source=u.source
                                                  AND other.subtype IS DISTINCT FROM 'availability_update'))
                        )
                    ), eligible AS (
                        -- Legacy discoveries retain their reported date. Classified
                        -- releases need their own assertion or exact historical link.
                        SELECT e.* FROM evidence e WHERE d.review_id IS NULL AND (
                            NOT EXISTS (SELECT 1 FROM anchors)
                            OR EXISTS (
                                SELECT 1 FROM members m JOIN exact x ON x.product=m.product
                                WHERE (m.subtype IN ('new_release','historical_release')
                                       AND e.source=m.source AND e.archive=m.archive AND e.revision=m.revision
                                       AND e.scope ~ '^pulse-assertion-v1:[0-9a-f]{64}:[0-9a-f]{64}$'
                                       AND split_part(e.scope,':',2)=m.key)
                                   OR (e.revision='pulse-historical-announcement-v1' AND e.product=m.product
                                       AND e.brand=m.brand_id AND e.scope='pulse-history-v1:'||m.product_key::text
                                       AND e.post_id IS NOT NULL AND e.code IN ('announcement','source_stated_release'))
                            )
                        )
                        UNION ALL
                        -- Reviews accept individual claims. An access update can
                        -- qualify only through a separately accepted launch source.
                        SELECT a.* FROM reviewed_launch_dates a JOIN product_release_details rd ON rd.review_id=d.review_id
                        JOIN products p ON p.product_key=rd.product_key JOIN brands b ON b.nickname=p.brand_id
                        WHERE d.review_state='confirmed' AND rd.disclosure_state!='unannounced' AND NOT b.is_sentinel
                          AND NOT coalesce(p.private,false) AND NOT coalesce(p.disabled,false)
                          AND NOT EXISTS (SELECT 1 FROM reviewed_launch_dates rival WHERE rival.product != p.id OR rival.brand != p.brand_id)
                    )
                    SELECT code, (SELECT product FROM exact) AS qualified_product,
                                 CASE WHEN count(DISTINCT day)=1 AND count(DISTINCT effective_at)<=1
                                          AND coalesce(max(effective_at)<=%(ceiling)s,true)
                                      THEN min(day) END AS day
                    FROM eligible WHERE day IS NOT NULL AND code IN ('source_stated_release','announcement','release_report')
                      AND (CASE WHEN d.review_id IS NULL THEN (SELECT count(*) FROM evidence)<=256
                                ELSE (SELECT count(*) FROM accepted)<=256 AND
                                (NOT d.approved_finding OR
                                 (SELECT count(*) FROM evidence WHERE scope ~ '^pulse-(finding|novelty)-v1:')<=256)
                           END)
                    GROUP BY code ORDER BY CASE code WHEN 'source_stated_release' THEN 1 WHEN 'announcement' THEN 2 ELSE 3 END
                    LIMIT 1
                ) chosen ON chosen.day <= (%(ceiling)s AT TIME ZONE 'UTC')::date
                    AND NOT coalesce((SELECT i.outcome IN ('scam','non_release','superseded')
                                     AND (d.review_id IS NULL OR i.recorded_at >= d.reviewed_at)
                                     FROM event_dossier_intake_decisions i
                                     WHERE i.event_dossier_id=d.id AND i.recorded_at<=%(ceiling)s
                                     ORDER BY i.recorded_at DESC,i.id DESC LIMIT 1),false)
            )
            SELECT i.id, day, code, qualified_product,
                   CASE WHEN %(legacy)s THEN created_at ELSE coalesce(day::timestamp AT TIME ZONE 'UTC',created_at) END AS clock,
                   (day IS NOT NULL AND NOT %(legacy)s) AS dated FROM inventory i LEFT JOIN dates ON dates.id=i.id
          ) timeline
          WHERE (%(clock)s::timestamptz IS NULL OR (dated,clock,id) < (%(dated)s,%(clock)s,%(id)s::uuid))
          ORDER BY dated DESC, clock DESC, id DESC LIMIT %(limit)s
        """, {"ceiling": ceiling, "clock": after[0] if after else None,
              "id": after[1] if after else None, "limit": limit, "dated": bool(dated),
              "legacy": after is not None and dated is None})
        return cursor.fetchall()


def release_page(*, cursor=None, limit=PAGE_SIZE):
    """One bounded canonical-discovery page; absent identity never drops a row."""
    limit = _limit(limit)
    marker = _cursor(cursor, kind="releases")
    ceiling = marker["ceiling"] if marker else timezone.now()
    timeline = _timeline_page(ceiling=ceiling, after=marker["after"] if marker else None, limit=limit + 1,
                              dated=marker.get("dated") if marker else None)
    has_next = len(timeline) > limit
    days = {pk: (day, kind, product) for pk, day, kind, _, product in timeline[:limit]}
    rows_by_id = {
        row["id"]: row for row in _events(ceiling).filter(pk__in=days).values(
            "id",
            "created_at",
            "first_seen_at",
            "snapshot_review__pk",
            "snapshot_review__review_state",
            "snapshot_review__recorded_at",
            "observed_name",
            "snapshot_review__product_release__product__id",
            "issuer_company_id",
            "has_pulse_finding",
            "report_names",
            "report_name",
            "claimed_products",
            "claimed_product_id",
            "claimed_brands",
            "claimed_brand_id",
            "source_count",
            "intake_outcome",
            "intake_recorded_at",
        )
    }
    rows = [rows_by_id[key] for key in days if key in rows_by_id]
    for row in rows:
        row["qualified_product_id"] = days[row["id"]][2]
    event_ids = [row["id"] for row in rows]
    novelties = _finding_novelties(event_ids, cutoff=ceiling)
    sources, dates = _source_previews(event_ids, ceiling), _dates(event_ids, ceiling)
    products, brands, owners, companies = _identities(rows, cutoff=ceiling)
    saved_categories = _saved_categories([
        row["id"] for row in rows
        if row["snapshot_review__pk"] is None
        and not products.get(_product_id(row), {}).get("product_type__code")
    ])
    entries = []
    for row in rows:
        product_id = _product_id(row)
        product = products.get(product_id)
        brand_id = (product["brand_key"] if product else None) or _reported_brand_id(row)
        name = (
            row["observed_name"]
            if row["snapshot_review__pk"] is not None
            else row["report_name"] if row["report_names"] == 1 else None
        )
        issuer_id = row["issuer_company_id"]
        company_ids = [issuer_id] if issuer_id else owners.get(brand_id, [])
        category = product["product_type__code"] if product else None
        category_source = "product" if category else None
        category_evidence = saved_categories.get(row["id"], {})
        reported_categories = sorted(category_evidence.get("categories", ()))
        category_conflict = len(reported_categories) > 1
        category_incomplete = category_evidence.get("incomplete", False)
        if len(reported_categories) == 1 and not category_incomplete:
            category, = reported_categories
            category_source = "saved_finding"
        entries.append(
            {
                "id": str(row["id"]),
                "name": name or (product["name"] if product else None),
                "has_pulse_finding": row["has_pulse_finding"],
                "novelty": novelties.get(row["id"]),
                "has_historical_launch": novelties.get(row["id"]) == "availability_update"
                and bool(days[row["id"]][0]) and product_id is not None,
                "review_state": row["snapshot_review__review_state"] or "pending",
                "review_id": str(row["snapshot_review__pk"])
                if row["snapshot_review__pk"]
                else None,
                "intake_outcome": row["intake_outcome"],
                "intake_is_current": not row["snapshot_review__recorded_at"] or (
                    row["intake_recorded_at"] is not None and row["intake_recorded_at"] >= row["snapshot_review__recorded_at"]
                ),
                "product_key": str(product["product_key"]) if product else None,
                "family": product["family"] if product else None,
                "family_conflict": product["family_conflict"] if product else False,
                "product_identity_state": (
                    "reviewed" if row["snapshot_review__pk"] is not None else "reported"
                ) if product else "pending",
                "provider_mapping_present": (
                    product["catalog_mapping_present"]
                    or product["metric_mapping_present"]
                )
                if product
                else None,
                "catalog_mapping_present": product["catalog_mapping_present"]
                if product
                else None,
                "metric_mapping_present": product["metric_mapping_present"]
                if product
                else None,
                "category": category if category in CURRENT_CATEGORIES else None,
                "category_source": category_source,
                "category_conflict": category_conflict,
                "category_evidence_incomplete": category_incomplete,
                "reported_categories": reported_categories,
                "legacy_category": category
                if category and category not in CURRENT_CATEGORIES
                else None,
                "brand": brands.get(brand_id),
                "companies": [
                    companies[key]
                    for key in company_ids[:COMPANY_PREVIEW_SIZE]
                ],
                "companies_more": len(company_ids) > COMPANY_PREVIEW_SIZE,
                "timeline_date": days[row["id"]][0],
                "timeline_date_kind": days[row["id"]][1],
                "discovered_at": row["created_at"],
                "first_seen_at": row["first_seen_at"],
                "release_dates": dates[row["id"]][:DATE_PREVIEW_SIZE],
                "dates_more": len(dates[row["id"]]) > DATE_PREVIEW_SIZE,
                "sources_count": row["source_count"],
                "sources": sources[row["id"]],
                "identity_conflict": row["qualified_product_id"] is None and (
                    row["claimed_products"] > 1 or row["report_names"] > 1 or row["claimed_brands"] > 1
                ),
            }
        )
    next_cursor = None
    if has_next:
        last_id, day, _, clock, _ = timeline[limit - 1]
        next_cursor = _next_cursor(
            kind="releases",
            event_id=None,
            ceiling=ceiling,
            clock=clock,
            identifier=last_id,
            dated=(day is not None) if marker is None or "dated" in marker else None,
        )
    return {"entries": entries, "next_cursor": next_cursor}


def _canonical_event(dossier_id):
    # Existing database guards prohibit cycles. Detect corrupt/imported chains
    # explicitly and cap their traversal instead of looping on a page request.
    visited = set()
    for _ in range(32):
        try:
            identifier = UUID(str(dossier_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise EventDossier.DoesNotExist from error
        if identifier in visited:
            raise PulseReadError("Invalid dossier merge chain")
        visited.add(identifier)
        row = (
            EventDossier.objects.filter(
                pk=identifier, event_kind_reference__code="product_release"
            )
            .values("id", "merged_into_id")
            .get()
        )
        if row["merged_into_id"] is None:
            return row["id"]
        dossier_id = row["merged_into_id"]
    raise PulseReadError("Dossier merge chain exceeds read limit")


def release_sources(dossier_id, *, cursor=None, limit=PAGE_SIZE):
    """Page every stored association, with accepted-review support kept separate."""
    limit = _limit(limit)
    event_id = _canonical_event(dossier_id)
    marker = _cursor(cursor, kind="sources", event_id=str(event_id))
    ceiling = marker["ceiling"] if marker else timezone.now()
    query = _source_query([event_id], ceiling)
    if marker:
        clock, identifier = marker["after"]
        query = query.filter(
            Q(linked_at__gt=clock) | Q(linked_at=clock, pk__gt=identifier)
        )
    rows = list(query.order_by("linked_at", "pk").values(*_SOURCE_FIELDS)[: limit + 1])
    has_next, rows = len(rows) > limit, rows[:limit]
    next_cursor = None
    if has_next:
        last = rows[-1]
        next_cursor = _next_cursor(
            kind="sources",
            event_id=str(event_id),
            ceiling=ceiling,
            clock=last["linked_at"],
            identifier=last["id"],
        )
    return {
        "event_id": str(event_id),
        "entries": [_source(row) for row in rows],
        "next_cursor": next_cursor,
    }
