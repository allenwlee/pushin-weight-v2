#!/usr/bin/env python3
"""U13 live-DB pin script — verify AFTER state of accounts.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U13 (formerly U4 of the original `2026-07-30-001` recon plan).

This script is the AFTER counterpart to scripts/u9_live_pin.py.
Run AFTER U10 apply (1,811 merge groups repointed, ~13.5K placeholders
deleted). It pins:

  - dup_groups dropped from 2142 to ≤ 462 (the no-integer residual)
  - placeholder counts dropped accordingly
  - the LOWER(handle) unique index EXISTS (created by U11 migration)
  - DRIFT DETECTOR: any account row with a placeholder author_id whose
    first_seen_at > 2026-07-30 indicates new drift after the fix.

Exit code: 0 if all AFTER pins pass + 0 drift, 1 otherwise.

Usage:
  DATABASE_URL=postgres://...pushinweight_shadow... python3 scripts/u13_live_pin.py
"""
import os
import sys
import psycopg


# These are the EXPECTED AFTER-state values. Pin them based on the
# post-U10 apply outcome (recompute after apply):
EXPECTED_DUPES_AT_PLAN_TIME_AFTER = 462          # all-placeholder residual
EXPECTED_POSTS_AT_PLACEHOLDERS_AFTER = 1965     # no-integer residual
EXPECTED_APPEARANCES_AT_PLACEHOLDERS_AFTER = 0  # 0 expected if U10 cleanly handled all APAs
EXPECTED_BRANDS_AT_PLACEHOLDERS_AFTER = 0
EXPECTED_COMPANIES_AT_PLACEHOLDERS_AFTER = 0


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if "pushinweight_shadow" not in db_url:
        print(f"ERROR: DATABASE_URL must point at the live pushinweight_shadow DB.", file=sys.stderr)
        return 1

    failures: list[str] = []
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # --- AFTER-state counts ------------------------------------
            cur.execute("""
                SELECT COUNT(*) FROM (
                  SELECT handle FROM accounts
                  WHERE handle IS NOT NULL AND handle != ''
                  GROUP BY handle HAVING COUNT(*) > 1
                ) t
            """)
            dup = cur.fetchone()[0]
            if dup > EXPECTED_DUPES_AT_PLAN_TIME_AFTER:
                failures.append(
                    f"dup_groups: {dup} > expected ≤ {EXPECTED_DUPES_AT_PLAN_TIME_AFTER}"
                )

            cur.execute("""
                SELECT COUNT(*) FROM posts p
                JOIN accounts a ON a.author_id = p.author_id
                WHERE a.author_id !~ '^[0-9]+$'
            """)
            p = cur.fetchone()[0]
            if p > EXPECTED_POSTS_AT_PLACEHOLDERS_AFTER:
                failures.append(
                    f"posts_at_placeholder: {p} > expected ≤ {EXPECTED_POSTS_AT_PLACEHOLDERS_AFTER}"
                )

            cur.execute("""
                SELECT COUNT(*) FROM account_post_appearances ap
                JOIN accounts a ON a.author_id = ap.author_id
                WHERE a.author_id !~ '^[0-9]+$'
            """)
            ap = cur.fetchone()[0]
            if ap > EXPECTED_APPEARANCES_AT_PLACEHOLDERS_AFTER:
                failures.append(
                    f"apa_at_placeholder: {ap} > expected ≤ {EXPECTED_APPEARANCES_AT_PLACEHOLDERS_AFTER}"
                )

            cur.execute("""
                SELECT COUNT(*) FROM brands_accounts ba
                JOIN accounts a ON a.author_id = ba.accounts_id
                WHERE a.author_id !~ '^[0-9]+$'
            """)
            ba = cur.fetchone()[0]
            if ba > EXPECTED_BRANDS_AT_PLACEHOLDERS_AFTER:
                failures.append(
                    f"brands_at_placeholder: {ba} > expected ≤ {EXPECTED_BRANDS_AT_PLACEHOLDERS_AFTER}"
                )

            cur.execute("""
                SELECT COUNT(*) FROM companies_accounts ca
                JOIN accounts a ON a.author_id = ca.author_id
                WHERE a.author_id !~ '^[0-9]+$'
            """)
            ca = cur.fetchone()[0]
            if ca > EXPECTED_COMPANIES_AT_PLACEHOLDERS_AFTER:
                failures.append(
                    f"companies_at_placeholder: {ca} > expected ≤ {EXPECTED_COMPANIES_AT_PLACEHOLDERS_AFTER}"
                )

            # --- U11 unique index must exist --------------------------
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = 'accounts'
                      AND indexname = 'uniq_accounts_handle_lower'
                )
            """)
            idx_exists = cur.fetchone()[0]
            if not idx_exists:
                failures.append("uniq_accounts_handle_lower index MISSING — U11 not yet applied")

            # --- DRIFT DETECTOR --------------------------------------
            # Any placeholder account row added after 2026-07-30
            # (the date the hybrid funnel plan began) indicates that
            # a code path is still writing placeholder author_ids.
            # The fix should prevent this entirely; a non-zero count
            # is a regression.
            cur.execute("""
                SELECT COUNT(*) FROM accounts
                WHERE (author_id LIKE 'handle:%' OR author_id LIKE 'synthetic:%')
                  AND first_seen_at > '2026-07-30'::date
            """)
            new_placeholders = cur.fetchone()[0]
            if new_placeholders > 0:
                failures.append(
                    f"DRIFT DETECTOR: {new_placeholders} new placeholder rows "
                    f"created since 2026-07-30. Code path is still writing "
                    f"handle:*/synthetic:* — investigate before U15."
                )

    print("U13 AFTER-state pins (live shadow DB audit):")
    print(f"  dup_groups                  = {dup} (expected ≤ {EXPECTED_DUPES_AT_PLAN_TIME_AFTER})")
    print(f"  posts_at_placeholder        = {p} (expected ≤ {EXPECTED_POSTS_AT_PLACEHOLDERS_AFTER})")
    print(f"  apa_at_placeholder          = {ap} (expected ≤ {EXPECTED_APPEARANCES_AT_PLACEHOLDERS_AFTER})")
    print(f"  brands_at_placeholder       = {ba} (expected ≤ {EXPECTED_BRANDS_AT_PLACEHOLDERS_AFTER})")
    print(f"  companies_at_placeholder    = {ca} (expected ≤ {EXPECTED_COMPANIES_AT_PLACEHOLDERS_AFTER})")
    print(f"  uniq_handle_index_exists    = {idx_exists} (expected True)")
    print(f"  drift_new_placeholders      = {new_placeholders} (expected 0)")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll AFTER pins pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())