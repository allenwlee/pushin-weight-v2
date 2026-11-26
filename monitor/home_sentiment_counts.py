"""Daily single-brand sentiment counts from valid saved facts and live changes."""

from django.db import DatabaseError, connection, transaction

from core.classification_contract import COMPATIBLE_TAXONOMY_VERSIONS, CONTRACT_VERSION
from core.materializations import sqlstate
from monitor.each_chart_facts import each_publication_details

_UNCLASSIFIED = "__unclassified__"
_FIELDS = (
    "post_id, brand_id, created_at, state_present, state_contract_version, "
    "state_taxonomy_version, state_outcome, state_sentiment"
)


def read_home_sentiment_counts(*, brand, sentiments, start, end, at, timezone_name,
                               promotion_mode, legacy_mode):
    """Return daily counts, or None when the saved prefix cannot safely be used.

    The caller limits this to a single selected brand and no other classification
    filters. The state read and both fact sources share one database snapshot.
    """
    if (connection.vendor != "postgresql" or connection.in_atomic_block
            or not isinstance(promotion_mode, str)
            or promotion_mode not in {"off", "only", "any"}
            or legacy_mode not in {None, "off", "only", "any"}):
        return None
    selected = [value for value in sentiments if value != _UNCLASSIFIED]
    include_unclassified = _UNCLASSIFIED in sentiments
    if not selected and not include_unclassified:
        return []

    conditions = []
    if selected:
        conditions.append("(recognized AND f.state_sentiment = ANY(cfg.selected))")
        # A missing state is already covered by the unclassified selection.
        # Otherwise preserve the existing grouped legacy ambiguity rule.
        if not include_unclassified:
            conditions.append("""(NOT f.state_present AND EXISTS (
                SELECT 1 FROM posts_brands_signals s
                WHERE s.post_id=f.post_id AND s.brand_id=f.brand_id
                  AND s.sentiment IS NOT NULL
                GROUP BY s.post_id,s.brand_id
                HAVING count(DISTINCT s.sentiment)=1
                   AND count(DISTINCT s.sentiment) FILTER
                       (WHERE s.sentiment = ANY(cfg.selected))=1
            ))""")
    if include_unclassified:
        conditions.append("NOT COALESCE(recognized AND f.state_outcome='classified', FALSE)")

    exclusions = []
    for table, mode in (
        ("posts_untracked_brand_promotions", promotion_mode),
        ("posts_unsanctioned_flags", "off" if legacy_mode is None and promotion_mode == "off" else legacy_mode),
    ):
        if mode in {"off", "only"}:
            negate = "NOT " if mode == "off" else ""
            exclusions.append(f"{negate}EXISTS (SELECT 1 FROM {table} x WHERE x.post_id=f.post_id)")

    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            boundary, dirty_ids = each_publication_details(cursor, start, end, at)
            if boundary <= start:
                return None
            saved_filter = '' if dirty_ids is None else ' AND NOT (post_id COLLATE "C" = ANY(%s::text[] COLLATE "C"))'
            dirty_source = ''
            if dirty_ids:
                dirty_source = f'''
                    UNION ALL
                    SELECT changed.* FROM (
                        SELECT DISTINCT item COLLATE "C" AS post_id FROM unnest(%s::text[]) item
                    ) dirty CROSS JOIN LATERAL (
                        SELECT {_FIELDS} FROM each_brand_post_facts_source
                        WHERE brand_id=%s AND created_at >= %s AND created_at < %s
                          AND post_id=dirty.post_id COLLATE "default"
                          AND post_id COLLATE "C"=dirty.post_id COLLATE "C" OFFSET 0
                    ) changed
                '''
            sql = f"""
                WITH cfg AS MATERIALIZED (
                    SELECT %s::text AS contract, %s::text[] AS taxonomy,
                           %s::text[] AS selected
                ), facts AS (
                    SELECT {_FIELDS} FROM each_brand_post_facts
                    WHERE brand_id=%s AND created_at >= %s AND created_at < %s {saved_filter}
                    UNION ALL
                    SELECT {_FIELDS} FROM each_brand_post_facts_source
                    WHERE brand_id=%s AND created_at >= %s AND created_at < %s
                    {dirty_source}
                ), resolved AS (
                    SELECT f.*, (f.state_contract_version=cfg.contract
                           AND f.state_taxonomy_version=ANY(cfg.taxonomy)) AS recognized
                    FROM facts f CROSS JOIN cfg
                )
                SELECT (f.created_at AT TIME ZONE %s)::date AS day, count(*)::bigint
                FROM resolved f CROSS JOIN cfg
                WHERE ({' OR '.join(conditions)})
                {''.join(' AND ' + item for item in exclusions)}
                GROUP BY 1
            """
            cursor.execute(sql, [
                CONTRACT_VERSION, list(COMPATIBLE_TAXONOMY_VERSIONS), selected,
                brand, start, boundary, *([] if dirty_ids is None else [dirty_ids]),
                brand, boundary, end,
                *([dirty_ids, brand, start, boundary] if dirty_ids else []), timezone_name,
            ])
            return [{"brand_id": brand, "day": day, "count": count}
                    for day, count in cursor.fetchall()]
    except DatabaseError as error:
        if sqlstate(error) in {"42P01", "55000", "55P03"}:
            return None
        raise
