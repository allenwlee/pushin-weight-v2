#!/usr/bin/env python3
"""U9 BEFORE-state pin - runs against the live shadow DB directly.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U9.

This is a plain Python script (not pytest) because:
  1. The tests verify state against the LIVE shadow DB.
  2. pytest-django's test runner creates a fresh test DB with schema
     stripped of the ICU `case_insensitive` collation, which makes
     the production tables unreadable.

Usage:
  DATABASE_URL=postgres://...pushinweight_shadow... python3 /tmp/u9_live_pin.py

Exit code: 0 if all pins pass, 1 otherwise.
"""
import os
import sys
import psycopg


EXPECTED_DUPES_AT_PLAN_TIME = 2142
EXPECTED_POSTS_AT_PLACEHOLDERS = 20079
EXPECTED_APPEARANCES_AT_PLACEHOLDERS = 6803
EXPECTED_BRANDS_AT_PLACEHOLDERS = 95
EXPECTED_COMPANIES_AT_PLACEHOLDERS = 0
EXPECTED_ACCOUNTS_TOTAL = 19284
EXPECTED_INTEGER_AUTHOR_IDS = 5776
EXPECTED_HANDLE_PREFIX_AUTHOR_IDS = 11964
EXPECTED_SYNTHETIC_PREFIX_AUTHOR_IDS = 1522


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if "pushinweight_shadow" not in db_url:
        print(f"ERROR: DATABASE_URL must point at the live pushinweight_shadow DB.", file=sys.stderr)
        print(f"       Got: {db_url[:80]}...", file=sys.stderr)
        return 1

    failures: list[str] = []
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Duplicate handle groups
            cur.execute("""
                SELECT COUNT(*) FROM (
                  SELECT handle FROM accounts
                  WHERE handle IS NOT NULL AND handle != ''
                  GROUP BY handle HAVING COUNT(*) > 1
                ) t
            """)
            dup = cur.fetchone()[0]
            if dup != EXPECTED_DUPES_AT_PLAN_TIME:
                failures.append(f"dup_groups: expected {EXPECTED_DUPES_AT_PLAN_TIME}, got {dup}")

            # Total accounts
            cur.execute("SELECT COUNT(*) FROM accounts")
            total = cur.fetchone()[0]
            if total != EXPECTED_ACCOUNTS_TOTAL:
                failures.append(f"total_accounts: expected {EXPECTED_ACCOUNTS_TOTAL}, got {total}")

            # Integer author_ids
            cur.execute("SELECT COUNT(*) FROM accounts WHERE author_id ~ '^[0-9]+$'")
            ints = cur.fetchone()[0]
            if ints != EXPECTED_INTEGER_AUTHOR_IDS:
                failures.append(f"integer_author_ids: expected {EXPECTED_INTEGER_AUTHOR_IDS}, got {ints}")

            # handle: prefix
            cur.execute("SELECT COUNT(*) FROM accounts WHERE author_id LIKE 'handle:%'")
            h = cur.fetchone()[0]
            if h != EXPECTED_HANDLE_PREFIX_AUTHOR_IDS:
                failures.append(f"handle_prefix_author_ids: expected {EXPECTED_HANDLE_PREFIX_AUTHOR_IDS}, got {h}")

            # synthetic: prefix
            cur.execute("SELECT COUNT(*) FROM accounts WHERE author_id LIKE 'synthetic:%'")
            s = cur.fetchone()[0]
            if s != EXPECTED_SYNTHETIC_PREFIX_AUTHOR_IDS:
                failures.append(f"synthetic_prefix_author_ids: expected {EXPECTED_SYNTHETIC_PREFIX_AUTHOR_IDS}, got {s}")

            # Posts at placeholder
            cur.execute("""
                SELECT COUNT(*) FROM posts p
                JOIN accounts a ON a.author_id = p.author_id
                WHERE a.author_id !~ '^[0-9]+$'
            """)
            p = cur.fetchone()[0]
            if p != EXPECTED_POSTS_AT_PLACEHOLDERS:
                failures.append(f"posts_at_placeholder: expected {EXPECTED_POSTS_AT_PLACEHOLDERS}, got {p}")

            # APAs at placeholder
            cur.execute("""
                SELECT COUNT(*) FROM account_post_appearances ap
                JOIN accounts a ON a.author_id = ap.author_id
                WHERE a.author_id !~ '^[0-9]+$'
            """)
            ap = cur.fetchone()[0]
            if ap != EXPECTED_APPEARANCES_AT_PLACEHOLDERS:
                failures.append(f"appearances_at_placeholder: expected {EXPECTED_APPEARANCES_AT_PLACEHOLDERS}, got {ap}")

            # brands_accounts at placeholder
            cur.execute("""
                SELECT COUNT(*) FROM brands_accounts ba
                JOIN accounts a ON a.author_id = ba.accounts_id
                WHERE a.author_id !~ '^[0-9]+$'
            """)
            ba = cur.fetchone()[0]
            if ba != EXPECTED_BRANDS_AT_PLACEHOLDERS:
                failures.append(f"brands_at_placeholder: expected {EXPECTED_BRANDS_AT_PLACEHOLDERS}, got {ba}")

            # companies_accounts at placeholder
            cur.execute("""
                SELECT COUNT(*) FROM companies_accounts ca
                JOIN accounts a ON a.author_id = ca.author_id
                WHERE a.author_id !~ '^[0-9]+$'
            """)
            ca = cur.fetchone()[0]
            if ca != EXPECTED_COMPANIES_AT_PLACEHOLDERS:
                failures.append(f"companies_at_placeholder: expected {EXPECTED_COMPANIES_AT_PLACEHOLDERS}, got {ca}")

            # Unique index must NOT exist yet
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = 'accounts'
                      AND indexname = 'uniq_accounts_handle_lower'
                )
            """)
            idx_exists = cur.fetchone()[0]
            if idx_exists:
                failures.append("uniq_accounts_handle_lower should NOT exist before U11")

    print("U9 BEFORE-state pins (live shadow DB audit):")
    print(f"  dup_groups                = {dup} (expected {EXPECTED_DUPES_AT_PLAN_TIME})")
    print(f"  total_accounts            = {total} (expected {EXPECTED_ACCOUNTS_TOTAL})")
    print(f"  integer_author_ids        = {ints} (expected {EXPECTED_INTEGER_AUTHOR_IDS})")
    print(f"  handle_prefix_author_ids  = {h} (expected {EXPECTED_HANDLE_PREFIX_AUTHOR_IDS})")
    print(f"  synthetic_prefix_author_ids = {s} (expected {EXPECTED_SYNTHETIC_PREFIX_AUTHOR_IDS})")
    print(f"  posts_at_placeholder      = {p} (expected {EXPECTED_POSTS_AT_PLACEHOLDERS})")
    print(f"  apa_at_placeholder        = {ap} (expected {EXPECTED_APPEARANCES_AT_PLACEHOLDERS})")
    print(f"  brands_at_placeholder     = {ba} (expected {EXPECTED_BRANDS_AT_PLACEHOLDERS})")
    print(f"  companies_at_placeholder  = {ca} (expected {EXPECTED_COMPANIES_AT_PLACEHOLDERS})")
    print(f"  uniq_handle_index_exists  = {idx_exists} (expected False)")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll BEFORE pins pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())