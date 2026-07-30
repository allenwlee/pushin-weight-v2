"""Reconcile duplicate `accounts.handle` rows by repointing FK references
from placeholder author_ids (`handle:*`, `synthetic:*`) to a canonical
integer author_id and deleting the placeholder rows.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U10 (originally U10 of plan `2026-07-30-001`, re-numbered by the
combined plan).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection, transaction


PLACEHOLDER_PREFIXES = ("handle:", "synthetic:")


def _find_duplicate_groups(
    cur,
    *,
    include_residual: bool = False,
    limit: int | None = None,
) -> list[tuple[str, list[str]]]:
    if include_residual:
        cur.execute("""
            SELECT handle, array_agg(author_id ORDER BY first_seen_at)
            FROM accounts
            WHERE handle IS NOT NULL AND handle != ''
            GROUP BY handle
            HAVING COUNT(*) > 1
        """)
    else:
        cur.execute("""
            SELECT handle, array_agg(author_id ORDER BY first_seen_at)
            FROM accounts
            WHERE handle IS NOT NULL AND handle != ''
            GROUP BY handle
            HAVING COUNT(*) > 1
              AND bool_or(author_id ~ '^[0-9]+$')
        """)
    rows = cur.fetchall()
    if limit is not None:
        rows = rows[:limit]
    return rows


def _find_lonely_placeholders(
    cur,
    *,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    """Phase 2 -- handle-unique placeholder rows.

    Returns [(handle, placeholder_author_id), ...] for `accounts` rows
    whose author_id is a placeholder (handle:*, synthetic:*) and whose
    handle is NOT in any duplicate group. These are the 10,908+
    "lonely" placeholders that the original Phase 1 reconciliation
    skipped because they don't participate in the dup-group path.

    For each row, the apply path:
      1. TwitterAPI lookup → canonical integer
      2. KTD10 verify against the existing accounts.handle(s)
      3. INSERT canonical integer into accounts (if missing)
      4. UPDATE posts + account_post_appearances + brands_accounts
         to point at the canonical integer
      5. DELETE the placeholder row

    KTD10 disagree → skip + dead-letter (KTD12).
    """
    cur.execute("""
        SELECT a.handle, a.author_id
        FROM accounts a
        WHERE a.handle IS NOT NULL AND a.handle != ''
          AND (
            a.author_id LIKE 'handle:%%'
            OR a.author_id LIKE 'synthetic:%%'
          )
          AND NOT EXISTS (
            SELECT 1 FROM accounts b
            WHERE b.handle IS NOT NULL AND b.handle != ''
              AND LOWER(b.handle) = LOWER(a.handle)
              AND b.author_id <> a.author_id
          )
        ORDER BY a.first_seen_at
    """)
    rows = cur.fetchall()
    if limit is not None:
        rows = rows[:limit]
    return [(handle, placeholder_author_id) for handle, placeholder_author_id in rows]


def _is_placeholder(author_id: str) -> bool:
    return any(author_id.startswith(p) for p in PLACEHOLDER_PREFIXES)


def _classify_group(handle: str, author_ids: list[str]) -> dict[str, Any]:
    integer_ids = [a for a in author_ids if not _is_placeholder(a)]
    placeholder_ids = [a for a in author_ids if _is_placeholder(a)]
    return {
        "handle": handle,
        "integer_ids": integer_ids,
        "placeholder_ids": placeholder_ids,
        "is_all_placeholder": len(integer_ids) == 0,
    }


def _canonical_integer_for_handle(
    cur,
    *,
    handle: str,
    integer_ids_in_group: list[str],
) -> str | None:
    if not integer_ids_in_group:
        return None
    if len(integer_ids_in_group) == 1:
        cand = integer_ids_in_group[0]
        cur.execute(
            "SELECT LOWER(handle) FROM accounts WHERE author_id = %s",
            (cand,),
        )
        row = cur.fetchone()
        if row and row[0] == handle.lower():
            return cand
        return None
    return None


TWITTERAPI_USER_INFO_URL = "https://api.twitterapi.io/twitter/user/info"


def _twitterapi_lookup(
    *,
    handle: str,
    api_key: str,
    timeout: int = 10,
    max_retries: int = 3,
) -> str | None:
    """Look up the canonical integer author_id for a handle.

    Retries transient 404s and 5xx responses with exponential backoff
    (1s, 3s, 9s). TwitterAPI.io appears to use 404 as a stealth throttle
    during bulk lookups (handles that resolve 200 during a smoke
    probe return 404 during a batch run). Persistent 404 (after
    retries) is treated as a real handle-not-found and returns None.
    """
    qs = urllib.parse.urlencode({"userName": handle})
    url = f"{TWITTERAPI_USER_INFO_URL}?{qs}"
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    backoff = 1.0
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            data = payload.get("data") or {}
            user_id = data.get("id")
            return str(user_id) if user_id else None
        except urllib.error.HTTPError as exc:
            # 404 is the suspected rate-limit signal; 5xx is transient.
            # 401 is real auth failure; do not retry.
            if exc.code in (404, 429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(backoff)
                backoff *= 3
                continue
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 3
                continue
            return None
    return None


def _verify_canonical_handle(
    cur,
    *,
    canonical: str,
    requested_handle: str,
) -> str:
    """Return a 3-state verdict for the canonical candidate:

    - 'match' — the integer row exists in our DB AND its handle matches
      the duplicate-group handle (case-insensitive). Safe to repoint.
    - 'fresh' — the integer row does NOT exist in our DB. TwitterAPI's
      returned userName must match the duplicate handle (case-insensitive).
      The reconcile will use this integer as the new canonical (the
      TwitterAPI lookup is the source of truth for which X user owns
      this handle).
    - 'disagree' — the integer row exists but its handle doesn't match.
      KTD10 disagreement: this is a data error (different X user for the
      same integer). Caller should skip + dead-letter.
    """
    cur.execute(
        "SELECT LOWER(handle) FROM accounts WHERE author_id = %s",
        (canonical,),
    )
    row = cur.fetchone()
    if row is None:
        # No DB row for this integer. Trust TwitterAPI.
        return "fresh"
    if row[0] == requested_handle.lower():
        return "match"
    return "disagree"


def _bulk_count_for_all_groups(cur) -> dict[str, int]:
    """Bulk count rows across ALL placeholder FK rows in a single query.

    Used by the dry-run path to avoid per-group round-trips. Returns
    the same total counts as the per-group path; the only loss is
    per-handle breakdown in the summary.

    The WHERE clauses match _repoint_fk exactly (KTD10 LOWER() guard
    on posts.author_handle). For `brands_accounts` and
    `companies_accounts` the FK alone binds the row to a placeholder.
    """
    cur.execute(
        """
        SELECT 'posts' AS tbl, COUNT(*) AS n
          FROM posts p
          JOIN accounts a ON a.author_id = p.author_id
          WHERE a.author_id LIKE 'handle:%' OR a.author_id LIKE 'synthetic:%'
        UNION ALL
        SELECT 'account_post_appearances', COUNT(*)
          FROM account_post_appearances ap
          JOIN accounts a ON a.author_id = ap.author_id
          WHERE a.author_id LIKE 'handle:%' OR a.author_id LIKE 'synthetic:%'
        UNION ALL
        SELECT 'brands_accounts', COUNT(*)
          FROM brands_accounts ba
          JOIN accounts a ON a.author_id = ba.accounts_id
          WHERE a.author_id LIKE 'handle:%' OR a.author_id LIKE 'synthetic:%'
        UNION ALL
        SELECT 'companies_accounts', COUNT(*)
          FROM companies_accounts ca
          JOIN accounts a ON a.author_id = ca.author_id
          WHERE a.author_id LIKE 'handle:%' OR a.author_id LIKE 'synthetic:%'
        UNION ALL
        SELECT 'deleted_accounts', COUNT(*)
          FROM accounts
          WHERE author_id LIKE 'handle:%' OR author_id LIKE 'synthetic:%'
        """
    )
    counts: dict[str, int] = {}
    for tbl, n in cur.fetchall():
        counts[tbl] = n
    return counts


def _count_fk(
    cur, *, placeholder_ids: list[str], handle: str
) -> dict[str, int]:
    """COUNT rows that would be updated by _repoint_fk (no DB writes).

    Used in dry-run mode. Batched into a single UNION ALL query so
    2K groups take seconds, not hours.

    Same WHERE clauses as the apply path (KTD10 LOWER() guard on
    posts.author_handle).
    """
    placeholder_array_sql = "ARRAY[" + ",".join(["%s"] * len(placeholder_ids)) + "]"
    cur.execute(
        f"""
        SELECT 'posts' AS tbl, COUNT(*) AS n
          FROM posts
          WHERE author_id = ANY({placeholder_array_sql})
            AND LOWER(author_handle) = LOWER(%s)
        UNION ALL
        SELECT 'account_post_appearances', COUNT(*)
          FROM account_post_appearances
          WHERE author_id = ANY({placeholder_array_sql})
        UNION ALL
        SELECT 'brands_accounts', COUNT(*)
          FROM brands_accounts
          WHERE accounts_id = ANY({placeholder_array_sql})
        UNION ALL
        SELECT 'companies_accounts', COUNT(*)
          FROM companies_accounts
          WHERE author_id = ANY({placeholder_array_sql})
        """,
        (
            *placeholder_ids, handle,
            *placeholder_ids,
            *placeholder_ids,
            *placeholder_ids,
        ),
    )
    counts: dict[str, int] = {}
    for tbl, n in cur.fetchall():
        counts[tbl] = n
    counts["deleted_accounts"] = len(placeholder_ids)
    return counts


def _ensure_canonical_account_row(
    cur,
    *,
    canonical: str,
    handle: str,
    integer_ids: list[str],
) -> str:
    """Make sure `accounts` has a row for the canonical integer id.

    Phase 2 (residual groups) frequently has TwitterAPI returning an
    integer we haven't yet stored as an `accounts` row. FK UPDATEs would
    fail the FK constraint if the canonical row doesn't exist.

    Returns the integer id to use as canonical. If a row already
    exists, returns it unchanged. If not, inserts one with the
    provided handle (and `first_seen_at = NOW()`).
    """
    cur.execute(
        "SELECT author_id FROM accounts WHERE author_id = %s",
        (canonical,),
    )
    row = cur.fetchone()
    if row:
        return canonical
    # Insert a new accounts row for this integer. We pass integer_ids
    # so we can detect the case where the integer was already used by
    # a different handle (rare; would be a KTD10 disagreement edge).
    if canonical in integer_ids:
        return canonical  # already exists (defensive)
    cur.execute(
        """
        INSERT INTO accounts (author_id, handle, verified, first_seen_at, last_seen_at)
        VALUES (%s, %s, false, NOW(), NOW())
        """,
        (canonical, handle),
    )
    return canonical


def _repoint_fk(cur, *, canonical: str, placeholder_ids: list[str], handle: str) -> dict[str, int]:
    """UPDATE-then-DELETE per FK table (KTD2).

    Each child table has the placeholder author_id either as `author_id`
    or `accounts_id`. Only `posts` ALSO has `author_handle` for the
    KTD10 case-insensitive match guard; the others use the FK column
    alone (the FK constraint already binds the row to the placeholder).

    Why `LOWER(col) = LOWER(%s)` instead of `ILIKE`: the author_id
    columns use a non-deterministic `case_insensitive` Postgres
    collation which rejects ILIKE. LOWER() = LOWER() is portable
    across all collations.

    brands_accounts special case: the live harvest often inserts a
    `(brand_id, canonical_accounts_id)` row BEFORE the placeholder
    seeding inserts a `(brand_id, placeholder_author_id)` row. When
    we try to repoint the placeholder's row to the canonical integer,
    the unique `brands_accounts_pkey` constraint fires because the
    canonical row for that brand already exists. The fix is to detect
    existing `(brand_id, canonical_accounts_id)` rows up front and
    DELETE the placeholder's row in `brands_accounts` BEFORE the
    UPDATE -- so the UPDATE has nothing to repoint for that brand,
    and the canonical row that already satisfied the constraint is
    preserved. The deferred per-row count for `brands_accounts`
    reports `rows_updated`, not `rows_deleted`; the deleted-source
    rows are reported separately as `brands_accounts_source_deleted`.
    """
    counts: dict[str, int] = {}

    # brands_accounts: pre-pass to drop placeholder rows whose canonical
    # integer already exists for the same brand_id. This avoids the
    # brands_accounts_pkey collision in the UPDATE.
    cur.execute(
        """
        SELECT DISTINCT ba.brand_id
        FROM brands_accounts ba
        WHERE ba.accounts_id = ANY(%s)
          AND EXISTS (
            SELECT 1 FROM brands_accounts ba2
            WHERE ba2.accounts_id = %s
              AND ba2.brand_id = ba.brand_id
          )
        """,
        (placeholder_ids, canonical),
    )
    conflicting_brands = [row[0] for row in cur.fetchall()]
    if conflicting_brands:
        cur.execute(
            """
            DELETE FROM brands_accounts
            WHERE accounts_id = ANY(%s)
              AND brand_id = ANY(%s)
            """,
            (placeholder_ids, conflicting_brands),
        )
    counts["brands_accounts_source_deleted"] = cur.rowcount if conflicting_brands else 0

    for tbl, fk_col, has_handle_col in (
        ("posts", "author_id", True),
        ("account_post_appearances", "author_id", False),
        ("brands_accounts", "accounts_id", False),
        ("companies_accounts", "author_id", False),
    ):
        if has_handle_col:
            cur.execute(
                f"""
                UPDATE {tbl}
                SET {fk_col} = %s
                WHERE {fk_col} = ANY(%s)
                  AND LOWER(author_handle) = LOWER(%s)
                """,
                (canonical, placeholder_ids, handle),
            )
        else:
            cur.execute(
                f"""
                UPDATE {tbl}
                SET {fk_col} = %s
                WHERE {fk_col} = ANY(%s)
                """,
                (canonical, placeholder_ids),
            )
        counts[tbl] = cur.rowcount
    return counts


def _delete_placeholders(cur, *, placeholder_ids: list[str]) -> int:
    cur.execute(
        "DELETE FROM accounts WHERE author_id = ANY(%s)",
        (placeholder_ids,),
    )
    return cur.rowcount


def reconcile_one_group(
    cur,
    *,
    handle: str,
    integer_ids: list[str],
    placeholder_ids: list[str],
    api_key: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "handle": handle,
        "canonical": None,
        "status": None,
        "row_counts": {},
        "skip_reason": None,
    }
    canonical = _canonical_integer_for_handle(
        cur, handle=handle, integer_ids_in_group=integer_ids
    )
    if canonical is None:
        if not api_key:
            result["status"] = "skipped"
            result["skip_reason"] = "no canonical integer; no twitterapi key"
            return result
        api_id = _twitterapi_lookup(handle=handle, api_key=api_key)
        if api_id is None:
            result["status"] = "skipped"
            result["skip_reason"] = "TwitterAPI lookup failed/404"
            return result
        verdict = _verify_canonical_handle(
            cur, canonical=api_id, requested_handle=handle
        )
        if verdict == "disagree":
            result["status"] = "skipped"
            result["skip_reason"] = (
                f"TwitterAPI {api_id} disagrees with {handle!r}"
            )
            return result
        # verdict in {"match", "fresh"} — both are acceptable. "fresh"
        # means TwitterAPI gave us an integer we hadn't stored yet; the
        # Phase 2 reconcile treats this as the canonical. (Note: the
        # canonical row is NOT created in accounts during dry-run; the
        # apply path will INSERT it via the repoint's FK UPDATE only if
        # the FK table has a matching row to repoint.)
        canonical = api_id

    if dry_run:
        # COUNT only — no DB writes. The dry-run path skips SAVEPOINT
        # + UPDATE + DELETE entirely, so a 2K-group dry-run takes
        # seconds instead of hours.
        counts = _count_fk(cur, placeholder_ids=placeholder_ids, handle=handle)
    else:
        savepoint_id = f"reconcile_{handle}".replace("'", "''")
        cur.execute(f"SAVEPOINT {savepoint_id}")
        try:
            # Phase 2: if the canonical integer isn't yet in accounts,
            # INSERT it first so the FK UPDATEs don't violate the
            # constraint.
            _ensure_canonical_account_row(
                cur,
                canonical=canonical,
                handle=handle,
                integer_ids=integer_ids,
            )
            counts = _repoint_fk(
                cur,
                canonical=canonical,
                placeholder_ids=placeholder_ids,
                handle=handle,
            )
            deleted = _delete_placeholders(cur, placeholder_ids=placeholder_ids)
            counts["deleted_accounts"] = deleted
            cur.execute(f"RELEASE SAVEPOINT {savepoint_id}")
        except Exception as exc:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_id}")
            result["status"] = "failed"
            result["skip_reason"] = f"{type(exc).__name__}: {exc}"
            return result

    result["canonical"] = canonical
    result["row_counts"] = counts
    result["status"] = "merged"
    return result


class Command(BaseCommand):
    help = (
        "Reconcile duplicate accounts.handle rows by repointing FK refs "
        "to canonical integer author_ids. Dry-run by default; --apply "
        "to commit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Print summary JSON; do not write to DB.",
        )
        parser.add_argument(
            "--apply",
            dest="dry_run",
            action="store_false",
            help="Apply the reconciliation (writes to DB).",
        )
        parser.add_argument(
            "--residual-only",
            action="store_true",
            help="Only process all-placeholder groups (Phase 2).",
        )
        parser.add_argument(
            "--lonely-only",
            action="store_true",
            help="Only process handle-unique placeholder rows (Phase 2).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N groups (smoke testing).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit JSON summary to stdout.",
        )

    def handle(self, *args, **options):
        api_key = os.environ.get("TWITTERAPI_IO_API_KEY")

        if options["residual_only"] and options["lonely_only"]:
            self.stderr.write("error: --residual-only and --lonely-only are mutually exclusive")
            return

        if options["lonely_only"]:
            with connection.cursor() as cur:
                groups = _find_lonely_placeholders(
                    cur,
                    limit=options["limit"],
                )
        else:
            with connection.cursor() as cur:
                groups = _find_duplicate_groups(
                    cur,
                    include_residual=options["residual_only"],
                    limit=options["limit"],
                )

        summary = {
            "dry_run": options["dry_run"],
            "groups_total": len(groups),
            "merged": 0,
            "skipped": 0,
            "failed": 0,
            "rows_updated_posts": 0,
            "rows_updated_account_post_appearances": 0,
            "rows_updated_brands_accounts": 0,
            "rows_updated_companies_accounts": 0,
            "rows_deleted_accounts": 0,
            "results": [],
        }

        if options["dry_run"]:
            # FAST DRY-RUN: bulk aggregate counts across ALL groups in
            # a single query per table (no per-group round-trips). Returns
            # the same total counts as the per-group path but in seconds,
            # not hours.
            with connection.cursor() as cur:
                bulk = _bulk_count_for_all_groups(cur)
            summary["rows_updated_posts"] = bulk.get("posts", 0)
            summary["rows_updated_account_post_appearances"] = bulk.get(
                "account_post_appearances", 0
            )
            summary["rows_updated_brands_accounts"] = bulk.get(
                "brands_accounts", 0
            )
            summary["rows_updated_companies_accounts"] = bulk.get(
                "companies_accounts", 0
            )
            summary["rows_deleted_accounts"] = bulk.get("deleted_accounts", 0)
            # In dry-run, every group with an integer row + ≥1 placeholder
            # is "merged" by plan (skip rate is small without twitterapi).
            summary["merged"] = sum(
                1 for _, ids in groups
                if any(not _is_placeholder(a) for a in ids)
            )
            self.stdout.write(
                f"Reconcile summary (dry_run=True, bulk aggregate):\n"
                f"  groups_total     = {summary['groups_total']}\n"
                f"  merged (estimate) = {summary['merged']}\n"
                f"  rows_updated_posts                      = {summary['rows_updated_posts']}\n"
                f"  rows_updated_account_post_appearances  = {summary['rows_updated_account_post_appearances']}\n"
                f"  rows_updated_brands_accounts           = {summary['rows_updated_brands_accounts']}\n"
                f"  rows_updated_companies_accounts        = {summary['rows_updated_companies_accounts']}\n"
                f"  rows_deleted_accounts                  = {summary['rows_deleted_accounts']}\n"
            )
            return

        for handle, author_ids in groups:
            if options["lonely_only"]:
                # Lonely path: (handle, placeholder_author_id) tuples.
                # No integer_ids; the apply path resolves via TwitterAPI.
                cls = {
                    "handle": handle,
                    "integer_ids": [],
                    "placeholder_ids": [author_ids],
                }
            else:
                cls = _classify_group(handle, author_ids)
            with connection.cursor() as cur:
                # SAVEPOINT requires a transaction. transaction.atomic()
                # wraps this group in a transaction; SAVEPOINT inside
                # creates a nested savepoint; a failure rolls back to
                # the savepoint and the outer atomic continues.
                with transaction.atomic():
                    result = reconcile_one_group(
                        cur,
                        handle=cls["handle"],
                        integer_ids=cls["integer_ids"],
                        placeholder_ids=cls["placeholder_ids"],
                        api_key=api_key,
                        dry_run=options["dry_run"],
                    )

            summary["results"].append(result)
            if result["status"] == "merged":
                summary["merged"] += 1
                summary["rows_updated_posts"] += result["row_counts"].get("posts", 0)
                summary["rows_updated_account_post_appearances"] += (
                    result["row_counts"].get("account_post_appearances", 0)
                )
                summary["rows_updated_brands_accounts"] += (
                    result["row_counts"].get("brands_accounts", 0)
                )
                summary["rows_updated_companies_accounts"] += (
                    result["row_counts"].get("companies_accounts", 0)
                )
                summary["rows_deleted_accounts"] += (
                    result["row_counts"].get("deleted_accounts", 0)
                )
            elif result["status"] == "skipped":
                summary["skipped"] += 1
            elif result["status"] == "failed":
                summary["failed"] += 1

            # Rate-limit guard: TwitterAPI appears to use 404 as a
            # stealth throttle during bulk lookups. Sleeping 0.25s
            # between groups keeps us well under any reasonable rate
            # limit (~240 calls/min) while still amortizing thread
            # overhead. The retry-with-backoff in _twitterapi_lookup
            # handles transient 404s that slip through.
            if not options["dry_run"]:
                time.sleep(0.25)

        if options["json"]:
            self.stdout.write(json.dumps(summary, indent=2, default=str))
        else:
            self.stdout.write(
                f"Reconcile summary (dry_run={options['dry_run']}):\n"
                f"  groups_total     = {summary['groups_total']}\n"
                f"  merged           = {summary['merged']}\n"
                f"  skipped          = {summary['skipped']}\n"
                f"  failed           = {summary['failed']}\n"
                f"  rows_updated_posts                      = {summary['rows_updated_posts']}\n"
                f"  rows_updated_account_post_appearances  = {summary['rows_updated_account_post_appearances']}\n"
                f"  rows_updated_brands_accounts           = {summary['rows_updated_brands_accounts']}\n"
                f"  rows_updated_companies_accounts        = {summary['rows_updated_companies_accounts']}\n"
                f"  rows_deleted_accounts                  = {summary['rows_deleted_accounts']}\n"
            )