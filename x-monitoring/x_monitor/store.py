# {{AGENT_ATTRIBUTION}}
"""SQLite storage layer for x-monitor (R18, R21)."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from .config import KNOWN_MODELS

if TYPE_CHECKING:
    from .attribution import MentionRow


_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrandRow:
    """A single row from the `brands` table.

    v1.8 (R12): the canonical brand registry lives in DB, not in
    KNOWN_MODELS. Read via `Store.read_brands()`. The sentinel brand
    (`brand_id = '_unattributed'`) has `is_sentinel = True`; all other
    brands have `is_sentinel = False`. Callers should filter sentinels
    at the read side per Decision 15.
    """

    brand_id: str
    display_name: str
    accent_color: str
    is_sentinel: bool

@dataclass(frozen=True)
class CompanyRow:
    """A single row from the `companies` table.

    The corporate-parent registry. A company may own zero, one, or many
    HuggingFace orgs (via the `hf_orgs` 1:N edge added in migration 005).
    """

    company_id: str
    display_name: str
    hq_country: str | None


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _parse_post_created_at(value):
    """Parse a `posts.created_at` value into an aware UTC datetime, or None.

    Handles both ISO 8601 ("Z" or "+HH:MM") and Twitter legacy
    ("Mon Jun 08 22:40:07 +0000 2026") formats. Returns None for
    empty or unparseable values so callers can use it as a sort key
    without raising.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


def _created_at_epoch(value) -> int | None:
    """Unix-second epoch for a `posts.created_at` value, or None.

    Populates `posts.created_at_epoch` so time-window queries (polarity
    windows in treemap.POLARITY_SQL; the QT daily-pass recency window) can
    filter on a parseable integer. String-comparing the Twitter-format
    `created_at` against ISO bounds sorts incorrectly (weekday-leading
    strings sort after any ``2...`` ISO bound), which silently ignored the
    polarity time window pre-migration-006.
    """
    dt = _parse_post_created_at(value)
    if dt is None:
        return None
    return int(dt.timestamp())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _coerce_for_json_dump(p: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-friendly copy of post dict `p`.

    Coerces `mentions` (v1.8) entries from MentionRow dataclass
    instances to plain dicts so `json.dumps` doesn't fail. Other
    nested values are passed through (the encoder's `default=str`
    catches the rest).
    """
    out = dict(p)
    ms = out.get("mentions")
    if isinstance(ms, list):
        out["mentions"] = [
            m if isinstance(m, dict) else (
                dict(vars(m)) if hasattr(m, "__dataclass_fields__")
                else m
            )
            for m in ms
        ]
    return out


class Store:
    """Thin wrapper around the x_monitoring.db SQLite file.

    The schema is documented in migrations/001_initial.sql.
    """

    def __init__(self, db_path: Path, auto_migrate: bool = True):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._ensure_migrations_table()
        if auto_migrate:
            self.apply_migrations()
        # v1.8 (R12): cache for read_brands() — populated lazily, never
        # invalidated within a Store instance (operators can call
        # store.close() and re-open if they mutate the brands table).
        self._brand_cache: list[BrandRow] | None = None
        # v1.8 (Unit 3): caches for the i18n enum-key sets
        # (roles). Same lazy / not-invalidated lifecycle as
        # _brand_cache — the *enum tables are seeded once by migration
        # 008 and not mutated at runtime. U9 removed the `signals`
        # cache; signal tables were dropped in migration 022.
        self._roles_cache: set[str] | None = None
        # U9: caches for the new enum families introduced by
        # migration 019 (post_type_keys, sentiment_keys). Same
        # lazy / not-invalidated lifecycle as the roles cache.
        self._post_type_cache: set[str] | None = None
        self._sentiment_cache: set[str] | None = None
        # U1: caches for the new enum families introduced by
        # migration 025 (discourse_keys, nationalism_keys). Same lazy /
        # not-invalidated lifecycle as the post_type / sentiment cache.
        self._discourse_cache: set[str] | None = None
        self._nationalism_cache: set[str] | None = None
        # Per-insert_posts counters, read by the cron caller to surface
        # in summary.totals. Reset at the start of each insert_posts call.
        self._classifications_written: int = 0
        self._classifications_dropped: int = 0
        # U8 (migration 020): integer-id lookup caches. These back the
        # "string-in, INTEGER-out" pattern at the Store API — public
        # methods still accept slug/keyword strings, but internal
        # INSERTs convert to INTEGER ids via these maps. Populated
        # lazily (the lookup tables are tiny: brands=12, companies=11,
        # accounts~20, roles=3, post_type_keys=4, sentiment_keys=4,
        # hf_orgs=11). Caches are not invalidated within a Store
        # instance lifetime — see the comments on _roles_cache above
        # for the same lifecycle.
        self._brand_id_map: dict[str, int] | None = None
        self._company_id_map: dict[str, int] | None = None
        self._account_id_map: dict[str, int] | None = None
        self._hf_org_id_map: dict[str, int] | None = None
        self._role_id_map: dict[str, int] | None = None
        self._post_type_id_map: dict[str, int] | None = None
        self._sentiment_id_map: dict[str, int] | None = None
        # U1: integer-id lookup caches for discourse_keys and
        # nationalism_keys (mirrors the pattern at _post_type_id_map).
        self._discourse_id_map: dict[str, int] | None = None
        self._nationalism_id_map: dict[str, int] | None = None

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self._conn.execute("BEGIN")
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _ensure_migrations_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )

    def applied_migrations(self) -> list[int]:
        rows = self._conn.execute(
            "SELECT version FROM _migrations ORDER BY version"
        ).fetchall()
        return [r["version"] for r in rows]

    def apply_migrations(self) -> list[int]:
        """Apply all forward-only migrations that haven't been applied yet.

        Returns the list of versions newly applied.
        """
        if not MIGRATIONS_DIR.exists():
            return []
        applied = set(self.applied_migrations())
        # Migration files are named NNN_*.sql
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        newly: list[int] = []
        for f in files:
            try:
                version = int(f.name.split("_", 1)[0])
            except ValueError:
                continue
            if version in applied:
                continue
            sql = f.read_text(encoding="utf-8")
            # executescript handles its own transactions; record migration
            # as applied AFTER all statements succeed.
            #
            # PRAGMA foreign_keys is a no-op inside a transaction (per
            # SQLite docs), so we toggle it at the connection level here.
            # FKs are disabled during the migration so that the parent→child
            # rebuild pattern (e.g., migration 020's TEXT→INTEGER PK
            # refactor) can drop parent tables without violating FKs in
            # the still-to-be-rebuilt children. FKs are re-enabled in the
            # finally clause so a failure doesn't leave the connection in
            # an FK-off state.
            self._conn.execute("PRAGMA foreign_keys = OFF")
            try:
                self._conn.executescript(sql)
                self._conn.execute(
                    "INSERT INTO _migrations(version, applied_at) VALUES (?, ?)",
                    (version, _now_iso()),
                )
            except Exception:
                # Migration failed — surface the error but don't leave a
                # half-applied state in the migrations table.
                raise
            finally:
                self._conn.execute("PRAGMA foreign_keys = ON")
            newly.append(version)
        return newly

    # --- call_state (U2: since= cursor persistence) -------------------

    # Sentinel written in place of NULL `bucket` so the composite
    # PRIMARY KEY can support ON CONFLICT semantics. SQLite (and the
    # SQL standard) treat two NULLs as distinct in UNIQUE/PK
    # constraints, so a NULL bucket would silently break the
    # UPSERT path. The empty string is never a real bucket value
    # (v1.6 buckets are nonempty identifiers; v1.7 calls always
    # pass bucket=None).
    _NULL_BUCKET_SENTINEL: str = ""

    @classmethod
    def _bucket_for_storage(cls, bucket: str | None) -> str:
        return cls._NULL_BUCKET_SENTINEL if bucket is None else bucket

    def get_last_completed_at(
        self,
        brand_id: str,
        call_id: str,
        call_kind: str,
        bucket: str | None,
        query_id: str,
    ) -> str | None:
        """Return the cursor for a PlannedCall, or None if no prior run.

        `last_completed_at` is the ISO-8601 timestamp of the last
        successful cycle that finished this exact PlannedCall. The
        caller subtracts CURSOR_OVERLAP_HOURS before emitting it as
        the TwitterAPI.io `since:` operator (see x_monitor/run.py).

        The composite key matches the migration 025 PRIMARY KEY:
        (brand_id, call_id, call_kind, bucket, query_id). Two Call C
        specs in the same cycle share call_kind/bucket/query_id but
        differ in call_id, so they're stored as separate cursors.

        Returns None when the row does not exist (first-ever cycle
        for this PlannedCall). Returns the stored ISO timestamp
        otherwise.
        """
        bucket_stored = self._bucket_for_storage(bucket)
        row = self._conn.execute(
            "SELECT last_completed_at FROM call_state "
            "WHERE brand_id = ? AND call_id = ? AND call_kind = ? "
            "AND bucket = ? AND query_id = ?",
            (brand_id, call_id, call_kind, bucket_stored, query_id),
        ).fetchone()
        if row is None:
            return None
        return row["last_completed_at"]

    def set_last_completed_at(
        self,
        brand_id: str,
        call_id: str,
        call_kind: str,
        bucket: str | None,
        query_id: str,
        last_completed_at: str,
    ) -> None:
        """Upsert the cursor for a PlannedCall after a successful cycle.

        Idempotent: re-running the same cycle leaves the cursor at
        `last_completed_at`. The caller is responsible for advancing
        the cursor only on success — if the cycle raises, this method
        must NOT be called, so a failed cycle does not lose data
        (the prior cursor is preserved).

        See migration 025 for the column shapes. Note the
        NULL-bucket sentinel: see `_NULL_BUCKET_SENTINEL`.
        """
        bucket_stored = self._bucket_for_storage(bucket)
        self._conn.execute(
            """
            INSERT INTO call_state(
                brand_id, call_id, call_kind, bucket, query_id,
                last_completed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(brand_id, call_id, call_kind, bucket, query_id)
            DO UPDATE SET
                last_completed_at = excluded.last_completed_at,
                updated_at = excluded.updated_at
            """,
            (
                brand_id, call_id, call_kind, bucket_stored, query_id,
                last_completed_at, _now_iso(),
            ),
        )
        self._conn.commit()

    # --- posts ------------------------------------------------------------

    def insert_posts(self, posts: list[dict[str, Any]]) -> int:
        """Idempotent insert. Returns number of NEWLY inserted rows.

        v1.8 (R16): writes to 4 tables in ONE transaction (posts,
        posts_brands, posts_brands_mentions, posts_brands_signals). Re-inserting
        the same tweet_id is a no-op (INSERT OR IGNORE on posts).

        Per-post dict fields (R2, R3, R6, R8, R15, R16, U9):
          - brand_ids: list[str]     (v1.8 multi-brand)
          - mentions: list[MentionRow] (4-source decomposition)
          - post_types: dict[brand_id, post_type]  (U9: per-brand classification)
          - sentiments: dict[brand_id, sentiment]  (U9: per-brand classification)

        Posts with no brand_id get a sentinel `_unattributed` row in
        posts_brands so the treemap's "unattributed" bin still works.
        `_unattributed` is BLOCKED from posts_brands_signals at the
        application level (post-U8 — the schema-level CHECK was
        dropped because the sentinel's INTEGER id is data-dependent).
        """
        if not posts:
            return 0
        # Source of truth for the posts_brands_signals / posts_brands_mentions FK
        # guards: the brand_ids actually present in the `brands` table
        # (cached). This is wider than the per-post `valid_brands` list
        # (which is brand_ids ∩ KNOWN_MODELS) so cross-mention classifications
        # and v1.8 brands (mistral/stepfun/ernie/hunyuan) are not
        # dropped. See store._known_brand_ids().
        known_ids: set[str] = self._known_brand_ids()
        # Reset per-call counters so the caller reads only this call's
        # write/drop totals.
        self._classifications_written = 0
        self._classifications_dropped = 0
        n_new = 0
        with self.transaction() as conn:
            for p in posts:
                tweet_id = p.get("id") or p.get("tweet_id")
                if not tweet_id:
                    continue
                tweet_id_str = str(tweet_id)
                # Normalize brand_ids (R2, R15). v1.8 callers pass
                # brand_ids: list[str]. Legacy callers pass brand_id:
                # str | list[str].
                brand_ids: list[str] = self._extract_brand_ids(p)
                # Compute weights: 1/N per distinct brand, or 1.0 for
                # the sentinel. Unknown brand slugs collapse into
                # `_unattributed` so the treemap still surfaces them.
                valid_brands: list[str] = []
                for b in brand_ids:
                    if b in KNOWN_MODELS:
                        valid_brands.append(b)
                if not valid_brands:
                    valid_brands = ["_unattributed"]
                weight = 1.0 / len(valid_brands)
                # U8 (migration 020): the `posts.author_id` column
                # now stores the INTEGER id from accounts.id (not the
                # TEXT author_id). Resolve via the accounts
                # lookup. Callers still pass the TEXT author_id
                # (X user id) on the post dict; we look it up here.
                p_author_id_text = (
                    p.get("author_id") or p.get("author_handle") or ""
                )
                p_author_id_int: int | None = None
                if p_author_id_text:
                    p_author_id_int = self._account_int_id(
                        p_author_id_text
                    )
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO posts(
                        tweet_id, author_handle, author_id, text, lang,
                        created_at, fetched_at, like_count, retweet_count,
                        reply_count, quote_count, in_reply_to_user_id,
                        quoted_status_id, conversation_id, entities,
                        source_query_id, raw, headline, headline_source,
                        text_en, text_zh_cn, lang_detected, quoted_text,
                        created_at_epoch
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        tweet_id_str,
                        p.get("author_handle") or p.get("author_id") or "",
                        p_author_id_int,
                        p.get("text"),
                        p.get("lang"),
                        p.get("created_at"),
                        _now_iso(),
                        int(p.get("like_count") or 0),
                        int(p.get("retweet_count") or 0),
                        int(p.get("reply_count") or 0),
                        int(p.get("quote_count") or 0),
                        p.get("in_reply_to_user_id"),
                        p.get("quoted_status_id"),
                        p.get("conversation_id"),
                        json.dumps(p.get("entities") or {}),
                        p.get("source_query_id"),
                        # v1.8: `mentions` may contain MentionRow
                        # dataclass instances (or their dict form
                        # from JSON reload). Coerce to dict so the
                        # JSON encoder doesn't choke. `default=str`
                        # covers anything else we didn't anticipate.
                        json.dumps(
                            _coerce_for_json_dump(p),
                            default=str,
                        ),
                        p.get("headline"),
                        p.get("headline_source"),
                        # v1.7: per-locale translation columns.
                        # NULL when callers don't supply (legacy call sites).
                        p.get("text_en"),
                        p.get("text_zh_cn"),
                        p.get("lang_detected"),
                        p.get("quoted_text"),
                        _created_at_epoch(p.get("created_at")),
                    ),
                )
                if cur.rowcount > 0:
                    n_new += 1
                    # Look up the INTEGER id of the new post (the
                    # posts.id PK that all attribution tables FK to).
                    post_id_int = self._tweet_int_id(tweet_id_str)
                    if post_id_int is None:
                        # The post INSERT succeeded but the lookup
                        # came back empty. This can only happen if a
                        # concurrent writer rolled back; treat as a
                        # hard failure so the caller's transaction
                        # surfaces the inconsistency.
                        raise RuntimeError(
                            f"insert_posts: post just inserted "
                            f"(tweet_id={tweet_id_str}) has no "
                            f"INTEGER id"
                        )
                    # Only write attribution rows for newly-inserted
                    # posts; re-inserts must not duplicate
                    # (posts_brands PK is (post_id, brand_id)).
                    for b in valid_brands:
                        brand_id_int = self._brand_int_id(b)
                        if brand_id_int is None:
                            # brand_id isn't in the brands table; the
                            # FK to brands.id would fail. Drop with a
                            # warning rather than aborting the call.
                            _log.warning(
                                "insert_posts: dropping posts_brands row "
                                "for brand_id=%r not in brands table "
                                "(post_id=%s)",
                                b, tweet_id_str,
                            )
                            continue
                        # R9: ON CONFLICT DO UPDATE so reattribution can
                        # refresh weight. The `weight` column MUST be in
                        # the INSERT column list (top-gun ON CONFLICT
                        # gotcha — only INSERT-listed columns update).
                        conn.execute(
                            """
                            INSERT INTO posts_brands(
                                brand_id, post_id, weight
                            ) VALUES (?, ?, ?)
                            ON CONFLICT(post_id, brand_id) DO UPDATE SET
                                weight = excluded.weight
                            """,
                            (brand_id_int, post_id_int, weight),
                        )
                    # Per-brand classifications (U9): callers pass
                    # `post_types` and `sentiments` as parallel dicts
                    # {brand_id: post_type_key} and {brand_id: sentiment_key}.
                    # Both must be present for a row to be written; if
                    # either is missing for a brand, drop with a warning.
                    post_types_map = p.get("post_types") or {}
                    sentiments_map = p.get("sentiments") or {}
                    classification_brands = set(post_types_map) | set(sentiments_map)
                    for b in classification_brands:
                        if b == "_unattributed":
                            # posts_brands_signals excludes the sentinel
                            # (the post-fetch attribution never emits a
                            # classification for the sentinel brand). Skip.
                            continue
                        # Guard against LLM hallucinations: the
                        # classification dicts come from the LLM and
                        # may contain a brand_id not in the brands
                        # table. Checked against the brands-table
                        # source of truth (known_ids), NOT the
                        # per-post valid_brands, so cross-mention
                        # classifications survive.
                        if b not in known_ids:
                            self._classifications_dropped += 1
                            _log.warning(
                                "insert_posts: dropping classification for "
                                "brand_id=%r not in brands table "
                                "(post_id=%s)",
                                b, tweet_id_str,
                            )
                            continue
                        brand_id_int = self._brand_int_id(b)
                        if brand_id_int is None:
                            self._classifications_dropped += 1
                            continue
                        pt = post_types_map.get(b)
                        sent = sentiments_map.get(b)
                        if not pt or not sent:
                            # U9 (migration 022) requires BOTH columns
                            # NOT NULL. Drop a classification if either
                            # half is missing rather than writing a
                            # half-populated row.
                            self._classifications_dropped += 1
                            _log.warning(
                                "insert_posts: dropping classification for "
                                "brand_id=%r — missing post_type or sentiment "
                                "(post_id=%s pt=%r sent=%r)",
                                b, tweet_id_str, pt, sent,
                            )
                            continue
                        # U9 (migration 019/022): post_type and
                        # sentiment are FK-validated against
                        # post_type_keys and sentiment_keys.
                        # Hallucinated values would raise
                        # IntegrityError; drop them to the dead-letter
                        # log instead.
                        if pt not in self._known_post_type_keys():
                            self._dead_letter_enum(
                                "post_type", pt,
                                table="posts_brands_signals",
                                post_id=tweet_id_str,
                                brand_id=b,
                            )
                            self._classifications_dropped += 1
                            continue
                        if sent not in self._known_sentiment_keys():
                            self._dead_letter_enum(
                                "sentiment", sent,
                                table="posts_brands_signals",
                                post_id=tweet_id_str,
                                brand_id=b,
                            )
                            self._classifications_dropped += 1
                            continue
                        # U1b: column is `post_type_key` and PK is
                        # (post_id, brand_id, post_type_key). Use TEXT
                        # values directly (migration 028). The pt /
                        # sent / b values were already validated against
                        # the *_keys() allow-lists above — no further
                        # id-resolution needed.
                        conn.execute(
                            """
                            INSERT INTO posts_brands_signals(
                                post_id, brand_id, post_type_key, sentiment
                            ) VALUES (?, ?, ?, ?)
                            ON CONFLICT(post_id, brand_id, post_type_key) DO UPDATE SET
                                sentiment = excluded.sentiment
                            """,
                            (tweet_id_str, b, pt, sent),
                        )
                        self._classifications_written += 1
                    # Mentions (R10). v1.8 callers pass `mentions` as a
                    # list of MentionRow-like dicts/dataclasses. Legacy
                    # callers don't pass mentions at all (no rows
                    # written). The `brand_id` may be NULL (un-attributed
                    # user mentions preserved with raw_token).
                    mentions = p.get("mentions") or []
                    for m in mentions:
                        if isinstance(m, dict):
                            m_brand = m.get("brand_id")
                            m_source = m.get("source")
                            m_token = m.get("raw_token")
                            m_at = m.get("mentioned_at") or p.get(
                                "created_at"
                            ) or _now_iso()
                        else:
                            # Dataclass / NamedTuple (MentionRow from
                            # attribution.py). Field order is the
                            # canonical v1.8 shape: post_id, brand_id,
                            # source, raw_token, mentioned_at.
                            m_brand = getattr(m, "brand_id", None)
                            m_source = getattr(m, "source", None)
                            m_token = getattr(m, "raw_token", None)
                            m_at = getattr(m, "mentioned_at", None) or (
                                p.get("created_at") or _now_iso()
                            )
                        if not m_source or not m_token:
                            continue
                        # U8: posts_brands_mentions stores INTEGER id
                        # for brand_id (or NULL for un-attributed).
                        # Resolve the integer id when m_brand is set.
                        m_brand_int: int | None = None
                        if m_brand is not None:
                            if m_brand not in known_ids:
                                _log.warning(
                                    "insert_posts: dropping mention for "
                                    "brand_id=%r not in brands table "
                                    "(post_id=%s source=%r)",
                                    m_brand, tweet_id_str, m_source,
                                )
                                continue
                            m_brand_int = self._brand_int_id(m_brand)
                            if m_brand_int is None:
                                continue
                        conn.execute(
                            """
                            INSERT INTO posts_brands_mentions(
                                post_id, brand_id, source, raw_token, mentioned_at
                            ) VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(post_id, brand_id, source) DO UPDATE SET
                                raw_token = excluded.raw_token
                            """,
                            (
                                post_id_int,
                                m_brand_int,
                                m_source,
                                m_token,
                                m_at,
                            ),
                        )
        return n_new

    def update_quote_tracking(
        self,
        tweet_id: str,
        quote_count: int,
        fetched_at: str | None,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Record the latest observed `quote_count` and QT-fetch timestamp.

        Written separately from `insert_posts` because `posts` is INSERT OR
        IGNORE (re-inserts update nothing) and these values change every
        cycle. Call this in the SAME transaction as the QT ingest batch so
        a failed ingest does not advance `last_quote_count_seen` /
        `last_quote_fetched_at` (which would silently skip un-fetched
        QTs); on failure the caller's transaction rolls back and the next
        cycle retries the same `sinceTime` window idempotently.

        Pass `conn=` to join an existing transaction (e.g. a
        `with store.transaction() as c:` block wrapping ingest + this
        call); omit it to use the Store's connection directly.
        """
        c = conn if conn is not None else self._conn
        c.execute(
            """
            UPDATE posts SET
                last_quote_count_seen = ?,
                last_quote_fetched_at = ?
            WHERE tweet_id = ?
            """,
            (int(quote_count or 0), fetched_at, str(tweet_id)),
        )

    def _extract_brand_ids(self, p: dict[str, Any]) -> list[str]:
        """Normalize the post dict's brand-id field(s) to a list[str].

        v1.8 callers pass `brand_ids: list[str]`. Legacy callers pass
        `brand_id: str | list[str]`. Empty / missing / unknown values
        collapse to `[]`; the caller decides whether to surface the
        `_unattributed` sentinel.
        """
        if "brand_ids" in p and p["brand_ids"] is not None:
            val = p["brand_ids"]
            if isinstance(val, list):
                return [b for b in val if b]
            return [val] if val else []
        if "brand_id" in p and p["brand_id"] is not None:
            val = p["brand_id"]
            if isinstance(val, list):
                return [b for b in val if b]
            return [val] if val else []
        return []

    def _extract_per_brand_classifications(
        self, p: dict[str, Any]
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Normalize the post dict's classification fields.

        U9 callers pass:
          - post_types: dict[brand_id, post_type_key]
          - sentiments: dict[brand_id, sentiment_key]

        Returns two parallel dicts. Brands present in only one of the
        two dicts are filtered out downstream (U9 requires both NOT
        NULL on the row).
        """
        post_types = p.get("post_types") or {}
        sentiments = p.get("sentiments") or {}
        if not isinstance(post_types, dict):
            post_types = {}
        if not isinstance(sentiments, dict):
            sentiments = {}
        # Filter to string keys/values only; defensive against
        # malformed LLM output.
        pt_out: dict[str, str] = {
            b: v for b, v in post_types.items()
            if isinstance(b, str) and b and isinstance(v, str) and v
        }
        sent_out: dict[str, str] = {
            b: v for b, v in sentiments.items()
            if isinstance(b, str) and b and isinstance(v, str) and v
        }
        return pt_out, sent_out

    # --- v1.7: per-locale translation helpers -----------------------------

    # Allowed locales — kept as a closed set so the column name can be
    # safely interpolated into the WHERE clause of get_posts_missing_translations
    # without a SQL-injection risk. Adding a new locale means adding a
    # column in migration 003 + a key here.
    _TRANSLATION_LOCALES: frozenset[str] = frozenset({"en", "zh_cn"})
    _LOCALE_TO_COLUMN: dict[str, str] = {
        "en": "text_en",
        "zh_cn": "text_zh_cn",
    }

    def bulk_update_translations(
        self, rows: list[dict[str, Any]]
    ) -> int:
        """Update text_en / text_zh_cn / lang_detected for a batch of posts.

        Each row is a dict with at least `tweet_id`; the other 3 fields
        (text_en, text_zh_cn, lang_detected) are optional and default
        to NULL. Rows whose tweet_id does not exist in `posts` are
        silently skipped (UPDATE matches 0 rows; we count only the
        ones that did match).

        A row missing `tweet_id` raises KeyError BEFORE the transaction
        starts (the test for this is at tests/test_store_v17.py).
        Returning the count of *updated* rows (not requested) lets the
        translation pass log accurate "X of N translated" stats.

        Empty list is a no-op and returns 0.

        See docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
        §"Column additions to posts" (Decision 5).
        """
        if not rows:
            return 0
        # Pre-validate: every row must have a tweet_id. This is a fast
        # check that raises before the transaction opens.
        for r in rows:
            if "tweet_id" not in r:
                raise KeyError(
                    "bulk_update_translations: row missing 'tweet_id': "
                    f"{r!r}"
                )
        n_updated = 0
        with self.transaction() as conn:
            for r in rows:
                cur = conn.execute(
                    """
                    UPDATE posts
                    SET text_en = ?, text_zh_cn = ?, lang_detected = ?
                    WHERE tweet_id = ?
                    """,
                    (
                        r.get("text_en"),
                        r.get("text_zh_cn"),
                        r.get("lang_detected"),
                        str(r["tweet_id"]),
                    ),
                )
                n_updated += cur.rowcount
        return n_updated

    def get_posts_missing_translations(
        self, locale: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return posts where `text_<locale>` IS NULL, newest-first.

        Used by the `x-monitor translate` backfill subcommand to find
        posts that the end-of-cycle translation pass missed (e.g. due
        to rate-limit, transient API errors, or new posts inserted
        since the last translate run).

        `locale` must be one of {"en", "zh_cn"} — closed-set validation
        prevents SQL-injection via the column name. Other strings
        raise ValueError. The limit caps the result count; pass a
        large number to disable (no streaming pagination in v1.7).

        Returns a list of dicts with at least tweet_id, brand_id, text,
        author_handle, created_at — the fields the translation pass
        needs to build a Claude Haiku prompt.
        """
        if locale not in self._TRANSLATION_LOCALES:
            raise ValueError(
                f"locale must be one of {sorted(self._TRANSLATION_LOCALES)}, "
                f"got {locale!r}"
            )
        col = self._LOCALE_TO_COLUMN[locale]
        # col is from a closed-set literal dict — safe to interpolate
        # directly into the SQL. DO NOT accept the column name from
        # the caller; route it through _LOCALE_TO_COLUMN only.
        #
        # v1.8: posts.brand_id is dropped (migration 004). Attribution
        # moves to posts_brands(brand_id, post_id, weight). We pick any
        # one brand_id per post (the first by lexicographic brand_id) so
        # the translation pipeline still has SOME brand to attribute
        # the post to for translation-prompt context. The translation
        # itself does not need multi-brand precision.
        #
        # U8 (migration 020): posts_brands.post_id and brand_id are
        # INTEGER. JOIN via the integer ids. Return the TEXT brand_id
        # slug (b.brand_id) for downstream code that expects a string.
        rows = self._conn.execute(
            f"""
            SELECT p.tweet_id, b.nickname AS brand_id, p.text, p.author_handle, p.created_at
            FROM posts p
            JOIN posts_brands pb ON pb.post_id = p.id
            JOIN brands b        ON b.id = pb.brand_id
            WHERE p.{col} IS NULL
            ORDER BY p.created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- v1.8 (Unit 4): registry-row translation helpers -----------------
    #
    # Mirrors bulk_update_translations / get_posts_missing_translations
    # for the per-locale columns on brands / companies / accounts. The
    # closed-set dicts below are the only way callers can pick a table +
    # column + PK; the column/table names are interpolated into SQL so
    # the closed-set is the SQL-injection defense.

    _REGISTRY_TABLES: frozenset[str] = frozenset({"brands", "companies", "accounts"})
    _REGISTRY_COLUMNS: frozenset[str] = frozenset({"display_name", "bio"})
    _REGISTRY_PK: dict[str, str] = {
        "brands": "nickname",
        "companies": "nickname",
        "accounts": "author_id",
    }
    # Registry locale-to-column-suffix. Unlike posts.text_en / text_zh_cn,
    # the registry columns are `<col>_en` / `<col>_zh_cn` where `<col>` is
    # the source column name (display_name or bio), NOT a fixed prefix.
    # So the "suffix" here is the column suffix (en / zh_cn), which is
    # what gets appended to `<col>` to form the actual column name.
    _REGISTRY_LOCALE_SUFFIX: dict[str, str] = {
        "en": "en",
        "zh_cn": "zh_cn",
    }

    def get_registry_missing_translations(
        self,
        table: str,
        column: str,
        locale: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return registry rows where `<column>_<locale>` IS NULL.

        Used by the `x-monitor translate-registry` backfill subcommand
        to find rows that the translator hasn't populated yet. Mirrors
        `get_posts_missing_translations` (Unit 4 / D6 in the plan).

        Args:
            table: one of "brands" / "companies" / "accounts".
            column: one of "display_name" / "bio". `bio` is only valid
                for "accounts" (brands/companies have no bio column).
            locale: one of "en" / "zh_cn".
            limit: cap on result count.

        Returns:
            List of dicts with the PK column + `<column>` (source) +
                `<column>_en` + `<column>_zh_cn` so the translator can
                build its prompt and write back the result.
        """
        if table not in self._REGISTRY_TABLES:
            raise ValueError(
                f"table must be one of {sorted(self._REGISTRY_TABLES)}, "
                f"got {table!r}"
            )
        if column not in self._REGISTRY_COLUMNS:
            raise ValueError(
                f"column must be one of {sorted(self._REGISTRY_COLUMNS)}, "
                f"got {column!r}"
            )
        if locale not in self._TRANSLATION_LOCALES:
            raise ValueError(
                f"locale must be one of {sorted(self._TRANSLATION_LOCALES)}, "
                f"got {locale!r}"
            )
        pk_col = self._REGISTRY_PK[table]
        # bio only exists on accounts; bail loudly if the caller asks
        # for an unsupported combo so we don't generate a SQL error
        # mid-test.
        if column == "bio" and table != "accounts":
            raise ValueError(
                f"column 'bio' is only valid for table 'accounts', "
                f"got table={table!r}"
            )
        col = self._REGISTRY_LOCALE_SUFFIX[locale]  # 'en' or 'zh_cn'
        rows = self._conn.execute(
            f"""
            SELECT {pk_col} AS pk, {column} AS source,
                   {column}_en AS col_en,
                   {column}_zh_cn AS col_zh_cn
            FROM {table}
            WHERE {column}_{col} IS NULL
              AND {column} IS NOT NULL
            ORDER BY {pk_col}
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def bulk_update_registry_translations(
        self,
        table: str,
        column: str,
        rows: list[dict[str, Any]],
    ) -> int:
        """Update `<column>_en` and `<column>_zh_cn` for a batch of rows.

        Each row dict MUST have `pk` (the PK column value); the other 2
        fields (`col_en`, `col_zh_cn`) are optional and default to NULL.

        Empty input list is a no-op returning 0. Rows whose PK does not
        exist in the table are silently skipped (UPDATE matches 0 rows).

        Used by the registry translator (Unit 4). Mirrors
        `bulk_update_translations` for posts.
        """
        if table not in self._REGISTRY_TABLES:
            raise ValueError(
                f"table must be one of {sorted(self._REGISTRY_TABLES)}, "
                f"got {table!r}"
            )
        if column not in self._REGISTRY_COLUMNS:
            raise ValueError(
                f"column must be one of {sorted(self._REGISTRY_COLUMNS)}, "
                f"got {column!r}"
            )
        if column == "bio" and table != "accounts":
            raise ValueError(
                f"column 'bio' is only valid for table 'accounts', "
                f"got table={table!r}"
            )
        if not rows:
            return 0
        for r in rows:
            if "pk" not in r:
                raise KeyError(
                    f"bulk_update_registry_translations: row missing 'pk': "
                    f"{r!r}"
                )
        pk_col = self._REGISTRY_PK[table]
        n_updated = 0
        with self.transaction() as conn:
            for r in rows:
                cur = conn.execute(
                    f"""
                    UPDATE {table}
                    SET {column}_en = ?, {column}_zh_cn = ?
                    WHERE {pk_col} = ?
                    """,
                    (
                        r.get("col_en"),
                        r.get("col_zh_cn"),
                        str(r["pk"]),
                    ),
                )
                n_updated += cur.rowcount
        return n_updated

    def get_posts_for_digest(
        self, brand_id: str, since_iso: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # U8 (migration 020): posts_brands.post_id and brand_id are
        # INTEGER; resolve the brand slug before the JOIN.
        brand_id_int = self._brand_int_id(brand_id)
        if brand_id_int is None:
            return []
        # v1.8: posts.brand_id is dropped (migration 004). Attribution
        # moves to posts_brands(brand_id, post_id, weight). The returned
        # dicts keep the `brand_id` key (with weight on the side) so
        # downstream code that does `p.get("brand_id")` continues to
        # work unchanged.
        if since_iso:
            rows = self._conn.execute(
                """
                SELECT p.*, pb.weight
                FROM posts p
                JOIN posts_brands pb ON pb.post_id = p.id
                WHERE pb.brand_id = ? AND p.created_at >= ?
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (brand_id_int, since_iso, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT p.*, pb.weight
                FROM posts p
                JOIN posts_brands pb ON pb.post_id = p.id
                WHERE pb.brand_id = ?
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (brand_id_int, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_posts(self, brand_id: str) -> list[dict[str, Any]]:
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # U8 (migration 020): posts_brands columns are INTEGER.
        brand_id_int = self._brand_int_id(brand_id)
        if brand_id_int is None:
            return []
        # The `created_at` column is TEXT and may hold either ISO 8601 or
        # Twitter legacy (e.g. "Wed Jun 10 21:31:32 +0000 2026"). A SQL
        # `ORDER BY created_at DESC` on the latter is lexicographic, not
        # chronological (Wed > Mon, "10" > "09"), which makes the model
        # detail page render 5-day-old posts at the top. Sort in Python by
        # parsed timestamp instead.
        #
        # v1.8: posts.brand_id is dropped (migration 004); JOIN posts_brands
        # to filter by brand.
        rows = self._conn.execute(
            """
            SELECT p.*, pb.weight
            FROM posts p
            JOIN posts_brands pb ON pb.post_id = p.id
            WHERE pb.brand_id = ?
            """,
            (brand_id_int,),
        ).fetchall()
        posts = [dict(r) for r in rows]
        posts.sort(
            key=lambda p: _parse_post_created_at(p.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return posts

    # --- headline enrichment (v1.2) -------------------------------------

    def update_post_headline(
        self,
        tweet_id: str,
        headline: str | None,
        source: str,
    ) -> bool:
        """Set the headline + headline_source for a single post.

        Returns True if a row was updated. Idempotent: re-running
        backfill with the same data is a no-op.
        """
        cur = self._conn.execute(
            """
            UPDATE posts
            SET headline = ?, headline_source = ?
            WHERE tweet_id = ?
            """,
            (headline, source, tweet_id),
        )
        return cur.rowcount > 0

    def iter_url_only_no_headline(
        self, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Yield posts where text is a bare URL and headline is NULL.

        Backs the `relevance backfill` subcommand. Ordered by rowid so
        the oldest unprocessed rows come first.
        """
        rows = self._conn.execute(
            """
            SELECT tweet_id, text
            FROM posts
            WHERE headline IS NULL
              AND text GLOB 'https*'
            ORDER BY rowid
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_url_only(self) -> int:
        """Total URL-only posts (text GLOB 'https*')."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM posts WHERE text GLOB 'https*'"
        ).fetchone()
        return int(row["n"]) if row else 0

    def count_headlines(self) -> int:
        """Total posts that have a non-NULL headline."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM posts WHERE headline IS NOT NULL"
        ).fetchone()
        return int(row["n"]) if row else 0

    # --- accounts ---------------------------------------------------------

    def upsert_account(
        self,
        brand_id: str,
        handle: str,
        role: str = "unknown",
        author_id: str | None = None,
        source_query_ids: list[str] | None = None,
        display_name: str | None = None,
        verified: bool = False,
        bio_contains_brand: bool = False,
        multi_brand_voice: bool = False,
        notes: str | None = None,
    ) -> None:
        """Upsert a per-brand account edge.

        v1.8: accounts table loses the brand_id/handle PK and the per-account
        role/multi_brand_voice columns (migration 004, Decision 10). The
        per-brand role now lives in `brands_accounts(brand_id, author_id,
        role)`. The `multi_brand_voice` column is dropped (R12) — that
        derivation moves to a query against brands_accounts.

        `author_id` is the X user id (immutable, globally-unique identifier
        Twitter/X assigns to each account). Pass it when the caller has it
        (e.g., the apify normalizers now extract it from the API response).
        For callers that don't have one (yaml-derived accounts in
        `data/brands/<brand>/accounts.yaml`), we synthesize a stable
        `handle:<handle>` author_id so re-upserts hit the same row.
        """
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # role is FK-validated against roles (renamed from role_keys in
        # 015; trimmed to {official, staff, community} in 016). Legacy
        # callers pass role="unknown" which is NOT in roles. In that
        # case, skip the brands_accounts edge write — the per-brand
        # role is unknowable, so the edge has no information.
        # In that case, skip the brands_accounts edge write — the
        # per-brand role is unknowable, so the edge has no information.
        # The accounts row is still upserted (no role column there
        # post-migration 004).
        role_known = role in self._known_role_keys()
        # Resolve author_id: real X user id when the caller passes one,
        # synthetic `handle:<handle>` fallback otherwise. The dead-letter
        # log uses the same synthesized value so the message is stable
        # across calls.
        resolved_author_id = author_id or f"handle:{handle}"
        if not role_known:
            self._dead_letter_enum(
                "role", role,
                table="brands_accounts",
                brand_id=brand_id,
                author_id=resolved_author_id,
            )
        now = _now_iso()
        # Upsert into accounts (author_id PK). We drop multi_brand_voice
        # silently — v1.8 callers can stop passing it; old callers passing
        # it just see the kwarg ignored.
        self._conn.execute(
            """
            INSERT INTO accounts(
                author_id, handle, display_name, verified,
                bio_contains_brand,
                first_seen_at, last_seen_at, source_query_ids, notes
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(author_id) DO UPDATE SET
                handle = COALESCE(excluded.handle, accounts.handle),
                display_name = COALESCE(excluded.display_name, accounts.display_name),
                verified = MAX(accounts.verified, excluded.verified),
                bio_contains_brand = MAX(accounts.bio_contains_brand, excluded.bio_contains_brand),
                last_seen_at = excluded.last_seen_at,
                source_query_ids = excluded.source_query_ids,
                notes = COALESCE(excluded.notes, accounts.notes)
            """,
            (
                resolved_author_id,
                handle,
                display_name,
                int(verified),
                int(bio_contains_brand),
                now,
                now,
                json.dumps(source_query_ids or []),
                notes,
            ),
        )
        # Upsert the per-brand edge in brands_accounts (the per-brand role).
        # Skipped when role was unknown to roles — see dead-letter
        # guard above. This preserves pre-v1.8 semantics: an unknown role
        # did not write a brands_accounts row either (the old DEFAULT was
        # 'community', so callers passing role='unknown' would have hit
        # the schema's TEXT convention with no enforcement).
        if role_known:
            # U8 (migration 020): brands_accounts stores INTEGER ids
            # (brands.id, accounts.id, roles.id), not TEXT slugs. Look
            # each up before the INSERT.
            brand_id_int = self._brand_int_id(brand_id)
            author_id_int = self._account_int_id(resolved_author_id)
            role_id_int = self._role_int_id(role)
            if brand_id_int is None:
                # brand_id isn't in the brands table; the FK would fail.
                _log.warning(
                    "upsert_account: skipping brands_accounts write; "
                    "brand_id=%r not in brands table (author_id=%s)",
                    brand_id, resolved_author_id,
                )
                return
            if author_id_int is None:
                # We just upserted the accounts row above, so this
                # should always resolve. If it doesn't, the cache is
                # stale — refresh once before giving up.
                self._account_id_map = None
                author_id_int = self._account_int_id(resolved_author_id)
            if author_id_int is None or role_id_int is None:
                # Truly unrecoverable; bail out to avoid an FK error.
                _log.warning(
                    "upsert_account: skipping brands_accounts write; "
                    "unresolvable integer id (brand=%s, author=%s, role=%s)",
                    brand_id, resolved_author_id, role,
                )
                return
            self._conn.execute(
                """
                INSERT INTO brands_accounts(
                    brand_id, accounts_id, role_id, added_at
                ) VALUES (?,?,?,?)
                ON CONFLICT(brand_id, accounts_id) DO UPDATE SET
                    role_id = excluded.role_id
                """,
                (brand_id_int, author_id_int, role_id_int, now),
            )

    def get_account(self, brand_id: str, handle: str) -> dict[str, Any] | None:
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # U8 (migration 020) + U6 (migration 031):
        # brands_accounts.brand_id is INTEGER (FK to brands.id) and
        # brands_accounts.accounts_id is INTEGER (FK to accounts.id,
        # the new surrogate PK). Resolve the brand slug to its id
        # before the JOIN; join on the surrogate integer key.
        brand_id_int = self._brand_int_id(brand_id)
        if brand_id_int is None:
            return None
        # v1.8: JOIN brands_accounts so we can return the per-brand role
        # alongside the account row. Also JOIN roles to expose the role
        # key string (consumers read role_id as text; this is the
        # integer→text bridge).
        row = self._conn.execute(
            """
            SELECT a.*, ba.role_id, r.key AS role_key
            FROM accounts a
            JOIN brands_accounts ba ON ba.accounts_id = a.id
            LEFT JOIN roles r ON r.id = ba.role_id
            WHERE ba.brand_id = ? AND a.handle = ?
            """,
            (brand_id_int, handle),
        ).fetchone()
        return dict(row) if row else None

    def get_accounts(self, brand_id: str) -> list[dict[str, Any]]:
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # U8 (migration 020): brands_accounts FK columns are INTEGER.
        brand_id_int = self._brand_int_id(brand_id)
        if brand_id_int is None:
            return []
        # v1.8: accounts no longer has brand_id. The per-brand accounts
        # live behind brands_accounts JOIN. LEFT JOIN roles to surface
        # the role key string alongside the integer role_id.
        rows = self._conn.execute(
            """
            SELECT a.*, ba.role_id, r.key AS role_key
            FROM accounts a
            JOIN brands_accounts ba ON ba.accounts_id = a.id
            LEFT JOIN roles r ON r.id = ba.role_id
            WHERE ba.brand_id = ?
            """,
            (brand_id_int,),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- appearances ------------------------------------------------------

    def record_appearance(
        self, brand_id: str, handle: str, tweet_id: str, role_at_time: str | None = None
    ) -> None:
        """Record that `handle` (an account edge of `brand_id`) appeared on
        `tweet_id`.

        v1.8: account_post_appearances PK changed from
        (model_id, handle, tweet_id) to (author_id, tweet_id) (Decision 4).
        Resolve handle -> author_id from accounts; if the handle isn't in
        accounts yet (race), silently skip — caller should upsert_account
        first.
        """
        author_id = f"handle:{handle}"
        # If the account row exists with this synthetic id, write the
        # appearance. Otherwise the FK on (author_id, tweet_id) would fail;
        # silently skip per the prior contract.
        try:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO account_post_appearances(
                    author_id, tweet_id, role_at_time
                ) VALUES (?,?,?)
                """,
                (author_id, str(tweet_id), role_at_time),
            )
        except sqlite3.IntegrityError:
            pass

    # --- v1.8: per-row write methods (R9, R10, R11) -----------------------

    def insert_posts_brands(self, post_id: str, brand_id: str, weight: float) -> None:
        """Upsert one row into posts_brands (R9).

        ON CONFLICT(post_id, brand_id) DO UPDATE SET weight = excluded.weight
        per Decision 14 — reattribution MUST overwrite stale weights when
        the detection registry evolves.

        Top-gun ON CONFLICT gotcha: the `weight` column MUST be in the
        INSERT column list (the SET clause can only update columns the
        INSERT actually wrote).

        U8 (migration 020): both `post_id` and `brand_id` are stored as
        INTEGER ids. The public signature still takes the TEXT tweet_id
        and TEXT brand_id slug; this method resolves each to its
        INTEGER id before the INSERT. Drops the write with a warning
        if either side cannot be resolved (the FK to posts.id /
        brands.id would fail).
        """
        post_id_int = self._tweet_int_id(post_id)
        brand_id_int = self._brand_int_id(brand_id)
        if post_id_int is None or brand_id_int is None:
            _log.warning(
                "insert_posts_brands: dropping row; unresolvable id "
                "(post_id=%s brand_id=%s)",
                post_id, brand_id,
            )
            return
        self._conn.execute(
            """
            INSERT INTO posts_brands(brand_id, post_id, weight)
            VALUES (?, ?, ?)
            ON CONFLICT(post_id, brand_id) DO UPDATE SET
                weight = excluded.weight
            """,
            (brand_id_int, post_id_int, float(weight)),
        )

    def insert_posts_brands_mentions(
        self,
        post_id: str,
        brand_id: str | None,
        source: str,
        raw_token: str,
        mentioned_at: str,
    ) -> None:
        """Upsert one row into posts_brands_mentions (R10).

        ON CONFLICT(post_id, brand_id, source) DO UPDATE SET
        raw_token = excluded.raw_token.

        `brand_id` may be NULL (un-attributed user mentions preserved
        with raw_token for later backfill). The PK allows NULLs in
        non-INTEGER-PRIMARY-KEY columns.

        Top-gun ON CONFLICT gotcha: the `raw_token` column MUST be in
        the INSERT column list.

        U8 (migration 020): `post_id` is stored as INTEGER (FK to
        posts.id) and `brand_id` (when not NULL) is stored as INTEGER
        (FK to brands.id). `source` and `raw_token` stay TEXT.
        """
        post_id_int = self._tweet_int_id(post_id)
        if post_id_int is None:
            _log.warning(
                "insert_posts_brands_mentions: dropping row; "
                "unresolvable post id (post_id=%s brand_id=%s source=%s)",
                post_id, brand_id, source,
            )
            return
        brand_id_int: int | None = None
        if brand_id is not None:
            brand_id_int = self._brand_int_id(brand_id)
            if brand_id_int is None:
                _log.warning(
                    "insert_posts_brands_mentions: dropping row; "
                    "unresolvable brand id (post_id=%s brand_id=%s source=%s)",
                    post_id, brand_id, source,
                )
                return
        self._conn.execute(
            """
            INSERT INTO posts_brands_mentions(
                post_id, brand_id, source, raw_token, mentioned_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(post_id, brand_id, source) DO UPDATE SET
                raw_token = excluded.raw_token
            """,
            (post_id_int, brand_id_int, source, raw_token, mentioned_at),
        )

    def insert_posts_brands_signals(
        self,
        post_id: str,
        brand_id: str,
        post_type: str,
        sentiment: str,
    ) -> None:
        """Upsert one row into posts_brands_signals (R11, U9, U1b).

        U9: both `post_type` and `sentiment` are required.
        U1b: PK is now (post_id, brand_id, post_type_key) — the
        method accepts one (post, brand, post_type) tuple at a time
        and the ON CONFLICT clause targets the new composite PK.
        For N post_types per (post, brand), call this method N times.

        Stores TEXT-natural-key values directly (post_id → posts.tweet_id,
        brand_id → brands.nickname, post_type → post_type_keys.key,
        sentiment → sentiment_keys.key). FK guards drop unknown
        values with a warning.

        `_unattributed` sentinel brand is blocked.
        """
        if brand_id not in self._known_brand_ids():
            _log.warning(
                "insert_posts_brands_signals: dropping classification for "
                "brand_id=%r not in brands table (post_id=%s)",
                brand_id, post_id,
            )
            return
        sentinel_brand_ids = {
            b.brand_id for b in self.read_brands() if b.is_sentinel
        }
        if brand_id in sentinel_brand_ids:
            _log.warning(
                "insert_posts_brands_signals: dropping classification for "
                "sentinel brand_id=%r (post_id=%s)",
                brand_id, post_id,
            )
            return
        # U9: post_type FK guard.
        if post_type not in self._known_post_type_keys():
            self._dead_letter_enum(
                "post_type", post_type,
                table="posts_brands_signals",
                post_id=post_id,
                brand_id=brand_id,
            )
            return
        # U9: sentiment FK guard.
        if sentiment not in self._known_sentiment_keys():
            self._dead_letter_enum(
                "sentiment", sentiment,
                table="posts_brands_signals",
                post_id=post_id,
                brand_id=brand_id,
            )
            return
        # U1b: write TEXT values directly. Migration 028 changed the
        # PK to (post_id, brand_id, post_type_key); post_type goes
        # into the post_type_key column.
        self._conn.execute(
            """
            INSERT INTO posts_brands_signals (
                post_id, brand_id, post_type_key, sentiment
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(post_id, brand_id, post_type_key) DO UPDATE SET
                sentiment = excluded.sentiment
            """,
            (post_id, brand_id, post_type, sentiment),
        )
        self._conn.commit()

    # --- U1: posts_brands_discourse helpers (migration 025) ----------------
    #
    # Per-act pragmatics signal junction. The `discourse_key` and
    # `act_id` parts of the composite PK are required (NOT NULL); the
    # two `*_nationalism` FKs are nullable during the backfill window
    # (filled by `bulk_update_nationalism` once U4's second pass runs).
    # All FK columns store INTEGER ids — see migration 025 header.

    def bulk_insert_post_brand_discourse(
        self, rows: list[dict[str, Any]]
    ) -> int:
        """Upsert rows into posts_brands_discourse (U1, U4).

        Each row dict requires:
          - `tweet_id` (TEXT, FK to posts.tweet_id)
          - `brand_id` (TEXT, FK to brands.brand_id)
          - `discourse_key` (TEXT; e.g. 'dunk_yingyang')
          - `act_id` (int, 1-99; v1 always writes 1)
        Optional (nullable during backfill window):
          - `china_nationalism` (TEXT; e.g. 'anti')
          - `us_nationalism` (TEXT; e.g. 'constructive_critical')

        Returns the number of rows successfully written (existing
        rows are upserted — same `(post, brand, discourse, act)` PK
        updates the nationalism columns in place).

        All FK resolutions are guarded: unknown `discourse_key` or
        `*_nationalism` is dead-lettered and the row is dropped (the
        parser must coerce before calling). Unknown `brand_id` is
        dropped with a warning. `act_id` outside 1-99 raises ValueError
        (a caller-side invariant).

        The bulk method follows the same shape as
        `bulk_update_translations`: one transaction, one cursor per
        row, count of *upserted* rows returned.
        """
        if not rows:
            return 0
        # Pre-validate: every row must have the four required keys.
        for r in rows:
            for required in (
                "tweet_id", "brand_id", "discourse_key", "act_id",
            ):
                if required not in r:
                    raise KeyError(
                        f"bulk_insert_post_brand_discourse: row missing "
                        f"{required!r}: {r!r}"
                    )
        n_written = 0
        with self.transaction() as conn:
            for r in rows:
                tweet_id = str(r["tweet_id"])
                brand_id = r["brand_id"]
                discourse_key = r["discourse_key"]
                act_id = int(r["act_id"])
                if not 1 <= act_id <= 99:
                    raise ValueError(
                        f"bulk_insert_post_brand_discourse: act_id={act_id} "
                        f"out of range [1, 99] (tweet_id={tweet_id} "
                        f"brand_id={brand_id} discourse_key={discourse_key})"
                    )
                # Discourse FK guard (dead-letter; never coerce silently).
                # `uncategorized` is the sentinel for LLM-hallucinated
                # discourse keys (KTD5); it's NOT a row in
                # discourse_keys (the table is intentionally tight).
                # We drop `uncategorized` rows with a dead-letter
                # note: they carry no actionable discourse signal,
                # the brief renderer cites them in the limitations
                # paragraph. Persisting them as rows would require
                # adding `uncategorized` to discourse_keys (which
                # would muddy the taxonomy — explicitly avoided).
                if discourse_key == "uncategorized":
                    self._dead_letter_enum(
                        "discourse", discourse_key,
                        table="posts_brands_discourse",
                        post_id=tweet_id,
                        brand_id=brand_id,
                        note="uncategorized-sentinel (KTD5): row skipped, no FK target",
                    )
                    continue
                if discourse_key not in self._known_discourse_keys():
                    self._dead_letter_enum(
                        "discourse", discourse_key,
                        table="posts_brands_discourse",
                        post_id=tweet_id,
                        brand_id=brand_id,
                    )
                    continue
                # Brand FK guard (drop with warning; mirrors the
                # pre-019 signal handler).
                if brand_id not in self._known_brand_ids():
                    _log.warning(
                        "bulk_insert_post_brand_discourse: dropping row "
                        "for brand_id=%r not in brands table "
                        "(tweet_id=%s discourse_key=%s)",
                        brand_id, tweet_id, discourse_key,
                    )
                    continue
                # Resolve INTEGER ids.
                post_id_int = self._tweet_int_id(tweet_id)
                brand_id_int = self._brand_int_id(brand_id)
                if post_id_int is None or brand_id_int is None:
                    _log.warning(
                        "bulk_insert_post_brand_discourse: dropping row; "
                        "unresolvable id (tweet_id=%s brand_id=%s)",
                        tweet_id, brand_id,
                    )
                    continue
                discourse_key_int = self._discourse_int_id(discourse_key)
                if discourse_key_int is None:
                    # Should be impossible — we just checked
                    # _known_discourse_keys() — but drop defensively if
                    # the cache is stale.
                    _log.warning(
                        "bulk_insert_post_brand_discourse: dropping row; "
                        "unresolvable discourse_key id "
                        "(tweet_id=%s brand_id=%s discourse_key=%s)",
                        tweet_id, brand_id, discourse_key,
                    )
                    continue
                china_natl_int = self._nationalism_int_id(
                    r.get("china_nationalism")
                )
                us_natl_int = self._nationalism_int_id(
                    r.get("us_nationalism")
                )
                # If caller supplied a key but it didn't resolve, log a
                # warning and write NULL (we don't dead-letter a half-
                # formed nationalism FK; we just leave the column NULL).
                if (r.get("china_nationalism") is not None
                        and china_natl_int is None):
                    _log.warning(
                        "bulk_insert_post_brand_discourse: NULLing "
                        "china_nationalism=%r (not in nationalism_keys) "
                        "for (tweet_id=%s brand_id=%s)",
                        r.get("china_nationalism"),
                        tweet_id, brand_id,
                    )
                if (r.get("us_nationalism") is not None
                        and us_natl_int is None):
                    _log.warning(
                        "bulk_insert_post_brand_discourse: NULLing "
                        "us_nationalism=%r (not in nationalism_keys) "
                        "for (tweet_id=%s brand_id=%s)",
                        r.get("us_nationalism"),
                        tweet_id, brand_id,
                    )
                # Top-gun ON CONFLICT gotcha: all written columns MUST be
                # in the INSERT column list (otherwise ON CONFLICT DO
                # UPDATE doesn't touch them on conflict).
                conn.execute(
                    """
                    INSERT INTO posts_brands_discourse(
                        post_id, brand_id, discourse_key, act_id,
                        china_nationalism, us_nationalism
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(post_id, brand_id, discourse_key, act_id)
                    DO UPDATE SET
                        china_nationalism = excluded.china_nationalism,
                        us_nationalism = excluded.us_nationalism
                    """,
                    (
                        post_id_int,
                        brand_id_int,
                        discourse_key_int,
                        act_id,
                        china_natl_int,
                        us_natl_int,
                    ),
                )
                n_written += 1
        return n_written

    # --- U4 (plan 2026-07-03-003): unsanctioned flags + multi-post_type ----

    # Evidence sanitization bounds (security R14).
    _EVIDENCE_MAX_LEN = 1024  # 1 KB
    _EVIDENCE_FORBIDDEN = re.compile(r"https?://", re.IGNORECASE)

    def upsert_unsanctioned_flags(
        self,
        post_id: str,
        flags: list[str],
        evidence: str | None = None,
    ) -> None:
        """Insert or update a row in posts_unsanctioned_flags (KTD3, R3).

        Security (R14):
        - `evidence` is capped at 1 KB and stripped of control characters
          (except \\t\\n\\r).
        - URLs in `evidence` are rejected (open-redirect / XSS surface on
          the dashboard's rendered output).

        The `flags` list is stored as JSON TEXT. Allowed values are
        filtered at the parser layer (`_parse_unsanctioned_flags`); this
        method trusts the caller and writes whatever it gets.

        ON CONFLICT(post_id) DO UPDATE — re-classification overwrites.
        """
        import json as _json
        if evidence is not None:
            if len(evidence) > self._EVIDENCE_MAX_LEN:
                raise ValueError(
                    f"evidence length {len(evidence)} > {self._EVIDENCE_MAX_LEN}"
                )
            if self._EVIDENCE_FORBIDDEN.search(evidence):
                raise ValueError(
                    "evidence must not contain http(s):// URLs"
                )
            # Strip C0 control chars except \t \n \r.
            evidence = "".join(
                ch for ch in evidence
                if ch in "\t\n\r" or (ord(ch) >= 0x20 and ord(ch) != 0x7F)
            )
        flags_json = _json.dumps(list(flags), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO posts_unsanctioned_flags (
                post_id, flags, evidence, decided_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(post_id) DO UPDATE SET
                flags = excluded.flags,
                evidence = excluded.evidence,
                decided_at = excluded.decided_at
            """,
            (post_id, flags_json, evidence, _now_iso()),
        )
        self._conn.commit()

    def get_unsanctioned_flags(self, post_id: str) -> list[str] | None:
        """Return the unsanctioned flags list for a post, or None if missing.

        Returns `None` for missing rows (so the dashboard can distinguish
        "no flags row" from "row exists with empty flags").
        On parse failure, returns None and logs a warning (per R14
        — silent `[]` would let dashboard hide flagged posts).
        """
        import json as _json
        row = self._conn.execute(
            "SELECT flags FROM posts_unsanctioned_flags WHERE post_id = ?",
            (post_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            parsed = _json.loads(row["flags"])
            if not isinstance(parsed, list):
                return None
            return [f for f in parsed if isinstance(f, str)]
        except (ValueError, TypeError) as e:
            logger.warning(
                "get_unsanctioned_flags: JSON parse failed for post_id=%s: %s",
                post_id, e,
            )
            return None

    def flag_get_status(self, post_id: str) -> str:
        """Return 'missing' | 'ok' | 'corrupt' for the flags row.

        'missing': no row exists for post_id.
        'ok': row exists, flags JSON parses cleanly.
        'corrupt': row exists but flags is not valid JSON.
        """
        import json as _json
        row = self._conn.execute(
            "SELECT flags FROM posts_unsanctioned_flags WHERE post_id = ?",
            (post_id,),
        ).fetchone()
        if row is None:
            return "missing"
        try:
            _json.loads(row["flags"])
            return "ok"
        except (ValueError, TypeError):
            return "corrupt"

    def recent_posts_unsanctioned_missing(self, limit: int) -> list[str]:
        """Return post_ids of recent posts that have NO unsanctioned_flags row.

        Used by U8b's backfill CLI to find posts that need classification.
        Returns post_ids ordered by fetched_at DESC.
        """
        rows = self._conn.execute(
            """
            SELECT p.tweet_id FROM posts p
            LEFT JOIN posts_unsanctioned_flags uf ON uf.post_id = p.tweet_id
            WHERE uf.post_id IS NULL
            ORDER BY p.fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [r["tweet_id"] for r in rows]

    def read_recent_posts(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return up to `limit` posts ordered by `fetched_at DESC`.

        Used by the smoketest's `--source=latest-n` mode (see
        `scripts/post_fetch_smoketest.py`). Surfaces the N most recent
        production posts regardless of brand attribution — no JOIN, no
        filter. The smoketest applies its own brand-keyword detector to
        populate the renderer's `brand_mentions:` block, and a post with
        no detected brand is still rendered (not silently dropped).

        Returns a list of dicts with keys: `tweet_id`, `text`,
        `lang_detected`, `author_handle`, `fetched_at`. Matches the row
        shape `get_posts_missing_translations` returns — TEXT-natural
        keys only, no INTEGER ids leaking through.

        `fetched_at` is included so callers can assert descending order
        without re-querying.
        """
        rows = self._conn.execute(
            """
            SELECT p.tweet_id, p.text, p.lang_detected, p.author_handle,
                   p.fetched_at
            FROM posts p
            ORDER BY p.fetched_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def bulk_insert_post_brand_signals(
        self,
        rows: list[dict[str, Any]],
    ) -> int:
        """U2b + U4: bulk insert per-(post × brand × post_type) signal rows.

        Each `row` is a dict with at minimum:
            post_id, brand_id, post_type, sentiment
        Optionally:
            china_nationalism, us_nationalism (forward-compat)

        Stores TEXT-natural-key values directly (post_id → posts.tweet_id,
        brand_id → brands.nickname). The post_type_key + sentiment columns
        are FKs to their respective *_keys tables; the Store validates
        these against `_known_post_type_keys()` / `_known_sentiment_keys()`
        and drops unknown values with a warning.

        ON CONFLICT(post_id, brand_id, post_type_key) DO UPDATE SET
        sentiment = excluded.sentiment — re-classification overwrites.

        Returns the count of rows written.
        """
        n_written = 0
        for r in rows:
            tweet_id = r.get("post_id")
            brand_id = r.get("brand_id")
            post_type = r.get("post_type")
            sentiment = r.get("sentiment")
            if not all(isinstance(x, str) for x in (tweet_id, brand_id,
                                                     post_type, sentiment)):
                continue
            if post_type not in self._known_post_type_keys():
                _log.warning(
                    "bulk_insert_post_brand_signals: dropping row; "
                    "post_type=%r not in post_type_keys (post_id=%s brand_id=%s)",
                    post_type, tweet_id, brand_id,
                )
                continue
            if sentiment not in self._known_sentiment_keys():
                _log.warning(
                    "bulk_insert_post_brand_signals: dropping row; "
                    "sentiment=%r not in sentiment_keys (post_id=%s)",
                    sentiment, tweet_id,
                )
                continue
            self._conn.execute(
                """
                INSERT INTO posts_brands_signals (
                    post_id, brand_id, post_type_key, sentiment
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(post_id, brand_id, post_type_key) DO UPDATE SET
                    sentiment = excluded.sentiment
                """,
                (tweet_id, brand_id, post_type, sentiment),
            )
            n_written += 1
        self._conn.commit()
        return n_written

    def get_post_brand_discourse_for_post(
        self, tweet_id: str
    ) -> list[dict[str, Any]]:
        """Return all (post × brand × discourse × act) rows for a tweet.

        Used by U7's smoketest runner to render sample posts with all
        four new prongs visible, and by U4's second-pass classifier to
        find rows whose nationalism FKs are still NULL.

        Returns a list of dicts with TEXT key values (joined back from
        the INTEGER FK ids via the *_keys tables) — the caller-facing
        shape stays in TEXT-land, the Store never leaks INTEGER ids.
        """
        # One-shot join for the per-post set. Resolves
        # discourse_key.id → discourse_keys.key and the two
        # nationalism.id → nationalism_keys.key (LEFT JOIN because the
        # two nationalism FKs are nullable).
        rows = self._conn.execute(
            """
            SELECT
                b.nickname      AS brand_id,
                dk.key          AS discourse_key,
                pbd.act_id      AS act_id,
                cn.key          AS china_nationalism,
                un.key          AS us_nationalism
            FROM posts_brands_discourse pbd
            JOIN posts p              ON p.id          = pbd.post_id
            JOIN brands b             ON b.id          = pbd.brand_id
            JOIN discourse_keys dk    ON dk.id         = pbd.discourse_key
            LEFT JOIN nationalism_keys cn ON cn.id      = pbd.china_nationalism
            LEFT JOIN nationalism_keys un ON un.id      = pbd.us_nationalism
            WHERE p.tweet_id = ?
            ORDER BY b.nickname, pbd.act_id, dk.key
            """,
            (tweet_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def bulk_update_nationalism(
        self,
        tweet_id: str,
        brand_id: str,
        discourse_key: str,
        act_id: int,
        china_nationalism: str | None,
        us_nationalism: str | None,
    ) -> bool:
        """Backfill the two nationalism FKs for an existing discourse row.

        Returns True if a row was updated, False if the discourse row
        doesn't exist or any FK resolution failed. Used by U4's
        second-pass classifier — the first pass writes the
        `discourse_key` row with both nationalism FKs NULL, then a
        second LLM call (or human-curated batch) fills them in.

        Mirrors the sentinel-blocking and dead-letter pattern of
        `bulk_insert_post_brand_discourse` (smaller surface: one row,
        no enumeration).
        """
        # Discourse FK guard (same as the bulk path).
        if discourse_key not in self._known_discourse_keys():
            self._dead_letter_enum(
                "discourse", discourse_key,
                table="posts_brands_discourse",
                post_id=tweet_id,
                brand_id=brand_id,
                via="bulk_update_nationalism",
            )
            return False
        if brand_id not in self._known_brand_ids():
            _log.warning(
                "bulk_update_nationalism: brand_id=%r not in brands "
                "table (tweet_id=%s)",
                brand_id, tweet_id,
            )
            return False
        post_id_int = self._tweet_int_id(tweet_id)
        brand_id_int = self._brand_int_id(brand_id)
        discourse_key_int = self._discourse_int_id(discourse_key)
        if (
            post_id_int is None
            or brand_id_int is None
            or discourse_key_int is None
        ):
            _log.warning(
                "bulk_update_nationalism: unresolvable id "
                "(tweet_id=%s brand_id=%s discourse_key=%s)",
                tweet_id, brand_id, discourse_key,
            )
            return False
        china_int = self._nationalism_int_id(china_nationalism)
        us_int = self._nationalism_int_id(us_nationalism)
        if (china_nationalism is not None and china_int is None):
            _log.warning(
                "bulk_update_nationalism: NULLing china_nationalism=%r "
                "(not in nationalism_keys) for (tweet_id=%s)",
                china_nationalism, tweet_id,
            )
        if (us_nationalism is not None and us_int is None):
            _log.warning(
                "bulk_update_nationalism: NULLing us_nationalism=%r "
                "(not in nationalism_keys) for (tweet_id=%s)",
                us_nationalism, tweet_id,
            )
        cur = self._conn.execute(
            """
            UPDATE posts_brands_discourse
            SET china_nationalism = ?, us_nationalism = ?
            WHERE post_id = ? AND brand_id = ?
              AND discourse_key = ? AND act_id = ?
            """,
            (
                china_int,
                us_int,
                post_id_int,
                brand_id_int,
                discourse_key_int,
                act_id,
            ),
        )
        return cur.rowcount > 0

    # --- v1.8: detection-registry read methods (R12, R13) -----------------

    def read_brands(self) -> list[BrandRow]:
        """Return all rows from the `brands` table (R12).

        Includes the `_unattributed` sentinel (is_sentinel=True). Result
        is cached in `self._brand_cache` for the lifetime of the Store
        instance so callers (attribution.py, dashboard.py) don't
        re-query on every ingest cycle.
        """
        if self._brand_cache is not None:
            return self._brand_cache
        rows = self._conn.execute(
            """
            SELECT nickname AS brand_id, display_name, accent_color, is_sentinel
            FROM brands
            ORDER BY display_name
            """
        ).fetchall()
        result = [
            BrandRow(
                brand_id=r["brand_id"],
                display_name=r["display_name"],
                accent_color=r["accent_color"],
                is_sentinel=bool(r["is_sentinel"]),
            )
            for r in rows
        ]
        self._brand_cache = result
        return result

    def _known_brand_ids(self) -> set[str]:
        """Cached set of brand_ids present in the `brands` table.

        The source of truth for the posts_brands_signals / posts_brands_mentions
        FK guards. Wider than KNOWN_MODELS (which is a 7-entry hardcoded
        frozenset) because it reflects whatever migration 004 seeded
        (12 brands) plus any operator-added rows. Includes the
        `_unattributed` sentinel row.
        """
        return {row.brand_id for row in self.read_brands()}

    # --- i18n (Unit 3): enum FK guards + per-locale helpers ---------------
    #
    # Cached sets of valid keys for the two enum families introduced
    # by migration 008. Used by insert_posts_brands_signals (signal)
    # and upsert_account (brands_accounts.role_id) to drop unknown values
    # to the dead-letter log BEFORE SQLite raises IntegrityError on
    # the FK.
    #
    # Cache lifecycle: populated on first call after Store.__init__.
    # Lookup-table seeds are fixed by migration 007, so the cache never
    # needs to be invalidated within a Store instance lifetime.
    # Operators who mutate the *_keys tables outside the migration
    # loader should call store.close() + re-open to refresh the cache.

    def _known_signal_keys(self) -> set[str]:
        """Legacy signal-key set.

        Migration 022 (U9) dropped the `signals` table. This method is
        kept as a stub that returns an empty set so callers (e.g.
        tests) that still import it don't crash. New code must use
        `_known_post_type_keys()` / `_known_sentiment_keys()` instead.
        """
        return set()

    def _known_role_keys(self) -> set[str]:
        """Return the set of canonical role keys (cached).

        Reads from the `roles` table (renamed from `role_keys` in
        migration 015). Used by upsert_account as the FK guard for
        brands_accounts.role_id.
        """
        if self._roles_cache is None:
            self._roles_cache = {
                r["key"]
                for r in self._conn.execute("SELECT key FROM roles").fetchall()
            }
        return self._roles_cache

    def _known_post_type_keys(self) -> set[str]:
        """Return the set of canonical post_type keys (cached).

        U9: reads from the `post_type_keys` table added by
        migration 019. Used by insert_posts_brands_signals as the FK
        guard for posts_brands_signals.post_type.
        """
        if self._post_type_cache is None:
            self._post_type_cache = {
                r["key"]
                for r in self._conn.execute(
                    "SELECT key FROM post_type_keys"
                ).fetchall()
            }
        return self._post_type_cache

    def _known_sentiment_keys(self) -> set[str]:
        """Return the set of canonical sentiment keys (cached).

        U9: reads from the `sentiment_keys` table added by
        migration 019. Used by insert_posts_brands_signals as the FK
        guard for posts_brands_signals.sentiment.
        """
        if self._sentiment_cache is None:
            self._sentiment_cache = {
                r["key"]
                for r in self._conn.execute(
                    "SELECT key FROM sentiment_keys"
                ).fetchall()
            }
        return self._sentiment_cache

    # --- U8 (migration 020): integer-id lookup helpers ---------------------
    #
    # After migration 020, every converted table's PK is an INTEGER
    # (id), and FK columns store the INTEGER id (not the TEXT slug). The
    # Store API still accepts TEXT slugs from callers (so consumer
    # code does not have to change), and converts to INTEGER id at the
    # call site via these helpers.
    #
    # All helpers return None when the slug is not in the table — the
    # caller decides what to do (skip the write, dead-letter, raise).
    # Caches are populated once per Store instance and never
    # invalidated; the lookup tables are small and seeded by
    # migrations, so the cache stays correct for the lifetime of the
    # connection. If an operator mutates a lookup table outside the
    # migration loader they should close() and re-open the Store.

    def _brand_int_id(self, brand_id: str) -> int | None:
        """Map `brand_id` (slug) to `brands.id` (INTEGER).

        Returns None if the slug is not in the brands table. Includes
        the `_unattributed` sentinel.
        """
        if self._brand_id_map is None:
            self._brand_id_map = {
                r["brand_id"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, nickname AS brand_id FROM brands"
                ).fetchall()
            }
        return self._brand_id_map.get(brand_id)

    def _company_int_id(self, company_id: str) -> int | None:
        """Map `company_id` (slug) to `companies.id` (INTEGER)."""
        if self._company_id_map is None:
            self._company_id_map = {
                r["company_id"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, nickname AS company_id FROM companies"
                ).fetchall()
            }
        return self._company_id_map.get(company_id)

    def _account_int_id(self, author_id: str) -> int | None:
        """Map `accounts.author_id` (TEXT) to `accounts.id` (INTEGER)."""
        if self._account_id_map is None:
            self._account_id_map = {
                r["author_id"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, author_id FROM accounts"
                ).fetchall()
            }
        return self._account_id_map.get(author_id)

    def _hf_org_int_id(self, namespace: str) -> int | None:
        """Map `hf_orgs.namespace` (TEXT) to `hf_orgs.id` (INTEGER).

        Note the rename in migration 020: the original TEXT PK `id`
        (HF namespace) is now the column `namespace`. Callers that
        previously passed `hf_org_id` as a namespace string now pass
        the same string under the new name.
        """
        if self._hf_org_id_map is None:
            self._hf_org_id_map = {
                r["namespace"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, namespace FROM hf_orgs"
                ).fetchall()
            }
        return self._hf_org_id_map.get(namespace)

    def _tweet_int_id(self, tweet_id: str) -> int | None:
        """Map `posts.tweet_id` (TEXT UNIQUE) to `posts.id` (INTEGER).

        NOT cached — the posts table grows with every ingest. Single
        SELECT per call; cheap because the tweet_id column is UNIQUE.
        """
        row = self._conn.execute(
            "SELECT id FROM posts WHERE tweet_id = ?", (tweet_id,)
        ).fetchone()
        return int(row["id"]) if row else None

    def _signal_int_id(self, signal_key: str) -> int | None:
        """Legacy signal-key → INTEGER-id lookup.

        Migration 022 (U9) dropped the `signals` table. This method is
        kept as a stub that returns None so callers (e.g. tests) that
        still import it don't crash. New code must use
        `_post_type_int_id()` / `_sentiment_int_id()` instead.
        """
        return None

    def _role_int_id(self, role_key: str) -> int | None:
        """Map `roles.key` (TEXT) to `roles.id` (INTEGER)."""
        if self._role_id_map is None:
            self._role_id_map = {
                r["key"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, key FROM roles"
                ).fetchall()
            }
        return self._role_id_map.get(role_key)

    def _post_type_int_id(self, post_type_key: str) -> int | None:
        """Map `post_type_keys.key` (TEXT) to `post_type_keys.id` (INTEGER)."""
        if self._post_type_id_map is None:
            self._post_type_id_map = {
                r["key"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, key FROM post_type_keys"
                ).fetchall()
            }
        return self._post_type_id_map.get(post_type_key)

    def _sentiment_int_id(self, sentiment_key: str) -> int | None:
        """Map `sentiment_keys.key` (TEXT) to `sentiment_keys.id` (INTEGER)."""
        if self._sentiment_id_map is None:
            self._sentiment_id_map = {
                r["key"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, key FROM sentiment_keys"
                ).fetchall()
            }
        return self._sentiment_id_map.get(sentiment_key)

    def _known_discourse_keys(self) -> set[str]:
        """Return the set of canonical discourse keys (cached).

        U1: reads from the `discourse_keys` table added by
        migration 025. Used by U4's parser and by
        `bulk_insert_post_brand_discourse` as the FK guard.

        The 9 valid keys are the literal set from research §2:
        genuine_hype, sarcasm, dunk_yingyang, self_deprecation, cope,
        fud, distillation_accusation, ai_slop_critique, absurdist_meme.
        The LLM's response parser coerces unknown keys to the literal
        string `uncategorized` (not in this set) — see KTD5.
        """
        if self._discourse_cache is None:
            self._discourse_cache = {
                r["key"]
                for r in self._conn.execute(
                    "SELECT key FROM discourse_keys"
                ).fetchall()
            }
        return self._discourse_cache

    def _known_nationalism_keys(self) -> set[str]:
        """Return the set of canonical nationalism keys (cached).

        U1: reads from the `nationalism_keys` table added by
        migration 025. Used by `bulk_insert_post_brand_discourse`
        and `bulk_update_nationalism` as the FK guard.

        The 6 valid keys are: none, mild_pro, pro,
        constructive_critical, anti, mixed. Shared across both
        china_nationalism and us_nationalism axes.
        """
        if self._nationalism_cache is None:
            self._nationalism_cache = {
                r["key"]
                for r in self._conn.execute(
                    "SELECT key FROM nationalism_keys"
                ).fetchall()
            }
        return self._nationalism_cache

    def _discourse_int_id(self, discourse_key: str) -> int | None:
        """Map `discourse_keys.key` (TEXT) to `discourse_keys.id` (INTEGER).

        Returns None when the key is not in the table. Caller
        decides whether to dead-letter or coerce to `uncategorized`
        before calling.
        """
        if self._discourse_id_map is None:
            self._discourse_id_map = {
                r["key"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, key FROM discourse_keys"
                ).fetchall()
            }
        return self._discourse_id_map.get(discourse_key)

    def _nationalism_int_id(self, nationalism_key: str | None) -> int | None:
        """Map `nationalism_keys.key` (TEXT) to `nationalism_keys.id` (INTEGER).

        Returns None when the key is None (intentional — nationalism
        FKs are nullable during the backfill window) or when the key
        is not in the table (caller decides coerce / dead-letter).
        """
        if nationalism_key is None:
            return None
        if self._nationalism_id_map is None:
            self._nationalism_id_map = {
                r["key"]: r["id"]
                for r in self._conn.execute(
                    "SELECT id, key FROM nationalism_keys"
                ).fetchall()
            }
        return self._nationalism_id_map.get(nationalism_key)

    def _dead_letter_enum(
        self, family: str, value: str, **context: Any
    ) -> None:
        """Append a JSONL record to the dead-letter log for unknown enum FKs.

        Migration 008 converts the enum TEXT columns (signal, role)
        into FKs pointing at *_keys tables. Any write that supplies a
        value outside the seeded set would raise IntegrityError at the
        SQLite layer. The application-level intersect-before-INSERT
        guard catches this first and writes the rejected value here so
        operators can audit dropped rows after the fact.

        File layout: `<db_path.parent>/runs/<YYYY-MM-DD>/enum_dead_letter.jsonl`.
        One file per calendar day. Created lazily on first drop.

        Args:
            family: one of "signal" / "role" / "post_type" / "sentiment".
            value: the unknown enum string that was rejected.
            **context: extra fields (table, post_id, author_id, ...) so
                the postmortem reader can find the offending row.
        """
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        run_dir = self.db_path.parent / "runs" / day
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "enum_dead_letter.jsonl"
        record = {
            "ts": _now_iso(),
            "family": family,
            "value": value,
            **context,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        _log.warning(
            "dead-letter enum: family=%s value=%r context=%r (logged to %s)",
            family, value, context, log_path,
        )

    @staticmethod
    def _pick_i18n_text(
        row: dict[str, Any], column: str, locale: str
    ) -> tuple[str | None, bool]:
        """Return `(display_text, is_translated)` for a registry row.

        Pure function: no DB access. Mirrors the shape of
        `dashboard._pick_text` (which is the post-text equivalent).

        Fallback chain (per plan D6):
            1. `<column>_<locale-suffix>` if non-NULL.
            2. `<column>_en` if non-NULL.
            3. `<column>` (source) — always present.

        The locale-to-suffix mapping mirrors dashboard._LOCALE_TO_COLUMN
        but is kept inline here so store.py stays self-contained.

        `is_translated` is False whenever the function fell back to the
        English column or the source column. Templates use the flag to
        render the "source fallback" badge.
        """
        suffix = {"en": "en", "zh-CN": "zh_cn", "zh_cn": "zh_cn"}.get(locale, "en")
        localized = row.get(f"{column}_{suffix}")
        if localized:
            return localized, True
        en_val = row.get(f"{column}_en")
        if en_val:
            return en_val, False
        return row.get(column), False

    def _pick_enum_label(
        self, family: str, value: str | None, locale: str
    ) -> str:
        """Return the localized label for an enum key, or the raw key on miss.

        Lookup order:
            1. `<family>_labels(key=?, lang=?)`
            2. `<family>_labels(key=?, lang='en')`
            3. The raw `value` (canonical English key)

        `family` must be one of "role" / "post_type" / "sentiment".
        The "signal" family was removed in migration 022 (U9) — the
        `signal_labels` table was dropped along with the legacy 6-signal
        taxonomy.
        Unknown family raises ValueError. Returns "" when value is
        None/empty (templates render nothing for missing enum labels).
        """
        if value is None or value == "":
            return ""
        labels_table = {
            "role": "role_labels",
            "post_type": "post_type_labels",
            "sentiment": "sentiment_labels",
        }.get(family)
        if labels_table is None:
            raise ValueError(
                f"unknown enum family {family!r}; expected "
                "'role' / 'post_type' / 'sentiment'"
            )
        suffix = {"en": "en", "zh-CN": "zh_cn", "zh_cn": "zh_cn"}.get(locale, "en")
        row = self._conn.execute(
            f"SELECT label FROM {labels_table} WHERE key = ? AND lang = ?",
            (value, suffix),
        ).fetchone()
        if row is not None:
            return row["label"]
        if suffix != "en":
            row = self._conn.execute(
                f"SELECT label FROM {labels_table} WHERE key = ? AND lang = 'en'",
                (value,),
            ).fetchone()
            if row is not None:
                return row["label"]
        return value

    def read_companies(self) -> list["CompanyRow"]:
        """Return all rows from the `companies` table.

        No cache (low cardinality: ~10 rows) — re-query on each call.
        Used by `hf_products.collect_all` to walk the 1:N companies→HF-orgs
        edge.
        """
        rows = self._conn.execute(
            """
            SELECT nickname AS company_id, display_name, hq_country
            FROM companies
            ORDER BY display_name
            """
        ).fetchall()
        return [
            CompanyRow(
                company_id=r["company_id"],
                display_name=r["display_name"],
                hq_country=r["hq_country"],
            )
            for r in rows
        ]

    def read_brands_companies_for_company(
        self, company_id: str
    ) -> list[str]:
        """Return the brand_ids that belong to `company_id` via brands_companies.

        Brands without a brands_companies edge (e.g. `_unattributed`) are
        never returned — they're corporate-parent-less and intentionally
        excluded from HF coverage.

        U8 (migration 020): brands_companies.brand_id and company_id
        are INTEGER. JOIN back to the parent tables to return the TEXT
        brand_id slugs the caller expects.
        """
        rows = self._conn.execute(
            """
            SELECT b.nickname AS brand_id
            FROM brands_companies bc
            JOIN brands b   ON b.id = bc.brand_id
            JOIN companies c ON c.id = bc.company_id
            WHERE c.nickname = ?
            ORDER BY b.nickname
            """,
            (company_id,),
        ).fetchall()
        return [r["brand_id"] for r in rows]

    def read_brands_accounts(self) -> dict[str, str]:
        """Return {author_id: brand_id} for all brand-account edges (R13).

        Consumed by `attribution.extract_user_mentions` to resolve
        `entities.user_mentions[].id` (numeric X user id) to a
        `brand_id`.

        U8 (migration 020) + U6 (migration 031):
        `brands_accounts.accounts_id` is INTEGER (FK to accounts.id) and
        `brands_accounts.brand_id` is INTEGER (FK to brands.id). JOIN
        both back to the source tables to recover the TEXT identities
        the caller cares about — the X user id
        (`accounts.author_id`) and the brand slug (`brands.nickname`).
        """
        rows = self._conn.execute(
            """
            SELECT a.author_id, b.nickname AS brand_id
            FROM brands_accounts ba
            JOIN accounts a ON a.id = ba.accounts_id
            JOIN brands b   ON b.id = ba.brand_id
            """
        ).fetchall()
        return {r["author_id"]: r["brand_id"] for r in rows}

    def read_brand_hashtags(self) -> dict[str, str]:
        """Return {tag: brand_id} for all brand_hashtags rows (R13).

        Keys are stored lowercase (per migration 004). The attribution
        extractor also lowercases the entity tag before lookup.
        """
        rows = self._conn.execute(
            "SELECT tag, brand_id FROM brand_hashtags"
        ).fetchall()
        return {r["tag"]: r["brand_id"] for r in rows}

    def read_brand_keywords(self) -> list[tuple[str, str, bool]]:
        """Return [(brand_id, pattern, is_regex)] for all brand_keywords (R13).

        Consumed by `attribution.extract_body_keywords` to build a
        compiled-regex index. `is_regex` is a SQLite INTEGER (0/1);
        converted to bool here.
        """
        rows = self._conn.execute(
            "SELECT brand_id, pattern, is_regex FROM brand_keywords"
        ).fetchall()
        return [
            (r["brand_id"], r["pattern"], bool(r["is_regex"])) for r in rows
        ]

    def read_brand_search_terms(self) -> dict[str, str]:
        """Return {term: brand_id} for all brand_search_terms (R13).

        Consumed by `attribution.extract_search_term_match` to resolve
        each search-query keyword to a brand_id.

        U8 (migration 020): brand_search_terms.brand_id is INTEGER
        (FK to brands.id). JOIN back to brands to return the TEXT
        brand_id slug the caller expects.
        """
        rows = self._conn.execute(
            """
            SELECT bst.term, b.nickname AS brand_id
            FROM brand_search_terms bst
            JOIN brands b ON b.id = bst.brand_id
            """
        ).fetchall()
        return {r["term"]: r["brand_id"] for r in rows}

    def read_hf_orgs(
        self, company_id: str, *, confirmed_only: bool = True
    ) -> list[dict[str, Any]]:
        """Return the company's HuggingFace org rows from `hf_orgs`.

        Each row is a dict: {namespace, company_id, confirmed,
        discovered_via, added_at}. With `confirmed_only=True` (default)
        only curated/operator-confirmed orgs are returned — the orgs
        the crawler scrapes. Discovered candidates (confirmed=0) are
        excluded so a wrong org is never silently scraped.

        U8 (migration 020): the HF namespace string lives in the
        `namespace` column (renamed from the original `id` TEXT PK to
        avoid the type-changing-same-name ambiguity). The `id` column
        is now the INTEGER surrogate PK. Callers receive `namespace`
        in the dict (the public identity of the org), not `id`.
        """
        sql = (
            "SELECT namespace, company_id, confirmed, discovered_via, added_at "
            "FROM hf_orgs WHERE company_id = ?"
        )
        if confirmed_only:
            sql += " AND confirmed = 1"
        sql += " ORDER BY namespace"
        rows = self._conn.execute(sql, (company_id,)).fetchall()
        return [dict(r) for r in rows]

    def upsert_hf_org(
        self,
        hf_org_id: str,
        company_id: str,
        *,
        confirmed: int = 0,
        discovered_via: str = "search",
    ) -> None:
        """Insert a company→HF-org edge, or update without downgrading.

        Discovery uses confirmed=0 (candidates flagged for operator review).
        On conflict, `confirmed` is never demoted (a curated/confirmed org
        survives a re-discovery) and a `curated` provenance is preserved.
        `hf_org_id` is the HF namespace string itself (e.g. "MiniMaxAI"),
        which lives in the `namespace` column (renamed from the
        pre-U8 TEXT PK `id` per migration 020). The INTEGER surrogate
        PK `id` is auto-assigned by SQLite. The FK to `companies.id`
        is INTEGER-storing-id, so the company_id slug is resolved
        here before the INSERT.
        """
        company_id_int = self._company_int_id(company_id)
        if company_id_int is None:
            raise ValueError(
                f"upsert_hf_org: company_id={company_id!r} not in companies table"
            )
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO hf_orgs (
                    namespace, company_id, confirmed, discovered_via, added_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(namespace) DO UPDATE SET
                    company_id = excluded.company_id,
                    confirmed = CASE
                        WHEN excluded.confirmed > hf_orgs.confirmed
                        THEN excluded.confirmed
                        ELSE hf_orgs.confirmed
                    END,
                    discovered_via = CASE
                        WHEN hf_orgs.discovered_via = 'curated'
                        THEN hf_orgs.discovered_via
                        ELSE excluded.discovered_via
                    END
                """,
                (hf_org_id, company_id_int, confirmed, discovered_via, _now_iso()),
            )

    def upsert_product(self, row: dict[str, Any]) -> None:
        """Insert a product row, or refresh mutable stats on conflict (repo_id PK).

        `row` must carry every product column. On conflict only the mutable
        stats refresh (downloads, downloads_all_time, download_velocity, likes,
        trending_score, last_modified, *_json, raw_json, updated_at); brand_id,
        hf_org_id, hf_type, display_name, collected_at stay stable so re-runs are
        idempotent and a brand assignment survives a refresh.

        U8 (migration 020): `brand_id` and `hf_org_id` are now INTEGER
        FKs. The public row dict still carries the TEXT slugs
        (brand_id=slug, hf_org_id=namespace string) — this method
        resolves them to INTEGER ids before the INSERT. NULLs in the
        input row are preserved (the brand_id / hf_org_id columns
        accept NULL with ON DELETE SET NULL semantics).
        """
        cols = [
            "repo_id", "brand_id", "hf_org_id", "hf_type", "display_name", "author",
            "sha", "private", "gated", "disabled", "pipeline_tag", "library_name",
            "downloads", "downloads_all_time", "download_velocity", "likes",
            "trending_score", "paperswithcode_id", "created_at", "last_modified",
            "tags_json", "siblings_json", "card_data_json", "config_json",
            "spaces_json", "raw_json", "collected_at", "updated_at",
        ]
        mutable = {
            "downloads", "downloads_all_time", "download_velocity", "likes",
            "trending_score", "last_modified", "tags_json", "siblings_json",
            "card_data_json", "config_json", "spaces_json", "raw_json", "updated_at",
        }
        assert set(mutable) <= set(cols), "mutable references unknown product column"
        set_clause = ", ".join(f"{c}=excluded.{c}" for c in cols if c in mutable)
        sql = (
            f"INSERT INTO products ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT(repo_id) DO UPDATE SET {set_clause}"
        )
        # Resolve brand_id and hf_org_id to INTEGER ids (or None).
        # Other columns pass through unchanged.
        brand_id = row.get("brand_id")
        hf_org_id = row.get("hf_org_id")
        brand_id_int: int | None = (
            self._brand_int_id(brand_id) if brand_id else None
        )
        hf_org_id_int: int | None = (
            self._hf_org_int_id(hf_org_id) if hf_org_id else None
        )
        values = list(row.get(c) for c in cols)
        # Substitute the INTEGER ids at the brand_id / hf_org_id
        # positions so the INSERT writes the right type.
        values[cols.index("brand_id")] = brand_id_int
        values[cols.index("hf_org_id")] = hf_org_id_int
        with self.transaction() as conn:
            conn.execute(sql, tuple(values))

    def read_products(
        self, brand_id: str | None = None, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Return product rows, optionally filtered by brand, downloads-desc.

        `brand_id` is the TEXT slug (e.g. "MiniMaxAI") — the public
        identity. The method resolves it to the INTEGER id before the
        WHERE filter, so callers don't need to know about U8's
        INTEGER-PK conversion.
        """
        sql = "SELECT * FROM products"
        params: tuple[Any, ...] = ()
        if brand_id is not None:
            brand_id_int = self._brand_int_id(brand_id)
            if brand_id_int is None:
                # Unknown brand slug → no products.
                return []
            sql += " WHERE brand_id = ?"
            params = (brand_id_int,)
        sql += " ORDER BY downloads DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params = params + (limit,)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

__all__ = [
    # Dataclasses
    "BrandRow",
    "CompanyRow",
    # Core
    "Store",
]
