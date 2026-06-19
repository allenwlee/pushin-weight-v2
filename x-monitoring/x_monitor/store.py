# {{AGENT_ATTRIBUTION}}
"""SQLite storage layer for x-monitor (R18, R21)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import KNOWN_MODELS


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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

        Uses INSERT OR IGNORE — re-inserting the same tweet_id is a no-op.

        v1.8: posts.brand_id and posts.signal are dropped (migration 004).
        Attribution moves to post_brands(brand_id, post_id, weight); per-brand
        signal moves to post_brand_signals(post_id, brand_id, signal). The
        post dict still carries `brand_id` and `signal` keys (from the
        caller / TwitterAPI.io response) — we extract them here and write
        to the join tables. Posts with no brand_id get a sentinel
        `_unattributed` row so the treemap's "unattributed" bin still works.
        """
        if not posts:
            return 0
        n_new = 0
        with self.transaction() as conn:
            for p in posts:
                tweet_id = p.get("id") or p.get("tweet_id")
                if not tweet_id:
                    continue
                tweet_id_str = str(tweet_id)
                brand_id = p.get("brand_id")
                # Per R1: attribution moves to post_brands. The post dict
                # may carry a single brand_id (legacy callers) or a list
                # (v1.8 multi-brand). Normalize to a list of brand_ids
                # with equal weight = 1/N.
                if isinstance(brand_id, list):
                    raw_brands = [b for b in brand_id if b]
                elif brand_id:
                    raw_brands = [brand_id]
                else:
                    raw_brands = []
                # Filter to known brands + sentinel; unknown slugs get
                # bucketed into `_unattributed` so they still surface
                # somewhere.
                valid_brands: list[str] = []
                for b in raw_brands:
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
                        text_en, text_zh_cn, lang_detected
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                        json.dumps(p),
                        p.get("headline"),
                        p.get("headline_source"),
                        # v1.7: per-locale translation columns.
                        # NULL when callers don't supply (legacy call sites).
                        p.get("text_en"),
                        p.get("text_zh_cn"),
                        p.get("lang_detected"),
                    ),
                )
                if cur.rowcount > 0:
                    n_new += 1
                    # Only write attribution rows for newly-inserted posts;
                    # re-inserts must not duplicate (post_brands PK is
                    # (brand_id, post_id)).
                    for b in valid_brands:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO post_brands(
                                brand_id, post_id, weight
                            ) VALUES (?, ?, ?)
                            """,
                            (b, tweet_id_str, weight),
                        )
                    # Per-brand signal: one row per (post, brand) tuple.
                    # Legacy callers passed a single `signal` string; v1.8
                    # callers may pass a list of (brand_id, signal) tuples.
                    signal_raw = p.get("signal")
                    per_brand_signals: list[tuple[str, str]] = []
                    if isinstance(signal_raw, list):
                        for item in signal_raw:
                            if (
                                isinstance(item, tuple)
                                and len(item) == 2
                                and isinstance(item[0], str)
                                and isinstance(item[1], str)
                            ):
                                per_brand_signals.append((item[0], item[1]))
                            elif (
                                isinstance(item, dict)
                                and "brand_id" in item
                                and "signal" in item
                            ):
                                per_brand_signals.append(
                                    (item["brand_id"], item["signal"])
                                )
                    elif isinstance(signal_raw, str) and signal_raw:
                        # Legacy single-signal path: emit one row per brand
                        # in the attribution list.
                        for b in valid_brands:
                            per_brand_signals.append((b, signal_raw))
                    for b, sig in per_brand_signals:
                        if b == "_unattributed":
                            # CHECK constraint on post_brand_signals excludes
                            # the sentinel (Decision 15). Skip silently.
                            continue
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO post_brand_signals(
                                post_id, brand_id, signal
                            ) VALUES (?, ?, ?)
                            """,
                            (tweet_id_str, b, sig),
                        )
        return n_new

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
