# {{AGENT_ATTRIBUTION}}
"""SQLite storage layer for x-monitor (R18, R21)."""

from __future__ import annotations

import json
import logging
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
        # Per-insert_posts counters, read by the cron caller to surface
        # in summary.totals. Reset at the start of each insert_posts call.
        self._signals_written: int = 0
        self._signals_dropped: int = 0

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
            newly.append(version)
        return newly

    # --- posts ------------------------------------------------------------

    def insert_posts(self, posts: list[dict[str, Any]]) -> int:
        """Idempotent insert. Returns number of NEWLY inserted rows.

        v1.8 (R16): writes to 4 tables in ONE transaction (posts,
        post_brands, post_mentions, post_brand_signals). Re-inserting
        the same tweet_id is a no-op (INSERT OR IGNORE on posts).

        Per-post dict fields (R2, R3, R6, R8, R15, R16):
          - brand_ids: list[str]     (v1.8 multi-brand)
          - mentions: list[MentionRow] (4-source decomposition)
          - signals: dict[brand_id, signal] (per-brand signal)

        Backward-compat: if `brand_id` (str|list) and/or `signal` (str|
        list[dict|tuple]) are present, derive v1.8 fields from them so
        legacy callers (Unit 3) continue to work.

        Posts with no brand_id get a sentinel `_unattributed` row in
        post_brands so the treemap's "unattributed" bin still works.
        `_unattributed` is BLOCKED from post_brand_signals by the
        schema's CHECK constraint (Decision 15).
        """
        if not posts:
            return 0
        # Source of truth for the post_brand_signals / post_mentions FK
        # guards: the brand_ids actually present in the `brands` table
        # (cached). This is wider than the per-post `valid_brands` list
        # (which is brand_ids ∩ KNOWN_MODELS) so cross-mention signals
        # and v1.8 brands (mistral/stepfun/ernie/hunyuan) are not
        # dropped. See store._known_brand_ids().
        known_ids: set[str] = self._known_brand_ids()
        # Reset per-call counters so the caller reads only this call's
        # write/drop totals.
        self._signals_written = 0
        self._signals_dropped = 0
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
                        p.get("author_id"),
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
                    # Only write attribution rows for newly-inserted posts;
                    # re-inserts must not duplicate (post_brands PK is
                    # (brand_id, post_id)).
                    for b in valid_brands:
                        # R9: ON CONFLICT DO UPDATE so reattribution can
                        # refresh weight. The `weight` column MUST be in
                        # the INSERT column list (top-gun ON CONFLICT
                        # gotcha — only INSERT-listed columns update).
                        conn.execute(
                            """
                            INSERT INTO post_brands(
                                brand_id, post_id, weight
                            ) VALUES (?, ?, ?)
                            ON CONFLICT(brand_id, post_id) DO UPDATE SET
                                weight = excluded.weight
                            """,
                            (b, tweet_id_str, weight),
                        )
                    # Per-brand signals: v1.8 callers pass signals as a
                    # dict[brand_id, signal]. Legacy callers pass a
                    # single `signal` string OR a list of
                    # (brand_id, signal) tuples.
                    per_brand_signals: list[tuple[str, str]] = (
                        self._extract_per_brand_signals(p, valid_brands)
                    )
                    for b, sig in per_brand_signals:
                        if b == "_unattributed":
                            # CHECK constraint on post_brand_signals
                            # excludes the sentinel (Decision 15). Skip.
                            continue
                        # Guard against LLM hallucinations: per_brand_signals
                        # comes from the LLM and may contain a brand_id not
                        # in the brands table. Checked against the
                        # brands-table source of truth (known_ids), NOT the
                        # per-post valid_brands, so cross-mention signals
                        # survive. Regression: cron hot path crashed at this
                        # site on 2026-06-20 (cycle 20260620T081403_0000-).
                        if b not in known_ids:
                            self._signals_dropped += 1
                            _log.warning(
                                "insert_posts: dropping signal for "
                                "brand_id=%r not in brands table "
                                "(post_id=%s signal=%r)",
                                b, tweet_id_str, sig,
                            )
                            continue
                        # R11: ON CONFLICT DO UPDATE.
                        conn.execute(
                            """
                            INSERT INTO post_brand_signals(
                                post_id, brand_id, signal
                            ) VALUES (?, ?, ?)
                            ON CONFLICT(post_id, brand_id) DO UPDATE SET
                                signal = excluded.signal
                            """,
                            (tweet_id_str, b, sig),
                        )
                        self._signals_written += 1
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
                        # post_mentions.brand_id may be NULL (un-attributed
                        # user mentions). Only guard non-null unknowns
                        # against the same FK (migration 004:117).
                        if m_brand is not None and m_brand not in known_ids:
                            _log.warning(
                                "insert_posts: dropping mention for "
                                "brand_id=%r not in brands table "
                                "(post_id=%s source=%r)",
                                m_brand, tweet_id_str, m_source,
                            )
                            continue
                        conn.execute(
                            """
                            INSERT INTO post_mentions(
                                post_id, brand_id, source, raw_token, mentioned_at
                            ) VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(post_id, brand_id, source) DO UPDATE SET
                                raw_token = excluded.raw_token
                            """,
                            (
                                tweet_id_str,
                                m_brand,
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

    def _extract_per_brand_signals(
        self, p: dict[str, Any], valid_brands: list[str]
    ) -> list[tuple[str, str]]:
        """Normalize the post dict's signal field(s) to list[(brand_id, signal)].

        v1.8 callers pass `signals: dict[brand_id, signal]`. Legacy
        callers pass `signal: str | list[(brand_id, signal)] | list[dict]`.
        The legacy single-string path emits one signal per brand in
        `valid_brands`.
        """
        if "signals" in p and isinstance(p["signals"], dict) and p["signals"]:
            return [(b, s) for b, s in p["signals"].items() if b and s]
        signal_raw = p.get("signal")
        per_brand: list[tuple[str, str]] = []
        if isinstance(signal_raw, list):
            for item in signal_raw:
                if (
                    isinstance(item, tuple)
                    and len(item) == 2
                    and isinstance(item[0], str)
                    and isinstance(item[1], str)
                ):
                    per_brand.append((item[0], item[1]))
                elif (
                    isinstance(item, dict)
                    and "brand_id" in item
                    and "signal" in item
                ):
                    per_brand.append((item["brand_id"], item["signal"]))
        elif isinstance(signal_raw, str) and signal_raw:
            # Legacy single-signal path: emit one row per brand.
            for b in valid_brands:
                per_brand.append((b, signal_raw))
        return per_brand

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
        # moves to post_brands(brand_id, post_id, weight). We pick any
        # one brand_id per post (the first by lexicographic brand_id) so
        # the translation pipeline still has SOME brand to attribute
        # the post to for translation-prompt context. The translation
        # itself does not need multi-brand precision.
        rows = self._conn.execute(
            f"""
            SELECT p.tweet_id, pb.brand_id, p.text, p.author_handle, p.created_at
            FROM posts p
            JOIN post_brands pb ON pb.post_id = p.tweet_id
            WHERE p.{col} IS NULL
            ORDER BY p.created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_posts_for_digest(
        self, brand_id: str, since_iso: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # v1.8: posts.brand_id is dropped (migration 004). Attribution
        # moves to post_brands(brand_id, post_id, weight). The returned
        # dicts keep the `brand_id` key (with weight on the side) so
        # downstream code that does `p.get("brand_id")` continues to
        # work unchanged.
        if since_iso:
            rows = self._conn.execute(
                """
                SELECT p.*, pb.weight
                FROM posts p
                JOIN post_brands pb ON pb.post_id = p.tweet_id
                WHERE pb.brand_id = ? AND p.created_at >= ?
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (brand_id, since_iso, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT p.*, pb.weight
                FROM posts p
                JOIN post_brands pb ON pb.post_id = p.tweet_id
                WHERE pb.brand_id = ?
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (brand_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_posts(self, brand_id: str) -> list[dict[str, Any]]:
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # The `created_at` column is TEXT and may hold either ISO 8601 or
        # Twitter legacy (e.g. "Wed Jun 10 21:31:32 +0000 2026"). A SQL
        # `ORDER BY created_at DESC` on the latter is lexicographic, not
        # chronological (Wed > Mon, "10" > "09"), which makes the model
        # detail page render 5-day-old posts at the top. Sort in Python by
        # parsed timestamp instead.
        #
        # v1.8: posts.brand_id is dropped (migration 004); JOIN post_brands
        # to filter by brand.
        rows = self._conn.execute(
            """
            SELECT p.*, pb.weight
            FROM posts p
            JOIN post_brands pb ON pb.post_id = p.tweet_id
            WHERE pb.brand_id = ?
            """,
            (brand_id,),
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
        engagement_tier: str = "low",
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
        per-brand role now lives in `brand_accounts(brand_id, author_id,
        role)`. The `multi_brand_voice` column is dropped (R12) — that
        derivation moves to a query against brand_accounts.

        For callers that don't have a real author_id (yaml-derived accounts
        in `data/brands/<brand>/accounts.yaml`), we synthesize a stable
        `handle:<handle>` author_id so re-upserts hit the same row.
        """
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        author_id = f"handle:{handle}"
        now = _now_iso()
        # Upsert into accounts (author_id PK). We drop multi_brand_voice
        # silently — v1.8 callers can stop passing it; old callers passing
        # it just see the kwarg ignored.
        self._conn.execute(
            """
            INSERT INTO accounts(
                author_id, handle, display_name, verified,
                bio_contains_brand, engagement_tier,
                first_seen_at, last_seen_at, source_query_ids, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(author_id) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, accounts.display_name),
                verified = MAX(accounts.verified, excluded.verified),
                bio_contains_brand = MAX(accounts.bio_contains_brand, excluded.bio_contains_brand),
                engagement_tier = excluded.engagement_tier,
                last_seen_at = excluded.last_seen_at,
                source_query_ids = excluded.source_query_ids,
                notes = COALESCE(excluded.notes, accounts.notes)
            """,
            (
                author_id,
                handle,
                display_name,
                int(verified),
                int(bio_contains_brand),
                engagement_tier,
                now,
                now,
                json.dumps(source_query_ids or []),
                notes,
            ),
        )
        # Upsert the per-brand edge in brand_accounts (the per-brand role).
        self._conn.execute(
            """
            INSERT INTO brand_accounts(
                brand_id, author_id, role, added_at
            ) VALUES (?,?,?,?)
            ON CONFLICT(brand_id, author_id) DO UPDATE SET
                role = excluded.role
            """,
            (brand_id, author_id, role, now),
        )

    def get_account(self, brand_id: str, handle: str) -> dict[str, Any] | None:
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # v1.8: JOIN brand_accounts so we can return the per-brand role
        # alongside the account row.
        row = self._conn.execute(
            """
            SELECT a.*, ba.role
            FROM accounts a
            JOIN brand_accounts ba ON ba.author_id = a.author_id
            WHERE ba.brand_id = ? AND a.handle = ?
            """,
            (brand_id, handle),
        ).fetchone()
        return dict(row) if row else None

    def get_accounts(self, brand_id: str) -> list[dict[str, Any]]:
        if brand_id not in KNOWN_MODELS:
            raise ValueError(f"unknown brand_id '{brand_id}'")
        # v1.8: accounts no longer has brand_id. The per-brand accounts
        # live behind brand_accounts JOIN.
        rows = self._conn.execute(
            """
            SELECT a.*, ba.role
            FROM accounts a
            JOIN brand_accounts ba ON ba.author_id = a.author_id
            WHERE ba.brand_id = ?
            """,
            (brand_id,),
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

    def insert_post_brands(self, post_id: str, brand_id: str, weight: float) -> None:
        """Upsert one row into post_brands (R9).

        ON CONFLICT(brand_id, post_id) DO UPDATE SET weight = excluded.weight
        per Decision 14 — reattribution MUST overwrite stale weights when
        the detection registry evolves.

        Top-gun ON CONFLICT gotcha: the `weight` column MUST be in the
        INSERT column list (the SET clause can only update columns the
        INSERT actually wrote).
        """
        self._conn.execute(
            """
            INSERT INTO post_brands(brand_id, post_id, weight)
            VALUES (?, ?, ?)
            ON CONFLICT(brand_id, post_id) DO UPDATE SET
                weight = excluded.weight
            """,
            (brand_id, post_id, float(weight)),
        )

    def insert_post_mentions(
        self,
        post_id: str,
        brand_id: str | None,
        source: str,
        raw_token: str,
        mentioned_at: str,
    ) -> None:
        """Upsert one row into post_mentions (R10).

        ON CONFLICT(post_id, brand_id, source) DO UPDATE SET
        raw_token = excluded.raw_token.

        `brand_id` may be NULL (un-attributed user mentions preserved
        with raw_token for later backfill). The PK allows NULLs in
        non-INTEGER-PRIMARY-KEY columns.

        Top-gun ON CONFLICT gotcha: the `raw_token` column MUST be in
        the INSERT column list.
        """
        self._conn.execute(
            """
            INSERT INTO post_mentions(
                post_id, brand_id, source, raw_token, mentioned_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(post_id, brand_id, source) DO UPDATE SET
                raw_token = excluded.raw_token
            """,
            (post_id, brand_id, source, raw_token, mentioned_at),
        )

    def insert_post_brand_signals(
        self, post_id: str, brand_id: str, signal: str
    ) -> None:
        """Upsert one row into post_brand_signals (R11).

        ON CONFLICT(post_id, brand_id) DO UPDATE SET signal = excluded.signal.

        `_unattributed` is BLOCKED by the schema's CHECK constraint
        (Decision 15). Passes a non-sentinel brand_id.

        Top-gun ON CONFLICT gotcha: the `signal` column MUST be in the
        INSERT column list.

        Guards brand_id against the brands table (the FK target) so the
        reattribute path can't raise IntegrityError. Unknown brand_ids
        are dropped with a warning rather than aborting the caller's
        transaction.
        """
        if brand_id not in self._known_brand_ids():
            _log.warning(
                "insert_post_brand_signals: dropping signal for "
                "brand_id=%r not in brands table (post_id=%s)",
                brand_id, post_id,
            )
            return
        self._conn.execute(
            """
            INSERT INTO post_brand_signals(post_id, brand_id, signal)
            VALUES (?, ?, ?)
            ON CONFLICT(post_id, brand_id) DO UPDATE SET
                signal = excluded.signal
            """,
            (post_id, brand_id, signal),
        )

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
            SELECT brand_id, display_name, accent_color, is_sentinel
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

        The source of truth for the post_brand_signals / post_mentions
        FK guards. Wider than KNOWN_MODELS (which is a 7-entry hardcoded
        frozenset) because it reflects whatever migration 004 seeded
        (12 brands) plus any operator-added rows. Includes the
        `_unattributed` sentinel row.
        """
        return {row.brand_id for row in self.read_brands()}

    def read_brand_accounts(self) -> dict[str, str]:
        """Return {author_id: brand_id} for all brand-account edges (R13).

        Consumed by `attribution.extract_user_mentions` to resolve
        `entities.user_mentions[].id` (numeric X user id) to a
        `brand_id`.
        """
        rows = self._conn.execute(
            "SELECT author_id, brand_id FROM brand_accounts"
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
        """
        rows = self._conn.execute(
            "SELECT term, brand_id FROM brand_search_terms"
        ).fetchall()
        return {r["term"]: r["brand_id"] for r in rows}

__all__ = [
    # Dataclasses
    "BrandRow",
    # Core
    "Store",
]
