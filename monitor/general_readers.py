"""Read-only, public display documents for General and atomic Post pages.

These are browser documents, not the G4 agent API. Feed membership is an exact
current classification; the identity of a public Post survives feed turnover.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
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
from monitor.general_budget import check_read_deadline
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


def _filter_fingerprint(filters):
    return sha256(json.dumps(filters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _traversal(section, locale, brands, cursor, as_of):
    filters = {"section": section, "locale": locale, "brands": brands, "version": 1}
    if cursor:
        try:
            payload = signing.loads(cursor, salt=CURSOR_SALT, max_age=86400)
            if not isinstance(payload, dict):
                raise TypeError("Invalid continuation")
            if payload.get("version") == 2:
                matching = payload.get("filters_sha256") == _filter_fingerprint(filters)
            else:
                matching = "version" not in payload and payload.get("filters") == filters
            if not matching:
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
        timing = _temporal_timing_fact(row, section, as_of=as_of)
        fact = {
            "kind": "event" if is_event else "opportunity",
            "id": row.pk,
            "brand_id": row.brand_id,
            "title": row.title
            if is_event
            else row.benefit_text or row.opportunity_type_reference.code.replace("_", " "),
            "organization": row.organizer_name if is_event else row.sponsor_name,
            **timing,
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


def _temporal_timing_fact(row, section, *, as_of):
    is_event = section == "calendar"
    return {
        "id": row.pk,
        "start": {
            "value": row.start_value if is_event else row.open_value,
            "precision": row.start_precision if is_event else row.open_precision,
        },
        "end": {
            "value": row.end_value if is_event else row.close_value,
            "precision": row.end_precision if is_event else row.close_precision,
        },
        "state": event_lifecycle(row, as_of=as_of) if is_event else opportunity_lifecycle(row, as_of=as_of),
    }


_TEMPORAL_CANDIDATE_BATCH_SIZE = 512


def _temporal_anchors(section, at):
    """Rank narrow facts without reading Post content or qualification state."""
    model = Event if section == "calendar" else Opportunity
    fields = ("start_value", "start_precision", "end_value", "end_precision") if section == "calendar" else ("open_value", "open_precision", "close_value", "close_precision")
    facts, anchors = {}, {}

    def link(post_id, fact):
        if post_id is None or fact["state"] in {"past", "closed", "cancelled"}:
            return
        previous = anchors.get(post_id)
        if previous is None or _fact_order(fact) < _fact_order(previous):
            anchors[post_id] = fact

    rows = model.objects.exclude(review_status="rejected").only("id", "source_post_id", "source_status", *fields).order_by("id")
    for row in rows.iterator(chunk_size=_TEMPORAL_CANDIDATE_BATCH_SIZE):
        check_read_deadline()
        fact = _temporal_timing_fact(row, section, as_of=at)
        facts[row.pk] = fact
        link(row.source_post_id, fact)
    if section == "calendar":
        evidence = EventEvidence.objects.exclude(event__review_status="rejected").order_by().values_list("event_id", "source_post_id")
        for event_id, post_id in evidence.iterator(chunk_size=_TEMPORAL_CANDIDATE_BATCH_SIZE):
            check_read_deadline()
            link(post_id, facts[event_id])
    return anchors


def _temporal_link_queries(section):
    if section == "calendar":
        return [Event.objects.exclude(review_status="rejected"), EventEvidence.objects.exclude(event__review_status="rejected")]
    return [Opportunity.objects.exclude(review_status="rejected")]


def _qualify_temporal_cohort(post_ids, public_query, signal_query, at, last, limit):
    """Finish a rank tie across batches before choosing its global top page."""
    public_sql, public_params = public_query
    signal_sql, signal_params = signal_query
    cursor_filter, cursor_params = "", []
    if last:
        last_fetch = datetime.fromtimestamp(-last[2], tz=UTC)
        cursor_filter = ' AND (p.fetched_at < %s OR (p.fetched_at = %s AND p.pk COLLATE "C" > %s COLLATE "C"))'
        cursor_params = [last_fetch, last_fetch, last[3]]
    selected = []
    for offset in range(0, len(post_ids), _TEMPORAL_CANDIDATE_BATCH_SIZE):
        check_read_deadline()
        batch = post_ids[offset:offset + _TEMPORAL_CANDIDATE_BATCH_SIZE]
        values = ",".join(["(%s)"] * len(batch))
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH linked_ids(pk) AS (VALUES {values})
                SELECT r.pk, r.fetched_at FROM (
                    SELECT p.pk, p.fetched_at FROM linked_ids ranked
                    CROSS JOIN LATERAL (
                        SELECT p.pk, p.fetched_at FROM ({public_sql}) p
                        WHERE p.pk=ranked.pk AND p.fetched_at <= %s {cursor_filter}
                        OFFSET 0
                    ) p
                    ORDER BY p.fetched_at DESC, p.pk COLLATE "C" OFFSET 0
                ) r
                WHERE EXISTS (SELECT 1 FROM ({signal_sql}) matched
                              WHERE matched.post_id=r.pk OFFSET 0)
                ORDER BY r.fetched_at DESC, r.pk COLLATE "C" LIMIT %s
                """,
                [*batch, *public_params, at, *cursor_params, *signal_params, limit + 1],
            )
            selected.extend(cursor.fetchall())
        selected.sort(key=lambda row: (-row[1].timestamp(), str(row[0])))
        del selected[limit + 1:]
    return dict(selected)


def _unlinked_temporal_candidates(section, signals, public_query, signal_query, at, last, limit, brands):
    """Bound the common recent case and complete sparse selections exactly."""
    public_sql, public_params = public_query
    signal_sql, signal_params = signal_query
    params = [*public_params, at]
    cursor_filter = ""
    if last and last[:2] == [2, 0]:
        last_fetch = datetime.fromtimestamp(-last[2], tz=UTC)
        cursor_filter = ' AND (p.fetched_at < %s OR (p.fetched_at = %s AND p.pk COLLATE "C" > %s COLLATE "C"))'
        params += [last_fetch, last_fetch, last[3]]
    recent_limit = 5000
    params.append(recent_limit)
    no_facts = []
    links = []
    for query in _temporal_link_queries(section):
        posts = query.filter(source_post_id__isnull=False).order_by().values("source_post_id")
        links.append(posts)
        sql, values = posts.query.sql_with_params()
        no_facts.append(f"r.pk NOT IN ({sql})")
        params.extend(values)
    params.extend(signal_params)
    params.append(limit + 1)
    rows = None
    if brands is None or len(brands) > 2:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
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
                """, params,
            )
            rows = cursor.fetchall()
    if rows is not None:
        unknown = [(pk, fetched) for pk, fetched, _ in rows if pk is not None]
        if len(unknown) > limit or rows[0][2] < recent_limit:
            return dict(unknown)
    eligible = public_posts().filter(pk__in=signals.values("post_id"), fetched_at__lte=at).annotate(_sort_id=Collate("tweet_id", "C"))
    for posts in links:
        eligible = eligible.exclude(pk__in=posts)
    if last and last[:2] == [2, 0]:
        eligible = eligible.filter(Q(fetched_at__lt=last_fetch) | Q(fetched_at=last_fetch, _sort_id__gt=last[3]))
    return dict(eligible.order_by("-fetched_at", "_sort_id").values_list("pk", "fetched_at")[:limit + 1])


def _bounded_temporal_candidates(section, signals, brands, at, last, limit):
    """Qualify ordered fact cohorts before hydrating only the selected cards."""
    if connection.vendor != "postgresql":
        return None
    with connection.cursor() as cursor:
        cursor.execute("SHOW transaction_isolation")
        if cursor.fetchone()[0] not in {"repeatable read", "serializable"}:
            return None
    if brands == []:
        return {}, {}
    if last and (len(last) != 4 or last[0] not in (0, 1, 2)):
        return None
    try:
        public_query = public_posts().order_by().values("pk", "fetched_at").query.sql_with_params()
        signal_query = signals.order_by().values("post_id").query.sql_with_params()
    except EmptyResultSet:
        return {}, {}
    anchors = _temporal_anchors(section, at)
    cohorts = {}
    for post_id, anchor in anchors.items():
        cohorts.setdefault(_fact_order(anchor)[:2], []).append(post_id)
    candidates, facts, ranked = {}, {}, []
    for prefix, post_ids in sorted(cohorts.items()):
        check_read_deadline()
        if last and list(prefix) < last[:2]:
            continue
        matched = _qualify_temporal_cohort(post_ids, public_query, signal_query, at, last if last and list(prefix) == last[:2] else None, limit)
        for pk, fetched in matched.items():
            candidates[pk], facts[pk] = fetched, [anchors[pk]]
            ranked.append(([*prefix, -fetched.timestamp(), str(pk)], pk))
        if prefix[0] < 2 and len(ranked) > limit:
            break
    if len(ranked) <= limit or (ranked and ranked[-1][0][0] == 2):
        unknown = _unlinked_temporal_candidates(section, signals, public_query, signal_query, at, last, limit, brands)
        for pk, fetched in unknown.items():
            candidates[pk], facts[pk] = fetched, []
            ranked.append(([2, 0, -fetched.timestamp(), str(pk)], pk))
    ranked.sort()
    selected = [pk for _, pk in ranked[:limit + 1]]
    return {pk: candidates[pk] for pk in selected}, {pk: facts[pk] for pk in selected}


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
        if section == "moving" else None
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
        candidates, _ = bounded
    facts = bounded[1] if bounded is not None else (
        temporal_facts(list(fact_ids), section, as_of=at)
        if section in {"calendar", "free"}
        else {}
    )
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
    if bounded is not None:
        facts = temporal_facts([pk for _, pk in page], section, as_of=at)
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
            {
                "version": 2, "filters_sha256": _filter_fingerprint(filters),
                "as_of": at.isoformat(), "last": page[-1][0],
            },
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
