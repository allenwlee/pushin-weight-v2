"""Exact grouped Each chart facts from saved history and its live remainder."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import DatabaseError, connection, transaction

from core.materializations import MaterializationDefinition, sqlstate
from monitor.each_request_budget import EachChartUnavailable, EachRequestBudget
from x_monitor.translator import SOURCE_SCRIPT_TAGS, TRUSTED_SOURCE_LANGS

__all__ = ["EACH_FACTS", "EachChartUnavailable", "each_publication_boundary", "read_each_fact_groups"]

EACH_FACTS = MaterializationDefinition(
    dataset_key="each.brand_post_facts.v1",
    relation="each_brand_post_facts",
    source_tables=(
        "brands",
        "posts",
        "posts_brands",
        "posts_brands_classification_states",
        "posts_brands_signals",
        "posts_brands_product_labels",
        "posts_brands_audience_topics",
        "posts_brands_geopolitical_modes",
        "posts_untracked_brand_promotions",
    ),
    lock_id=726_514_095,
    cutoff_sql="date_trunc('day', transaction_timestamp(), 'UTC') - interval '1 day'",
    # Concurrent refresh includes the source SELECT, diff, and index updates.
    # A three-minute attempt timed out under live load. The five-minute bound
    # can leave little room for the other work in the 15-minute interval.
    refresh_timeout="300s",
    bootstrap_timeout="300s",
    refresh_work_mem="8MB",
    advance_barrier=True,
    online_refresh=True,
    online_barrier_attempts=61,
    online_capability="each_facts_online_tracking_v1",
)
STATE_COLUMNS = ("state_contract_version", "state_taxonomy_version", "state_outcome")
SIGNATURE_COLUMNS = {
    "sentiment": (
        "state_present",
        "state_brand_id",
        *STATE_COLUMNS,
        "state_sentiment",
        "legacy_sentiment_brand_ids",
        "legacy_sentiment_values",
    ),
    "post_types": (*STATE_COLUMNS, "post_type_keys"),
    "product_labels": (*STATE_COLUMNS, "product_label_keys"),
    "audience_topics": ("state_taxonomy_version", "audience_topic_edges"),
    "geopolitical_modes": ("geopolitical_mode_versions", "geopolitical_mode_keys"),
    "untracked_brand_promotions": ("promotion_keys",),
    "lang": ("lang_detected", "lang"),
    "role": ("author_account_key",),
}


def each_publication_boundary(cursor, start, end, at):
    """Return the prefix whose saved facts are valid in the current snapshot."""
    day = at.astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)
    cursor.execute(
        """
            SELECT CASE WHEN COALESCE((SELECT relispopulated FROM pg_class
                         WHERE oid=to_regclass('each_brand_post_facts')), FALSE)
                         AND published_generation IS NOT NULL
                         AND cutoff IS NOT NULL
                         AND (source_generation=published_generation OR dirty_since IS NOT NULL)
                    THEN least(cutoff,%s::timestamptz,
                         CASE WHEN source_generation=published_generation THEN cutoff ELSE dirty_since END)
                    END
            FROM materialization_state WHERE dataset_key=%s
        """,
        [day, EACH_FACTS.dataset_key],
    )
    publication = cursor.fetchone()
    boundary = publication[0] if publication and publication[0] is not None else start
    return max(start, min(boundary, end))


def _read_groups(brand_id, tab, start, end, bucket, tz, at):
    columns = SIGNATURE_COLUMNS[tab]
    with connection.cursor() as cursor:
        boundary = each_publication_boundary(cursor, start, end, at)
    projected = ", ".join(("created_at", *columns))
    if tab == "sentiment":
        # The source view looks the Post up again and always reads legacy
        # signals. The category reader only consults those signals when there
        # is no state for the exact requested brand spelling.
        live = """
            SELECT p.created_at, s.post_id IS NOT NULL AS state_present,
                   s.brand_id::text AS state_brand_id,
                   s.contract_version AS state_contract_version,
                   s.taxonomy_version AS state_taxonomy_version,
                   s.outcome AS state_outcome, s.sentiment::text AS state_sentiment,
                   COALESCE(legacy.brand_ids, ARRAY[]::text[]) AS legacy_sentiment_brand_ids,
                   COALESCE(legacy.sentiments, ARRAY[]::text[]) AS legacy_sentiment_values
            FROM posts p
            CROSS JOIN LATERAL (
                SELECT post_id, brand_id FROM posts_brands
                WHERE post_id=p.tweet_id AND brand_id=%s OFFSET 0
            ) pb
            LEFT JOIN posts_brands_classification_states s
              ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
            LEFT JOIN LATERAL (
                SELECT array_agg(v.brand_id ORDER BY v.brand_id COLLATE "C") AS brand_ids,
                       array_agg(v.sentiment ORDER BY v.brand_id COLLATE "C") AS sentiments
                FROM (
                    SELECT g.brand_id::text COLLATE "C" AS brand_id,
                           CASE WHEN count(DISTINCT NULLIF(g.sentiment::text, '') COLLATE "C")=1
                                THEN min(NULLIF(g.sentiment::text, '') COLLATE "C") END AS sentiment
                    FROM posts_brands_signals g
                    WHERE (s.post_id IS NULL OR s.brand_id::text COLLATE "C" <> %s COLLATE "C")
                      AND g.post_id=pb.post_id AND g.brand_id=pb.brand_id
                    GROUP BY g.brand_id::text COLLATE "C"
                ) v
            ) legacy ON true
            WHERE p.created_at >= %s AND p.created_at < %s
        """
        live_brand_params = [brand_id, brand_id]
    else:
        live = (
            "SELECT "
            + ", ".join("f." + column for column in ("created_at", *columns))
            + " FROM posts p CROSS JOIN LATERAL (SELECT " + projected
            + " FROM each_brand_post_facts_source WHERE post_id=p.tweet_id AND brand_id=%s OFFSET 0) f"
            + " WHERE p.created_at >= %s AND p.created_at < %s"
        )
        live_brand_params = [brand_id]

    def live_params(lower):
        return [*live_brand_params, lower, end]

    data_params = live_params(boundary)
    if boundary > start:
        sources = (
            "SELECT "
            + projected
            + " FROM each_brand_post_facts WHERE brand_id=%s AND created_at >= %s AND created_at < %s UNION ALL "
            + live
        )
        data_params = [brand_id, start, boundary, *data_params]
    else:
        sources = live
    bucket_sql = (
        "(f.created_at AT TIME ZONE %s)::date"
        if bucket == "day"
        else "floor(extract(epoch FROM (f.created_at - %s::timestamptz))/300)::int"
    )
    bucket_value = tz if bucket == "day" else start
    joins = ""
    selected = []
    signature_params = []
    output_columns = list(columns)
    if tab == "role":
        joins = " LEFT JOIN brands_accounts ba ON ba.account_key=f.author_account_key AND ba.brand_id=%s LEFT JOIN accounts a ON a.account_key=ba.account_key AND a.data_source_id='x'"
        selected = [
            'CASE WHEN a.account_key IS NOT NULL THEN ba.role_id::text END COLLATE "C" AS role_key'
        ]
        output_columns = ["role_key"]
    elif tab == "lang":
        # Match _post_language_expression exactly: PostgreSQL trim removes
        # spaces, not arbitrary Python whitespace, and detected text owns NULLIF.
        selected = [
            ("COALESCE(NULLIF(f.lang_detected, ''), CASE WHEN lower(trim(f.lang)) = ANY(%s) "
             'THEN lower(trim(f.lang)) ELSE (%s::jsonb ->> lower(trim(f.lang))) END) COLLATE "C" AS effective_language')
        ]
        signature_params = [list(TRUSTED_SOURCE_LANGS), json.dumps(SOURCE_SCRIPT_TAGS)]
        output_columns = ["effective_language"]
    elif tab == "audience_topics":
        # Resolve current concept keys after the first grouping. Historical
        # facts retain typed identity, so renames and revision changes remain
        # visible without rebuilding the saved facts.
        output_columns = [
            "state_taxonomy_version",
            "audience_revision",
            "audience_topic_keys",
        ]
    else:
        for name in columns:
            suffix = "" if name == "state_present" else ' COLLATE "C"'
            selected.append(f"f.{name}{suffix} AS {name}")
    select = ", ".join(
        [bucket_sql + " AS bucket", *selected, "count(*)::bigint AS count"]
    )
    groups = ", ".join(str(i) for i in range(1, len(selected) + 2))
    query = f"WITH facts AS ({sources}) SELECT {select} FROM facts f{joins} GROUP BY {groups}"
    if tab == "audience_topics":
        # MATERIALIZED prevents the concept lookup from moving back below the
        # raw grouping. Decode once per distinct edge signature, shared across
        # buckets and state versions, then carry each raw group's multiplicity.
        query = f"""
            WITH facts AS ({sources}),
            raw_groups AS MATERIALIZED (
                SELECT {bucket_sql} AS bucket,
                       f.state_taxonomy_version COLLATE "C" AS state_taxonomy_version,
                       f.audience_topic_edges COLLATE "C" AS audience_topic_edges,
                       count(*)::bigint AS count
                FROM facts f GROUP BY 1, 2, 3
            ),
            audience_signatures AS MATERIALIZED (
                SELECT audience_topic_edges FROM raw_groups GROUP BY 1
            ),
            audience_scheme AS MATERIALIZED (
                SELECT (SELECT revision FROM audience_topic_schemes
                        WHERE key='ai_audience_topics/v1') AS revision
            ),
            audience_decoded AS MATERIALIZED (
                SELECT signatures.audience_topic_edges,
                       scheme.revision AS audience_revision,
                       ARRAY(
                           SELECT c.key::text COLLATE "C"
                           FROM unnest(signatures.audience_topic_edges) edge
                           JOIN audience_topic_concepts c
                             ON c.id=split_part(edge, ':', 2)::bigint
                           WHERE c.scheme_key='ai_audience_topics/v1'
                             AND split_part(edge, ':', 1)::int=scheme.revision
                           ORDER BY c.key COLLATE "C"
                       ) AS audience_topic_keys
                FROM audience_signatures signatures CROSS JOIN audience_scheme scheme
            )
            SELECT raw.bucket, raw.state_taxonomy_version,
                   decoded.audience_revision, decoded.audience_topic_keys,
                   sum(raw.count)::bigint AS count
            FROM raw_groups raw JOIN audience_decoded decoded
              ON raw.audience_topic_edges = decoded.audience_topic_edges
            GROUP BY 1, 2, 3, 4
        """
    params = [*data_params, bucket_value, *signature_params] + ([brand_id] if tab == "role" else [])
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(query, params)
            return [
                dict(zip(("bucket", *output_columns, "count"), row, strict=True))
                for row in cursor.fetchall()
            ]
    except DatabaseError as error:
        if boundary > start and sqlstate(error) in {"42P01", "55000"}:
            # An unavailable saved relation must not poison the shared snapshot.
            fallback = query.replace(sources, live)
            with connection.cursor() as cursor:
                cursor.execute(
                    fallback,
                    [*live_params(start), bucket_value, *signature_params]
                    + ([brand_id] if tab == "role" else []),
                )
                return [
                    dict(zip(("bucket", *output_columns, "count"), row, strict=True))
                    for row in cursor.fetchall()
                ]
        raise


def read_each_fact_groups(
    brand_id: str,
    tab: str,
    start: datetime,
    end: datetime,
    bucket: str,
    tz: str,
    at: datetime,
) -> list[dict[str, Any]]:
    """Read health plus grouped data in one consistent snapshot.

    The fixed signature list is code-defined; no identifier comes from a request.
    A surrounding request owns its deadline, including nested reference ranking.
    """
    if tab not in SIGNATURE_COLUMNS or bucket not in {"day", "minute"}:
        raise ValueError("Unsupported Each facts grouping")
    with EachRequestBudget() as budget, budget.query_scope():
        owns_snapshot = not connection.in_atomic_block
        with transaction.atomic():
            if owns_snapshot:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
            result = _read_groups(brand_id, tab, start, end, bucket, tz, at)
            budget.remaining_ms()
            return result
