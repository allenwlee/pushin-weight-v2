"""Daily sentiment counts from valid saved facts and live changes."""

from django.db import DatabaseError, connection, transaction

from core.classification_contract import COMPATIBLE_TAXONOMY_VERSIONS, CONTRACT_VERSION
from core.materializations import MaterializationDefinition, sqlstate
from monitor.each_chart_facts import _publication_day, each_publication_details

_UNCLASSIFIED = "__unclassified__"
_MASK_CONTRACT = "stage1-v1"
_MASK_TAXONOMIES = (
    "stage1-taxonomy-v1", "stage1-taxonomy-v2", "stage1-taxonomy-v3", "stage1-taxonomy-v4",
)
_MASK_KEYS = frozenset({"positive", "negative", "neutral", "mixed", _UNCLASSIFIED})
HOME_SENTIMENT = MaterializationDefinition(
    dataset_key="home.post_sentiment_facts.v1",
    relation="home_post_sentiment_facts",
    source_tables=(
        "brands", "posts", "posts_brands", "posts_brands_classification_states",
        "posts_brands_signals", "posts_untracked_brand_promotions", "posts_unsanctioned_flags",
    ),
    lock_id=726_514_097,
    cutoff_sql="date_trunc('day', transaction_timestamp(), 'UTC') - interval '1 day'",
    refresh_timeout="300s", bootstrap_timeout="300s", refresh_work_mem="16MB",
    advance_barrier=True, online_refresh=True, online_barrier_attempts=61,
    online_capability="home_sentiment_masks_v1",
    online_dirty_ids_capability="each_facts_dirty_post_ids_v1",
    # A bounded number of changed Posts is cheaper to overlay live than to
    # rebuild the full summary every 15 minutes.
    dirty_refresh_threshold=384,
)
_MASK_FIELDS = "post_id,created_at,brands,unclassified,positive,negative,neutral,mixed,promotion_flag,legacy_flag"
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


def _mask_publication_details(cursor, start, end, at):
    """Read the summary and its dirty IDs from the caller's stable snapshot."""
    # Reading the state table before checking the capability also prevents a
    # concurrent reverse migration from removing its columns mid-request.
    cursor.execute(
        """SELECT source_generation,published_generation,cutoff,dirty_since,dirty_post_ids,
                  COALESCE((SELECT relispopulated FROM pg_class
                            WHERE oid=to_regclass('home_post_sentiment_facts')), FALSE),
                  to_regprocedure('home_sentiment_masks_v1()') IS NOT NULL
           FROM materialization_state WHERE dataset_key=%s""",
        [HOME_SENTIMENT.dataset_key],
    )
    state = cursor.fetchone()
    if not state:
        return start, None
    source, published, cutoff, dirty_since, dirty_ids, populated, capability = state
    if not capability or not populated or published is None or cutoff is None:
        return start, None
    if source != published and dirty_since is None:
        return start, None
    day = _publication_day(at)
    if dirty_ids is None and source != published:
        cutoff = min(cutoff, dirty_since)
    return max(start, min(cutoff, day, end)), dirty_ids


def read_home_multibrand_sentiment_counts(*, brands, output_brands, sentiments, start, end,
                                         at, timezone_name, promotion_mode, legacy_mode):
    """Count associated brands after a Post matches any selected-brand sentiment.

    A versioned compact projection preserves current, legacy, orphan and
    unclassified evidence. Unknown contracts and unsupported filter modes use
    the existing complete reader instead.
    """
    if (connection.vendor != 'postgresql' or connection.in_atomic_block
            or CONTRACT_VERSION != _MASK_CONTRACT
            or tuple(COMPATIBLE_TAXONOMY_VERSIONS) != _MASK_TAXONOMIES
            or not isinstance(promotion_mode, str)
            or promotion_mode not in {'off', 'only', 'any'}
            or legacy_mode not in {None, 'off', 'only', 'any'}
            or not set(sentiments) <= _MASK_KEYS):
        return None
    if brands == [] or not output_brands or not sentiments:
        return []
    selected = set(sentiments)
    unscoped = brands is None
    predicates = [
        f'cardinality(f.{key}) > 0' if unscoped else
        f'f.{key} COLLATE case_insensitive && cfg.scope'
        for key in ('positive', 'negative', 'neutral', 'mixed') if key in selected
    ]
    if _UNCLASSIFIED in selected:
        predicates.append('cardinality(f.unclassified) > 0' if unscoped else
                          'f.unclassified COLLATE case_insensitive && cfg.scope')
    flag_predicates = []
    for column, mode in (
        ('promotion_flag', promotion_mode),
        ('legacy_flag', 'off' if legacy_mode is None and promotion_mode == 'off' else legacy_mode),
    ):
        if mode == 'off':
            flag_predicates.append(f'NOT f.{column}')
        elif mode == 'only':
            flag_predicates.append(f'f.{column}')
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            boundary, dirty_ids = _mask_publication_details(cursor, start, end, at)
            if boundary <= start:
                return None
            dirty_cte = ''
            saved_filter = ''
            live = f'''SELECT {_MASK_FIELDS} FROM home_post_sentiment_facts_source
                       WHERE created_at >= %s AND created_at < %s'''
            dirty = ''
            if dirty_ids:
                dirty_cte = ''', dirty_ids AS MATERIALIZED (
                    SELECT DISTINCT item COLLATE "C" AS post_id FROM unnest(%s::text[]) item
                )'''
                saved_filter = ''' AND NOT EXISTS (
                    SELECT 1 FROM dirty_ids d WHERE d.post_id = saved.post_id COLLATE "C"
                )'''
                dirty = f''' UNION ALL SELECT changed.* FROM dirty_ids dirty CROSS JOIN LATERAL (
                    SELECT {_MASK_FIELDS} FROM home_post_sentiment_facts_source
                    WHERE post_id=dirty.post_id COLLATE "default"
                      AND post_id COLLATE "C"=dirty.post_id COLLATE "C"
                      AND created_at >= %s AND created_at < %s OFFSET 0
                ) changed'''
            sql = f'''
                WITH cfg AS MATERIALIZED (
                    SELECT %s::text[] COLLATE case_insensitive AS scope,
                           %s::varchar[] COLLATE case_insensitive AS outputs
                ){dirty_cte}, facts AS (
                    SELECT {_MASK_FIELDS} FROM home_post_sentiment_facts saved
                    WHERE saved.created_at >= %s AND saved.created_at < %s {saved_filter}
                    UNION ALL {live} {dirty}
                )
                SELECT b.nickname,(f.created_at AT TIME ZONE %s)::date,count(*)::bigint
                FROM facts f CROSS JOIN cfg CROSS JOIN LATERAL unnest(f.brands) associated(brand_id)
                JOIN brands b ON b.nickname=associated.brand_id COLLATE case_insensitive
                WHERE NOT b.is_sentinel AND b.nickname=ANY(cfg.outputs)
                  AND ({' OR '.join(predicates)})
                  {''.join(' AND ' + p for p in flag_predicates)}
                GROUP BY 1,2
            '''
            cursor.execute(sql, [brands or [], output_brands, *([dirty_ids] if dirty_ids else []),
                                 start, boundary,
                                 boundary, end,
                                 *([start, boundary] if dirty_ids else []), timezone_name])
            return [{'brand_id': brand, 'day': day, 'count': count}
                    for brand, day, count in cursor.fetchall()]
    except DatabaseError as error:
        # An older service can temporarily reconcile grants without knowing
        # these new views during a rolling deployment. Use the complete reader.
        if sqlstate(error) in {'42501', '42P01', '42703', '42883', '55000', '55P03'}:
            return None
        raise
