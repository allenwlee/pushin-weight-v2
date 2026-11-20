"""Exact grouped Each chart facts from saved history and its live remainder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import DatabaseError, connection, transaction

from core.materializations import MaterializationDefinition, sqlstate
from monitor.each_request_budget import EachChartUnavailable, EachRequestBudget
from x_monitor.translator import TRUSTED_SOURCE_LANGS

__all__ = ["EACH_FACTS", "EachChartUnavailable", "read_each_fact_groups"]

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
    refresh_timeout="90s",
    advance_barrier=True,
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


def _read_groups(brand_id, tab, start, end, bucket, tz, at):
    columns = SIGNATURE_COLUMNS[tab]
    day = at.astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT CASE WHEN COALESCE((SELECT relispopulated FROM pg_class
                         WHERE oid=to_regclass('each_brand_post_facts')), FALSE)
                         AND published_generation IS NOT NULL
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
    boundary = max(start, min(boundary, end))
    projected = ", ".join(("created_at", *columns))
    live = (
        "SELECT "
        + projected
        + " FROM each_brand_post_facts_source WHERE brand_id=%s AND created_at >= %s AND created_at < %s"
    )
    data_params = [brand_id, boundary, end]
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
             'THEN lower(trim(f.lang)) END) COLLATE "C" AS effective_language')
        ]
        signature_params = [list(TRUSTED_SOURCE_LANGS)]
        output_columns = ["effective_language"]
    elif tab == "audience_topics":
        selected = [
            'f.state_taxonomy_version COLLATE "C" AS state_taxonomy_version',
            "(SELECT revision FROM audience_topic_schemes WHERE key='ai_audience_topics/v1') AS audience_revision",
            """ARRAY(SELECT c.key::text COLLATE "C" FROM unnest(f.audience_topic_edges) edge
                JOIN audience_topic_concepts c ON c.id=split_part(edge,':',2)::bigint
                WHERE c.scheme_key='ai_audience_topics/v1'
                AND split_part(edge,':',1)::int=(SELECT revision FROM audience_topic_schemes WHERE key='ai_audience_topics/v1')
                ORDER BY c.key COLLATE "C") AS audience_topic_keys""",
        ]
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
                    [brand_id, start, end, bucket_value, *signature_params]
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
