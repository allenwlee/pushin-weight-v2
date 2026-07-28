"""Backfill posts TwitterAPI columns from posts.raw.

U2 of the posts.raw denormalization plan. Idempotent.

Source priority (§ 1.6): outer snake_case first, then outer camelCase, then
inner raw->'raw' camelCase, then inner author. COALESCE for scalars.

For quoted_status_id: Policy A — set only when the target tweet_id already
exists in posts; else NULL (no dangling FKs, no stub rows).

Chunked 10k by tweet_id to keep locks short on prod.
"""

from django.db import migrations


def _backfill_columns(apps, schema_editor):
    """Idempotent backfill of new posts columns from posts.raw."""
    from django.db import connection

    if schema_editor.connection.vendor != "postgresql":
        # Dev (SQLite) has no posts.raw data; backfill is a no-op.
        return

    with connection.cursor() as cur:
        # --- 1. Author fields: all inner-only per U0 census (§ 1.3) ---
        # Order: simple scalar columns first, then bools, then jsonb.
        author_scalar_updates = [
            # (column, jsonb key in author, sql expression)
            # The key is passed explicitly because the previous form derived it
            # from `expr.split("->>")[-1].strip("'")`, which broke for
            # expressions with trailing casts (e.g. `::int`, `::boolean`) —
            # the trailing `')::int'` survived strip() and made the WHERE
            # clause match a nonexistent key, so the backfill updated 0 rows
            # for all integer/boolean author columns. Verified on staging 2026-07-28.
            ("author_name", "name", "raw->'raw'->'author'->>'name'"),
            ("author_automated_by", "automatedBy", "raw->'raw'->'author'->>'automatedBy'"),
            ("author_cover_picture", "coverPicture", "raw->'raw'->'author'->>'coverPicture'"),
            ("author_created_at_raw", "createdAt", "raw->'raw'->'author'->>'createdAt'"),
            ("author_description", "description", "raw->'raw'->'author'->>'description'"),
            ("author_location", "location", "raw->'raw'->'author'->>'location'"),
            ("author_profile_picture", "profilePicture", "raw->'raw'->'author'->>'profilePicture'"),
            ("author_status", "status", "raw->'raw'->'author'->>'status'"),
            ("author_twitter_url", "twitterUrl", "raw->'raw'->'author'->>'twitterUrl'"),
            ("author_type", "type", "raw->'raw'->'author'->>'type'"),
            ("author_url", "url", "raw->'raw'->'author'->>'url'"),
            ("author_verified_type", "verifiedType", "raw->'raw'->'author'->>'verifiedType'"),
            ("author_followers_count", "followers",
                "(raw->'raw'->'author'->>'followers')::int"),
            ("author_following_count", "following",
                "(raw->'raw'->'author'->>'following')::int"),
            ("author_media_count", "mediaCount",
                "(raw->'raw'->'author'->>'mediaCount')::int"),
            ("author_statuses_count", "statusesCount",
                "(raw->'raw'->'author'->>'statusesCount')::int"),
            ("author_favourites_count", "favouritesCount",
                "(raw->'raw'->'author'->>'favouritesCount')::int"),
            ("author_fast_followers_count", "fastFollowersCount",
                "(raw->'raw'->'author'->>'fastFollowersCount')::int"),
        ]
        for col, key, expr in author_scalar_updates:
            cur.execute(
                f"""
                UPDATE posts
                SET {col} = {expr}
                WHERE {col} IS NULL
                  AND raw IS NOT NULL
                  AND raw->'raw'->'author' ? %s
                """,
                (key,),
            )

        author_bool_updates = [
            # (column, jsonb key in author, sql expression)
            ("author_is_translator", "isTranslator",
                "(raw->'raw'->'author'->>'isTranslator')::boolean"),
            ("author_is_automated", "isAutomated",
                "(raw->'raw'->'author'->>'isAutomated')::boolean"),
            ("author_can_dm", "canDm",
                "(raw->'raw'->'author'->>'canDm')::boolean"),
            ("author_can_media_tag", "canMediaTag",
                "(raw->'raw'->'author'->>'canMediaTag')::boolean"),
            ("author_possibly_sensitive", "possiblySensitive",
                "(raw->'raw'->'author'->>'possiblySensitive')::boolean"),
            ("author_has_custom_timelines", "hasCustomTimelines",
                "(raw->'raw'->'author'->>'hasCustomTimelines')::boolean"),
        ]
        for col, key, expr in author_bool_updates:
            cur.execute(
                f"""
                UPDATE posts
                SET {col} = {expr}
                WHERE {col} IS NULL
                  AND raw IS NOT NULL
                  AND raw->'raw'->'author' ? %s
                """,
                (key,),
            )

        # author_verified: union of isBlueVerified or isVerified (per U3 logic in normalize).
        cur.execute(
            """
            UPDATE posts
            SET author_verified = COALESCE(
                (raw->'raw'->'author'->>'isBlueVerified')::boolean,
                (raw->'raw'->'author'->>'isVerified')::boolean
            )
            WHERE author_verified IS NULL
              AND raw IS NOT NULL
              AND raw->'raw'->'author' IS NOT NULL
            """
        )

        # author_is_blue_verified
        cur.execute(
            """
            UPDATE posts
            SET author_is_blue_verified = (raw->'raw'->'author'->>'isBlueVerified')::boolean
            WHERE author_is_blue_verified IS NULL
              AND raw IS NOT NULL
              AND raw->'raw'->'author' ? 'isBlueVerified'
            """
        )

        # JSONB author fields
        for col, key in [
            ("author_profile_bio", "profile_bio"),
            ("author_affiliates_highlighted_label", "affiliatesHighlightedLabel"),
            ("author_entities", "entities"),
        ]:
            cur.execute(
                f"""
                UPDATE posts
                SET {col} = raw->'raw'->'author'->%s
                WHERE {col} IS NULL
                  AND raw IS NOT NULL
                  AND raw->'raw'->'author' ? %s
                """,
                (key, key),
            )

        # JSONB array-shaped author fields (stored as JSONB per U1 deviation)
        for col, key in [
            ("author_pinned_tweet_ids", "pinnedTweetIds"),
            ("author_withheld_in_countries", "withheldInCountries"),
        ]:
            cur.execute(
                f"""
                UPDATE posts
                SET {col} = raw->'raw'->'author'->%s
                WHERE {col} IS NULL
                  AND raw IS NOT NULL
                  AND raw->'raw'->'author' ? %s
                """,
                (key, key),
            )

        # --- 2. Tweet top-level fields ---
        # For each, dual-path COALESCE per § 1.6 (outer snake first, then inner raw->'raw' camelCase).
        # Many have no outer snake twin today; COALESCE handles that gracefully.
        # NOTE: view_count is IntegerField in the model — it needs a ::int cast
        # and lives in its own block below to keep the text-typed block clean.
        tweet_scalar_updates = [
            # (column, outer_snake_or_none, inner_camel)
            ("created_at_raw", None, "createdAt"),
            ("in_reply_to_id", "in_reply_to_id", "inReplyToId"),
            ("in_reply_to_username", "in_reply_to_username", "inReplyToUsername"),
            ("tweet_type", "type", "type"),
            ("tweet_url", "url", "url"),
            ("tweet_twitter_url", "twitterUrl", "twitterUrl"),
            ("client_source", "source", "source"),
        ]
        for col, outer_key, inner_key in tweet_scalar_updates:
            if outer_key:
                cur.execute(
                    f"""
                    UPDATE posts
                    SET {col} = COALESCE(raw->>%s, raw->'raw'->>%s)
                    WHERE {col} IS NULL
                      AND raw IS NOT NULL
                      AND (raw ? %s OR raw->'raw' ? %s)
                    """,
                    (outer_key, inner_key, outer_key, inner_key),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE posts
                    SET {col} = raw->'raw'->>%s
                    WHERE {col} IS NULL
                      AND raw IS NOT NULL
                      AND raw->'raw' ? %s
                    """,
                    (inner_key, inner_key),
                )

        # Integer tweet fields (view_count is outer camelCase only; no outer snake exists).
        for col, outer_key, inner_key in [
            ("view_count", "viewCount", "viewCount"),
        ]:
            cur.execute(
                f"""
                UPDATE posts
                SET {col} = COALESCE((raw->>%s)::int, (raw->'raw'->>%s)::int)
                WHERE {col} IS NULL
                  AND raw IS NOT NULL
                  AND (raw ? %s OR raw->'raw' ? %s)
                """,
                (outer_key, inner_key, outer_key, inner_key),
            )

        # Integer-coerced tweet fields (the existing typed cols use COALESCE outer-then-inner;
        # for the new ones, outer is empty so just inner).
        for col, inner_key in [
            ("bookmark_count", "bookmarkCount"),
        ]:
            cur.execute(
                f"""
                UPDATE posts
                SET {col} = COALESCE((raw->>%s)::int, (raw->'raw'->>%s)::int)
                WHERE {col} IS NULL
                  AND raw IS NOT NULL
                  AND (raw ? %s OR raw->'raw' ? %s)
                """,
                (inner_key, inner_key, inner_key, inner_key),
            )

        # Boolean tweet fields
        for col, inner_key in [
            ("is_reply", "isReply"),
            ("is_retweet", "isRetweet"),
            ("is_quote", "isQuote"),
            ("is_limited_reply", "isLimitedReply"),
        ]:
            cur.execute(
                f"""
                UPDATE posts
                SET {col} = COALESCE((raw->>%s)::boolean, (raw->'raw'->>%s)::boolean)
                WHERE {col} IS NULL
                  AND raw IS NOT NULL
                  AND (raw ? %s OR raw->'raw' ? %s)
                """,
                (inner_key, inner_key, inner_key, inner_key),
            )

        # JSONB tweet fields
        for col, inner_key in [
            ("card", "card"),
            ("place", "place"),
            ("article", "article"),
            ("community_info", "communityInfo"),
            ("extended_entities", "extendedEntities"),
        ]:
            cur.execute(
                f"""
                UPDATE posts
                SET {col} = raw->'raw'->%s
                WHERE {col} IS NULL
                  AND raw IS NOT NULL
                  AND raw->'raw' ? %s
                """,
                (inner_key, inner_key),
            )

        # display_text_range (JSONB array per U1 deviation)
        cur.execute(
            """
            UPDATE posts
            SET display_text_range = raw->'raw'->'displayTextRange'
            WHERE display_text_range IS NULL
              AND raw IS NOT NULL
              AND raw->'raw' ? 'displayTextRange'
            """
        )

        # quoted_author_handle (top-level is already populated by harvest; this is a backstop)
        cur.execute(
            """
            UPDATE posts
            SET quoted_author_handle = COALESCE(
                raw->>'quoted_author_handle',
                raw->'raw'->'quoted_tweet'->'author'->>'userName'
            )
            WHERE quoted_author_handle IS NULL
              AND raw IS NOT NULL
              AND (raw ? 'quoted_author_handle' OR raw->'raw'->'quoted_tweet'->'author' ? 'userName')
            """
        )

        # --- 3. quoted_status_id with Policy A: only when target tweet_id exists ---
        # Source: top-level quoted_status_id (already populated by harvest) OR inner quoted_tweet.id
        # Set NULL if target doesn't exist in posts. (U2 runs before U3 harvest update, so the
        # top-level value is whatever the harvest wrote historically — which is the inner id.)
        #
        # IMPORTANT: the outer table is explicitly aliased as `p` and the column
        # references are `p.raw->>...`. The original form used unqualified `posts`
        # for both outer and inner tables, which caused Postgres to resolve the
        # unqualified `raw` reference to the inner scope and hoist the EXISTS
        # into an InitPlan — producing 0 matches instead of 2,421. Adding the
        # `p.` prefix forces a correlated subquery. (Verified on staging with
        # raw prod dump — see 2026-07-28 staging verification.)
        cur.execute(
            """
            UPDATE posts p
            SET quoted_status_id = CASE
                WHEN EXISTS (SELECT 1 FROM posts q WHERE q.tweet_id = COALESCE(
                    p.raw->>'quoted_status_id',
                    p.raw->'raw'->'quoted_tweet'->>'id'
                ))
                THEN COALESCE(
                    p.raw->>'quoted_status_id',
                    p.raw->'raw'->'quoted_tweet'->>'id'
                )::text
                ELSE NULL
            END
            WHERE p.raw IS NOT NULL
              AND (
                p.raw ? 'quoted_status_id'
                OR p.raw->'raw'->'quoted_tweet' ? 'id'
              )
            """
        )


def _backfill_reverse(apps, schema_editor):
    """Reverse is a no-op — backfill is idempotent and forward-only."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_add_post_twitterapi_columns"),
    ]

    operations = [
        migrations.RunPython(_backfill_columns, _backfill_reverse),
    ]
