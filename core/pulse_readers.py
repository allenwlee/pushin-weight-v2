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
    EventDossierReviewClaim,
    EventDossierSource,
    Product,
    ProductGroupMembership,
    SourceSubjectMapping,
)

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
            or set(value) != {"kind", "event_id", "ceiling", "after"}
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


def _next_cursor(*, kind, event_id, ceiling, clock, identifier):
    return signing.dumps(
        {
            "kind": kind,
            "event_id": event_id,
            "ceiling": ceiling.isoformat(),
            "after": [clock.isoformat(), str(identifier)],
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


def _events():
    claims = EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier_id=OuterRef("pk")
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
    accepted_brand = EventDossierReviewClaim.objects.filter(
        claim_id=OuterRef("pk"),
        review_id=OuterRef("event_dossier_source__event_dossier__current_review_id"),
        disposition="accepted",
    )
    brands = (
        claims.filter(reported_brand__isnull=False)
        .annotate(
            canonical_brand=FilteredRelation("reported_brand"),
            accepted_by_current_review=Exists(accepted_brand),
        )
        .filter(
            Q(event_dossier_source__event_dossier__current_review_id__isnull=True)
            | Q(accepted_by_current_review=True)
        )
    )
    sources = EventDossierSource.objects.filter(event_dossier_id=OuterRef("pk"))
    intake = EventDossierIntakeDecision.objects.filter(
        event_dossier_id=OuterRef("pk")
    ).order_by("-recorded_at", "-pk")
    return EventDossier.objects.filter(
        event_kind_reference__code="product_release", merged_into__isnull=True
    ).annotate(
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
        observed_name=Substr("current_review__product_release__observed_name", 1, 512),
        canonical_issuer=FilteredRelation(
            "current_review__product_release__release_issuer_company"
        ),
        issuer_company_id=F("canonical_issuer__nickname"),
    )


def _source_query(event_ids):
    accepted = EventDossierReviewClaim.objects.filter(
        claim__event_dossier_source_id=OuterRef("pk"),
        review_id=OuterRef("event_dossier__current_review_id"),
        disposition="accepted",
    )
    return EventDossierSource.objects.filter(event_dossier_id__in=event_ids).annotate(
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
        "observation_id": row["collection_observation_id"],
        "label": row["post_label"]
        or row["observation_label"]
        or str(post_id or row["collection_observation_id"]),
        "url": _url(url),
        "linked_at": row["linked_at"],
        "supports_current_review": row["supports_current_review"],
    }


def _source_previews(event_ids):
    rows = (
        _source_query(event_ids)
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


def _dates(event_ids):
    disposition = EventDossierReviewClaim.objects.filter(
        claim_id=OuterRef("pk"),
        review_id=OuterRef("event_dossier_source__event_dossier__current_review_id"),
    ).values("disposition")[:1]
    rows = (
        EventDossierClaim.objects.filter(
            event_dossier_source__event_dossier_id__in=event_ids,
            claim_kind_reference__code__in=_DATE_KINDS,
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
    if row["current_review_id"] is not None:
        return row["current_review__product_release__product__id"]
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


def _identities(rows):
    product_ids = {_product_id(row) for row in rows} - {None}
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


def release_page(*, cursor=None, limit=PAGE_SIZE):
    """One bounded canonical-discovery page; absent identity never drops a row."""
    limit = _limit(limit)
    marker = _cursor(cursor, kind="releases")
    ceiling = marker["ceiling"] if marker else timezone.now()
    query = _events().filter(created_at__lte=ceiling)
    if marker:
        clock, identifier = marker["after"]
        query = query.filter(
            Q(created_at__lt=clock) | Q(created_at=clock, pk__lt=identifier)
        )
    rows = list(
        query.order_by("-created_at", "-id").values(
            "id",
            "created_at",
            "first_seen_at",
            "current_review_id",
            "current_review__review_state",
            "observed_name",
            "current_review__product_release__product__id",
            "issuer_company_id",
            "report_names",
            "report_name",
            "claimed_products",
            "claimed_product_id",
            "claimed_brands",
            "claimed_brand_id",
            "source_count",
            "intake_outcome",
        )[: limit + 1]
    )
    has_next, rows = len(rows) > limit, rows[:limit]
    event_ids = [row["id"] for row in rows]
    sources, dates = _source_previews(event_ids), _dates(event_ids)
    products, brands, owners, companies = _identities(rows)
    saved_categories = _saved_categories([
        row["id"] for row in rows
        if row["current_review_id"] is None
        and not products.get(_product_id(row), {}).get("product_type__code")
    ])
    entries = []
    for row in rows:
        product_id = _product_id(row)
        product = products.get(product_id)
        brand_id = (product["brand_key"] if product else None) or _reported_brand_id(row)
        name = (
            row["observed_name"]
            if row["current_review_id"] is not None
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
                "review_state": row["current_review__review_state"] or "pending",
                "review_id": str(row["current_review_id"])
                if row["current_review_id"]
                else None,
                "intake_outcome": row["intake_outcome"],
                "product_key": str(product["product_key"]) if product else None,
                "family": product["family"] if product else None,
                "family_conflict": product["family_conflict"] if product else False,
                "product_identity_state": (
                    "reviewed" if row["current_review_id"] is not None else "reported"
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
                "discovered_at": row["created_at"],
                "first_seen_at": row["first_seen_at"],
                "release_dates": dates[row["id"]][:DATE_PREVIEW_SIZE],
                "dates_more": len(dates[row["id"]]) > DATE_PREVIEW_SIZE,
                "sources_count": row["source_count"],
                "sources": sources[row["id"]],
                "identity_conflict": row["claimed_products"] > 1
                or row["report_names"] > 1
                or row["claimed_brands"] > 1,
            }
        )
    next_cursor = None
    if has_next:
        last = rows[-1]
        next_cursor = _next_cursor(
            kind="releases",
            event_id=None,
            ceiling=ceiling,
            clock=last["created_at"],
            identifier=last["id"],
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
    query = _source_query([event_id]).filter(linked_at__lte=ceiling)
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
