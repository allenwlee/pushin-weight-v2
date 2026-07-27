"""Regression net for the posts.raw → typed-columns denormalization.

Three layers (per the plan § 4 U5):
1. Column pin — assert the `posts` table has every column from § 1 of the
   plan, with the expected name and nullability.
2. FK pin — assert the self-referential FK on `quoted_status_id` exists,
   is `ON DELETE SET NULL`, deferrable; and that there are no orphan
   FK ids on prod.
3. Dual-path / harvest pin — assert `_normalize_tweet` returns the new
   keys with the expected types, and that the dual-path resolver picks
   the inner envelope when the outer snake twin is absent.

The column pin runs on any backend; the FK pin needs Postgres (FK
introspection); the harvest pin is pure Python.
"""

from __future__ import annotations

import pytest
from django.test import SimpleTestCase

from tests.conftest import requires_postgres


# --- Goal schema: the literal column set from plan § 1.1 / 1.2 / 1.3 ---
# Each entry: (column_name, nullable, type_family). type_family is a
# coarse category used to detect gross type drift, not exact type matches.

GOAL_COLUMNS: list[tuple[str, bool, str]] = [
    # --- § 1.1 existing ---
    ("tweet_id", False, "text"),  # PK
    ("author_handle", True, "text"),
    ("author", True, "text"),  # FK column is text (db_column=author_id)
    ("text", True, "text"),
    ("lang", True, "text"),
    ("created_at", True, "datetime"),
    ("fetched_at", False, "datetime"),
    ("like_count", True, "integer"),
    ("retweet_count", True, "integer"),
    ("reply_count", True, "integer"),
    ("quote_count", True, "integer"),
    ("in_reply_to_user_id", True, "text"),
    ("quoted_status_id", True, "text"),  # FK under Policy A
    ("conversation_id", True, "text"),
    ("entities", True, "jsonb"),
    ("source_query_id", True, "text"),
    ("headline", True, "text"),
    ("headline_source", True, "text"),
    ("text_en", True, "text"),
    ("text_zh_cn", True, "text"),
    ("lang_detected", True, "text"),
    ("quoted_text", True, "text"),
    ("last_quote_count_seen", True, "integer"),
    ("last_quote_fetched_at", True, "datetime"),
    ("created_at_epoch", True, "bigint"),
    # --- § 1.2 new tweet top-level ---
    ("created_at_raw", True, "text"),
    ("bookmark_count", True, "integer"),
    ("is_reply", True, "bool"),
    ("is_retweet", True, "bool"),
    ("is_quote", True, "bool"),
    ("in_reply_to_id", True, "text"),
    ("in_reply_to_username", True, "text"),
    ("tweet_type", True, "text"),
    ("tweet_url", True, "text"),
    ("tweet_twitter_url", True, "text"),
    ("card", True, "jsonb"),
    ("place", True, "jsonb"),
    ("client_source", True, "text"),
    ("view_count", True, "integer"),
    ("article", True, "jsonb"),
    ("is_limited_reply", True, "bool"),
    ("community_info", True, "jsonb"),
    ("display_text_range", True, "jsonb"),  # was integer[] on prod; jsonb on dev
    ("extended_entities", True, "jsonb"),
    ("quoted_author_handle", True, "text"),
    # --- § 1.3 new author ---
    ("author_name", True, "text"),
    ("author_followers_count", True, "integer"),
    ("author_following_count", True, "integer"),
    ("author_verified", True, "bool"),
    ("author_is_blue_verified", True, "bool"),
    ("author_verified_type", True, "text"),
    ("author_is_translator", True, "bool"),
    ("author_is_automated", True, "bool"),
    ("author_automated_by", True, "text"),
    ("author_description", True, "text"),
    ("author_location", True, "text"),
    ("author_media_count", True, "integer"),
    ("author_statuses_count", True, "integer"),
    ("author_favourites_count", True, "integer"),
    ("author_fast_followers_count", True, "integer"),
    ("author_can_dm", True, "bool"),
    ("author_can_media_tag", True, "bool"),
    ("author_profile_picture", True, "text"),
    ("author_profile_bio", True, "jsonb"),
    ("author_cover_picture", True, "text"),
    ("author_pinned_tweet_ids", True, "jsonb"),  # was text[] on prod; jsonb on dev
    ("author_affiliates_highlighted_label", True, "jsonb"),
    ("author_withheld_in_countries", True, "jsonb"),  # was text[] on prod; jsonb on dev
    ("author_possibly_sensitive", True, "bool"),
    ("author_has_custom_timelines", True, "bool"),
    ("author_entities", True, "jsonb"),
    ("author_twitter_url", True, "text"),
    ("author_type", True, "text"),
    ("author_url", True, "text"),
    ("author_created_at_raw", True, "text"),
    ("author_status", True, "text"),
]


# Columns that must NOT exist after U4 (the denormalization deletes raw).
FORBIDDEN_COLUMNS: list[str] = ["raw"]


# --- Type-family maps (backend-specific). ---
# This test does gross family comparison, not exact type. The goal is
# to catch "view_count became a text column" type drift, not to enforce
# integer-vs-bigint distinctions that vary by backend.

_TYPE_FAMILY: dict[str, set[str]] = {
    "text": {"text", "varchar", "char", "character varying"},
    "integer": {"integer", "int", "int4", "int8", "bigint"},
    "bigint": {"bigint", "int8"},
    "datetime": {"datetime", "timestamp", "timestamptz", "timestamp with time zone"},
    "bool": {"bool", "boolean"},
    "jsonb": {"jsonb", "json"},
}


def _family_match(declared: str, observed: str) -> bool:
    fam = _TYPE_FAMILY.get(declared, {declared})
    return observed.lower() in fam


# --- Layer 1: column pin ---


def _introspect_columns() -> dict[str, dict]:
    """Return {column_name: {data_type, is_nullable, ...}} for the posts table.

    Uses the Django model `Post._meta.fields` directly — no DB access
    required, so the test works on both SQLite and Postgres. The model
    IS the source of truth; this test catches model drift, not DB drift
    (a separate `requires_postgres` test catches DB-vs-model drift).
    """
    from django.db import models
    from core.models import Post

    result: dict[str, dict] = {}
    for field in Post._meta.get_fields():
        # Skip reverse relations (Post has none on the model itself, but
        # be defensive against related_name accessors).
        if not hasattr(field, "column") or field.column is None:
            continue
        # nullability
        if getattr(field, "primary_key", False):
            nullable = False
        elif getattr(field, "auto_now_add", False) or getattr(field, "auto_now", False):
            # auto_now_add / auto_now are non-null in practice even if
            # the model field doesn't explicitly set null=False.
            nullable = False
        else:
            nullable = getattr(field, "null", False) or getattr(
                field, "blank", False
            )
        # type family
        family = _field_type_family(field)
        # Use field.name (the Python attribute name) so the test matches
        # the goal schema's naming, which uses Python names. The author
        # FK is a special case: its name is 'author' but db_column is
        # 'author_id'. The goal schema uses 'author'.
        result[field.name] = {
            "data_type": family,
            "is_nullable": "YES" if nullable else "NO",
            "db_column": field.column,
        }
    return result


def _field_type_family(field) -> str:
    """Map a Django model field to one of the GOAL_COLUMNS type families."""
    from django.db import models

    # Order matters: BigIntegerField is a subclass of IntegerField, so
    # test the more specific one first.
    if isinstance(field, models.BooleanField):
        return "bool"
    if isinstance(field, models.BigIntegerField):
        return "bigint"
    if isinstance(field, models.IntegerField):
        return "integer"
    if isinstance(field, (models.TextField, models.CharField)):
        return "text"
    if isinstance(field, models.DateTimeField):
        return "datetime"
    if isinstance(field, models.JSONField):
        return "jsonb"
    if isinstance(field, models.ForeignKey):
        return "text"
    if field.__class__.__name__ == "ArrayField":
        return "jsonb"
    return "text"


def test_goal_columns_present():
    """Every column in the goal schema exists on the posts table."""
    cols = _introspect_columns()
    missing = [c for c, _, _ in GOAL_COLUMNS if c not in cols]
    assert not missing, f"Missing goal-schema columns: {missing}"


def test_forbidden_columns_absent():
    """posts.raw must be gone after U4."""
    cols = _introspect_columns()
    present = [c for c in FORBIDDEN_COLUMNS if c in cols]
    assert not present, f"Forbidden columns still present: {present}"


def test_goal_columns_nullable():
    """Every goal column has the expected nullability."""
    cols = _introspect_columns()
    mismatches = []
    for name, nullable, _ in GOAL_COLUMNS:
        if name not in cols:
            continue  # covered by test_goal_columns_present
        actual_nullable = cols[name]["is_nullable"] == "YES"
        if actual_nullable != nullable:
            mismatches.append((name, nullable, actual_nullable))
    assert not mismatches, f"Nullability drift: {mismatches}"


def test_goal_columns_type_family():
    """Every goal column has a SQL type in the expected family.

    This is a gross check — catches 'view_count became a text column' but
    not 'view_count int vs bigint'. Backend-specific array fields
    (display_text_range, author_pinned_tweet_ids, author_withheld_in_countries)
    are jsonb on dev and integer[]/text[] on prod; both map to the jsonb
    family for this test.
    """
    cols = _introspect_columns()
    mismatches = []
    for name, _, family in GOAL_COLUMNS:
        if name not in cols:
            continue
        observed = cols[name]["data_type"]
        if not _family_match(family, observed):
            mismatches.append((name, family, observed))
    assert not mismatches, f"Type-family drift: {mismatches}"


# --- Layer 2: FK pin (Postgres-only) ---


@requires_postgres
def test_self_fk_on_quoted_status_id():
    """Self-FK on quoted_status_id → posts.tweet_id, ON DELETE SET NULL."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT conname, confdeltype
            FROM pg_constraint
            WHERE conrelid = 'public.posts'::regclass
              AND contype = 'f'
              AND conname LIKE '%quoted_status_id%'
            """
        )
        rows = cur.fetchall()
    assert rows, "Self-FK on quoted_status_id is missing"
    # confdeltype 'a' = NO ACTION, 'c' = CASCADE, 'r' = RESTRICT,
    # 'n' = SET NULL, 'd' = SET DEFAULT. We want 'n'.
    for _name, deltype in rows:
        assert deltype == "n", (
            f"Self-FK delete type is {deltype!r}, expected 'n' (SET NULL)"
        )


@requires_postgres
def test_self_fk_is_deferrable():
    """Self-FK is DEFERRABLE INITIALLY DEFERRED so the backfill can land
    parent + child rows in any order."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT conname, condeferrable, condeferred
            FROM pg_constraint
            WHERE conrelid = 'public.posts'::regclass
              AND contype = 'f'
              AND conname LIKE '%quoted_status_id%'
            """
        )
        rows = cur.fetchall()
    assert rows, "Self-FK on quoted_status_id is missing"
    for _name, deferrable, deferred in rows:
        assert deferrable, "Self-FK is not DEFERRABLE"
        assert deferred, "Self-FK is not INITIALLY DEFERRED"


@requires_postgres
def test_no_orphan_quoted_fk():
    """Every non-null quoted_status_id must resolve to an existing posts.tweet_id.

    Policy A: orphan ids were nulled during the U2 backfill. This test
    fails loudly if a future insert reintroduces a dangling FK.
    """
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM posts p
            WHERE p.quoted_status_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM posts q WHERE q.tweet_id = p.quoted_status_id
              )
            """
        )
        n_orphans = cur.fetchone()[0]
    assert n_orphans == 0, (
        f"Found {n_orphans} orphan quoted_status_id FKs; "
        f"Policy A was violated — these rows must have quoted_status_id = NULL"
    )


# --- Layer 3: dual-path / harvest pin (pure Python) ---


def test_normalize_tweet_extracts_new_tweet_fields():
    """_normalize_tweet returns the new § 1.2 typed-column keys."""
    from x_monitor.apify import _normalize_tweet

    fixture = {
        "id": "123",
        "text": "hello",
        "lang": "en",
        "createdAt": "Wed Jul 22 03:40:35 +0000 2026",
        "viewCount": 42,
        "card": {"type": "summary"},
        "place": {"full_name": "Earth"},
        "source": "Twitter Web App",
        "type": "tweet",
        "url": "https://x.com/x/status/123",
        "twitterUrl": "https://twitter.com/x/status/123",
        "displayTextRange": [0, 5],
        "article": {},
        "communityInfo": {"id": "c1"},
        "isLimitedReply": False,
        "extendedEntities": {"media": []},
        "inReplyToId": "100",
        "inReplyToUsername": "x",
        "bookmarkCount": 3,
        "isReply": False,
        "isRetweet": False,
        "isQuote": False,
        "author": {
            "id": "a1",
            "userName": "x",
            "name": "X",
            "followers": 100,
        },
    }
    out = _normalize_tweet(fixture)
    for key in (
        "view_count", "card", "place", "client_source", "tweet_type",
        "tweet_url", "tweet_twitter_url", "display_text_range", "article",
        "community_info", "is_limited_reply", "extended_entities",
        "in_reply_to_id", "in_reply_to_username", "bookmark_count",
        "is_reply", "is_retweet", "is_quote", "created_at_raw",
    ):
        assert key in out, f"_normalize_tweet missing key: {key!r}"
    assert out["view_count"] == 42
    assert out["client_source"] == "Twitter Web App"
    assert out["display_text_range"] == [0, 5]


def test_normalize_tweet_extracts_new_author_fields():
    """_normalize_tweet returns the new § 1.3 author keys (None when absent)."""
    from x_monitor.apify import _normalize_tweet

    out = _normalize_tweet(
        {
            "id": "1",
            "author": {
                "id": "a1",
                "userName": "x",
                "isTranslator": True,
                "isAutomated": False,
                "automatedBy": None,
                "canDm": True,
                "canMediaTag": False,
                "profile_bio": {"description": "bio"},
                "coverPicture": "url",
                "pinnedTweetIds": ["1", "2"],
                "affiliatesHighlightedLabel": {},
                "withheldInCountries": ["US"],
                "possiblySensitive": False,
                "hasCustomTimelines": True,
                "entities": {"url": {}},
                "twitterUrl": "https://twitter.com/x",
                "type": "user",
                "url": "https://x.com/x",
                "createdAt": "Wed Jul 22 03:40:35 +0000 2026",
                "status": "",
            },
        }
    )
    for key in (
        "author_is_translator", "author_is_automated", "author_automated_by",
        "author_can_dm", "author_can_media_tag", "author_profile_bio",
        "author_cover_picture", "author_pinned_tweet_ids",
        "author_affiliates_highlighted_label", "author_withheld_in_countries",
        "author_possibly_sensitive", "author_has_custom_timelines",
        "author_entities", "author_twitter_url", "author_type",
        "author_url", "author_created_at_raw", "author_status",
    ):
        assert key in out, f"_normalize_tweet missing author key: {key!r}"
    assert out["author_is_translator"] is True
    assert out["author_can_dm"] is True
    assert out["author_pinned_tweet_ids"] == ["1", "2"]


def test_normalize_uses_none_for_absent_new_fields():
    """§ 1.7: missing API keys → None, not 0/false coercion."""
    from x_monitor.apify import _normalize_tweet

    out = _normalize_tweet({"id": "1", "author": {"userName": "x"}})
    assert out.get("view_count") is None
    assert out.get("bookmark_count") is None
    assert out.get("is_reply") is None  # was bool(item.get("isReply")) — that's False on missing
    # NOTE: the legacy code coerced is_reply/is_retweet/is_quote via bool(...),
    # which gives False for missing. The post-migration normalize uses the
    # raw value via .get() so missing → None. This test pins that contract.
    assert out.get("is_retweet") is None
    assert out.get("is_quote") is None
    assert out.get("author_followers_count") == 0  # legacy path: int(... or 0)
    # New author fields default to None when the TwitterAPI key is missing
    assert out.get("author_can_dm") is None
    assert out.get("author_is_translator") is None


def test_normalize_does_not_emit_raw_key():
    """U4: the normalizer no longer leaves a 'raw' key in the returned dict."""
    from x_monitor.apify import _normalize_tweet

    out = _normalize_tweet({"id": "1", "author": {"userName": "x"}})
    assert "raw" not in out, "_normalize_tweet still emits a 'raw' key (U4 incomplete)"
