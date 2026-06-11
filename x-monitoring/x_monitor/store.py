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
        """
        if not posts:
            return 0
        n_new = 0
        with self.transaction() as conn:
            for p in posts:
                tweet_id = p.get("id") or p.get("tweet_id")
                if not tweet_id:
                    continue
                model_id = p.get("model_id")
                if model_id not in KNOWN_MODELS:
                    continue
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO posts(
                        tweet_id, model_id, author_handle, author_id, text, lang,
                        created_at, fetched_at, favorite_count, retweet_count,
                        reply_count, quote_count, in_reply_to_user_id,
                        quoted_status_id, conversation_id, entities,
                        source_query_id, raw, headline, headline_source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        str(tweet_id),
                        model_id,
                        p.get("author_handle") or p.get("author_id") or "",
                        p.get("author_id"),
                        p.get("text"),
                        p.get("lang"),
                        p.get("created_at"),
                        _now_iso(),
                        int(p.get("favorite_count") or 0),
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
                    ),
                )
                if cur.rowcount > 0:
                    n_new += 1
        return n_new

    def get_posts_for_digest(
        self, model_id: str, since_iso: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        if model_id not in KNOWN_MODELS:
            raise ValueError(f"unknown model_id '{model_id}'")
        if since_iso:
            rows = self._conn.execute(
                """
                SELECT * FROM posts
                WHERE model_id = ? AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (model_id, since_iso, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM posts
                WHERE model_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (model_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_posts(self, model_id: str) -> list[dict[str, Any]]:
        if model_id not in KNOWN_MODELS:
            raise ValueError(f"unknown model_id '{model_id}'")
        rows = self._conn.execute(
            "SELECT * FROM posts WHERE model_id = ? ORDER BY created_at DESC",
            (model_id,),
        ).fetchall()
        return [dict(r) for r in rows]

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
        model_id: str,
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
        if model_id not in KNOWN_MODELS:
            raise ValueError(f"unknown model_id '{model_id}'")
        now = _now_iso()
        self._conn.execute(
            """
            INSERT INTO accounts(
                model_id, handle, display_name, role, verified,
                bio_contains_brand, engagement_tier, multi_brand_voice,
                first_seen_at, last_seen_at, source_query_ids, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(model_id, handle) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, accounts.display_name),
                role = excluded.role,
                verified = MAX(accounts.verified, excluded.verified),
                bio_contains_brand = MAX(accounts.bio_contains_brand, excluded.bio_contains_brand),
                engagement_tier = excluded.engagement_tier,
                multi_brand_voice = MAX(accounts.multi_brand_voice, excluded.multi_brand_voice),
                last_seen_at = excluded.last_seen_at,
                source_query_ids = excluded.source_query_ids,
                notes = COALESCE(excluded.notes, accounts.notes)
            """,
            (
                model_id,
                handle,
                display_name,
                role,
                int(verified),
                int(bio_contains_brand),
                engagement_tier,
                int(multi_brand_voice),
                now,
                now,
                json.dumps(source_query_ids or []),
                notes,
            ),
        )

    def get_account(self, model_id: str, handle: str) -> dict[str, Any] | None:
        if model_id not in KNOWN_MODELS:
            raise ValueError(f"unknown model_id '{model_id}'")
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE model_id = ? AND handle = ?",
            (model_id, handle),
        ).fetchone()
        return dict(row) if row else None

    def get_accounts(self, model_id: str) -> list[dict[str, Any]]:
        if model_id not in KNOWN_MODELS:
            raise ValueError(f"unknown model_id '{model_id}'")
        rows = self._conn.execute(
            "SELECT * FROM accounts WHERE model_id = ?", (model_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- appearances ------------------------------------------------------

    def record_appearance(
        self, model_id: str, handle: str, tweet_id: str, role_at_time: str | None = None
    ) -> None:
        # FK enforces that both (model_id, handle) and tweet_id exist; ignore
        # silently on FK violation since the pipeline can call this before
        # the account is upserted in some races — caller should upsert first.
        try:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO account_post_appearances(
                    model_id, handle, tweet_id, role_at_time
                ) VALUES (?,?,?,?)
                """,
                (model_id, handle, tweet_id, role_at_time),
            )
        except sqlite3.IntegrityError:
            pass
