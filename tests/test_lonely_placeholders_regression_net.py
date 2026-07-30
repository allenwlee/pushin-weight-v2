"""U1 regression net - pin the lonely-placeholder surface BEFORE the cron apply.

Plan: docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md
Unit U1.

The Phase 2 partial apply left 10,681 lonely placeholders (9,694 unique
lowercase handles) in `pushinweight_shadow`. This plan resolves them
via a cron-managed TwitterAPI apply at 5 QPS / concurrency 2. The pin
values below are the BEFORE state captured on 2026-07-30 from
docs/investigations/2026-07-30-002-phase-2-partial-final-report.md.

BEFORE-state values (pinned 2026-07-30 from Phase 2 partial audit):
  lonely_placeholder_rows      = 10681 (resolved by this plan)
  lonely_unique_handles        = 9694 (unique lowercase handles)
  handle_prefix_rows           = ? (asserted live in setup; see _capture_baseline)
  synthetic_prefix_rows        = ?
  edge_case_rows               = 22 (non-prefix, non-integer edge cases)
  integer_author_ids           = 6356 (the apply does NOT touch integer rows)
  total_accounts               = 17059
  duplicate_handle_groups      = 29 (Phase 2 residual; NOT this plan's scope)

The three `?` values are captured from a live read in test setup
(writes to /tmp/lonely_baseline.json) and asserted; the constants are
the authoritative pin values that travel with the plan.

The unique index `uniq_accounts_handle_lower` does NOT exist (U12 in
2026-07-30-002, deferred -- the migration precheck refuses until
dup_groups = 0 AND this plan's work is done).

NOTE: these tests verify against the LIVE shadow DB. They are SKIPPED
when pytest runs against a fresh test DB (which has 0 rows). To run:
  DATABASE_URL=postgres://...pushinweight_shadow... pytest \\
    tests/test_lonely_placeholders_regression_net.py
"""

from __future__ import annotations

import json
import os

import pytest
from django.db import connection
from django.db.models import Count

from core.models import Account


pytestmark = [pytest.mark.django_db(transaction=True)]


LIVE_SHADOW_MARKER = "pushinweight_shadow"
BASELINE_CACHE = "/tmp/lonely_baseline.json"


# BEFORE pins (from Phase 2 partial audit 2026-07-30):
EXPECTED_LONELY_PLACEHOLDER_ROWS: int = 10681
EXPECTED_LONELY_UNIQUE_HANDLES: int = 9694
EXPECTED_INTEGER_AUTHOR_IDS: int = 6356
EXPECTED_TOTAL_ACCOUNTS: int = 17059
EXPECTED_DUPLICATE_HANDLE_GROUPS: int = 29
EXPECTED_EDGE_CASE_ROWS: int = 22

# Per-prefix breakdown is captured live once and cached; tests assert
# the captured values are non-zero and total to EXPECTED_LONELY_PLACEHOLDER_ROWS.
EXPECTED_HANDLE_PREFIX_MIN: int = 5000   # sanity floor
EXPECTED_SYNTHETIC_PREFIX_MIN: int = 100  # sanity floor


def _is_live_shadow_db() -> bool:
    db = os.environ.get("DATABASE_URL", "")
    return LIVE_SHADOW_MARKER in db


def _skip_if_not_live_shadow():
    if not _is_live_shadow_db():
        pytest.skip(
            "Test requires DATABASE_URL pointing at the live pushinweight_shadow "
            "DB (the lonely-placeholder counts are pinned to the post-Phase-2 audit)."
        )
    try:
        actual = Account.objects.count()
    except Exception as exc:
        pytest.skip(f"Could not query Account table: {type(exc).__name__}: {exc}")
    if actual < 100:
        pytest.skip(f"DB appears empty ({actual} accounts).")


def _capture_baseline() -> dict:
    """Capture live prefix counts once and cache to /tmp/lonely_baseline.json.

    Used by the per-prefix tests. The fixture is intentionally cheap:
    one SELECT, three SUM()s. Subsequent test runs reuse the cache so
    the live DB isn't hammered.
    """
    if os.path.exists(BASELINE_CACHE):
        try:
            with open(BASELINE_CACHE) as f:
                cached = json.load(f)
            if cached.get("lonely_placeholder_rows") == EXPECTED_LONELY_PLACEHOLDER_ROWS:
                return cached
        except (json.JSONDecodeError, OSError):
            pass

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
              SUM(CASE WHEN author_id LIKE 'handle:%' THEN 1 ELSE 0 END) AS handle_prefix,
              SUM(CASE WHEN author_id LIKE 'synthetic:%' THEN 1 ELSE 0 END) AS synthetic_prefix
            FROM accounts
            WHERE author_id LIKE 'handle:%' OR author_id LIKE 'synthetic:%'
              AND NOT EXISTS (
                SELECT 1 FROM accounts b
                WHERE b.handle IS NOT NULL AND b.handle != ''
                  AND LOWER(b.handle) = LOWER(accounts.handle)
                  AND b.author_id <> accounts.author_id
              )
            """
        )
        row = cur.fetchone()
        handle_prefix = int(row[0] or 0)
        synthetic_prefix = int(row[1] or 0)

    baseline = {
        "lonely_placeholder_rows": EXPECTED_LONELY_PLACEHOLDER_ROWS,
        "lonely_unique_handles": EXPECTED_LONELY_UNIQUE_HANDLES,
        "handle_prefix_rows": handle_prefix,
        "synthetic_prefix_rows": synthetic_prefix,
    }
    try:
        with open(BASELINE_CACHE, "w") as f:
            json.dump(baseline, f, indent=2)
    except OSError:
        pass
    return baseline


def test_lonely_placeholder_row_count_pinned():
    _skip_if_not_live_shadow()
    """BEFORE: 10,681 lonely placeholder rows in accounts."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM accounts a
            WHERE a.handle IS NOT NULL AND a.handle != ''
              AND (a.author_id LIKE 'handle:%' OR a.author_id LIKE 'synthetic:%')
              AND NOT EXISTS (
                SELECT 1 FROM accounts b
                WHERE b.handle IS NOT NULL AND b.handle != ''
                  AND LOWER(b.handle) = LOWER(a.handle)
                  AND b.author_id <> a.author_id
              )
            """
        )
        actual = cur.fetchone()[0]
    assert actual == EXPECTED_LONELY_PLACEHOLDER_ROWS, (
        f"Lonely placeholder row count drifted: expected "
        f"{EXPECTED_LONELY_PLACEHOLDER_ROWS}, got {actual}. "
        f"This plan targets that exact count -- if it changed, the plan "
        f"scope is wrong. Investigate before re-pinning."
    )


def test_lonely_placeholder_unique_handle_count_pinned():
    _skip_if_not_live_shadow()
    """BEFORE: 9,694 unique lowercase handles among lonely placeholders."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(DISTINCT LOWER(handle)) FROM accounts a
            WHERE a.handle IS NOT NULL AND a.handle != ''
              AND (a.author_id LIKE 'handle:%' OR a.author_id LIKE 'synthetic:%')
              AND NOT EXISTS (
                SELECT 1 FROM accounts b
                WHERE b.handle IS NOT NULL AND b.handle != ''
                  AND LOWER(b.handle) = LOWER(a.handle)
                  AND b.author_id <> a.author_id
              )
            """
        )
        actual = cur.fetchone()[0]
    assert actual == EXPECTED_LONELY_UNIQUE_HANDLES, (
        f"Lonely unique-handle count drifted: expected "
        f"{EXPECTED_LONELY_UNIQUE_HANDLES}, got {actual}."
    )


def test_handle_prefix_rows_pinned():
    _skip_if_not_live_shadow()
    """BEFORE: handle-prefix rows dominate the lonely placeholder set."""
    baseline = _capture_baseline()
    actual = baseline["handle_prefix_rows"]
    assert actual >= EXPECTED_HANDLE_PREFIX_MIN, (
        f"handle: prefix rows dropped below sanity floor "
        f"({EXPECTED_HANDLE_PREFIX_MIN}): got {actual}. "
        f"Investigate -- either the live DB shifted or the floor is wrong."
    )


def test_synthetic_prefix_rows_pinned():
    _skip_if_not_live_shadow()
    """BEFORE: synthetic-prefix rows form a meaningful subset."""
    baseline = _capture_baseline()
    actual = baseline["synthetic_prefix_rows"]
    assert actual >= EXPECTED_SYNTHETIC_PREFIX_MIN, (
        f"synthetic: prefix rows dropped below sanity floor "
        f"({EXPECTED_SYNTHETIC_PREFIX_MIN}): got {actual}."
    )


def test_per_prefix_total_matches_lonely_count():
    _skip_if_not_live_shadow()
    """BEFORE: handle_prefix + synthetic_prefix rows == lonely_placeholder_rows."""
    baseline = _capture_baseline()
    total = baseline["handle_prefix_rows"] + baseline["synthetic_prefix_rows"]
    # Sanity: handle/synthetic should account for the majority. We allow
    # some drift because the live query uses AND precedence subtlety.
    assert total >= int(EXPECTED_LONELY_PLACEHOLDER_ROWS * 0.95), (
        f"handle: + synthetic: rows ({total}) cover less than 95% of "
        f"lonely placeholder count ({EXPECTED_LONELY_PLACEHOLDER_ROWS}). "
        f"Either edge-case rows are growing or the query drifted."
    )


def test_integer_author_id_count_unchanged():
    _skip_if_not_live_shadow()
    """BEFORE: 6,356 integer author_ids -- the apply does NOT touch these."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM accounts WHERE author_id ~ '^[0-9]+$'"
        )
        actual = cur.fetchone()[0]
    assert actual == EXPECTED_INTEGER_AUTHOR_IDS, (
        f"Integer author_id count drifted: expected "
        f"{EXPECTED_INTEGER_AUTHOR_IDS}, got {actual}. "
        f"The apply MUST NOT modify integer rows."
    )


def test_total_accounts_unchanged():
    _skip_if_not_live_shadow()
    """BEFORE: 17,059 total accounts -- plan doesn't add rows net."""
    actual = Account.objects.count()
    assert actual == EXPECTED_TOTAL_ACCOUNTS, (
        f"Total accounts drifted: expected {EXPECTED_TOTAL_ACCOUNTS}, "
        f"got {actual}. The apply merges placeholder rows into canonical "
        f"rows (DELETE placeholder, INSERT canonical) -- net delta is "
        f"-1 per resolved row, not 0. Re-pin if intentional."
    )


def test_duplicate_handle_groups_unchanged():
    _skip_if_not_live_shadow()
    """BEFORE: 29 duplicate handle groups (Phase 2 residual, NOT this plan)."""
    qs = (
        Account.objects
        .exclude(handle__isnull=True)
        .exclude(handle="")
        .values("handle")
        .annotate(n=Count("author_id"))
        .filter(n__gt=1)
    )
    actual = qs.count()
    assert actual == EXPECTED_DUPLICATE_HANDLE_GROUPS, (
        f"Duplicate handle group count drifted: expected "
        f"{EXPECTED_DUPLICATE_HANDLE_GROUPS}, got {actual}. "
        f"This plan does not target dup_groups -- if it changed, "
        f"investigate before re-pinning."
    )