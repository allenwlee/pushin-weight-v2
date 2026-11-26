"""Read-only, public display documents for General and atomic Post pages.

These are browser documents, not the G4 agent API. Feed membership is an exact
current classification; the identity of a public Post survives feed turnover.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

from django.core import signing
from django.core.exceptions import EmptyResultSet
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.db.models.functions import Collate
from django.utils import timezone

from core.brand_presentation import brand_logo_urls
from core.classification_contract import (
    CANONICAL_TAXONOMY_VERSION,
    CONTRACT_VERSION,
    STAGE1_TAXONOMY_V3_VERSION,
)
from core.intelligence_readers import (
    _parse_temporal,
    _reported_source_timezone,
    event_lifecycle,
    opportunity_lifecycle,
)
from core.job_locations import canonical_job_locations, location_prefetch
from core.job_vocabulary import classification_prefetches, classification_text
from core.models import (
    Event,
    EventEvidence,
    JobListingEvidence,
    Opportunity,
    PersonBrandAffiliationEvidence,
    PersonNameSelection,
    Post,
    PostBrandClassificationState,
    PostBrandSignal,
    PostSynthesisArtifact,
)
from monitor.post_artifacts import SUPPORTED_CONTENT_LOCALES, read_post_content_many

SECTIONS = {
    "calendar": "events",
    "free": "opportunities",
    "jobs": "job_listings",
    "moving": "personnel_changes",
}
CURSOR_SALT = "monitor.general.v1"
_RECENT_CLASSIFIED_SCAN_LIMIT = 100_000


def safe_external_url(value):
    """Keep source links and media inert unless they are ordinary web URLs."""
    value = str(value or "").strip()
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        ):
            return value
    except ValueError:
        pass
    return ""


def public_posts():
    # The existing anonymous public feed exposes stored Posts without a recency
    # or classification access restriction. Keep that same policy for permalinks.
    return Post.objects.all()


def current_signals():
    state = PostBrandClassificationState.objects.filter(
        post_id=OuterRef("post_id"),
        brand_id=OuterRef("brand_id"),
        outcome="classified",
        contract_version=CONTRACT_VERSION,
        taxonomy_version__in=(STAGE1_TAXONOMY_V3_VERSION, CANONICAL_TAXONOMY_VERSION),
    )
    return PostBrandSignal.objects.filter(Exists(state))


def _localized(values, locale, source):
    selected = next(
        (
            key
            for key in dict.fromkeys((locale, *SUPPORTED_CONTENT_LOCALES))
            if values.get(key)
        ),
        None,
    )
    return {
        "text": values.get(selected, ""),
        "locale": selected,
        "fallback": bool(selected and selected != locale),
        "source": source if selected else "unavailable",
    }


def post_documents(posts, *, locale="en", section=None):
    """Batch-load an allowlisted projection; never enqueue missing enrichment."""
    if not posts:
        return {}
    content = read_post_content_many(posts)
    post_ids = [post.pk for post in posts]
    revisions = {
        post_id: (revision_id, review_state)
        for post_id, revision_id, review_state in PostSynthesisArtifact.objects.filter(
            post_id__in=post_ids,
            is_current=True,
            state="succeeded",
        ).values_list("post_id", "pk", "review_state")
    }
    signals = current_signals().filter(post_id__in=post_ids).select_related("brand")
    if section:
        signals = signals.filter(post_type_id=SECTIONS[section])
    brands = {post_id: {} for post_id in post_ids}
    logo_urls = brand_logo_urls()
    for signal in signals.order_by("brand_id"):
        brand = signal.brand
        name = (
            (brand.display_name_zh_cn if locale == "zh-cn" else brand.display_name_en)
            or brand.display_name
            or brand.pk
        )
        brands[signal.post_id][brand.pk] = {
            "id": brand.pk,
            "name": name,
            "url": f"/brands/{quote(brand.pk, safe='')}/",
            "logo": logo_urls.get(brand.pk),
        }
    documents = {}
    for post in posts:
        stored = content[str(post.pk)]
        revision_id, review_state = revisions.get(post.pk, (None, None))
        withdrawn = review_state in {"withdrawn", "rejected"}
        commentary = _localized(
            {} if withdrawn else stored.synthesis, locale, stored.synthesis_source
        )
        commentary["artifact_id"] = (
            revision_id if commentary["source"] == "normalized" else None
        )
        literal = _localized(stored.literal, locale, stored.literal_source)
        documents[str(post.pk)] = {
            "id": str(post.pk),
            "url": f"/posts/{quote(str(post.pk), safe='')}/",
            "fetched_at": post.fetched_at.isoformat(),
            "published_at": post.created_at.isoformat() if post.created_at else None,
            "source": {
                "text": post.text or "",
                "author": post.author_handle or "",
                "url": safe_external_url(post.tweet_url or post.tweet_twitter_url),
                "language": post.lang_detected or "",
                "translation": literal,
            },
            "commentary": commentary,
            "brands": list(brands[post.pk].values()),
            "facts": [],
        }
    return documents


def _traversal(section, locale, brands, cursor, as_of):
    filters = {"section": section, "locale": locale, "brands": brands, "version": 1}
    if cursor:
        try:
            payload = signing.loads(cursor, salt=CURSOR_SALT, max_age=86400)
            if payload["filters"] != filters:
                raise ValueError("Continuation belongs to different filters")
            at = datetime.fromisoformat(payload["as_of"])
            last = payload["last"]
            if not timezone.is_aware(at) or not isinstance(last, list):
                raise ValueError("Invalid continuation")
        except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid or expired continuation") from exc
    else:
        at, last = as_of or timezone.now(), None
        if not timezone.is_aware(at):
            raise ValueError("as_of must include a timezone")
    return filters, at, last


def temporal_facts(post_ids, section, *, as_of):
    """Read linked schedule facts in batches, including evidence-only event links."""
    result = {post_id: [] for post_id in post_ids}
    if not result:
        return result
    if section == "calendar":
        records = (
            Event.objects.filter(
                Q(source_post_id__in=post_ids)
                | Q(evidence__source_post_id__in=post_ids),
            )
            .exclude(review_status="rejected")
            .distinct()
            .order_by("id")
            .prefetch_related(
                Prefetch(
                    "evidence",
                    queryset=EventEvidence.objects.filter(
                        source_post_id__in=post_ids
                    ).only("event_id", "source_post_id"),
                ),
            )
        )
    else:
        records = (
            Opportunity.objects.filter(source_post_id__in=post_ids)
            .exclude(review_status="rejected")
            .select_related("opportunity_type_reference")
            .order_by("id")
        )
    for row in records:
        is_event = section == "calendar"
        start = {
            "value": row.start_value if is_event else row.open_value,
            "precision": row.start_precision if is_event else row.open_precision,
        }
        end = {
            "value": row.end_value if is_event else row.close_value,
            "precision": row.end_precision if is_event else row.close_precision,
        }
        state = (
            event_lifecycle(row, as_of=as_of)
            if is_event
            else opportunity_lifecycle(row, as_of=as_of)
        )
        fact = {
            "kind": "event" if is_event else "opportunity",
            "id": row.pk,
            "brand_id": row.brand_id,
            "title": row.title
            if is_event
            else row.benefit_text or row.opportunity_type_reference.code.replace("_", " "),
            "organization": row.organizer_name if is_event else row.sponsor_name,
            "start": start,
            "end": end,
            "state": state,
            "timezone": _reported_source_timezone(row),
            "schedule": row.source_schedule_text
            if is_event
            else row.source_availability_text,
            "url": safe_external_url(
                row.attendance_url or row.canonical_url or row.source_url
            )
            if is_event
            else safe_external_url(row.action_url or row.source_url),
            "location": (
                row.physical_location or row.virtual_location or row.attendance_mode
            )
            if is_event
            else row.geographic_restrictions,
            "eligibility": None if is_event else row.eligibility,
            "confirmed": row.review_status == "confirmed",
        }
        linked = {row.source_post_id}
        if is_event:
            linked.update(evidence.source_post_id for evidence in row.evidence.all())
        for post_id in linked & result.keys():
            result[post_id].append(fact)
    return result


def _fact_order(fact):
    start = _parse_temporal(fact["start"]["value"], fact["start"]["precision"])
    if fact["state"] in {"live", "open"}:
        return (0, start.timestamp() if start else 0, fact["id"])
    if fact["state"] == "upcoming" and start:
        return (1, start.timestamp(), fact["id"])
    return (2, 0, fact["id"])


def timing_anchor(facts):
    active = [
        fact for fact in facts if fact["state"] not in {"past", "closed", "cancelled"}
    ]
    if not active:
        return None if facts else {"state": "unknown", "target": None, "fact_id": None}
    anchor = min(active, key=_fact_order)
    if anchor["state"] in {"live", "open"}:
        target = anchor["end"]
    elif anchor["state"] == "upcoming":
        target = anchor["start"]
    else:
        target = {}
    instant = _parse_temporal(target.get("value"), target.get("precision", "unknown"))
    return {
        "state": anchor["state"],
        "target": instant.isoformat() if instant else None,
        "fact_id": anchor["id"],
    }


def jobs_people_facts(post_ids, section, *, as_of, locale="en"):
    result = {post_id: {} for post_id in post_ids}
    if section == "jobs":
        evidence = (
            JobListingEvidence.objects.filter(
                source_post_id__in=post_ids,
                listing__source_key__isnull=True,
            )
            .select_related("listing")
            .prefetch_related(location_prefetch(prefix="listing__"), *classification_prefetches(
                prefix="listing__", dimensions=("employment_type", "workplace_type"),
            ))
            .order_by("listing_id", "id")
        )
        for source in evidence:
            row = source.listing
            closed = (
                row.status == "closed"
                or bool(row.closed_at and row.closed_at <= as_of)
                or bool(row.expires_at and row.expires_at <= as_of)
            )
            result[source.source_post_id][row.pk] = {
                "kind": "job",
                "id": row.pk,
                "brand_id": row.brand_id,
                "title": row.title,
                "organization": row.hiring_organization,
                "state": "closed" if closed else row.status,
                "url": safe_external_url(row.application_url or row.canonical_url),
                "description": row.description_text or "",
                "location": " · ".join(place["label"] for place in canonical_job_locations(row, locale=locale) if place["label"]),
                "workplace": classification_text(row, "workplace_type"),
                "employment": classification_text(row, "employment_type"),
                "salary": row.salary_text,
                "contact": row.application_contact,
                "application_kind": row.application_route_kind,
            }
    else:
        from core.person_names import selected_name_for

        evidence = (
            PersonBrandAffiliationEvidence.objects.filter(
                source_post_id__in=post_ids,
                affiliation__superseded_by__isnull=True,
                affiliation__superseded_at__isnull=True,
            )
            .exclude(review_status="rejected")
            .exclude(affiliation__review_status="rejected")
            .select_related(
                "affiliation__person__primary_name",
                "affiliation__person__english_name",
                "affiliation__affiliation_type_reference",
            )
            .prefetch_related(
                Prefetch(
                    "affiliation__person__name_selections",
                    queryset=PersonNameSelection.objects.select_related("name"),
                )
            )
            .order_by("affiliation_id", "id")
        )
        for source in evidence:
            row, person = source.affiliation, source.affiliation.person
            name = selected_name_for(person, locale) or selected_name_for(
                person, "und"
            ) or "Unreviewed person"
            confirmed = (
                row.review_status == "confirmed" and source.review_status == "confirmed"
            )
            previous = result[source.source_post_id].get(row.pk)
            result[source.source_post_id][row.pk] = {
                "kind": "personnel",
                "id": row.pk,
                "brand_id": row.brand_id,
                "person_id": str(person.pk),
                "name": name,
                "title": row.title_raw or row.title_normalized or "",
                "organization": row.observed_organization_name,
                "relationship": row.affiliation_type_reference.code,
                "state": row.status,
                "confirmed": confirmed or bool(previous and previous["confirmed"]),
                "start": {
                    "value": row.start_date,
                    "precision": row.start_date_precision,
                },
                "end": {"value": row.end_date, "precision": row.end_date_precision},
                "portrait": None,
                "initials": "".join(part[0] for part in name.split()[:2]).upper()
                if name
                else "?",
            }
    return {pk: list(rows.values()) for pk, rows in result.items()}


def _bounded_temporal_candidates(section, signals, brands, at, last, limit):
    """Keep linked posts plus a bounded, ordered page of posts without facts.

    If the recent window does not contain a full page, fall back to the
    original complete reader: a rare brand may have older matches.
    """
    if connection.vendor != "postgresql":
        return None
    with connection.cursor() as cursor:
        cursor.execute("SHOW transaction_isolation")
        if cursor.fetchone()[0] not in {"repeatable read", "serializable"}:
            # A caller-owned READ COMMITTED transaction cannot keep the
            # linked and unlinked queries on the same snapshot.
            return None
    if brands == []:
        return {}, set()
    recent_limit = 5000
    try:
        public_sql, public_params = public_posts().order_by().values("pk", "fetched_at").query.sql_with_params()
        signal_sql, signal_params = signals.order_by().values("post_id").query.sql_with_params()
    except EmptyResultSet:
        return {}, set()
    params = [*public_params, at]
    cursor_filter = ""
    if last and len(last) == 4 and last[0] == 2 and last[1] == 0:
        try:
            last_fetch = datetime.fromtimestamp(-last[2], tz=UTC)
        except (ValueError, OverflowError, TypeError):
            return None
        cursor_filter = (
            ' AND p.fetched_at <= %s AND (p.fetched_at < %s OR (p.fetched_at = %s AND p.pk COLLATE "C" > %s COLLATE "C"))'
        )
        params += [last_fetch, last_fetch, last_fetch, last[3]]
    elif last and (len(last) != 4 or last[0] not in (0, 1, 2)):
        return None

    if section == "calendar":
        link_queries = [
            Event.objects.exclude(review_status="rejected"),
            EventEvidence.objects.exclude(event__review_status="rejected"),
        ]
    else:
        link_queries = [Opportunity.objects.exclude(review_status="rejected")]
    linked_queries = []
    linked_params = []
    no_facts = []
    params.append(recent_limit)
    for link_query in link_queries:
        posts = link_query.filter(source_post_id__isnull=False).order_by().values("source_post_id")
        link_sql, link_params = posts.query.sql_with_params()
        linked_queries.append(link_sql)
        linked_params.extend(link_params)
        no_facts.append(f"r.pk NOT IN ({link_sql})")
        params.extend(link_params)
    params.extend(signal_params)
    params.append(limit + 1)
    query = f"""
        WITH recent AS MATERIALIZED (
            SELECT p.pk, p.fetched_at FROM ({public_sql}) p
            WHERE p.fetched_at <= %s {cursor_filter}
            ORDER BY p.fetched_at DESC, p.pk COLLATE "C" LIMIT %s
        ), window_size AS (SELECT count(*) AS scanned FROM recent)
        SELECT matching.pk, matching.fetched_at, window_size.scanned
        FROM window_size LEFT JOIN LATERAL (
            SELECT r.pk, r.fetched_at FROM recent r
            WHERE {' AND '.join(no_facts)} AND EXISTS (
                SELECT 1 FROM ({signal_sql}) matched WHERE matched.post_id=r.pk OFFSET 0
            )
            ORDER BY r.fetched_at DESC, r.pk COLLATE "C" LIMIT %s
        ) matching ON true
    """
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    unknown = [(pk, fetched) for pk, fetched, _ in rows if pk is not None]
    scanned = rows[0][2]
    if len(unknown) <= limit and scanned == recent_limit:
        return None
    # Drive the lookup from the comparatively small set of linked fact IDs.
    # A single ORM IN/OR expression can make PostgreSQL scan the complete
    # classified-post set first, even though only a few posts have dates.
    linked_sql = " UNION ALL ".join(linked_queries)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH linked AS MATERIALIZED (
                SELECT DISTINCT source_post_id FROM ({linked_sql}) linked_sources
            )
            SELECT p.pk, p.fetched_at FROM linked l
            CROSS JOIN LATERAL (
                SELECT p.pk, p.fetched_at FROM ({public_sql}) p
                WHERE p.pk=l.source_post_id AND p.fetched_at <= %s
                  AND EXISTS (SELECT 1 FROM ({signal_sql}) matched
                              WHERE matched.post_id=p.pk OFFSET 0)
                OFFSET 0
            ) p
            """,
            [*linked_params, *public_params, at, *signal_params],
        )
        candidates = dict(cursor.fetchall())
    linked_ids = set(candidates)
    candidates.update(unknown)
    return candidates, linked_ids


def _recent_classified_candidates(signals, brands, at, last, limit):
    """Read a time-ordered page while probing the exact classification by Post."""
    if connection.vendor != "postgresql":
        return None
    try:
        public_sql, public_params = public_posts().order_by().values("pk", "fetched_at").query.sql_with_params()
        signal_sql, signal_params = signals.order_by().values("post_id").query.sql_with_params()
    except EmptyResultSet:
        return {}
    cursor_filter = ""
    cursor_params = []
    if last is not None:
        last_fetch = datetime.fromtimestamp(-last[0], tz=UTC)
        cursor_filter = (
            ' AND p.fetched_at <= %s AND (p.fetched_at < %s OR '
            '(p.fetched_at = %s AND p.pk COLLATE "C" > %s COLLATE "C"))'
        )
        cursor_params = [last_fetch, last_fetch, last_fetch, last[1]]
    scan_limit = (
        min(_RECENT_CLASSIFIED_SCAN_LIMIT, 5_000)
        if brands is not None and len(brands) <= 2 else _RECENT_CLASSIFIED_SCAN_LIMIT
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT r.pk,r.fetched_at FROM (
                SELECT p.pk,p.fetched_at FROM ({public_sql}) p
                WHERE p.fetched_at <= %s {cursor_filter}
                ORDER BY p.fetched_at DESC,p.pk COLLATE "C" LIMIT %s OFFSET 0
            ) r
            WHERE EXISTS (SELECT 1 FROM ({signal_sql}) matched
                          WHERE matched.post_id=r.pk OFFSET 0)
            ORDER BY r.fetched_at DESC,r.pk COLLATE "C" LIMIT %s
            """,
            [*public_params, at, *cursor_params, scan_limit, *signal_params, limit + 1],
        )
        rows = cursor.fetchall()
    # An incomplete recent page may hide older matches for a sparse brand.
    return dict(rows) if len(rows) > limit else None


def _general_feed(
    section, *, locale="en", brands=None, limit=20, cursor=None, as_of=None
):
    """Return a bounded page, ordered against the first request's fixed clock."""
    if section not in SECTIONS or locale not in SUPPORTED_CONTENT_LOCALES:
        raise ValueError("Unknown section or locale")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    brands = sorted(set(brands)) if brands is not None else None
    filters, at, last = _traversal(section, locale, brands, cursor, as_of)
    signals = current_signals().filter(post_type_id=SECTIONS[section])
    if brands is not None:
        signals = signals.filter(brand_id__in=brands)
    bounded = (
        _bounded_temporal_candidates(section, signals, brands, at, last, limit)
        if section in {"calendar", "free"}
        else None
    )
    recent_candidates = (
        _recent_classified_candidates(signals, brands, at, last, limit)
        if section in {"jobs", "moving"} else None
    )
    if recent_candidates is not None:
        candidates = recent_candidates
        fact_ids = []
    elif bounded is None:
        eligible = public_posts().filter(
            pk__in=signals.values("post_id"), fetched_at__lte=at
        )
        if section in {"jobs", "moving"}:
            # Preserve the exact C-collated ordering in the sparse fallback.
            eligible = eligible.annotate(_sort_id=Collate("tweet_id", "C"))
            if last is not None:
                last_fetch = datetime.fromtimestamp(-last[0], tz=UTC)
                eligible = eligible.filter(
                    Q(fetched_at__lt=last_fetch)
                    | Q(fetched_at=last_fetch, _sort_id__gt=last[1])
                )
            eligible = eligible.order_by("-fetched_at", "_sort_id")[: limit + 1]
        candidates = dict(eligible.values_list("pk", "fetched_at"))
        fact_ids = list(candidates)
    else:
        candidates, fact_ids = bounded
    facts = (
        temporal_facts(list(fact_ids), section, as_of=at)
        if section in {"calendar", "free"}
        else {}
    )
    if bounded is not None:
        facts.update({pk: [] for pk in candidates if pk not in facts})
    timing = {pk: timing_anchor(rows) for pk, rows in facts.items()}
    ordered = []
    for pk, fetched in candidates.items():
        if pk in timing:
            if timing[pk] is None:
                continue
            selected = next(
                (row for row in facts[pk] if row["id"] == timing[pk]["fact_id"]), None
            )
            prefix = list(_fact_order(selected)[:2]) if selected else [2, 0]
        else:
            prefix = []
        ordered.append(([*prefix, -fetched.timestamp(), str(pk)], str(pk)))
    ordered.sort()
    if last is not None:
        ordered = [(key, pk) for key, pk in ordered if key > last]
    page = ordered[:limit]
    posts = list(public_posts().filter(pk__in=[pk for _, pk in page]))
    documents = post_documents(posts, locale=locale, section=section)
    if section in {"jobs", "moving"}:
        facts = jobs_people_facts(list(documents), section, as_of=at, locale=locale)
    for pk, document in documents.items():
        document["facts"] = facts.get(pk, [])
        document["timing"] = timing.get(pk)
        document["age_seconds"] = max(0, (at - candidates[pk]).total_seconds())
        document["recent"] = section == "jobs" and document["age_seconds"] < 86400
    next_cursor = None
    if len(ordered) > limit:
        next_cursor = signing.dumps(
            {"filters": filters, "as_of": at.isoformat(), "last": page[-1][0]},
            salt=CURSOR_SALT,
            compress=True,
        )
    return {
        "section": section,
        "locale": locale,
        "as_of": at.isoformat(),
        "items": [documents[pk] for _, pk in page],
        "next_cursor": next_cursor,
    }


def general_feed(section, *, locale="en", brands=None, limit=20, cursor=None, as_of=None):
    """Read one page against a consistent snapshot when this call owns it."""
    options = {"locale": locale, "brands": brands, "limit": limit, "cursor": cursor, "as_of": as_of}
    if (
        section not in {"calendar", "free"}
        or connection.vendor != "postgresql"
        or connection.in_atomic_block
        or not connection.get_autocommit()
    ):
        return _general_feed(section, **options)
    with transaction.atomic():
        with connection.cursor() as db_cursor:
            db_cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return _general_feed(section, **options)
